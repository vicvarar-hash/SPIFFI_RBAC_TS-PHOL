# PALADIN Paper — Talking Cheat Sheet

## The one-sentence pitch
> *PALADIN is a six-stage policy pipeline that bolts deterministic, explainable access control onto LLM-driven MCP tool calls — and we show empirically that the pipeline, not the LLM, is what makes agentic systems safe.*

## Research questions

| # | RQ (plain English) | Where it's answered |
|---|---|---|
| **RQ1** | Can layered deterministic enforcement give agentic tool-use a *stable* security floor that doesn't depend on which LLM you plug in? | §8.1 three-model guarantee |
| **RQ2** | Which layer (RBAC, ABAC, TRAC) actually does the security work — and does that depend on whether the LLM *picks* tools or *judges* a candidate bundle? | §8.5 layer reversal + §8.6 per-domain map |
| **RQ3** | Does retrieval-augmented in-context learning (showing the LLM similar past examples) help or hurt security? | §8.7 RA-ICL paired comparison |
| **RQ4** | Are our results consistent with the existing ASTRA benchmark, run under the same model? | §8.3 ASTRA replication |
| **RQ5** | Are the standard "which layer denied?" attribution charts actually telling the truth about layer importance? | §8.8 attribution paradox |
| **RQ6** | What's the practical upper bound on tool-selection accuracy on this kind of dataset? | §8.9 dataset ceiling |

## The 6 contributions in plain English

**1. The system itself (PALADIN).** Six-stage pipeline: identity → transport → RBAC → ABAC → TRAC → execute. Plus a *dual-mode* evaluation methodology — testing both when the LLM *judges* a bundle (validation) and when the LLM *generates* the bundle (selection). Most prior work tests only one.
> *"We built a six-layer governance stack and a way to evaluate it from both angles — the LLM as judge and the LLM as planner."*

**2. Three models, same security floor.** gpt-3.5, gpt-4o, gpt-5.4 — three generations 2023–2026 — full stack: SecFail ≤0.5%, F1 ≈ 0.856. Three numbers statistically indistinguishable. Without the stack: F1 ranges 0.47 to 0.76.
> *"Plug in any of three OpenAI models and the stack gives you the same security number. Safety comes from the policy stack, not from picking the 'right' LLM."*
> Caveat: all three are OpenAI — cross-vendor replication is our top future-work item.

**3. We reproduced ASTRA.** Their gpt-4o F1 = 0.67; ours under their convention = 0.595 (gap of 0.075). Gap explained by single LLM call per bundle vs their 3-call AND-aggregated protocol. Same precision-recall signature.
> *"We can replicate the published benchmark within rounding, and we extend it from one model to three."*

**4. The dominant layer flips by mode.**
- **Validation** (LLM judges): TRAC does 25–110× the work of RBAC/ABAC.
- **Selection** (LLM generates): RBAC and ABAC dominate ~equally.
- In **7 of 8 domains**, TRAC alone in validation catches everything; only `mongodb` shows independent weight for the other layers.
> *"There's no single 'most important layer.' Which one matters depends entirely on the input distribution. Single-layer designs catastrophically fail in at least one mode."*

**5. RA-ICL helps security.** On a fingerprint-paired 4,512-row cohort, BM25 retrieval lifts F1 by +0.023, recall by +0.046, and *reduces* SecFail by −0.046 (CI excludes zero), at a tiny precision cost of −0.009. Tool-selection accuracy jumps from 10% to 39%.
> *"Showing the LLM similar past examples improves selection quality AND security. We report this on the methodologically right cohort — identity-joined task by task."*

**6. Two methodological lessons.**
- **Attribution paradox:** RBAC denies 66% of the time but contributes ≤1% to security improvement — it just *fires first*. "Who denied?" charts mislead.
- **Dataset ceiling:** Tool-selection exact-match maxes out around 30–40% on this dataset for reasons unrelated to model capability (naming pedantry, multiple defensible answers, missing bundle-size hints, label noise). 39% is near-ceiling.
> *"Don't trust 'who denied' charts as importance metrics, and don't read 40% exact match against an implicit 100% — read it against the real ceiling."*

## Likely questions & quick answers

