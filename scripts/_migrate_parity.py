"""Parity check: replay(original legacy log) ?= replay(its llm_inference_v1 migration).

Confirms the migration preserves every per-row governance decision, is_legitimate,
and the LLM verdict — so the migrated logs reproduce the lab's headline + corrective
metrics exactly.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services.llm_inference_log import migrate_experiment_log, save_log
from app.services.experiment_config import PERSONAS
from app.loaders.astra_loader import load_astra_dataset

OLD = sys.argv[1] if len(sys.argv) > 1 else \
    "datasets/experiment_logs/run_20260613_005419_llm_gpt-4o_validation.json"


def _verdict(info):
    isv, e4 = info.get("is_valid"), info.get("llm_e4_decision")
    if isv is not None:
        return bool(isv)
    if e4 is not None:
        return e4 not in ("DENY", "DECEPTION_ROUTED")
    return None


def _lookup(log_path, experiment, schema):
    """Mirror post_experiment_lab._row_lookup for both formats (kept local to avoid st)."""
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    out = {}
    if log.get("schema") == "llm_inference_v1":
        for t in log.get("tasks", []):
            ti = t.get("task_idx")
            info = {"is_valid": t.get("is_valid"), "match_tag": t.get("match_tag"),
                    "llm_e4_decision": None}
            for p in PERSONAS:
                out[(p, ti)] = dict(info)
        return out
    for r in log["experiments"][experiment]["rows"]:
        out[(r.get("persona"), r.get("task_idx"))] = {
            "is_valid": r.get("is_valid"), "match_tag": r.get("match_tag"),
            "llm_e4_decision": None}
    if log.get("evaluation_mode") == "validation" and "E4" in log["experiments"]:
        for r in log["experiments"]["E4"]["rows"]:
            k = (r.get("persona"), r.get("task_idx"))
            if k in out:
                out[k]["llm_e4_decision"] = r.get("final_decision")
    return out


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")

    with open(OLD, encoding="utf-8") as f:
        old_log = json.load(f)
    migrated = migrate_experiment_log(old_log, os.path.basename(OLD))

    tmp = os.path.join(tempfile.gettempdir(), "_parity_llm_inference.json")
    save_log(tmp, migrated)

    print(f"OLD : {os.path.basename(OLD)}  ({old_log.get('evaluation_mode')}, {old_log.get('llm_model')})")
    print(f"NEW : {migrated['schema']}  ({migrated['mode']}, {migrated['model']}, {len(migrated['tasks'])} tasks)")

    ro, so, _ = rs.replay_experiment(OLD, tasks, experiment="E1")
    rn, sn, _ = rs.replay_experiment(tmp, tasks, experiment="E1")
    print(f"\nrows: old={len(ro)}  new={len(rn)}")

    ho, hn = rs.headline(ro), rs.headline(rn)
    for k in ("secfail", "legit_allow", "deny_rate", "rbac_deny_rate", "abac_deny_rate", "tsphol_deny_rate"):
        flag = "" if abs(ho[k] - hn[k]) < 1e-9 else "  <-- DIFF"
        print(f"  {k:18s} old={ho[k]:.4f}  new={hn[k]:.4f}{flag}")

    # Per-row decision parity, keyed by (persona, task_idx).
    def key_map(rows):
        return {(x.persona, x.task_idx): (x.is_legitimate, x.rbac_deny, x.abac_deny, x.tsphol_deny)
                for x in rows}
    mo, mn = key_map(ro), key_map(rn)
    shared = set(mo) & set(mn)
    mism = [k for k in shared if mo[k] != mn[k]]
    print(f"\nper-row keys: old={len(mo)} new={len(mn)} shared={len(shared)} "
          f"only_old={len(set(mo)-set(mn))} only_new={len(set(mn)-set(mo))}")
    print(f"decision mismatches: {len(mism)}")
    for k in mism[:8]:
        print(f"   {k}: old={mo[k]} new={mn[k]}")

    # LLM-verdict parity (drives catch/rescue).
    lo = _lookup(OLD, "E1", "experiments_v0")
    ln = _lookup(tmp, "E1", "llm_inference_v1")
    vmism = [k for k in shared if _verdict(lo.get(k, {})) != _verdict(ln.get(k, {}))]
    print(f"verdict mismatches:  {len(vmism)}")
    for k in vmism[:8]:
        print(f"   {k}: old={_verdict(lo.get(k, {}))} new={_verdict(ln.get(k, {}))} "
              f"(old_e4={lo.get(k, {}).get('llm_e4_decision')})")

    ok = not mism and not vmism and len(mo) == len(mn)
    print("\nPARITY:", "PASS ✅" if ok else "FAIL ❌")


if __name__ == "__main__":
    main()
