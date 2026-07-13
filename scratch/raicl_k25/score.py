"""Score the k=25 exploratory run: exact-match + Jaccard.

Faithful to the pipeline: tool_match = set(selected)==set(candidate_tools),
Jaccard = |inter|/|union| (raw strings) — matching llm_inference_producer.py.
NO LLM calls. References use the released logs' STORED tool_match (authoritative).
"""
from __future__ import annotations

import json
import os

from app.loaders.astra_loader import load_astra_dataset
from app.services.split_service import load_or_build_split
from app.services.experiment_runner import _task_fingerprint
from app.services.llm_inference_producer import _candidate_tools

LOGDIR = os.path.join("datasets", "llm_inference_logs")
K25_DIR = os.path.join("scratch", "raicl_k25")
RELEASED_BASELINE = os.path.join(LOGDIR, "20260613105137_gpt-5-4_selection.json")
RELEASED_BM25_FULL = os.path.join(LOGDIR, "20260613165151_gpt-5-4_selection_ra-bm25-k10000.json")


def _match(sel, gold):
    s, g = set(sel or []), set(gold or [])
    u = s | g
    return (s == g), (len(s & g) / len(u) if u else 1.0)


def _load_jsonl(path):
    rows = {}
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows[o["id"]] = [s.get("tool") for s in (o.get("selections") or []) if s.get("tool")]
    return rows


def _score_rows(rows, by_fp):
    n = em = 0
    jsum = 0.0
    for fp, sel in rows.items():
        t = by_fp.get(fp)
        if t is None:
            continue
        m, j = _match(sel, _candidate_tools(t))
        n += 1
        em += int(m)
        jsum += j
    return n, em, (jsum / n if n else 0.0)


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    by_fp = {_task_fingerprint(t): t for t in tasks}
    split = load_or_build_split(tasks, ratio=0.7, seed=42)
    test_fps = set(split.test_fingerprints)  # 174 correct-test

    # --- validation: recompute agrees with released baseline log ---
    rel = json.load(open(RELEASED_BASELINE, encoding="utf-8"))
    agree = tot = 0
    for t in rel["tasks"]:
        if t.get("tool_match") is None:
            continue
        m, _ = _match(t.get("selected_tools"), _candidate_tools(tasks[t["task_idx"]]))
        tot += 1
        agree += int(m == t["tool_match"])
    print(f"[validation] recompute==stored tool_match: {agree}/{tot}")

    # --- references on the FULL 174 correct-test slice (STORED tool_match) ---
    bm = json.load(open(RELEASED_BM25_FULL, encoding="utf-8"))
    fp_em = fp_n = 0
    for t in bm["tasks"]:
        if t.get("match_tag") == "correct" and t.get("tool_match") is not None:
            fp_n += 1
            fp_em += int(bool(t["tool_match"]))
    bl_em = bl_n = 0
    for t in rel["tasks"]:
        if t.get("tool_match") is None:
            continue
        if _task_fingerprint(tasks[t["task_idx"]]) in test_fps:
            bl_n += 1
            bl_em += int(bool(t["tool_match"]))

    print("\n=== EXACT-MATCH on correct-test slice ===")
    print(f"Azure baseline (k=0)          [n={bl_n}]  : {bl_em}/{bl_n} = {bl_em/bl_n:.3f}")
    print(f"Azure BM25 full-pool k=10000  [n={fp_n}]  : {fp_em}/{fp_n} = {fp_em/fp_n:.3f}")

    print("\n--- CLI gpt-5.4 exploratory run (n=50 subset of the 174) ---")
    for label, f in [("CLI baseline  (contaminated 1-agent)", "out_baseline.jsonl"),
                     ("CLI k=25      (contaminated 1-agent)", "out_k25.jsonl"),
                     ("CLI baseline  (BLIND agent)         ", "out_baseline2.jsonl"),
                     ("CLI k=25      (BLIND agent)         ", "out_k25_2.jsonl")]:
        rows = _load_jsonl(os.path.join(K25_DIR, f))
        if not rows:
            print(f"[{label}] no output yet")
            continue
        n, em, jac = _score_rows(rows, by_fp)
        print(f"[{label}] n={n}  exact-match={em}/{n}={em/n:.3f}  avg_jaccard={jac:.3f}")


if __name__ == "__main__":
    main()
