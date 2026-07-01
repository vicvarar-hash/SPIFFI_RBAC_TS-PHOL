"""Sweep capability_coverage top-K and tool_relevance threshold over the gpt-4o validation log.

Runs the real replay engine (faithful) for each (K, threshold), reporting the security vs
availability tradeoff: headline SecFail / legit-allow / deny-rate, plus TRAC-UNIQUE catches
(illegit RBAC/ABAC would allow but TRAC denies = security value) and TRAC-UNIQUE over-denials
(legit RBAC/ABAC would allow but TRAC denies = availability cost).
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services import task_domain_classifier as tdc
from app.services import tool_relevance as trel

LOG = os.path.join("datasets", "llm_inference_logs", "20260613005419_gpt-4o_validation.json")
GRID = [(1, 1.0), (2, 1.0), (3, 1.0), (2, 0.5), (3, 0.5)]


def metrics(rows):
    legit = [x for x in rows if x.is_legitimate]
    illeg = [x for x in rows if not x.is_legitimate]
    h = rs.headline(rows)
    def denied(x):
        return x.rbac_deny or x.abac_deny or x.tsphol_deny
    # TRAC-unique = RBAC and ABAC both allow, TRAC decides
    trac_unique_overdeny = sum(1 for x in legit if x.tsphol_deny and not (x.rbac_deny or x.abac_deny))
    trac_unique_catch = sum(1 for x in illeg if x.tsphol_deny and not (x.rbac_deny or x.abac_deny))
    return {
        "secfail": round(h["secfail"], 4),
        "legit_allow": round(h["legit_allow"], 4),
        "deny_rate": round(h["deny_rate"], 4),
        "tsphol_deny_rate": round(h["tsphol_deny_rate"], 4),
        "trac_unique_overdeny": trac_unique_overdeny,
        "trac_unique_catch": trac_unique_catch,
        "legit_n": len(legit), "illeg_n": len(illeg),
    }


def main():
    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    results = []
    for k, thr in GRID:
        tdc.CAPCOV_TOPK = k
        trel.THRESHOLD = thr
        rows, _, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=None,
                                          policies=rs.baseline_policies())
        m = metrics(rows)
        m["K"] = k
        m["tool_rel_thr"] = thr
        results.append(m)
        print(f"K={k} thr={thr} | SecFail={m['secfail']:.3f} legit_allow={m['legit_allow']:.3f} "
              f"deny={m['deny_rate']:.3f} | TRAC-unique catch={m['trac_unique_catch']} "
              f"over-deny={m['trac_unique_overdeny']}", flush=True)
    with open(os.path.join("scratch", "trac_sweep_result.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nSaved -> scratch/trac_sweep_result.json")
    # Pretty table
    print("\n K  thr | SecFail legit  deny  | TRACcatch TRACoverdeny")
    for m in results:
        print(f" {m['K']}  {m['tool_rel_thr']:<4} | {m['secfail']:.3f}  {m['legit_allow']:.3f} "
              f"{m['deny_rate']:.3f} | {m['trac_unique_catch']:>5}     {m['trac_unique_overdeny']:>5}")


if __name__ == "__main__":
    main()
