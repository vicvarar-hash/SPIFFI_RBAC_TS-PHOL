"""P4: validate the shipped policies across all cached validation models.

Replays each model's validation log with the shipped (P2+P3) policies and reports
headline + corrective (catches/rescues) + per-rule firing. No reevaluation tricks —
this exercises the real engines / real YAML end-to-end, per model.
"""
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs

LOGS = [
    ("gpt-3.5", "run_20260613_141204_llm_gpt-35-turbo-16k_validation.json"),
    ("gpt-4o",  "run_20260613_005419_llm_gpt-4o_validation.json"),
    ("gpt-5.4", "run_20260612_191843_llm_gpt-5_4_validation.json"),
    ("gemini",  "run_20260612_160439_llm_gemini-2_5-pro_validation.json"),
]
LOGDIR = os.path.join("datasets", "experiment_logs")


def _llm_verdict(info):
    isv, e4 = info.get("is_valid"), info.get("llm_e4_decision")
    if isv is not None:
        return bool(isv)
    if e4 is not None:
        return e4 not in ("DENY", "DECEPTION_ROUTED")
    return None


def _lookup(log_path):
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    out = {}
    for r in log["experiments"]["E1"]["rows"]:
        out[(r.get("persona"), r.get("task_idx"))] = {
            "is_valid": r.get("is_valid"), "llm_e4_decision": None}
    if log.get("evaluation_mode") == "validation" and "E4" in log["experiments"]:
        for r in log["experiments"]["E4"]["rows"]:
            k = (r.get("persona"), r.get("task_idx"))
            if k in out:
                out[k]["llm_e4_decision"] = r.get("final_decision")
    return out


def corrective(rows, lookup):
    catch_den = catches = resc_den = rescues = 0
    leak = {"null": 0, "cross_domain": 0, "same_domain": 0, "other": 0}
    for x in rows:
        v = _llm_verdict(lookup.get((x.persona, x.task_idx), {}))
        if v is None:
            continue
        deny = x.rbac_deny or x.abac_deny or x.tsphol_deny
        if x.is_legitimate:
            if not v:
                resc_den += 1
                rescues += not deny
        else:
            if v:
                catch_den += 1
                if deny:
                    catches += 1
                else:
                    tag = (x.match_tag or "").lower()
                    if tag in ("null", "empty") or (not x.contains_read and not x.contains_write):
                        leak["null"] += 1
                    elif x.domain_mismatch or x.multi_domain:
                        leak["cross_domain"] += 1
                    elif tag == "wrong":
                        leak["same_domain"] += 1
                    else:
                        leak["other"] += 1
    return catch_den, catches, resc_den, rescues, leak


tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
for model, fname in LOGS:
    path = os.path.join(LOGDIR, fname)
    if not os.path.exists(path):
        print(f"\n### {model}: MISSING {fname}")
        continue
    rows, _summ, _bc = rs.replay_experiment(path, tasks, experiment="E1")
    h = rs.headline(rows)
    lk = _lookup(path)
    cd, c, rd, r, leak = corrective(rows, lk)
    fire = {}
    for x in rows:
        if x.tsphol_deny and x.tsphol_rule:
            fire[x.tsphol_rule] = fire.get(x.tsphol_rule, 0) + 1
    legit = [x for x in rows if x.is_legitimate]
    ts_fp = sum(1 for x in legit if x.tsphol_deny and not x.rbac_deny and not x.abac_deny)
    n = h["n"]
    print(f"\n### {model}  (n={n})")
    print("  secfail %.4f  legit-allow %.3f  deny %.3f  | rbac %.2f abac %.2f tsphol %.2f"
          % (h["secfail"], h["legit_allow"], h["deny_rate"],
             h["rbac_deny_rate"], h["abac_deny_rate"], h["tsphol_deny_rate"]))
    print("  CATCHES %d/%d (%.1f%%)  RESCUES %d/%d (%.1f%%)"
          % (c, cd, 100 * c / max(cd, 1), r, rd, 100 * r / max(rd, 1)))
    print("  TRAC false-pos on legit (sole denier): %d (%.1f%% of legit)"
          % (ts_fp, 100 * ts_fp / max(len(legit), 1)))
    print("  per-rule firing:", dict(sorted(fire.items(), key=lambda kv: -kv[1])))
    print("  leak by kind:", leak)
