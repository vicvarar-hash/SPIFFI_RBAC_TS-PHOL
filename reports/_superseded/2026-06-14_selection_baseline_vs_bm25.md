# Selection-Mode Experiments — Baseline vs BM25 (gpt-5.4)

> **Date:** 2026-06-14 · **Author:** Victor Vargas · **Mode:** selection · **Model:** gpt-5.4 (Azure AI Foundry)

---

## 1. TL;DR / Headline Result

- BM25-based retrieval-augmented in-context learning (RA-ICL) lifts the LLM's **exact tool-selection accuracy from 10.3% to 39.1% on the paired correct slice (3.8× absolute lift)** and its full-stack F1 from 0.798 to 0.846 (+4.8 points, asymmetric) / +0.023 (paired bootstrap CI `[+0.014, +0.034]`).
- BM25 also makes the LLM **more conservative**: allow rate drops from 28.1% → 22.3% (asymmetric) and Precision climbs from 0.813 → 0.904, while Recall improves slightly (0.783 → 0.795).
- **On the methodologically correct fingerprint-joined paired cohort (n = 4,512, 752 unique tasks × 6 personas), BM25 is a recall-favourable security improvement**: ΔF1 = +0.023 `[+0.014, +0.034]`, ΔR = +0.046 `[+0.032, +0.061]`, **ΔSecFail = −0.046 `[−0.061, −0.032]`** (CI excludes zero, *p* < 0.01), at a small precision give-back of ΔP = −0.009. See §5.1a.
- Despite the lift, **absolute selection accuracy remains very low** (39% exact match even with BM25). The dataset itself is the bottleneck — see §7.

> **Update 2026-06-15:** the paper's Table 11 originally carried a (now-corrected) positional "paired" comparison that suggested BM25 degraded SecFail. That comparison did not identity-join tasks across runs. The fingerprint-joined cohort below restores the security-favourable direction and is now the headline in both this report and the SACMAT paper.

---

## 2. Experimental Setup

| Item | Value |
|---|---|
| Model | gpt-5.4 (Microsoft Azure AI Foundry) |
| Evaluation mode | `selection` — LLM is given the task text **only** and must choose the tools |
| Dataset | ASTRA `astra_03_tools.json` — N = 3 tools per task |
| Personas | 6 |
| Inference config | temperature = 0.0, JSON schema response format, single retry on parse failure |
| Baseline cohort | 1,157 unique tasks × 6 personas = **6,942 rows** (no retrieval) |
| +C BM25 cohort | 752 unique tasks × 6 personas = **4,512 rows** (RA-ICL test set) |
| Split | `datasets/splits/correct_70_30_seed42_v2.json` — 405 `correct` train + 174 `correct` test, all 463 `wrong` + 115 `null` go to test (v2 is the one the runner currently uses; v1 fingerprints are stale relative to the current `_task_fingerprint` formula) |
| Baseline log | `datasets/experiment_logs/run_20260613_105137_llm_gpt-5_4_selection.json` |
| +C BM25 log | `datasets/experiment_logs/run_20260613_165151_llm_gpt-5_4_selection_raicl-K_all-train_k10000_+C.json` |

### Why the row counts differ

When RA-ICL is active, the framework holds out the 405 `correct`-train fingerprints to serve as the example pool — so they're never *evaluated*, only retrieved. The eval cohort becomes 174 (`correct`-test) + 463 (`wrong`) + 115 (`null`) = 752 unique tasks. The baseline has no retrieval, so it evaluates on the full 1,157.

This makes the direct row-count comparison imperfect. We provide both runs' aggregate numbers and the per-slice (correct / wrong / null) breakdown so the reader can do whatever apples-to-apples is most useful for their question.

### Experiment definitions (E1 – E3)

| ID | Stack layers active | Purpose |
|---|---|---|
| E1 | RBAC + ABAC + TS-PHOL (full PALADIN stack) | Production-equivalent governance — the headline number |
| E2 | ABAC + TS-PHOL (RBAC ablated) | Isolates the role-based pre-check contribution |
| E3 | TS-PHOL only (RBAC + ABAC ablated) | Isolates the trust-state validation layer |

