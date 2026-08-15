"""Audit LLM-authored RBAC/ABAC policies for shape validity, coverage, type hygiene and leakage.

Run:  python scratch/audit_authored.py
Reads policies/llm_authored/<model>/{rbac.yaml,abac_rules.yaml}.
"""
import os, sys, yaml, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from app.services.experiment_config import (
    PERSONAS, LEGITIMATE_PAIRINGS, rbac_production, abac_production,
)
from app.services.normalization import normalize_mcp_name

AUTH = os.path.join(ROOT, "policies", "llm_authored")
MODELS = ["opus48", "sonnet46", "gpt54", "gemini31", "grok45"]

EXPECTED_SPIFFE = {p["spiffe_id"] for p in PERSONAS.values()}

# Known attribute vocabulary from the brief / engine
KNOWN = {
    ("subject", "attributes.clearance_level"), ("subject", "attributes.department"),
    ("subject", "attributes.trust_score"), ("subject", "role"),
    ("resource", "risk_level"), ("resource", "compliance_tier"),
    ("resource", "data_sensitivity"), ("resource", "trust_boundary"),
    ("action", "contains_write"), ("action", "contains_destructive_write"),
    ("action", "contains_read_before_write"),
}


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def rbac_allow_domains(rbac):
    """spiffe_id -> set(normalized allowed domains)."""
    out = {}
    for pol in (rbac or {}).get("policies", []):
        allowed = {normalize_mcp_name(r.get("mcp")) for r in pol.get("rules", [])
                   if r.get("action") == "allow" and r.get("mcp") not in ("*", None)}
        out[pol.get("spiffe_id")] = allowed
    return out


def audit_rbac(model, rbac):
    print(f"  RBAC:")
    if not isinstance(rbac, dict) or "policies" not in rbac:
        print(f"    !! BAD SHAPE: top-level keys = {list(rbac) if isinstance(rbac, dict) else type(rbac)}")
        return
    sp = {p.get("spiffe_id") for p in rbac["policies"]}
    missing = EXPECTED_SPIFFE - sp
    extra = sp - EXPECTED_SPIFFE
    print(f"    policies={len(rbac['policies'])}  spiffe_ok={not missing and not extra}")
    if missing: print(f"    !! MISSING spiffe: {missing}")
    if extra:   print(f"    !! UNKNOWN spiffe: {extra}")
    dom = rbac_allow_domains(rbac)
    for p in rbac["policies"]:
        rules = p.get("rules", [])
        has_deny = any(r.get("action") == "deny" for r in rules)
        # tool granularity: any rule with a specific (non-*) tool list?
        toolwise = any(r.get("tools") and r.get("tools") != ["*"] for r in rules)
        ntools = sum(len(r.get("tools", []) or []) for r in rules if r.get("action") == "allow")
        print(f"      {p.get('spiffe_id'):38} allow_domains={sorted(dom.get(p.get('spiffe_id'), []))} "
              f"default_deny={has_deny} tool_level={toolwise} n_allow_tools={ntools}")


def audit_abac(model, abac):
    print(f"  ABAC:")
    if isinstance(abac, dict):
        rules = abac.get("rules")
        if rules is None:
            print(f"    !! BAD SHAPE: top-level keys = {list(abac)}")
            return
    elif isinstance(abac, list):
        rules = abac
        print(f"    (top-level is a bare list — engine expects {{'rules': [...]}})")
    else:
        print(f"    !! BAD SHAPE: {type(abac)}")
        return
    strbool = 0
    unknown = set()
    ops = {}
    for rule in rules:
        for spec in rule.get("match_attributes", []):
            src, attr = spec.get("source"), spec.get("attribute")
            if (src, attr) not in KNOWN:
                unknown.add(f"{src}.{attr}")
            v = spec.get("value")
            if isinstance(v, str) and v.strip().lower() in ("true", "false"):
                strbool += 1
            ops[spec.get("op")] = ops.get(spec.get("op"), 0) + 1
    print(f"    rules={len(rules)}  string_bool_values={strbool}  ops={ops}")
    if unknown:
        print(f"    !! UNKNOWN attributes referenced: {sorted(unknown)}")


def leak_check(model, rbac, abac):
    prod_rbac = rbac_production()
    prod_dom = rbac_allow_domains(prod_rbac)
    auth_dom = rbac_allow_domains(rbac)
    exact = [sp for sp in EXPECTED_SPIFFE
             if sp in auth_dom and sp in prod_dom and auth_dom[sp] == prod_dom[sp] and auth_dom[sp]]
    # Compare against LEGITIMATE_PAIRINGS (the withheld ground truth)
    legit_by_spiffe = {PERSONAS[k]["spiffe_id"]: {normalize_mcp_name(d) for d in v}
                       for k, v in LEGITIMATE_PAIRINGS.items()}
    matches_legit = [sp for sp in EXPECTED_SPIFFE
                     if sp in auth_dom and auth_dom[sp] == legit_by_spiffe.get(sp) and auth_dom[sp]]
    print(f"  LEAK: rbac_domains==production for {len(exact)}/6 personas {exact if exact else ''}")
    print(f"        rbac_domains==withheld LEGITIMATE_PAIRINGS for {len(matches_legit)}/6 {matches_legit if matches_legit else ''}")


def main():
    for m in MODELS:
        d = os.path.join(AUTH, m)
        rp, ap = os.path.join(d, "rbac.yaml"), os.path.join(d, "abac_rules.yaml")
        print(f"\n=== {m} ===")
        if not (os.path.exists(rp) and os.path.exists(ap)):
            print(f"  (missing files: rbac={os.path.exists(rp)} abac={os.path.exists(ap)})")
            continue
        try:
            rbac = load(rp)
        except Exception as e:
            print(f"  !! RBAC YAML parse error: {e}"); rbac = None
        try:
            abac = load(ap)
        except Exception as e:
            print(f"  !! ABAC YAML parse error: {e}"); abac = None
        if rbac is not None:
            audit_rbac(m, rbac)
        if abac is not None:
            audit_abac(m, abac)
        if rbac is not None:
            leak_check(m, rbac, abac)


if __name__ == "__main__":
    main()