| Question | Answer |
|---|---|
| *"Aren't you just reporting your own policy spec?"* | Yes, and we say so. Architectural results (stack-induced floor; layer reversal) hold across operating points; specific F1 and legitimate-allow numbers depend on *this* spec, which is fully released and tunable. |
| *"Why only OpenAI models?"* | Honest: budget and Azure Foundry credit access. Called out as central caveat; cross-vendor replication is future-work item #1. |
| *"How does this differ from Cedar / OPA / XACML?"* | Those are general policy engines without LLM-confidence reasoning, capability inference, or agentic-context awareness. PALADIN integrates SPIFFE identity, runtime risk/alignment reasoning, and ontological capability inference. |
| *"Why is legitimate-allow only 1.5–2.9%?"* | Conservative deny-leaning operating point chosen by *our* spec — not the architecture. Loosening alignment/coverage thresholds trades recall for allow-rate; tunable without rerunning LLM. |
| *"What's TRAC?"* | Typed, Staged, Predicate-Hierarchical Ordered Logic — a typed-fact-base rule engine with deterministic ordered evaluation, where rules compose via derived predicates. 12 rules total. Linear-time. Not a general theorem prover. |
| *"What's the headline number?"* | "Across three OpenAI models, full PALADIN stack drives SecFail ≤0.5% at F1 ≈ 0.856, while the LLM alone ranges from 0.47 to 0.76 — same models, very different outcomes." |

## 10-minute talk narrative

1. **Problem** — LLMs invoke tools autonomously over MCP; no native identity or policy enforcement.
2. **Approach** — Six-stage pipeline composing well-understood building blocks (SPIFFE, RBAC, ABAC) with a new typed predicate layer (TRAC).
3. **Evaluation novelty** — Two modes (validation + selection), three models, 3 years of LLM generations, 117,666 evaluations.
4. **Headline** — Stack gives same safety floor regardless of LLM. Within an OpenAI lineage, safety comes from the stack, not the model.
5. **Sharpening** — Different layers dominate different modes; in 7/8 domains TRAC alone in validation is enough.
6. **Bonus** — BM25 retrieval is a net safety win on the paired cohort.
7. **Methodology lessons** — First-firing attribution lies; selection-accuracy ceiling is dataset-bound near 40%.
8. **Limitations** — Single vendor lineage; single retriever; single policy spec; cross-vendor replication is the next experiment.

## Key numbers to memorize

| Metric | Value |
|---|---|
| Total evaluations | 117,666 |
| Tasks × personas | 1,157 × 6 = 6,942 per run |
| Models | gpt-3.5-turbo-16k, gpt-4o, gpt-5.4 |
| Full-stack F1 (all 3 models) | ≈ 0.856 |
| Full-stack SecFail | ≤ 0.5% (CI [0.003, 0.008]) |
| LLM-only F1 range | 0.466 (gpt-5.4) – 0.763 (gpt-4o) |
| SecFail reduction (LLM-only → full stack) | 56× to 170× |
| Legitimate-allow rate (E1) | 1.5%–2.9% across the three models |
| ASTRA replication gap (gpt-4o) | 0.075 F1 |
| RA-ICL tool exact-match lift | 10.3% → 39.1% (3.8×) |
| RA-ICL paired ΔSecFail | −0.046 [−0.061, −0.032] |
| TRAC dominance ratio (validation) | 25–110× over RBAC/ABAC |
| Domains where TRAC alone suffices | 7 of 8 |
| RBAC fire rate vs marginal contribution | 66% of denials, ≤1% ΔSecFail |
| Dataset ceiling (exact-match) | ~30%–40% |


---

# Glossary — Technical & Mathematical Terms

## A. Core architecture & ecosystem

| Term | Definition |
|---|---|
| **PALADIN** | The six-stage decision pipeline this paper introduces. Stages: identity → transport → RBAC → ABAC → TRAC → execute. |
| **MCP** (Model Context Protocol) | Anthropic-introduced open standard that lets LLM agents discover and invoke external tools/data sources. The deployment substrate PALADIN governs. |
| **MCP server** | A hosted endpoint exposing a set of tools for a single domain (e.g., `atlassian`, `mongodb`, `azure`). 8 servers used here. |
| **Tool** | A single callable function exposed by an MCP server (e.g., `jira_search_issues`). 194 tools total across 8 domains. |
| **Tool bundle** | An ordered set of tools (usually 3) selected to accomplish a task. The unit of decision in our evaluation. |
| **Agent** | An LLM-driven actor that selects and invokes tools to perform a task. Has an identity, role, and trust state. |
| **Persona** | A pre-defined agent profile combining role, clearance, department, and trust score. 6 personas evaluated per task. |
| **SPIFFE** | Secure Production Identity Framework For Everyone — open standard for cryptographic workload identity (SVIDs, trust domains). The identity layer in PALADIN's first stage. |
| **SPIRE** | The reference SPIFFE implementation: an attestation-driven SVID issuer. |
| **SVID** | SPIFFE Verifiable Identity Document — the cryptographic credential SPIFFE issues to a workload. |
| **Short-circuit composition** | Pipeline ordering where the first DENY decision terminates evaluation. Means an "earlier" layer can mask the marginal contribution of a "later" layer — drives the attribution paradox. |
| **Fail-secure** | When fact extraction or rule evaluation fails, the engine defaults to a conservative (DENY-like) outcome rather than allow. |

