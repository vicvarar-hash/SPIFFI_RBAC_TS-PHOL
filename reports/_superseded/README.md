# ⚠️ SUPERSEDED REPORTS — pre-agnostic (oracle-aided) system

The reports in this folder describe an **earlier version of PALADIN** and do **not**
match the current paper (`paper/main_acm.tex`) or the released results. They are kept
for provenance only. **Do not cite them.**

They predate two major changes:

1. **Agnostic, leak-free engine.** The old TRAC/capability layer consulted the gold MCP
   (`gt_mcps[0]`) as an oracle, giving an artificially low validation `SecFail ≤ 1%`
   (`F1 ≈ 0.856`). The current engine infers the task domain from **task text only**
   (BM25), consuming no ground-truth label. This raises the honest floor and
   redistributes the security work onto RBAC/ABAC.
2. **Renamed layer + trimmed policy.** `TS-PHOL` → **TRAC**; deception routing
   (`DECEPTION_ROUTED`) removed (pure ALLOW/DENY + advisory alerts); ABAC reduced to
   **6 rules**.

## Current canonical headline (see `reports/2026-07-01_canonical_results.md`)

| Config | F1 | SecFail | Admit |
|---|---|---|---|
| **E1 deterministic stack** (identical for every model) | **0.844** | **0.107** | **43.9%** |
| E4 LLM-only — gpt-4o / gpt-5.4 / gpt-3.5-turbo-16k | 0.760 / 0.482 / 0.652 | 0.268 / 0.665 / 0.482 | 50.9 / 85.8 / 82.3% |
| FULL (stack + gate) — gpt-4o / gpt-5.4 / gpt-3.5-turbo-16k | 0.859 / 0.849 / 0.867 | 0.021 / 0.075 / 0.046 | 24.6 / 36.6 / 38.2% |

Source of truth: `scratch/canonical_rebuild.py` → `scratch/canonical_rows/` →
`scratch/canonical_tables.py` (replays the released raw logs through the live agnostic
engine).
