"""Circularity robustness check (deterministic, no API).

Construct-validity check. The RBAC allow-list in ``rbac.yaml`` grants each persona *exactly*
its ``LEGITIMATE_PAIRINGS`` domains, and ``is_legitimate`` is *also* defined from
``LEGITIMATE_PAIRINGS`` (``domain in LEGITIMATE_PAIRINGS[persona] AND match_tag==correct``). So
RBAC's cross-domain denials coincide with the label's domain criterion *by construction*, which may
inflate RBAC's drop-one layer marginal.

This script re-authors RBAC *independently of the legitimacy label* and recomputes the drop-one
marginals, holding the labels and the ABAC/TRAC layers fixed. Only ``rbac_deny`` changes.

Variants (all replayed through the live deterministic stack, gpt-4o validation log; the floor is
model-invariant so one validation log is representative):
  * ``baseline``    — ``rbac.yaml`` (tool-granular; domains == label map). What the paper reports.
  * ``domain_label``— domain-level RBAC, tools=* on exactly the label domains. Isolates the pure
                      domain coincidence (strips rbac.yaml's independent tool-granularity).
  * ``role_indep``  — coarse job-function roles that OVER-PROVISION relative to the fine-grained
                      label (as real deployments do), breaking the RBAC<->label domain coincidence.

If RBAC's marginal survives under ``role_indep`` it is not a label artifact; if it collapses, we
report that honestly (the slack moves to TRAC/ABAC, or to SecFail).
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services import tool_relevance as trel
from app.services.experiment_config import (
    PERSONAS, LEGITIMATE_PAIRINGS, abac_production, tsphol_production, rbac_production,
)

LL = os.path.join("datasets", "llm_inference_logs")
VAL_LOG = "20260613005419_gpt-4o_validation.json"   # floor is model-invariant; representative

ALL_DOMAINS = sorted({d for doms in LEGITIMATE_PAIRINGS.values() for d in doms})

# Coarse job-function roles, authored from role semantics (NOT the legitimacy label). The two
# tight operational personas (incident, finance, research) are over-provisioned with adjacent
# read domains, exactly the "role creep" real RBAC exhibits. Service/audit accounts are broad in
# both the label and reality, so they are unchanged.
ROLE_INDEP = {
    "devops_agent":       {"grafana", "atlassian", "azure", "mongodb", "notion"},
    "incident_agent":     {"grafana", "atlassian", "azure", "mongodb"},
    "finance_agent":      {"stripe", "hummingbot-mcp", "azure", "mongodb", "notion"},
    "research_agent":     {"wikipedia-mcp", "paper-search", "notion", "stripe"},
    "automation_gateway": set(ALL_DOMAINS),
    "security_engine":    set(ALL_DOMAINS),
}


def rbac_from_domainmap(domain_map):
    """Build a domain-level RBAC policy dict (tools=* on each granted domain + default deny)."""
    policies = []
    for pkey, pdata in PERSONAS.items():
        grants = sorted(domain_map.get(pkey, set()))
        rules = [{"rule_name": f"allow_{d}", "mcp": d, "action": "allow", "tools": ["*"]}
                 for d in grants]
        rules.append({"rule_name": "default_deny", "mcp": "*", "action": "deny", "tools": ["*"]})
        policies.append({"spiffe_id": pdata["spiffe_id"], "description": f"{pkey} ({len(grants)} domains)",
                         "rules": rules})
    return {"policies": policies}


def metr(rows, deny):
    tp = fp = tn = fn = 0
    for x in rows:
        legit = x.is_legitimate
        allow = not deny(x)
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    fb = fp / (fp + tn) if (fp + tn) else 0.0     # false-block rate on legitimate rows
    return f1, sf, fb


def dropone(rows):
    R = lambda x: x.rbac_deny
    A = lambda x: x.abac_deny
    T = lambda x: x.tsphol_deny
    full = lambda x: R(x) or A(x) or T(x)
    res = {}
    res["FULL"] = metr(rows, full)
    for layer, without in [("RBAC", lambda x: A(x) or T(x)),
                           ("ABAC", lambda x: R(x) or T(x)),
                           ("TRAC", lambda x: R(x) or A(x))]:
        res[layer + "_without"] = metr(rows, without)
    return res


def replay(rbac_dict, tasks):
    trel.RESCUE_RELEVANCE = 4.0
    rows, _, _ = rs.replay_experiment(os.path.join(LL, VAL_LOG), tasks, experiment="E1",
                                      limit=None, policies=(rbac_dict, abac_production(), tsphol_production()))
    return rows


def main():
    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    variants = [
        ("baseline (rbac.yaml, tool-granular; domains=label)", rbac_production()),
        ("domain_label (tools=*, domains=label map)",          rbac_from_domainmap(LEGITIMATE_PAIRINGS)),
        ("role_indep (over-provisioned job-function roles)",   rbac_from_domainmap(ROLE_INDEP)),
    ]
    out = {}
    for name, rbac_dict in variants:
        rows = replay(rbac_dict, tasks)
        d = dropone(rows)
        full_f1, full_sf, full_fb = d["FULL"]
        rbac_marg = full_sf - d["RBAC_without"][1]
        abac_marg = full_sf - d["ABAC_without"][1]
        trac_marg = full_sf - d["TRAC_without"][1]
        rbac_rate = sum(1 for x in rows if x.rbac_deny) / len(rows)
        out[name] = {
            "n": len(rows),
            "full_f1": round(full_f1, 4), "full_secfail": round(full_sf, 4),
            "full_false_block": round(full_fb, 4),
            "rbac_deny_rate": round(rbac_rate, 4),
            "dropone_rbac_pp": round(100 * rbac_marg, 2),
            "dropone_abac_pp": round(100 * abac_marg, 2),
            "dropone_trac_pp": round(100 * trac_marg, 2),
        }
        print(f"\n### {name}")
        print(f"  n={len(rows)}  RBAC-deny-rate={rbac_rate:.3f}")
        print(f"  FULL: F1={full_f1:.3f}  SecFail={full_sf:.4f}  false-block={full_fb:.3f}")
        print(f"  drop-one marginals (delta SecFail, pp; negative = layer lowers SecFail):")
        print(f"    RBAC {100*rbac_marg:+.2f}   ABAC {100*abac_marg:+.2f}   TRAC {100*trac_marg:+.2f}")

    json.dump(out, open(os.path.join("scratch", "independent_rbac.json"), "w"), indent=2)
    print("\nSaved -> scratch/independent_rbac.json")


if __name__ == "__main__":
    main()