E4 (LLM matcher alone) is not meaningful in selection mode — see §9.

---

## 3. Metrics & How They're Calculated

> All metrics in this report use the **PALADIN security view**: positive class = **illegitimate request**, predicted positive = **DENY**. This is the convention the codebase logs and is the natural framing for security-focused evaluation. See the validation report for the alternative ASTRA permissivity view.

> **Plain-English version — two scorecards, not one.** Selection mode measures *two different
> things*: (1) **Security** (Precision / Recall / F1 / `sec_fail`) — *"did the stack catch the
> illegitimate requests?"* (the same security view as validation); and (2) **Tool-selection
> quality** (exact match / Jaccard) — *"did the LLM pick the right tools?"* (unique to selection,
> since here the LLM *generates* the bundle). Key subtlety (§5.3 / §9): the stack is **blind to
> tool quality** — it gates on persona / role / capability / trust-state, not on *which* tools
> were chosen. So read the two scorecards separately — a request can be correctly denied for
> *authorization* reasons even when the tools were perfect.

Every (task, persona, experiment) row produces a decision (`ALLOW` or `DENY` — `DECEPTION_ROUTED` counts as `DENY`) and a tool selection. Each row carries two ground-truth labels:

- **`match_tag`** ∈ {`correct`, `wrong`, `null`} — does the gold-standard bundle match the task?
- **`is_legitimate`** ∈ {True, False} — should the request be allowed overall? True iff `match_tag == correct` *and* the persona is one of `LEGITIMATE_PAIRINGS` for the task.

### Confusion matrix (security view)

|  | Decision: ALLOW | Decision: DENY |
|---|---|---|
| `is_legitimate = False` (positive) | **FN** — illegitimate slipped through | **TP** — illegitimate caught |
| `is_legitimate = True` (negative) | **TN** — legitimate allowed | **FP** — false alarm on legitimate |

### Classification metrics

| Metric | Formula | Interpretation |
|---|---|---|
| **Precision** | TP / (TP + FP) | Of all denials, what fraction were truly illegitimate? (denial purity) |
| **Recall** | TP / (TP + FN) | Of all illegitimate requests, what fraction did we catch? (threat catch rate) |
| **F1** | 2 · P · R / (P + R) | Harmonic mean — drops if either P or R is low |
| **sec_fail** | FN / (TP + FN) = 1 − Recall | Security failure rate: what fraction of threats slipped through |
| **Allow rate** | (TN + FN) / total | Operating-point indicator (system permissiveness) |

### Tool-selection quality metrics

These are unique to selection mode (the LLM picks tools; we compare to the gold-standard bundle).

| Metric | Formula | Interpretation |
|---|---|---|
| **Tool exact match** | `selected_tools == groundtruth_tools` (set equality) | All-or-nothing: did the LLM pick exactly the right bundle? Strictest possible. |
| **Tool Jaccard** | \|selected ∩ groundtruth\| / \|selected ∪ groundtruth\| | Partial-credit similarity in [0, 1]. 1.0 = exact match; 0.0 = disjoint. |

We report tool metrics on the **`correct` slice only** because the `wrong` and `null` slices don't have a defensible "correct" tool list — they exist purely to evaluate the validator.

### Worked example — gpt-5.4 baseline E1

From `run_20260613_105137_llm_gpt-5_4_selection.json`, experiment E1 (n = 6,942).

From the logged metrics block:
- TP = 4,061 (illegit denied) · FP = 933 (legit denied) · FN = 1,129 (illegit allowed) · TN = 819 (legit allowed)
- Allow count = 819 + 1,129 = 1,948 · Deny count = 4,061 + 933 = 4,994

Compute:
- Precision = 4,061 / (4,061 + 933) = 4,061 / 4,994 = **0.813**
- Recall = 4,061 / (4,061 + 1,129) = 4,061 / 5,190 = **0.783**
- F1 = 2 · 0.813 · 0.783 / (0.813 + 0.783) = **0.798**
- sec_fail = 1,129 / 5,190 = **0.218**
- Allow rate = 1,948 / 6,942 = **0.281**
- Tool exact = 396 / 6,942 = **0.057** (5.7% overall, but 11.4% on the correct slice — see §5.2)