## B. The three governance layers

| Term | Definition |
|---|---|
| **RBAC** (Role-Based Access Control) | "Can role *R* invoke tool *T*?" Binary lookup against role-binding tables. Cheapest layer, fires first. |
| **ABAC** (Attribute-Based Access Control) | Policy gates over (subject, resource, action, environment) attribute tuples — e.g., clearance, time-of-day, compliance tier, incident state. 16 rules in our spec. |
| **TRAC** | Typed, Staged, Predicate-Hierarchical Ordered Logic — the typed-fact-base rule engine PALADIN introduces. 12 rules. Linear-time evaluation. |
| **Typed (in TRAC)** | Predicates operate on a fixed schema of booleans, enumerations, and reals — no type confusion. |
| **Staged (in TRAC)** | Facts are derived in a preceding extraction pass, *then* rule evaluation runs against the precomputed fact base. |
| **Predicate-Hierarchical (in TRAC)** | Rules can consume predicates derived by other rules, inducing a DAG over the predicate signature (e.g., `ElevatedRisk` is derived by one rule and consumed by alignment/isolation rules). |
| **Ordered Logic (in TRAC)** | Rules fire in a deterministic, policy-declared order with short-circuit denial — decisions are a total function of the fact base and policy text. |
| **Deception routing** | A graduated-enforcement action layered atop TRAC: instead of outright DENY, suspicious-but-borderline write requests are routed to a throttled execution path. Counted as DENY in security metrics. |

## C. TRAC rule predicates (the 12 rules)

| Priority | Rule name | What it checks |
|---|---|---|
| 120 | `task_bundle_domain_mismatch` | Bundle's domain differs from task's domain. |
| 115 | `severe_domain_mismatch_override` | Re-engages domain check in selection mode when alignment is also low. |
| 110 | `validation_failure_denial` | Validator marked critical failure AND alignment is low. |
| 105 | `hard_capability_violation` | A mission-critical capability is missing from the bundle. |
| 102 | `mutation_without_context_read` | High-risk write not preceded by a read (verify-before-mutate). |
| 100 | `destructive_write_prevention` | Destructive op (delete/drop) without accompanying read verification. |
| 95 | `bundle_irrelevant_strong` | Validator marked bundle irrelevant AND alignment is low. |
| 80 | `elevated_risk_detection` | Derives `ElevatedRisk` predicate for downstream rules (ALLOW action). |
| 70 | `multi_domain_low_alignment` | Multi-domain bundle whose task alignment is weak. |
| 65 | `partial_capability_coverage` | Bundle covers <50% of the task's required capabilities. |
| 60 | `low_task_alignment` | Bundle is semantically irrelevant to the task (strict, <0.30). |
| 60 | `low_task_alignment_with_tolerance` | Same, but selection-tolerance mode (<0.25). |

## D. Evaluation methodology

| Term | Definition |
|---|---|
| **Validation mode** | Evaluation setup where a candidate tool bundle exists and the LLM judges whether to ALLOW or DENY it. Adversarial bundles are pre-mixed (80% same-MCP `wrong`, 20% cross-MCP `null`). |
| **Selection mode** | Evaluation setup where the LLM generates the tool bundle from scratch given only the task text; the generated bundle is then run through the deterministic pipeline. |
| **Convention A (PALADIN security view)** | Positive class = illegitimate request, predicted positive = DENY. Used for SecFail / security metrics. |
| **Convention B (ASTRA permissivity view)** | Positive class = legitimate request, predicted positive = ALLOW. Used only for ASTRA replication. |
| **E1** | Full stack: RBAC + ABAC + TRAC all active. The production-equivalent setting. |
| **E2** | RBAC ablated; only ABAC + TRAC. Isolates RBAC's marginal contribution. |
| **E3** | RBAC + ABAC ablated; only TRAC. Isolates TRAC alone. |
| **E4** | All deterministic layers ablated; LLM matcher alone. Used as the "no-policy-stack" baseline in validation; degenerates to allow-all in selection. |
| **Ablation** | Removing one or more pipeline components and re-running the same evaluation to measure that component's marginal contribution. |
| **Marginal contribution / Δ** | The change in a metric when a component is ablated. E.g., `ΔRBAC = F1(E1) − F1(E2)`. |
| **Attribution (first-firing)** | The fraction of denials a given layer fires. Distinct from marginal contribution — the attribution paradox is that they can disagree by orders of magnitude. |

