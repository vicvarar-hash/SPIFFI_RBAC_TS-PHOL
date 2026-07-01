"""RBAC + ABAC parity: real `opa eval` vs the Python engine, fed the engine's EXACT attrs.

For each (persona, candidate bundle) we run the isolated RBAC and ABAC engines, take the
Python decision, and capture the ABAC `attributes_used` the engine actually evaluated; we
then feed those same attributes (and the RBAC spiffe/mcps/tools) to real OPA and compare.
"""
import json, os, subprocess, sys, tempfile
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services.experiment_config import PERSONAS
from app.services.normalization import normalize_mcp_name
from app.loaders.astra_loader import load_astra_dataset
from app.loaders.mcp_loader import load_mcp_personas

OPA = os.path.join(os.environ.get("TEMP", "."), "opa.exe")
INPUT = os.path.join(tempfile.gettempdir(), f"_opa_in_{os.getpid()}.json")


def opa_raw(deps, query, inp):
    with open(INPUT, "w", encoding="utf-8") as f:
        json.dump(inp, f)
    cmd = [OPA, "eval"]
    for d in deps:
        cmd += ["-d", d]
    cmd += ["-i", INPUT, "-f", "raw", query]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip()


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    mcp_personas, _ = load_mcp_personas("mcp_servers")
    rbac_pol, abac_pol, tsphol_pol = rs.baseline_policies()
    engines = rs._engines_from_policies(mcp_personas, rbac_pol, abac_pol, tsphol_pol)

    abac_mm, rbac_mm, n = 0, 0, 0
    a_ex, r_ex = [], []
    for ti, t in enumerate(tasks[:30]):
        tools, mcps = list(t.candidate_tools), list(t.candidate_mcp)
        dom = normalize_mcp_name(t.groundtruth_mcp[0]) if t.groundtruth_mcp else None
        for pk in PERSONAS:
            spiffe = PERSONAS[pk]["spiffe_id"]
            # ── ABAC ──
            ares = rs._eval(engines["abac"], pk, tools, mcps, t.task, "validation", task_domain=dom)
            py_abac = ares.final_decision in rs.DENY_STATES
            attrs = (ares.context or {}).get("abac_baseline", {}).get("attributes_used")
            if attrs:
                d = opa_raw(["policies/abac_rules.yaml", "policies/rego/abac.rego"],
                            "data.paladin.abac.decision",
                            {"subject": attrs["subject"], "resource": attrs["resource"], "action": attrs["action"]})
                if (d == "DENY") != py_abac:
                    abac_mm += 1
                    if len(a_ex) < 6:
                        a_ex.append((pk, ti, d, py_abac, ares.denial_source))
            # ── RBAC ──
            rres = rs._eval(engines["rbac"], pk, tools, mcps, t.task, "validation")
            py_rbac = rres.final_decision in rs.DENY_STATES
            d = opa_raw(["policies/rbac.yaml", "policies/rego/rbac.rego"],
                        "data.paladin.rbac.decision",
                        {"spiffe_id": spiffe, "mcps": mcps, "tools": tools})
            if (d == "DENY") != py_rbac:
                rbac_mm += 1
                if len(r_ex) < 6:
                    r_ex.append((pk, ti, d, py_rbac))
            n += 1

    if os.path.exists(INPUT):
        os.remove(INPUT)
    rs._release_engines(engines)
    print("evaluations: %d" % n)
    print("ABAC mismatches (OPA vs Python): %d" % abac_mm)
    for pk, ti, d, py, src in a_ex:
        print("   ABAC", pk, "task", ti, "opa=", d, "py_deny=", py, "src=", src)
    print("RBAC mismatches (OPA vs Python): %d" % rbac_mm)
    for pk, ti, d, py in r_ex:
        print("   RBAC", pk, "task", ti, "opa=", d, "py_deny=", py)
    print("\nRBAC+ABAC OPA PARITY:", "PASS" if (abac_mm == 0 and rbac_mm == 0) else "FAIL")


if __name__ == "__main__":
    main()