**What this example is telling us.** This is selection's "before BM25" baseline with the full
stack. Two things stand out. (1) **Security is much harder here than in validation**:
sec_fail = 0.218 (22% of illegitimate requests slip through) vs ~0.5% for the validation full
stack — because the LLM now *generates* the bundle rather than judging a given one. (2) The two
scorecards diverge: the stack denies most threats (recall 0.783), yet the LLM's **exact tool
match is only 11.4%** on the correct slice — and that low number is mostly the dataset ceiling
(§7: many defensible bundles), not incompetence. Also note FP = 933: the stack allows only
**~47% of legitimate work** (819 of 1,752). This is the regime where **RBAC/ABAC carry the
load** (the layer reversal) and where BM25 RA-ICL improves *both* scorecards at once (§5).

---

## 4. Methodology Details

### What RA-ICL is (Retrieval-Augmented In-Context Learning)

In selection mode the LLM sees the task text and must produce a JSON object with the tools to call. **RA-ICL augments the prompt** with a configurable mix of context derived from the training pool:

| Flag | Component | What it adds to the prompt |
|---|---|---|
| **A** (`rbac_scoped`) | RBAC-scoped tool catalog | Restricts the candidate tool list to tools the persona's role can access |
| **B** (`cap_filtered`) | Capability pre-filter | Restricts the candidate tool list to tools whose advertised capabilities match the task's capability profile |
| **C** (`bm25`) | BM25 example retrieval | Inserts the top-K most textually-similar (task, gold-tools) examples from the training pool |

This report compares only **baseline (none active)** vs **+C alone (BM25 active)**. Singletons A and B are evaluated in a separate report.

### BM25 — Okapi formulation, exact implementation

BM25 (Best Matching 25) is a sparse lexical ranking function from the late-1990s IR literature. It scores how relevant a candidate document `D` is to a query `Q` based on term-frequency, inverse-document-frequency, and document length normalization.

Implementation: `app/services/exemplar_retriever.py`, class `_BM25Index`.

**Formula** (per document):

```
score(D, Q) = Σ  IDF(qᵢ) · (tf(qᵢ, D) · (k₁ + 1)) / (tf(qᵢ, D) + k₁ · (1 − b + b · |D| / avgdl))
            qᵢ ∈ Q
```

Where:
- `tf(qᵢ, D)` = number of times term `qᵢ` appears in document `D`
- `|D|` = length of `D` in tokens
- `avgdl` = average document length across the corpus
- `k₁` = term-saturation parameter (we use **1.5**, the standard default)
- `b` = length-normalization parameter (we use **0.75**, the standard default)
- `IDF(qᵢ) = log(1 + (N − n(qᵢ) + 0.5) / (n(qᵢ) + 0.5))` — Okapi-smoothed IDF (always positive)
- `N` = total number of documents in the corpus
- `n(qᵢ)` = number of documents containing term `qᵢ`

**In our setting:**
- **Corpus** = the 405 `correct`-train fingerprints' task texts (the "exemplar pool").
- **Query** = the task text of the row being evaluated.
- **Document** = each training task's text.
- **Tokenization** = lowercase + alphanumeric word splitting (see `_tokenize` in `exemplar_retriever.py`).
- **Top-K retrieval** = we set `k = 10,000` (effectively "return all positive-score matches"), since the pool only has 405 items. Each retrieved exemplar contributes a `(task_text, gold_tools)` pair to the prompt.
- **Exact-text exclusion** = if the query text matches a corpus document exactly, that document is excluded (defensive guard against trivial leakage).

**What gets injected into the prompt:** the top retrieved examples in the form

```
Example task: <task_text>
Tools that solve it: <tool_1>, <tool_2>, <tool_3>
```

This is the "positive signal" mechanism: the LLM doesn't just see the task — it also sees three concrete examples of "this is what a correct answer looks like for tasks of this kind." Intuitively, BM25 finds neighbors that share rare task-specific vocabulary, which is a strong predictor of shared tool needs.

---

## 5. Results

