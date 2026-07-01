# PALADIN — Canonical Results (current agnostic engine)

> **Date:** 2026-07-01 · **Mode:** validation + selection · **Panel:** gpt-3.5-turbo-16k,
> gpt-4o, gpt-5.4 (+ blind Claude Opus 4.8 cross-vendor probe).
> **Provenance:** every number below is re-derived by replaying the released raw logs
> (`datasets/llm_inference_logs/*.json`) through the **live agnostic deterministic stack**:
> `scratch/canonical_rebuild.py` → `scratch/canonical_rows/*.json` → `scratch/canonical_tables.py`.
> Supersedes `reports/_superseded/*` (pre-agnostic, oracle-aided).

## Key facts
- **Dataset:** ASTRA v0.3 — 1,157 tasks × 6 personas = **6,942 rows**; 8 MCP domains;
  **194 tools** (grafana 43 / atlassian 37 / azure 27 / stripe 22 / mongodb 21 /
  notion 19 / hummingbot 15 / wikipedia 10). `match_tag`: 3,474 correct / 2,778 wrong / 690 null.
- **Stack:** SPIFFE/SPIRE → RBAC → ABAC (**6 rules**) → TRAC (agnostic `{domain}:{action}`,
  leak-free BM25 domain inference, corroborated-coverage rescue ≥ 4.0). Pure ALLOW/DENY
  (+ advisory alerts). Layer formerly named TS-PHOL is now **TRAC**.
- **Conventions:** A = security view (positive = illegitimate; default). B = ASTRA
  permissivity view (positive = correct; ASTRA replication only).
- **≈114K policy decisions** = 3 validation models × 6,942 × 4 ablation views (83,304) +
  6 selection configs (30,618).

## Validation — deterministic stack masks model variance (Convention A, n = 6,942)
The deterministic stack (E1) conditions only on the bundle/persona/inferred-domain, so it is
**identical across every model**.

| Model | Exp | F1 | Prec | Recall | SecFail | Admit |
|---|---|---|---|---|---|---|
| *all three* | **E1 (stack)** | **0.844** | 0.800 | 0.893 | **0.107** | **43.9%** |
| gpt-4o | E4 (LLM) | 0.760 | 0.789 | 0.733 | 0.268 | 50.9% |
| gpt-5.4 | E4 (LLM) | 0.482 | 0.856 | 0.335 | 0.665 | 85.8% |
| gpt-3.5-turbo-16k | E4 (LLM) | 0.652 | 0.880 | 0.518 | 0.482 | 82.3% |
| gpt-4o | FULL | 0.859 | 0.765 | 0.979 | 0.021 | 24.6% |
| gpt-5.4 | FULL | 0.849 | 0.786 | 0.925 | 0.075 | 36.6% |
| gpt-3.5-turbo-16k | FULL | 0.867 | 0.795 | 0.954 | 0.046 | 38.2% |

## Operating-point sweep (validation)
| OP | Configuration | F1 | SecFail | Admit |
|---|---|---|---|---|
| OP1 | TRAC only | 0.583 | 0.550 | 76.4% |
| OP2 | −RBAC | 0.746 | 0.314 | 61.6% |
| OP3 | full deterministic stack | 0.844 | 0.107 | 43.9% |
| OP4 | full stack + gate (gpt-4o / gpt-5.4 / gpt-3.5) | 0.859 / 0.849 / 0.867 | 0.021 / 0.075 / 0.046 | 24.6 / 36.6 / 38.2% |
| OP5 | LLM only (gpt-4o / gpt-5.4 / gpt-3.5) | 0.760 / 0.482 / 0.652 | 0.268 / 0.665 / 0.482 | 50.9 / 85.8 / 82.3% |