## E. Classification metrics (security view)

| Metric | Formula | Interpretation |
|---|---|---|
| **TP** | Pred=DENY, Actual=illegitimate | Threat correctly denied. |
| **TN** | Pred=ALLOW, Actual=legitimate | Legitimate request correctly allowed. |
| **FP** | Pred=DENY, Actual=legitimate | False alarm (legitimate denied). |
| **FN** | Pred=ALLOW, Actual=illegitimate | Threat slipped through. |
| **Precision** *P* | TP / (TP + FP) | Of all denials, what fraction were truly illegitimate? Denial purity. |
| **Recall** *R* | TP / (TP + FN) | Of all illegitimate requests, what fraction did we catch? Threat-catch rate. |
| **F1** | 2·P·R / (P + R) | Harmonic mean of P and R. Drops if either is low. |
| **SecFail** | FN / (TP + FN) = 1 − R | Fraction of true threats that slipped through. PALADIN's primary security metric. |
| **Accuracy** | (TP + TN) / total | Overall correctness. Reported for ASTRA replication only. |
| **Allow rate** | (TN + FN) / total | System permissiveness — useful as an operating-point indicator. |
| **Legitimate-allow rate** | TN / (TN + FP) | Fraction of *legitimate* requests the stack lets through. The "operating cost" metric (1.5–2.9% in our spec). |

## F. Tool-selection quality metrics (selection mode only)

| Metric | Formula | Interpretation |
|---|---|---|
| **Tool exact match** | `selected == groundtruth` (set equality) | All-or-nothing: did the LLM pick exactly the gold bundle? |
| **Tool Jaccard** | \|*selected* ∩ *gold*\| / \|*selected* ∪ *gold*\| | Partial-credit similarity in [0, 1]. 1.0 = exact match, 0.0 = disjoint. |

## G. Statistical / inference terms

| Term | Definition |
|---|---|
| **Bootstrap (task-level)** | Resample the unique tasks with replacement *B* = 1,000 times; for each resample, recompute the metric on all 6 personas of the sampled tasks. The 2.5/97.5 percentiles of the resampled distribution are the 95% CI. Used because rows within a task are correlated. |
| **95% CI** | The interval inside which 95% of bootstrap-resampled metric estimates fall. "CI excludes zero" means the effect is statistically distinguishable from no-effect at *p* ≈ 0.05. |
| **Paired bootstrap** | Same as above, but resampling the same tasks for *both* baseline and treatment in each iteration. Reduces variance of the Δ estimate. |
| **Fingerprint join** | Identity-based join across runs using `SHA-256(task_text \| sorted(mcp_servers) \| match_tag)[:16]` as the row key. Necessary because the `task_idx` log field is per-run-positional. |
| **Paired cohort** | The subset of rows present in *both* runs being compared, identity-joined via fingerprint. The methodologically correct unit for RA-ICL Δ statistics. |
| **Asymmetric cohort** | A non-identity-joined comparison where baseline and treatment runs evaluate different row sets. Useful as a cohort-shift diagnostic but not as a paired statistical test. |
| **Flip ledger** | A per-row accounting of how ALLOW/DENY decisions changed between baseline and treatment on the paired cohort, broken out by `match_tag` (correct/wrong/null). |

## H. Alignment and capability terms

| Term | Definition |
|---|---|
| **Domain** | High-level grouping of related tools (one per MCP server). 8 domains: `atlassian`, `azure`, `aws`, `gcp`, `okta`, `mongodb`, `postgres`, `notion`. |
| **Capability** | An abstract function a tool performs (e.g., `LogAnalysis`, `MetricsQuery`). 28 source capabilities, 22 abstract, organised in an ontology. |
| **Capability ontology** | A DAG over capabilities with 40 implication edges (e.g., `LogAnalysis ⇒ LogQuery`). Used for ontological enrichment of bundle coverage. |
| **Hard capability** | Mission-critical capability whose absence triggers immediate DENY. |
| **Soft capability** | Advisory capability whose absence reduces alignment score but does not independently DENY. |
| **Coverage score** | Fraction of the task's required capabilities the bundle satisfies (after ontological expansion). Threshold: <0.5 → `partial_capability_coverage` DENY. |
| **Alignment score** | Weighted sum *(0.4·domain + 0.4·capability + 0.2·semantic)* of bundle–task fit. Drives several TRAC rules. |
| **Domain alignment** | Boolean: does the bundle's dominant domain match the task's domain? |
| **Capability alignment** | Ratio of required capabilities covered by the bundle (post-ontological expansion). |
| **Semantic alignment** | Cosine similarity between task-text and bundle-text embeddings. |