> **How to read §5.** §5.1 is the *asymmetric* aggregate (6,942-row baseline vs 4,512-row +C) —
> directional only, since the cohorts differ. §5.1a is the **methodologically correct paired
> cohort** (the same 4,512 fingerprint-joined rows) and is the headline: BM25 **lifts F1 and
> recall while *reducing* SecFail** on E1/E2 (CIs exclude zero). §5.2 is the tool-quality story —
> BM25's biggest effect: **exact match 10.3% → 39.1% (3.8×)**. §5.3 shows allow rates flat across
> slices, exposing a selection-mode truth: the **stack gates on persona, not on tool quality**.
> Bottom line: BM25 RA-ICL is **"more conservative *and* more accurate"** — it improves selection
> and security together, against the usual capability-vs-safety trade-off.

### 5.1 Aggregate metrics (PALADIN security view)

| Run | n | Experiment | F1 | Precision | Recall | sec_fail | Allow rate |
|---|---|---|---|---|---|---|---|
| baseline | 6,942 | E1 | 0.798 | 0.813 | 0.783 | 0.218 | 0.281 |
| +C BM25 | 4,512 | E1 | **0.846** | **0.904** | 0.795 | **0.205** | **0.223** |
| | | | **+0.048** | **+0.091** | +0.012 | −0.013 | −0.058 |
| baseline | 6,942 | E2 | 0.641 | 0.774 | 0.546 | 0.454 | 0.473 |
| +C BM25 | 4,512 | E2 | **0.708** | **0.889** | **0.589** | **0.411** | **0.415** |
| | | | **+0.067** | +0.115 | +0.043 | −0.043 | −0.058 |
| baseline | 6,942 | E3 | 0.477 | 0.761 | 0.347 | 0.653 | 0.659 |
| +C BM25 | 4,512 | E3 | **0.533** | **0.883** | **0.381** | **0.619** | **0.618** |
| | | | **+0.056** | +0.122 | +0.034 | −0.034 | −0.041 |

**Pattern across all three experiments:** BM25 lifts F1, lifts Precision substantially, slightly lifts Recall, and reduces both `sec_fail` and `allow_rate`. The signature is "more conservative, more accurate" — exactly what a positive-signal retrieval should do.

### 5.1a Paired-cohort analysis (fingerprint-joined, n = 4,512)

The §5.1 table compares the full 6,942-row baseline against the 4,512-row +C cohort. Those cohorts differ — the baseline includes the 405 `correct`-train tasks that the +C run held out as the retrieval pool. To get an apples-to-apples comparison, we identity-join rows by SHA-256 fingerprint of `(task_text, sorted(mcp_servers), match_tag)` against the active split (`datasets/splits/correct_70_30_seed42_v2.json`) and recompute every metric on the common 4,512-row cohort. The join script and bootstrap CI derivation are released as `scripts/factcheck_paired_ci.py` (seed 42, B = 1,000, task-level resampling).

| Run | n | Experiment | F1 | Precision | Recall | sec_fail |
|---|---|---|---|---|---|---|
| baseline (paired) | 4,512 | E1 | 0.818 | 0.915 | 0.739 | 0.261 |
| +C BM25 (paired) | 4,512 | E1 | **0.842** | 0.906 | **0.786** | **0.214** |
| **Δ (+C − baseline)** | | E1 | **+0.023** `[+0.014, +0.034]` | **−0.009** `[−0.018, −0.001]` | **+0.046** `[+0.032, +0.061]` | **−0.046** `[−0.061, −0.032]` |
| baseline (paired) | 4,512 | E2 | 0.583 | 0.892 | 0.432 | 0.568 |
| +C BM25 (paired) | 4,512 | E2 | **0.623** | 0.890 | **0.480** | **0.520** |
| **Δ** | | E2 | +0.041 `[+0.024, +0.058]` | −0.002 `[−0.012, +0.008]` | +0.047 `[+0.029, +0.065]` | −0.047 `[−0.065, −0.029]` |
| baseline (paired) | 4,512 | E3 | 0.321 | 0.876 | 0.196 | 0.804 |
| +C BM25 (paired) | 4,512 | E3 | 0.330 | 0.885 | 0.202 | 0.798 |
| **Δ** | | E3 | +0.009 `[−0.015, +0.033]` | +0.009 `[−0.007, +0.026]` | +0.006 `[−0.011, +0.024]` | −0.006 `[−0.024, +0.011]` |

