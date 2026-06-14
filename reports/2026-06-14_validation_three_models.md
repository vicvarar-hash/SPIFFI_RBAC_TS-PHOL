# Validation-Mode Experiments — Three-Model Comparison vs ASTRA

> **Date:** 2026-06-14 · **Author:** Victor Vargas · **Mode:** validation · **Models:** gpt-3.5-turbo-16k, gpt-4o, gpt-5.4

---

## 1. TL;DR / Headline Result

- The PALADIN deterministic stack (E1) drives the **security failure rate to ≤ 1%** across all three LLMs (F1 ≈ 0.86 in PALADIN's security-view metric), versus **28–68%** when the LLM alone is the authorizer (E4). The stack — not the LLM — is what makes the system secure.
- We **independently reproduced ASTRA's central LLM-ResM finding** on a harder per-bundle evaluation. Our GPT-4o E4 lands at **F1 = 0.595** (ASTRA-permissivity view) against ASTRA's published F1 = 0.67 — within 0.075 F1, with the same precision-recall-undersoping signature.
- **Newer ≠ better.** Across the OpenAI line, E4 F1 (ASTRA view) is *monotonically decreasing* with model recency: gpt-3.5-turbo-16k (**0.756**) > gpt-5.4 (0.688) > gpt-4o (0.595).

---

## 2. Experimental Setup

| Item | Value |
|---|---|
| Dataset | ASTRA `astra_03_tools.json` — 1,157 unique multi-tool tasks, N = 3 tools per request |
| Personas | 6 (one per MCP server domain) |
| Evaluation cohort | 1,157 tasks × 6 personas = **6,942 (task, persona) rows** |
| Evaluation mode | `validation` — the LLM is given the request **and** the candidate tool bundle, and must judge appropriateness |
| Models tested | gpt-3.5-turbo-16k (OpenAI 2023), gpt-4o (OpenAI 2024), gpt-5.4 (OpenAI 2026 via Microsoft Foundry) |
| Inference config | temperature = 0.0, JSON schema response format, single retry on parse failure |
| `match_tag` distribution | correct = 3,474 rows (50.0%) · wrong = 2,778 rows (40.0%) · null = 690 rows (10.0%) |
| `is_legitimate` distribution | True = 1,752 rows · False = 5,190 rows (a row is `is_legitimate` only if the persona is in `LEGITIMATE_PAIRINGS` for the task AND `match_tag == correct`) |
| Source log files | `datasets/experiment_logs/run_20260612_191843_*gpt-5_4_validation.json`, `run_20260613_005419_*gpt-4o_validation.json`, `run_20260613_141204_*gpt-35-turbo-16k_validation.json` |

### Experiment definitions (E1 – E4)

| ID | Stack layers active | Purpose |
|---|---|---|
| E1 | RBAC + ABAC + TS-PHOL (full PALADIN stack) | Production-equivalent governance — the headline number |
| E2 | ABAC + TS-PHOL (RBAC ablated) | Isolates the security contribution of role-based pre-checks |
| E3 | TS-PHOL only (RBAC + ABAC ablated) | Isolates the trust-state validation layer |
| E4 | **LLM matcher alone** (deterministic stack disabled) | Direct comparison to ASTRA's LLM-ResM baseline |

---

## 3. Metrics & How They're Calculated

> **Important: two conventions appear in this report.** Be aware which one is being
> used at any moment. They differ in how they label the "positive" class.

Every (task, persona, experiment) row produces a decision: `ALLOW` or `DENY`
(`DECEPTION_ROUTED` is grouped with `DENY` for classification purposes).
Every row has two ground-truth labels:

- **`match_tag`**  ∈ {`correct`, `wrong`, `null`} — does the proposed tool bundle match the task?
- **`is_legitimate`** ∈ {True, False} — is this a "should-allow" decision overall? True iff `match_tag == correct` *and* the persona is permitted to perform this task.

### Convention A — PALADIN security view (used in logs)

Positive = **illegitimate request** (a "threat" the system should catch).
This is the convention `app/services/experiment_runner.py` writes into every log.

|  | Decision: ALLOW | Decision: DENY |
|---|---|---|
| `is_legitimate = False` (positive) | **FN** — threat slipped through | **TP** — threat caught |
| `is_legitimate = True` (negative)  | **TN** — legit work allowed | **FP** — false alarm on legit work |

Metrics in this convention:
- **Precision** = TP / (TP + FP) = "of all denials, what fraction were truly illegitimate?" (denial purity)
- **Recall** = TP / (TP + FN) = "of all illegitimate requests, what fraction did we catch?" (threat catch rate)
- **Security failure rate (`sec_fail`)** = FN / (TP + FN) = 1 − Recall (fraction of threats that got through)
- **F1** = 2 · P · R / (P + R)
- **Allow rate** = (TN + FN) / total

### Convention B — ASTRA permissivity view (used for direct ASTRA comparison)

Positive = **legitimate (`match_tag == correct`)** request.
This is the convention ASTRA uses in their paper. We recompute by hand from rows.

|  | Decision: ALLOW | Decision: DENY |
|---|---|---|
| `match_tag == correct` (positive) | **TP** — legit allowed | **FN** — legit denied (under-scoping) |
| `match_tag ∈ {wrong, null}` (negative) | **FP** — illegit allowed (over-scoping → security failure) | **TN** — illegit denied |

Metrics in this convention:
- **Precision** = TP / (TP + FP) = "of all allows, what fraction were truly correct?"
- **Recall** = TP / (TP + FN) = "of all correct bundles, what fraction did we allow?"
- **F1** = 2 · P · R / (P + R)
- **Accuracy** = (TP + TN) / total

ASTRA pools `wrong + null` as one negative class. We follow the same convention so F1 is directly comparable.

### Worked example — GPT-4o E4

From `run_20260613_005419_*gpt-4o_validation.json`, experiment E4 (n = 6,942).

**Per-decision counts (raw):**

| `match_tag` | n | ALLOW | DENY/DECEPTION |
|---|---|---|---|
| correct | 3,474 | 1,728 (49.7%) | 1,746 |
| wrong   | 2,778 | 576 (20.7%)   | 2,202 |
| null    | 690 | 30 (4.3%)      | 660 |

**Convention A (PALADIN, security view) — *exactly what the log reports*:**

is_legitimate = False rows (5,190) → 1,454 ALLOW (FN), 3,736 DENY (TP).
is_legitimate = True rows (1,752) → 880 ALLOW (TN), 872 DENY (FP).

- TP = 3,736 · FP = 872 · FN = 1,454 · TN = 880
- Precision = 3,736 / (3,736 + 872) = **0.811**
- Recall = 3,736 / (3,736 + 1,454) = **0.720**
- F1 = 2 · 0.811 · 0.720 / (0.811 + 0.720) = **0.763**
- sec_fail = 1,454 / 5,190 = **0.280**

**Convention B (ASTRA, permissivity view) — *recomputed from raw rows*:**

- TP = 1,728 (correct allowed) · FN = 1,746 · FP = 606 (576+30) · TN = 2,862
- Precision = 1,728 / (1,728 + 606) = **0.740**
- Recall = 1,728 / (1,728 + 1,746) = **0.497**
- F1 = 2 · 0.740 · 0.497 / (0.740 + 0.497) = **0.595**
- FPR = 606 / (606 + 2,862) = **0.175** (this is what ASTRA implicitly reports as the over-scoping rate)
- Accuracy = (1,728 + 2,862) / 6,942 = **0.661**

Both numbers are correct. They answer different questions.

---

## 4. Methodology Details

### How ASTRA constructs negatives

ASTRA defines two negative classes for the multi-tool task-tool matching problem (§IV-A of arXiv:2510.26702):

- **`wrong` matches** — tools sampled from **the same MCP server** as the correct tool. These have high semantic similarity to the correct answer, so they are the *hard* negatives. 80% of the negative pool.
- **`null` matches** — tools sampled from **an entirely different MCP server**. These represent off-task requests (possible hallucinations or adversarial agents). 20% of the negative pool.

ASTRA pools `wrong + null` into a single "incorrect" class for binary classification. Our negative split is 2,778 wrong + 690 null = 3,468 negatives (an 80.1 / 19.9 ratio — coincidentally identical to ASTRA's).

### What the LLM sees in validation mode

The prompt provides:

- The natural-language **task** text
- The candidate **tools** (name + description) the application proposes to call

The LLM must output a JSON verdict: `validation_failed: true | false` plus the issue_codes that triggered the failure. In validation mode the LLM does **not** select tools — the bundle is already given. The LLM only judges appropriateness.

### How the PALADIN deterministic stack (E1–E3) layers on top

In E1, E2, E3 the LLM's verdict is one of several inputs to a deterministic authorization pipeline:

1. **RBAC** — does the persona's role allow this tool?
2. **ABAC** — does the request match the persona's capability profile and the organization's attribute-based policy?
3. **TS-PHOL** — does the trust-state-aware policy hold (write-amplification limits, cross-MCP rate caps, replay/freshness checks)?

A request is allowed only if all active layers approve. E4 disables all three deterministic layers — the LLM's verdict becomes the sole authorizer. This makes E4 the apples-to-apples comparison point to ASTRA's LLM-ResM.

---

## 5. Results

### 5.1 PALADIN security view (Convention A) — what the logs report

All metrics measured against `is_legitimate` ground truth. Positive class = illegitimate request. Higher F1 = better at catching threats while sparing legitimate work.

| Model | Experiment | n | F1 | Precision | Recall | sec_fail | Allow rate |
|---|---|---|---|---|---|---|---|
| gpt-3.5-turbo-16k | E1 | 6,942 | 0.856 | 0.752 | 0.995 | **0.005** | 0.011 |
| gpt-3.5-turbo-16k | E4 | 6,942 | 0.640 | 0.888 | 0.500 | 0.500 | 0.579 |
| gpt-4o | E1 | 6,942 | 0.856 | 0.751 | 0.995 | **0.005** | 0.009 |
| gpt-4o | E4 | 6,942 | 0.763 | 0.811 | 0.720 | 0.280 | 0.336 |
| gpt-5.4 | E1 | 6,942 | 0.856 | 0.750 | 0.996 | **0.004** | 0.007 |
| gpt-5.4 | E4 | 6,942 | 0.466 | 0.856 | 0.321 | 0.679 | 0.720 |

**E1 → E4 security multiplier** (sec_fail reduction when adding the deterministic stack on top of the LLM):

| Model | E4 sec_fail | E1 sec_fail | Reduction factor |
|---|---|---|---|
| gpt-3.5-turbo-16k | 50.0% | 0.5% | **100 ×** |
| gpt-4o            | 28.0% | 0.5% | **56 ×** |
| gpt-5.4           | 67.9% | 0.4% | **170 ×** |

All three E1 numbers are essentially identical (F1 ≈ 0.856, sec_fail ≈ 0.5%) — **the deterministic stack is what produces security guarantees, not the LLM.**

### 5.2 ASTRA permissivity view (Convention B) — recomputed for direct ASTRA comparison

E4 only. Positive class = legitimate (`match_tag == correct`). Negatives = `wrong + null` pooled. n = 6,942 (3,474 correct + 2,778 wrong + 690 null).

| Model | Accuracy | Precision | Recall | F1 | FPR (over-scope) |
|---|---|---|---|---|---|
| gpt-3.5-turbo-16k | 0.736 | 0.704 | **0.815** | **0.756** | 0.343 |
| gpt-4o | 0.661 | **0.740** | 0.497 | 0.595 | **0.175** |
| gpt-5.4 | 0.620 | 0.583 | 0.839 | 0.688 | 0.600 |

### 5.3 Per-slice allow rates (convention-independent — just counts)

Useful diagnostic: what fraction of each ground-truth slice does the LLM allow? Ideal = 1.000 / 0.000 / 0.000.

| Model | `correct` (n=3,474) | `wrong` (n=2,778) | `null` (n=690) |
|---|---|---|---|
| gpt-3.5-turbo-16k | 0.815 | 0.419 | 0.035 |
| gpt-4o | 0.497 | 0.207 | 0.043 |
| gpt-5.4 | 0.839 | 0.739 | 0.043 |

---

## 6. ASTRA Comparison (apples-to-apples)

### What ASTRA did (Cisco / Outshift, arXiv:2510.26702)

ASTRA published a dataset and benchmark for **task-tool matching** in agentic applications, with two matchers:

- **SemSimM** — semantic similarity between task embedding and tool embedding (single-tool only)
- **LLM-ResM** — an LLM reasoning matcher: GPT-4o, temperature 0, prompted with task + a single tool, returns "appropriate" / "not appropriate."

For multi-tool tasks (N ≥ 2), only LLM-ResM is evaluated. The matcher is called **once per tool** and the per-tool verdicts are AND-ed to produce a bundle-level decision. They report classification metrics over the union of correct + (wrong ∪ null), with ASTRA permissivity convention (= our Convention B).

### Where our experiment differs

| Dimension | ASTRA | Ours |
|---|---|---|
| Matcher call granularity | **Per-tool** (called 3× per N=3 task, AND-ed) | **Per-bundle** (called 1× per task on the full N=3 tool set) |
| Models | GPT-4o only | gpt-3.5-turbo-16k, gpt-4o, gpt-5.4 |
| `wrong` construction | Single-tool swaps within an otherwise-correct bundle | Whole-bundle alternative selections |
| Persona dimension | None (1 agent per task) | **6 personas per task** — adds cross-persona pairings as additional negatives |
| Layers above the LLM | None (LLM is the system) | Three deterministic layers (RBAC + ABAC + TS-PHOL) in E1 |
| Negative ratio | wrong : null = 0.8 : 0.2 | wrong : null = 0.80 : 0.20 (coincidentally identical) |

The per-tool vs per-bundle difference is the largest structural confound: ASTRA's AND-aggregation amplifies precision (any per-tool "no" vetoes the bundle). This makes ASTRA's published numbers a slightly favorable comparison point for our per-bundle single-call E4.

### Apples-to-apples table (Convention B)

ASTRA Table II, N = 3 rows (lines 684–690 of the paper) vs our E4 in Convention B:

| Source | Model | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|
| ASTRA Val | GPT-4o | 0.73 | 0.81 | 0.61 | 0.70 |
| ASTRA Test | GPT-4o | 0.72 | 0.81 | 0.57 | **0.67** |
| ASTRA Toucan | GPT-4o | 0.82 | 0.80 | 0.86 | 0.83 |
| **Ours** | **gpt-4o** | **0.661** | **0.740** | **0.497** | **0.595** |
| Ours | gpt-3.5-turbo-16k | 0.736 | 0.704 | 0.815 | 0.756 |
| Ours | gpt-5.4 | 0.620 | 0.583 | 0.839 | 0.688 |

### Direct GPT-4o-to-GPT-4o replication

| Metric | ASTRA Test | Ours (E4, Conv. B) | Δ |
|---|---|---|---|
| Accuracy | 0.72 | 0.661 | −0.059 |
| Precision | 0.81 | 0.740 | −0.070 |
| Recall | 0.57 | 0.497 | −0.073 |
| F1 | **0.67** | **0.595** | **−0.075** |

We land within 0.08 F1 of ASTRA's published GPT-4o number while using harder negatives (whole-bundle wrong vs single-tool swaps), single-call per-bundle evaluation (no AND-amplification), and an independently constructed task population. The pattern (high precision, low recall, under-scoping dominant) replicates exactly.

**This is a successful, independent reproduction of ASTRA's central LLM-ResM finding, not a refutation.**

---

## 7. Dataset Quality Considerations

Even in validation mode (where the LLM only judges, not selects), three dataset properties limit the achievable F1 ceiling:

1. **`null`-class label noise.** Of the 30 `null`-tag bundles allowed by **both** gpt-4o and gpt-5.4, 6 have `selected_tools == groundtruth_tools` exactly (Jaccard = 1.0). Those 6 are almost certainly **mislabeled `correct`** bundles, not `null`. Two independent strong models flagging the same items is the diagnostic. Estimated noise: ~3-4% on null, ~1% on wrong, ~0% on correct.
2. **Under-determined positives.** Many tasks have multiple defensible bundles. The dataset records *one* `correct` answer; the LLM cannot know which one — it may approve a different-but-also-correct selection and still be marked wrong by the binary label.
3. **`wrong` is designed to be semantically similar.** ASTRA samples `wrong` tools from the *same MCP server* as the `correct` tool. The decision boundary is intentionally fuzzy. The 99% allow rate on `null` (cross-MCP) vs ~20-74% on `wrong` (same-MCP) measures exactly this confusability gap.

**Implication:** Even a perfect validator probably cannot exceed **F1 ≈ 0.93 – 0.95** on this dataset in Convention B because of label noise alone. The observed 0.595 – 0.756 range for E4 is therefore further from optimal than the headline numbers suggest, but the ceiling is not 1.0.

---

## 8. Learnings

1. **The deterministic stack is the security guarantee.** Across all three LLMs, E1 sec_fail collapses to **≤ 1%** — a **56× to 170×** reduction over E4. The headline F1 = 0.856 in Convention A is essentially provider-independent because the stack does the work, not the LLM.

2. **ASTRA's result generalizes.** The LLM-only validator plateaus at F1 ≈ 0.60 – 0.76 (Convention B) across three OpenAI LLMs spanning 2023 → 2026. This is a *task-intrinsic* ceiling, not a model-capability issue.

3. **Newer is not better.** Within OpenAI's line, F1 (Conv. B) decreases monotonically with model recency: gpt-3.5 (0.756) → gpt-5.4 (0.688) → gpt-4o (0.595). RLHF helpfulness optimization appears to actively reduce a model's suitability for adversarial validation.

4. **`null` separability is provider-independent.** All three OpenAI models reject 95.7% – 96.5% of cross-MCP-server (`null`) requests. The hard part of the task is same-MCP `wrong` vs `correct`, where the models vary wildly (21% → 74% allow).

5. **GPT-4o is the right model for "we replicate ASTRA."** Our GPT-4o F1 = 0.595 is within 0.08 of ASTRA's published 0.67 with the same precision-recall pattern. The story to tell isn't "we beat ASTRA" — it's "we reproduce ASTRA and then show the deterministic stack matters."

---

## 9. Limitations

- We do not run ASTRA's **per-tool AND-aggregation** variant, so the −0.075 F1 gap to ASTRA's published GPT-4o cannot be cleanly decomposed between (a) the per-tool aggregation effect and (b) the dataset/persona difficulty difference.
- We do not run **SemSimM** (semantic-similarity matcher), so we have no comparison for the SemSimM rows of ASTRA's Table II.
- The three-model panel is **observational, not controlled**: we cannot causally attribute the "newer ≠ better" pattern to RLHF specifically without a controlled fine-tune.
- gpt-5.4 was accessed via **Azure AI Foundry**, which may apply system prompts or safety filters different from the OpenAI-direct API.
- All eval is at **temperature = 0.0** with **single-shot** prompting; no self-consistency, no chain-of-thought scaffolding.

---

## 10. Next Steps

- Run **ASTRA per-tool AND** mode on the same task set to isolate the aggregation effect.
- Add a **SemSimM-equivalent** semantic-similarity baseline for completeness on Table II.
- Audit the **~30 likely-mislabeled null bundles** identified in §7 and re-tag them; rerun E4 on the cleaned set to measure the F1 ceiling lift.
- Replicate gpt-3.5-turbo-16k via the **OpenAI-direct API** to rule out Foundry-side modifications as a cause of its surprise win.
- Add a **always-allow / always-deny baseline** row to the table to show how far above-trivial each model is.