## Per-layer marginals (ΔSecFail = metric(Π) − metric(Π∖S); negative = layer helps)
| Mode | Config | F1 | SecFail | Marginal |
|---|---|---|---|---|
| Validation | E1 full stack | 0.844 | 0.107 | — |
| | E2 −RBAC | 0.746 | 0.314 | ΔRBAC = −0.207 |
| | E3 TRAC only | 0.583 | 0.550 | ΔABAC = −0.236 |
| Selection (gpt-5.4) | E1 full stack | 0.800 | 0.214 | — |
| | E2 −RBAC | 0.599 | 0.517 | ΔRBAC = −0.303 |
| | E3 TRAC only | 0.377 | 0.746 | ΔABAC = −0.229 |

First-firing attribution (model-independent): RBAC 82% / TRAC 15% / ABAC 4% of denials —
yet ABAC carries the largest marginal (−23.6pp). Attribution ≠ marginal necessity.

## Cross-vendor (identical stratified 45-task subset; 270 persona rows)
Deterministic floor (model-independent): **E1 F1 = 0.903, SecFail = 0.054, Admit = 32.7%**.

| Model | E4 F1 | E4 SecFail | FULL F1 | FULL SecFail |
|---|---|---|---|---|
| gpt-4o | 0.811 | 0.231 | 0.902 | 0.018 |
| gpt-5.4 | 0.549 | 0.606 | 0.904 | 0.036 |
| gpt-3.5-turbo-16k | 0.752 | 0.389 | 0.915 | 0.032 |
| claude-opus-4.8 (non-OpenAI, blind) | 0.704 | 0.457 | 0.921 | 0.018 |

Blind agreement with `match_tag`: 35/45 (15/15 correct, 10/20 wrong, 10/10 null).

## ASTRA LLM-ResM replication (Convention B, E4)
| Model | Acc | Prec | Recall | F1 |
|---|---|---|---|---|
| ASTRA Test (GPT-4o, per-tool AND) | 0.72 | 0.81 | 0.57 | 0.67 |
| Ours gpt-4o (per-bundle) | 0.661 | 0.740 | 0.497 | **0.595** |
| Ours gpt-3.5-turbo-16k | 0.736 | 0.704 | 0.815 | 0.756 |
| Ours gpt-5.4 | 0.620 | 0.583 | 0.839 | 0.688 |

Newer ≠ safer: gpt-3.5 (0.756) > gpt-5.4 (0.688) > gpt-4o (0.595).

## Selection + RA-ICL (gpt-5.4, Convention A, paired 4,512-row cohort)
| Variant | Exact | n | F1 | SecFail |
|---|---|---|---|---|
| No retrieval (paired) | 10.3% | 4,512 | 0.784 | 0.131 |
| + random RA-ICL | 33.3% | 4,512 | 0.901 | 0.072 |
| + BM25 RA-ICL | 39.1% | 4,512 | 0.905 | 0.066 |

ΔExact (BM25 − none) = +28.8pp (3.8×); ΔSecFail = −0.064 (BM25), −0.058 (random) — both
CIs exclude zero. Jaccard 0.343 → 0.624 (+82%). Selection baseline tool exact-match on
full correct slice = 11.4%.

## Corroborated coverage (rescue-bar sweep, gpt-4o validation)
| Rescue bar | SecFail | Admit | TRAC-unique catch | TRAC-unique over-deny |
|---|---|---|---|---|
| 0 (disabled) | 0.1063 | 43.3% | 580 | 242 |
| 5.0 | 0.107 | 43.5% | 578 | 238 |
| **4.0 (production)** | 0.1067 | **43.9%** | 578 | **231** |
| 3.0 | 0.108 | 44.1% | 573 | 226 |

4.0 is the knee: vs disabled it rescues 11 legit over-denials at 2 lost catches; dropping
to 3.0 rescues 16 but costs 7 catches.

## Substrate portability (OPA v1.18.0, rules-as-data parity)
RBAC 120 / ABAC 120 / TRAC 100 unique-bundle evaluations — **0 decision and 0 advisory
mismatches**; live `opa run --server` verified over the REST Data API.
`scratch/opa_parity_result.json`.