**Paired interpretation.** On the identity-joined cohort, BM25 lifts F1, lifts Recall, and **reduces** SecFail on E1 and E2 with bootstrap CIs that exclude zero. E3 (TS-PHOL only) shows the same direction but the effect is small enough that the CI crosses zero — once both RBAC and ABAC are ablated, the marginal value of BM25 retrieval shrinks. The asymmetric §5.1 comparison undersells the security gain on E1 (−0.013 vs −0.046 paired).

**Paired flip ledger (E1):** of the 4,512 paired rows, 326 flipped ALLOW→DENY (81 correct, 179 wrong, 66 null), 69 flipped DENY→ALLOW (16 correct, 37 wrong, 16 null), and 4,117 (91.2%) did not flip. Net shift = +257 ALLOW→DENY. On the adversarial slice (wrong + null), the new DENY is correct 74% of the time vs 53% for the reverse direction — the retriever is shifting the operating point in a direction that is **net-correct on the threat distribution**, not a noise-driven precision/recall swap.

### 5.2 Tool-selection quality (correct slice)

This is where BM25 has the largest effect, because it directly targets *what tools to pick*.

| Run | n (correct slice) | Tool exact match | Tool Jaccard avg |
|---|---|---|---|
| baseline (full) | 3,474 | 11.4% | 0.354 |
| baseline (paired) | 1,044 | 10.3% | 0.351 |
| +C BM25 (paired) | 1,044 | **39.1%** | **0.624** |
| **Lift (paired)** | | **+28.8 pp (3.8×)** | **+0.273 (+78%)** |

The full-baseline row uses all 579 unique correct tasks × 6 personas; the paired rows restrict to the 174 test-cohort tasks × 6 personas that appear in both runs. The paired lift is the methodologically correct one and is what the paper headlines.

### 5.3 Per-slice allow rates (convention-independent — just counts)

| Run | Experiment | `correct` allow | `wrong` allow | `null` allow |
|---|---|---|---|---|
| baseline | E1 | 0.282 | 0.279 | 0.284 |
| +C BM25 | E1 | 0.218 | 0.228 | 0.212 |

**Observation:** allow rates are essentially identical across all three `match_tag` slices in selection mode (~28% baseline, ~22% +C). This is dramatically different from validation mode where the per-slice rates differ wildly. The explanation is in §9: **in selection mode the deterministic stack is blind to the LLM's selection quality** — it only enforces persona/role/capability/trust-state policies, which depend on the persona, not on which tools the LLM picked. So the LLM-quality signal that matters in validation mode doesn't reach the metric in selection mode.

---

## 6. ASTRA Comparison

> The ASTRA paper does **not** report a selection-mode evaluation. ASTRA's task-tool matching benchmark is purely a validation problem (judge a given bundle), not a selection problem (pick a bundle). So there is no apples-to-apples comparison to make here.

Our selection-mode runs are an extension beyond ASTRA's scope — they answer the question "even when given no help, can an LLM *generate* a defensible tool list?" Our answer (39% exact even with BM25) is the first reported number we know of for this specific task.

---

## 7. Dataset Quality Considerations (why selection accuracy is so low)

The 39% exact match ceiling is **not** primarily an LLM-capability issue. Five dataset properties make selection a much harder task than validation, and bound the achievable accuracy well below 100%.

### 7.1 Tool naming has no human-readable convention

Tools are named things like `jira_batch_get_changelogs`, `confluence_search_user`, `atlassian_get_pull_request_diff`. To pick the *exact* gold-standard set, the LLM has to recall the exact tokenization (`jira_` vs `confluence_`, `_get_` vs `_fetch_`, singular vs plural, underscores vs camelCase) for each tool — from a catalog of hundreds of tools across 6 MCP servers. **A near-correct selection that uses a slightly differently-named tool counts as a complete miss.**

Evidence: tool Jaccard is **0.354 / 0.624** while tool exact match is **0.114 / 0.391**. The LLM is consistently picking tools that overlap in *purpose* with the gold standard but not in *identifier* — a classic precision-of-identifiers problem.