## I. RA-ICL (Retrieval-Augmented In-Context Learning)

| Term | Definition |
|---|---|
| **RA-ICL** | Augmenting the LLM prompt with retrieved (task, gold-tools) example pairs from a training pool, so the LLM has concrete demonstrations of correct selections. |
| **Exemplar pool** | The 405 `correct`-tagged training tasks held out from evaluation specifically to serve as retrieval targets. |
| **Retriever** | The component that scores and ranks exemplar candidates against a query task. We use BM25. |
| **BM25** (Best Matching 25) | Okapi sparse lexical ranking function from 1990s IR literature. Score = Σ IDF(qᵢ) · tf-saturation · length-normalisation. |
| **k₁** | BM25 term-frequency saturation parameter. We use 1.5 (standard default). |
| **b** | BM25 document-length normalisation parameter. We use 0.75 (standard default). |
| **IDF** (Inverse Document Frequency) | log(1 + (N − n + 0.5)/(n + 0.5)) — Okapi-smoothed, always positive. |
| **top-K** | Number of exemplars returned per query. We set K = 10,000 (effectively "rank all 405 exemplars by score"). |
| **Variants A / B / C** | Three RA-ICL prompt augmentations: A = RBAC-scoped catalog, B = capability-prefilter catalog, C = BM25 exemplars. This paper reports baseline vs +C. |

## J. Dataset (ASTRA v0.3)

| Term | Definition |
|---|---|
| **ASTRA** | Public benchmark dataset for LLM-as-tool-matcher evaluation. We use v0.3 ("astra_03_tools"). 1,157 tasks. |
| **ASTRA LLM-ResM** | The published baseline in the ASTRA paper: LLM-as-Resource-Matcher under per-tool AND aggregation. Our Convention-B replication target. |
| **Task** | A natural-language description of what an agent needs to do. |
| **match_tag** | Per-task label: `correct` (gold bundle solves it), `wrong` (gold bundle is wrong-domain same-MCP), `null` (gold bundle is cross-MCP nonsense). |
| **correct slice** | The 579 (×6 personas = 3,474 rows) tasks tagged `correct`. The only slice with a defensible "right answer" for tool-quality metrics. |
| **wrong slice** | The 463 (×6 = 2,778 rows) tasks tagged `wrong`. Adversarial: bundle is plausible but mis-scoped. |
| **null slice** | The 115 (×6 = 690 rows) tasks tagged `null`. Adversarial: bundle is cross-domain nonsense. |
| **is_legitimate** | Per-row boolean: TRUE iff `match_tag == correct` AND persona is in the task's `LEGITIMATE_PAIRINGS`. The actual class label for security metrics. |
| **Split (70/30)** | Stratified random partition of `correct` tasks into 405 train + 174 test (`correct_70_30_seed42_v2.json`). All `wrong` and `null` go to test. |

## K. Inference & reproducibility

| Term | Definition |
|---|---|
| **Temperature** | LLM sampling parameter; 0.0 means deterministic argmax decoding. We use 0.0 for all experiments. |
| **JSON-schema response format** | Constrained generation mode that forces the LLM to emit valid JSON matching a supplied schema. |
| **Inference retry** | Single retry on JSON parse failure. We measured zero unrecoverable failures across all 117,666 evaluations. |
| **Foundry** | Microsoft Azure AI Foundry — the hosted inference endpoint used to access gpt-5.4. May apply system prompts or safety filters not present in the OpenAI-direct API. |
| **Configuration commit hash** | Git SHA of the policy/threshold configuration frozen before any experimental run, recorded in the released artefact. |

## L. Notational conventions used in the paper

| Symbol | Meaning |
|---|---|
| *n* | Sample size (rows) |
| *N* | Document corpus size (BM25) |
| *B* | Bootstrap resample count (=1,000) |
| *c* | LLM confidence score (note: no rule actually gates on this in the released policy) |
| *T* | Tool bundle |
| ⊻ ⊥ ⊤ | Logical XOR / false / true (used in TRAC predicates) |
| ⇒ | Capability implication (in ontology) |
| Δ*X* | Change in metric *X* between two settings (e.g., ΔF₁ = F₁(treatment) − F₁(baseline)) |
| [*a*, *b*] | Bootstrap 95% CI |
| × | Reduction multiplier (e.g., "56×" = SecFail dropped by a factor of 56) |
| pp | Percentage points (additive on a percent scale) |
