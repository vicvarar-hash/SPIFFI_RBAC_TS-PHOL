"""P2 probe: does a case-insensitive domain lookup in the capability ontology
separate correct from wrong bundles (rescues up, catches stay high)?

Read-only: monkeypatches get_hard_capabilities + infer_minimum_capabilities to
resolve the domain key case-insensitively, then re-runs the corrective scoreboard.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services.domain_capability_ontology import (
    DomainCapabilityOntology as O,
    get_domain_capabilities,
)

LOG = sys.argv[1] if len(sys.argv) > 1 else \
    "datasets/experiment_logs/run_20260613_005419_llm_gpt-4o_validation.json"
LIM = int(sys.argv[2]) if len(sys.argv) > 2 else None


def _ci_get(d, key):
    if key in d:
        return d[key]
    low = str(key).lower()
    for k in d:
        if str(k).lower() == low:
            return d[k]
    return None


def _llm_verdict(info):
    isv, e4 = info.get("is_valid"), info.get("llm_e4_decision")
    if isv is not None:
        return bool(isv)
    if e4 is not None:
        return e4 not in ("DENY", "DECEPTION_ROUTED")
    return None


def _lookup(log_path, experiment):
    import json
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    out = {}
    for r in log["experiments"][experiment]["rows"]:
        out[(r.get("persona"), r.get("task_idx"))] = {
            "is_valid": r.get("is_valid"), "llm_e4_decision": None}
    if log.get("evaluation_mode") == "validation" and "E4" in log["experiments"]:
        for r in log["experiments"]["E4"]["rows"]:
            k = (r.get("persona"), r.get("task_idx"))
            if k in out:
                out[k]["llm_e4_decision"] = r.get("final_decision")
    return out


def corrective(rows, lookup):
    c = {"legit": {"a": 0, "d": 0}, "illeg": {"a": 0, "d": 0},
         "catch_den": 0, "resc_den": 0, "catches": 0, "rescues": 0}
    leak = {"null": 0, "cross_domain": 0, "same_domain": 0, "other": 0}
    miss = {"null": 0, "cross_domain": 0, "same_domain": 0, "other": 0}
    for x in rows:
        v = _llm_verdict(lookup.get((x.persona, x.task_idx), {}))
        if v is None:
            continue
        deny = x.rbac_deny or x.abac_deny or x.tsphol_deny
        if x.is_legitimate:
            c["legit"]["d" if deny else "a"] += 1
            if not v:  # LLM rejected a legit -> rescue opportunity
                c["resc_den"] += 1
                if not deny:
                    c["rescues"] += 1
                else:
                    _bucket(miss, x)
        else:
            c["illeg"]["d" if deny else "a"] += 1
            if v:  # LLM allowed an illegit -> catch opportunity
                c["catch_den"] += 1
                if deny:
                    c["catches"] += 1
                else:
                    _bucket(leak, x)
    c["leak"], c["miss"] = leak, miss
    return c


def _bucket(d, x):
    tag = (x.match_tag or "").lower()
    if tag in ("null", "empty") or (not x.contains_read and not x.contains_write):
        d["null"] += 1
    elif x.domain_mismatch or x.multi_domain:
        d["cross_domain"] += 1
    elif tag == "wrong":
        d["same_domain"] += 1
    else:
        d["other"] += 1


def run(label):
    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    rows, _summ, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=LIM)
    h = rs.headline(rows)
    lk = _lookup(LOG, "E1")
    c = corrective(rows, lk)
    print(f"\n=== {label} ===")
    print("  secfail %.4f  legit-allow %.3f  deny %.3f"
          % (h["secfail"], h["legit_allow"], h["deny_rate"]))
    print("  CATCHES %d/%d (%.1f%%)  RESCUES %d/%d (%.1f%%)"
          % (c["catches"], c["catch_den"],
             100 * c["catches"] / c["catch_den"] if c["catch_den"] else 0,
             c["rescues"], c["resc_den"],
             100 * c["rescues"] / c["resc_den"] if c["resc_den"] else 0))
    print("  LEAK (illegit allowed) by kind:", c["leak"])
    print("  MISSED rescues (legit denied) by kind:", c["miss"])
    return c


# 1) baseline (buggy, case-sensitive) -- skip to save time; numbers already known
# run("BASELINE (case-sensitive lookup)")

# 2) patch: case-insensitive domain + intent resolution
_orig_fallbacks = O.infer_minimum_capabilities


def _ci_hard(domain, intent):
    caps = get_domain_capabilities()
    domain_intents = _ci_get(caps, domain) or {}
    data = _ci_get(domain_intents, intent)
    if isinstance(data, dict) and "hard" in data:
        return set(data["hard"])
    if isinstance(data, dict):
        return set(data.get("required", []))
    fb = _ci_fallback(domain)
    return set(fb.get("hard", fb.get("required", [])))


def _ci_fallback(domain):
    import app.services.domain_capability_ontology as mod
    ont = mod._get_ontology()
    fbs = ont.get("domain_fallbacks", {})
    hit = _ci_get(fbs, domain)
    if hit is not None:
        return hit
    return {"required": ["GenericRead"], "hard": ["GenericRead"]}


O.get_hard_capabilities = staticmethod(_ci_hard)
O.infer_minimum_capabilities = staticmethod(_ci_fallback)
import os as _os
if _os.environ.get("USE_REAL_CODE"):
    # Restore the real (now-fixed) implementations to validate the shipped fix.
    importlib_reload = __import__("importlib").reload
    import app.services.domain_capability_ontology as _m
    importlib_reload(_m)
    from app.services.domain_capability_ontology import DomainCapabilityOntology as _O2
    O.get_hard_capabilities = _O2.get_hard_capabilities
    O.infer_minimum_capabilities = _O2.infer_minimum_capabilities
    run("REAL shipped fix (case-insensitive in code)")
else:
    run("FIXED (monkeypatched case-insensitive lookup)")