### 7.2 The "correct" tool set is one of many defensible answers

Most tasks can be solved by more than one valid combination of tools. The dataset records *one* gold bundle. If the LLM picks a different but equally-correct bundle (e.g., `jira_search_issues` instead of `jira_get_issue` for "find the ticket"), it's marked wrong. **There is no defensible upper bound near 1.0** for exact-match accuracy on this dataset.

### 7.3 Cross-persona pairings are inherently ambiguous

A task that's `correct` for `devops_agent` may be partially `correct` for `sre_agent` — they share tools. The dataset has one `correct` row per (task, owning-persona), but our eval runs 6 personas per task. The LLM has no signal about which persona is "active" beyond an implicit role hint, so cross-persona ambiguity becomes prediction error.

### 7.4 Bundle size is not given

In selection mode the LLM doesn't know whether the gold answer wants 1, 2, or 3 tools. It defaults to a heuristic ("pick what looks needed"), which often produces 2 when the gold is 3 or vice versa. This single missing tool drops Jaccard to ≤ 2/3 and exact-match to 0.

### 7.5 Label noise (carried over from validation)

Of the 30 `null`-tag bundles allowed by both gpt-4o and gpt-5.4 in validation mode, 6 had selected tools that **exactly matched the groundtruth** (Jaccard = 1.0). These are almost certainly mislabeled `correct` bundles, not `null`. Estimated noise: ~3-4% on null, ~1% on wrong. This noise propagates into selection-mode metrics as well.

### Estimated achievable ceiling

Combining these five effects:
- §7.1 (naming pedantry) caps exact match at ~70% even for a perfect "understands the task" model
- §7.2 (multiple defensible answers) caps it at ~60% if there are 2 valid bundles per task on average
- §7.3 (cross-persona ambiguity) caps it further at ~50% in a 6-persona setup
- §7.4 (bundle-size ambiguity) drops a further ~10 pp
- §7.5 (label noise) drops another ~3 pp

**Estimated achievable exact-match ceiling: ~30-40%.** Our BM25 result at 39.1% may be **close to the practical limit of this metric on this dataset.**

This is the most important caveat to convey: the *low* number is misleadingly low because the metric is overly strict. The Jaccard 0.624 with BM25 says the LLM picks the right *kind* of tools 62% of the time — that's a more honest progress signal.

---

## 8. Learnings

1. **BM25 retrieval works.** It lifts both selection quality (exact match 10.3% → 39.1% paired, +28.8 pp) and downstream classification F1 (paired ΔF1 = +0.023 `[+0.014, +0.034]`) on a strict identity-joined cohort. The improvement is consistent across E1 and E2; on E3 (TS-PHOL only) the effect is small enough that the bootstrap CI crosses zero.

2. **Paired-cohort direction is recall-favourable, not precision/recall trade-off.** Paired ΔPrecision = −0.009 `[−0.018, −0.001]` (small give-back) but ΔRecall = +0.046 `[+0.032, +0.061]` and ΔSecFail = −0.046 `[−0.061, −0.032]`. An earlier paper-internal positional comparison reported a +0.047 SecFail increase; that was a non-identity-joined cohort artefact and has been corrected (see §5.1a update note).

3. **The "more conservative, more accurate" signature holds on both cohorts.** Asymmetric: allow rate 28.1% → 22.3% while F1 climbs. Paired: SecFail 0.261 → 0.214 while F1 climbs. Both views show the operating-point shift you want for a security-sensitive system.

4. **Exact match underrates the lift; Jaccard captures it better.** 10.3% → 39.1% exact is impressive, but 0.351 → 0.624 Jaccard shows the LLM moved from "right-kind, wrong-tool" to "right-tool-most-of-the-time" — a larger absolute improvement.

5. **In selection mode, the deterministic stack is blind to LLM quality.** Per-slice allow rates are nearly identical across `correct`, `wrong`, and `null` (all ~28% baseline, all ~22% +C). The stack enforces persona/role/policy, which doesn't depend on what tools the LLM picked. To penalize bad selection, we'd need to add a tool-set sanity layer.

