"""Inspect the two TRAC evidence sets on the gpt-5.4 validation log:
  (1) the 13 unique catches — illegit survivors of RBAC&ABAC that the LLM ACCEPTED
      but TRAC denied (the purest deterministic-over-LLM saves).
  (2) the legit bundles write_safety blocks (correct vs false-positive check).
"""
import json, os, sys
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services.experiment_config import PERSONAS
from app.loaders.astra_loader import load_astra_dataset

LOG = "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"


def short(s, n=110):
    s = " ".join(str(s).split())
    return s[:n] + ("…" if len(s) > n else "")


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    with open(LOG, encoding="utf-8") as f:
        verdict = {(p, t["task_idx"]): t.get("is_valid")
                   for t in json.load(f)["tasks"] for p in PERSONAS}
    rows, _, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=None)

    survivors = [x for x in rows if not x.rbac_deny and not x.abac_deny]
    unique = [x for x in survivors if (not x.is_legitimate) and x.tsphol_deny
              and verdict.get((x.persona, x.task_idx)) is True]
    legit_block = [x for x in survivors if x.is_legitimate and x.tsphol_deny
                   and x.tsphol_rule == "write_safety"]

    def task_of(i):
        return tasks[i]

    print("=" * 90)
    print("(1) THE %d UNIQUE CATCHES — RBAC+ABAC+LLM all said OK, only TRAC stopped it" % len(unique))
    print("=" * 90)
    print("unique tasks:", len({x.task_idx for x in unique}))
    for x in sorted(unique, key=lambda r: r.task_idx):
        t = task_of(x.task_idx)
        print("\n[task %d | %s | match_tag=%s | rule=%s]" % (x.task_idx, x.persona, x.match_tag, x.tsphol_rule))
        print("  task     :", short(getattr(t, "task", "")))
        print("  candidate:", short(getattr(t, "candidate_tools", []), 130),
              "@", getattr(t, "candidate_mcp", []))
        print("  groundtru:", short(getattr(t, "groundtruth_tools", []), 130),
              "@", getattr(t, "groundtruth_mcp", []))
        print("  facts    : hard_missing=%s cap_cov=%.2f write=%s read=%s domain_mismatch=%s"
              % (x.hard_missing, x.cap_coverage, x.contains_write, x.contains_read, x.domain_mismatch))

    print("\n" + "=" * 90)
    print("(2) LEGIT BUNDLES write_safety BLOCKS — %d rows (correct vs false-positive?)" % len(legit_block))
    print("=" * 90)
    from collections import Counter
    print("unique tasks:", len({x.task_idx for x in legit_block}),
          "| match_tag:", dict(Counter(x.match_tag for x in legit_block)))
    seen = set()
    for x in sorted(legit_block, key=lambda r: r.task_idx):
        if x.task_idx in seen:
            continue
        seen.add(x.task_idx)
        t = task_of(x.task_idx)
        print("\n[task %d | %s | match_tag=%s]" % (x.task_idx, x.persona, x.match_tag))
        print("  task     :", short(getattr(t, "task", "")))
        print("  candidate:", short(getattr(t, "candidate_tools", []), 150), "@", getattr(t, "candidate_mcp", []))
        print("  facts    : write=%s read=%s" % (x.contains_write, x.contains_read))


if __name__ == "__main__":
    main()
