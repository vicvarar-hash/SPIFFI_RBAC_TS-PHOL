# k=25 RA-ICL exploratory investigation

Purpose: check whether the released BM25 RA-ICL selection result (which used
`k=10000` = full-pool injection, 39.1% exact-match) holds at a *genuine* retrieval
depth (`k=25`). This investigation informed the decision to **remove RA-ICL from
the paper**.

## Constraint
No user/Azure API keys were used. LLM inference was done via **CLI-provided
`gpt-5.4` sub-agents** acting as the selection model; all deterministic parts
(BM25 exemplar retrieval, scoring, availability analysis) are local compute.

## Method
- `gen_prompts.py` — captures **byte-identical** `PredictionService` prompts (a
  fake LLM records the `(system, user)` prompt instead of calling any model) for
  the 50 correct-test tasks of the `0.7@seed42` split, under two conditions:
  baseline (`k=0`, no exemplars) and `k=25` BM25 exemplars. Factors out the
  constant 12-MCP / 352-tool catalog so it is sent once.
- Inference: two **blind** `gpt-5.4` agents (one baseline-only, one k25-only) so
  neither can copy the other. (An earlier single agent doing both conditions was
  **contaminated** — 47/50 identical across conditions — and discarded.)
- `score.py` — exact-match = `set(selected)==set(candidate_tools)`, Jaccard =
  intersection/union, matching `llm_inference_producer.py`. Validated: recomputed
  `tool_match` agrees with the released baseline log 1157/1157.

## Results (exact-match, correct-test slice)
| Condition | exact-match | source |
|---|---|---|
| Azure baseline (k=0) | 10.3% (18/174) | released log |
| CLI baseline (k=0), blind | 10.0% (5/50) | this run (endpoint calibration ✓) |
| **CLI BM25 k=25, blind** | **24.0% (12/50)** | this run |
| Azure BM25 full-pool k=10000 | 39.1% (68/174) | released log |

Deterministic copyable-exemplar availability (no LLM): a perfect-copy exemplar is
present for **96.6%** of tasks at full-pool vs **70.7%** at k=25. So full-pool's
39.1% is largely the model *copying* an available near-duplicate (present 97% of
the time, copied ~40%); at a genuine k=25 the copyable exemplar survives ~73% as
often, predicting ~28% — consistent with the empirical 24%.

## Conclusion
- k=25 is **genuine retrieval** (~24%, clearly above the 10% baseline) — but the
  headline full-pool 39.1% is **copy-inflated**, and at k=10000 "BM25 retrieval"
  is really re-ranking, not retrieval.
- Peripheral (single-model, selection-mode), and the copy-inflation is
  reconstructible from the released logs — a reviewer liability. **Dropped from
  the paper.** The "LLM tool choices need the deterministic floor" angle is
  retained by baseline selection (exact-match ~11%, selection-mode SecFail 21.9%).
- Caveats: n=50 (95% CI on 24% ≈ ±12pp); CLI `gpt-5.4` endpoint may differ from
  Azure Foundry, though the baseline calibration (10.0% vs 10.3%) indicates
  comparability. Exploratory.

## Files
- `gen_prompts.py`, `score.py` — harness (regenerate everything).
- `out_baseline2.jsonl`, `out_k25_2.jsonl` — **blind** agent selections (used).
- `out_baseline.jsonl`, `out_k25.jsonl` — earlier one-agent run (contaminated; kept for the record).
- Large regenerable prompt files (`payload.json`, `tasks*.jsonl`, `context.txt`)
  are git-ignored; regenerate with `PYTHONPATH=. python scratch/raicl_k25/gen_prompts.py`.