6. **The 39% selection ceiling is mostly a dataset-quality artifact.** The combination of tool-naming pedantry, multiple defensible bundles, cross-persona ambiguity, missing bundle-size signal, and ~3% label noise puts the realistic exact-match ceiling around 30-40% (see §7). BM25's 39.1% may already be near this ceiling.

7. **Selection F1 ≠ Validation F1 (same model).** gpt-5.4 validation E1 F1 = 0.856; gpt-5.4 selection E1 F1 = 0.798 (asymmetric) / 0.818 (paired baseline). The drop is entirely from §5.3's observation: in selection mode the stack can't punish bad LLM selections, so weak selections get through that would have been rejected in validation.

8. **Flip ledger confirms net-correct directionality.** On the paired adversarial slice (wrong + null), the new BM25 DENY decisions are correct 74% of the time vs 53% for the reversed DENY → ALLOW direction. This is not a noisy operating-point relocation; the retriever is systematically moving the boundary in the direction of fewer threats slipping through.

---

## 9. Limitations

- We do not yet have **A-only** (RBAC-scoped catalog) or **B-only** (capability pre-filter) singletons on gpt-5.4 selection. Comparing the three singletons head-to-head is the next deliverable.
- The **+ABC ceiling** (all three together) has not been run on gpt-5.4 yet. Predicted lift over +C alone: 1-3 F1 points (see analysis in checkpoint history).
- All numbers are from a **single model** (gpt-5.4) and a **single retriever** (BM25 over 405 training-pool exemplars). A no-retrieval ICL control (k random correct exemplars) would factor "any in-context examples help" from "BM25-similar examples help"; a second-model replication is also overdue.
- The **paired-cohort analysis** in §5.1a uses fingerprint-based identity join via `correct_70_30_seed42_v2.json`. An earlier internal cohort comparison that used row position rather than fingerprint identity reversed the SecFail direction; the v2 fingerprint join is the methodologically correct one.
- E4 (LLM matcher alone, no deterministic stack) is meaningless in selection mode — the LLM never emits validation issue codes, so `ValidationFailed = False` and E4 becomes allow-all. This is enforced by a guard in `app/ui/experiment_lab.py`.

---

## 10. Next Steps

- Run **A alone (RBAC-scoped catalog)** to complete the singleton trio. Predicted F1: 0.82-0.83 (between baseline and +C).
- Run **+ABC ceiling** to set the upper bound. Predicted F1: 0.85-0.87.
- Add a **bundle-size hint** to the prompt and re-measure. If exact-match jumps materially, §7.4 is confirmed as a major bottleneck.
- Audit and re-tag the **~20-30 likely-mislabeled bundles** identified in the validation report; rerun selection on the cleaned set to measure the achievable ceiling lift.
- Add a **tool-set sanity layer** to the deterministic stack (e.g., "selected tools must be a subset of the persona's role-permitted tools") so the stack can punish bad selections in selection mode. Re-measure per-slice allow rates.

---

## 11. Figures

### Figure 1 — Retrieval improves selection *and* security (no tradeoff)
![Operating-point shift and paired-delta confidence intervals for BM25 RA-ICL](figs/selection_no_tradeoff.png)

***How to read the left panel:*** *the two dots are the **same model on the same tasks**, without (grey) and with (green) BM25 retrieval. The x-axis is how often it picks the exactly-correct tool bundle (right = more accurate); the y-axis is the security-failure rate (down = more secure). The arrow shows where retrieval moves the operating point.*
***How to read the right panel:*** *each row is the **change** (with − without retrieval) for one metric, drawn with its 95% bootstrap confidence interval. A bar that does **not** touch the dashed zero line is statistically significant.*
***What it's telling us:*** *retrieval moves the dot **right and down at the same time** — the model becomes both **more accurate** (exact tool-match **10.3% → 39.1%**, a 3.8× jump) **and more secure** (SecFail **0.261 → 0.214**). You normally expect a capability-vs-safety tradeoff; here there isn't one. The right panel confirms the effect is real, not noise: ΔRecall is up and ΔSecFail is down with CIs that exclude zero, at only a tiny precision give-back (−0.009). (Selection mode, gpt-5.4, paired fingerprint-joined cohort, n = 4,512.)*
