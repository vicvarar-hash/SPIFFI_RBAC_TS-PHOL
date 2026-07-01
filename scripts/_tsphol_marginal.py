"""TRAC marginal value: what it catches/costs AMONG RBAC-and-ABAC survivors.

Replays the full stack and isolates the rows that pass both RBAC and ABAC, then
asks what TRAC adds (security catch) and costs (legit blocked) on that residual —
the only set where TRAC can contribute. Crosses with the LLM verdict to find the
purest demonstration: illegit bundles the LLM accepted that ONLY TRAC stops.
"""
import json, os, sys
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services.experiment_config import PERSONAS
from app.loaders.astra_loader import load_astra_dataset

LOG = "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    with open(LOG, encoding="utf-8") as f:
        verdict = {(p, t["task_idx"]): t.get("is_valid")
                   for t in json.load(f)["tasks"] for p in PERSONAS}
    rows, _, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=None)
    n = len(rows)

    survivors = [x for x in rows if not x.rbac_deny and not x.abac_deny]  # pass RBAC & ABAC
    s_illeg = [x for x in survivors if not x.is_legitimate]
    s_legit = [x for x in survivors if x.is_legitimate]
    ts_caught_illeg = [x for x in s_illeg if x.tsphol_deny]
    ts_missed_illeg = [x for x in s_illeg if not x.tsphol_deny]
    ts_blocked_legit = [x for x in s_legit if x.tsphol_deny]

    print("LOG=%s  rows=%d" % (os.path.basename(LOG), n))
    print("RBAC denies %d (%.0f%%) · ABAC denies %d (%.0f%%) [independent]"
          % (sum(x.rbac_deny for x in rows), 100*sum(x.rbac_deny for x in rows)/n,
             sum(x.abac_deny for x in rows), 100*sum(x.abac_deny for x in rows)/n))
    print("\n=== RBAC&ABAC SURVIVORS: %d / %d rows (%.1f%%) ===" % (len(survivors), n, 100*len(survivors)/n))
    print("  of which legitimate=%d  illegitimate=%d" % (len(s_legit), len(s_illeg)))

    print("\n--- TRAC on illegitimate survivors (its marginal SECURITY catch) ---")
    print("  caught by TRAC : %d / %d (%.1f%%)" % (len(ts_caught_illeg), len(s_illeg),
                                                      100*len(ts_caught_illeg)/len(s_illeg) if s_illeg else 0))
    print("  still slip through: %d  (residual SecFail after full stack)" % len(ts_missed_illeg))
    # which TRAC rule does the catching
    from collections import Counter
    print("  catch by rule:", dict(Counter(x.tsphol_rule for x in ts_caught_illeg)))
    # of the caught, how many did the LLM ACCEPT? (purest TRAC value: only-TRAC stops an LLM-accepted threat)
    llm_accepted_caught = [x for x in ts_caught_illeg if verdict.get((x.persona, x.task_idx)) is True]
    print("  ...of those, LLM had ACCEPTED: %d  <- threats only TRAC stops (RBAC/ABAC/LLM all miss)"
          % len(llm_accepted_caught))

    print("\n--- TRAC on legitimate survivors (its marginal AVAILABILITY cost) ---")
    print("  legit blocked by TRAC: %d / %d (%.1f%%)" % (len(ts_blocked_legit), len(s_legit),
                                                            100*len(ts_blocked_legit)/len(s_legit) if s_legit else 0))
    print("  block by rule:", dict(Counter(x.tsphol_rule for x in ts_blocked_legit)))

    # net marginal: security gained vs availability lost
    print("\n=== TRAC MARGINAL LEDGER (over RBAC+ABAC) ===")
    print("  + illegit caught that RBAC/ABAC missed : %d" % len(ts_caught_illeg))
    print("    (of which the LLM also missed        : %d)" % len(llm_accepted_caught))
    print("  - legit blocked that RBAC/ABAC allowed : %d" % len(ts_blocked_legit))


if __name__ == "__main__":
    main()
