"""Break down TRAC (TRAC) over-denials of legitimate work by domain / persona / rule.

Replays the production (baseline) stack over the SAME log the last post-experiment run used
(gpt-4o validation, all 6,942 rows) and isolates the availability cost: legitimate rows that
TRAC denies — especially those TRAC denies *uniquely* (RBAC and ABAC would have allowed them).
"""
import os
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs

LOG = os.path.join("datasets", "llm_inference_logs", "20260613005419_gpt-4o_validation.json")
OUT = os.path.join("scratch", "trac_overdeny_result.json")


def main():
    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    rows, summ, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=None,
                                         policies=rs.baseline_policies())
    n = len(rows)
    legit = [x for x in rows if x.is_legitimate]
    # All TRAC denials of legitimate work
    trac_legit_deny = [x for x in legit if x.tsphol_deny]
    # TRAC-UNIQUE over-denials: legit work only TRAC blocks (RBAC & ABAC would allow)
    trac_unique = [x for x in trac_legit_deny if not (x.rbac_deny or x.abac_deny)]

    def brk(rowset, key):
        return dict(Counter(key(x) for x in rowset).most_common())

    result = {
        "log": os.path.basename(LOG),
        "total_rows": n,
        "legit_rows": len(legit),
        "trac_denies_legit": len(trac_legit_deny),
        "trac_unique_overdeny": len(trac_unique),
        "trac_unique_overdeny_pct_of_legit": round(100 * len(trac_unique) / len(legit), 1) if legit else 0,
        # TRAC-unique over-denials (the real availability cost)
        "unique_by_rule": brk(trac_unique, lambda x: x.tsphol_rule or "(unnamed)"),
        "unique_by_domain": brk(trac_unique, lambda x: x.domain or "(none)"),
        "unique_by_persona": brk(trac_unique, lambda x: x.persona or "(none)"),
        "unique_by_match_tag": brk(trac_unique, lambda x: x.match_tag or "(none)"),
        # Cross-tab: rule x domain (top combos)
        "unique_rule_x_domain": dict(Counter(
            (f"{(x.tsphol_rule or '?')} | {x.domain or '?'}") for x in trac_unique).most_common(25)),
        # All-TRAC-legit-deny (incl. redundant) for context
        "all_legit_deny_by_rule": brk(trac_legit_deny, lambda x: x.tsphol_rule or "(unnamed)"),
        # Sample of unique over-denials for drill-down (task_idx + persona + domain + rule)
        "sample": [
            {"persona": x.persona, "task_idx": x.task_idx, "domain": x.domain,
             "match_tag": x.match_tag, "rule": x.tsphol_rule}
            for x in trac_unique[:60]
        ],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    # Console summary
    print(f"rows={n} legit={len(legit)} trac_denies_legit={len(trac_legit_deny)} "
          f"trac_unique_overdeny={len(trac_unique)} "
          f"({result['trac_unique_overdeny_pct_of_legit']}% of legit)")
    print("UNIQUE over-deny by rule:", json.dumps(result["unique_by_rule"]))
    print("UNIQUE over-deny by domain:", json.dumps(result["unique_by_domain"]))
    print("UNIQUE over-deny by persona:", json.dumps(result["unique_by_persona"]))
    print("UNIQUE by match_tag:", json.dumps(result["unique_by_match_tag"]))
    print("Saved ->", OUT)


if __name__ == "__main__":
    main()
