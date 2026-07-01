# Fact-Check Report — `paper/main_acm.tex` vs System + Logs
**Date:** 2026-06-15
**Scope:** Every numerical claim, architectural assertion, and policy parameter in `paper/main_acm.tex`, cross-checked against the live codebase (`app/services/*`, `policies/*`) and the 5 released raw experiment logs (`datasets/experiment_logs/run_*.json`).
**Reproducibility:** All numbers in this report were re-derived by `scripts/factcheck_paper.py` and `scripts/factcheck_paired2.py`.

---

## TL;DR

| Severity | Count | Examples |
|---|---|---|
| ✅ Verified exact | 80%+ of numeric claims | Tables 5–10, §8.7 read/write split, App D confusion matrices, ASTRA replication, denial attribution, deception precision |
| 🟡 Minor (rounding, slight mismatch) | 4 | Reduction multipliers, "≈2.2% legit-allow" hides 1.5–2.9% spread |
| 🔴 **Critical** | 5 | **Table 11 paired analysis is wrong (retraction is itself wrong)**, TS-PHOL rule table lists 3 rules that don't exist + omits 5 that do, §7.10 thresholds wrong for 3 of 5 parameters, deny-flip ledger numbers don't reproduce |

The architecture claims, headline numbers (Tables 5, 6, 7, 8, 9, 10), and ASTRA replication are all solid. **The §8.7 paired RA-ICL retraction — the centerpiece of contribution #5 and conclusion #4 — does not reproduce from the logs and actually reverses sign when computed correctly.**

---

## ✅ VERIFIED EXACT (numbers reproduce from logs to ≥4 decimals)

### Architecture / dataset
- **8 MCP domains** in `domain_capability_ontology.json` ✓ (paper §5.4)
- **40 capability entailment edges across 28 source capabilities** ✓ (paper §5.4 — "40 entailment relationships across 28 source capabilities spanning 8 domains")
- **194 unique tools across 8 domains** ✓ (paper Table 16: 43/37/27/21/22/19/15/10 = 194 — matches `astra_03_tools.json` exactly)
- **1,157 ASTRA tasks** ✓
- **match_tag breakdown 3,474 correct / 2,778 wrong / 690 null** ✓ (paper §7.3)
- **80.1/19.9 wrong-to-null ratio** ✓ (2778/(2778+690) = 80.1%)
- **Table 1 per-domain task counts (246/211/156/135/130/115/93/71)** ✓ — caveat: these are by `input.mcp_servers[0]` (assigned-bundle domain), not by `groundtruth`. Worth a footnote in the paper.
- **6 personas × 1157 = 6942 evaluation rows** ✓
- **1,752 legitimate rows** ✓ (matches `is_legitimate` derivation: correct AND persona ∈ LEGITIMATE_PAIRINGS)
- **405 train / 174 test / 578 other fingerprints** in `correct_70_30_seed42_v2.json` ✓ — NOTE: paper §7.4 says "405 task fingerprints" and "RA-ICL cohort = 174 + 463 + 115 = 752" — the 578 in the v2 file matches 463 wrong + 115 null = 578 ✓
- **Alignment weights (0.4 / 0.4 / 0.2)** in `decision_engine.py:320` ✓
- **BM25 (k1=1.5, b=0.75, k=10000)** in `exemplar_retriever.py` ✓ (verified in earlier sessions)

### Results — Table 5 (validation E1 vs E4, Convention A)
All 6 cells exact:

| Model | Exp | Paper F1 | Actual F1 | Paper SF | Actual SF |
|---|---|---|---|---|---|
| gpt-3.5-turbo-16k | E1 | 0.857 | **0.8565** ✓ | 0.005 | **0.0054** ✓ |
| gpt-3.5-turbo-16k | E4 | 0.640 | **0.6400** ✓ | 0.500 | **0.4998** ✓ |
| gpt-4o            | E1 | 0.856 | **0.8557** ✓ | 0.005 | **0.0052** ✓ |
| gpt-4o            | E4 | 0.763 | **0.7626** ✓ | 0.280 | **0.2802** ✓ |
| gpt-5.4           | E1 | 0.856 | **0.8555** ✓ | 0.004 | **0.0040** ✓ |
| gpt-5.4           | E4 | 0.466 | **0.4665** ✓ | 0.679 | **0.6794** ✓ |

### Results — Table 6 (Convention B, ASTRA replication, E4)
All 3 models exact to 3 decimals:

| Model | Paper (Acc/P/R/F1) | Actual (Acc/P/R/F1) |
|---|---|---|
| gpt-3.5-turbo-16k | 0.736 / 0.704 / 0.815 / 0.756 | 0.7364 / 0.7045 / 0.8152 / **0.7558** ✓ |
| gpt-4o            | 0.661 / 0.740 / 0.497 / 0.595 | 0.6612 / 0.7404 / 0.4974 / **0.5950** ✓ |
| gpt-5.4           | 0.620 / 0.583 / 0.839 / 0.688 | 0.6197 / 0.5834 / 0.8394 / **0.6884** ✓ |

ASTRA's published gpt-4o F1 = 0.67. Δ = -0.075 ✓ (paper claim exact).

### Results — Table 7 (gpt-5.4 E4 per-domain allow rates)
All 8 rows exact ✓ (wikipedia 100% wrong / 10.5% null; grafana 91.6% / 0%; atlassian 79.3% / 23.1%; etc.)

### Results — Table 8 (per-layer Δ in validation)
All 9 Δ values match within rounding, all 3 ratios match within ±2:

| Model | Paper TS×RBAC | Actual ratio |
|---|---|---|
| gpt-3.5  | 47× | **46.1×** ≈✓ |
| gpt-4o   | 25× | **26.3×** ≈✓ |
| gpt-5.4  | 110× | **107×** ≈✓ |

### Results — Table 9 (per-domain dominance, gpt-4o)
All 8 rows exact ✓. 7 zero deltas, mongodb +0.038/+0.052 ✓ matches paper +0.038/+0.052.

### Results — Table 10 (denial attribution)
All 9 cells exact (RBAC 4536 across all 3 models, ABAC 294, TS-PHOL 2034/2047/2064) ✓

### Results — §8.7 read/write asymmetry (gpt-4o E1)
- Paper: write F1 0.841, SF 0.002; read F1 0.869, SF 0.008
- Actual: write F1 **0.8407**, SF **0.0021**; read F1 **0.8692**, SF **0.0079** ✓ all exact

### Results — Deception precision (§8.10)
- Paper claims E1 ≈ 0.44; E3 ≈ 0.73 across all 3 models
- Actual: E1 = 0.435 / 0.443 / 0.447; E3 = 0.729 / 0.730 / 0.731 ✓ all exact

### Results — App D Table 19 (full confusion matrices)
All values reconcile: sums match, P/R/F1 match. Spot-checked gpt-4o E1: ALW 65 ✓, DENY 6624 ✓, DEC 253 ✓, TP/FP/TN/FN 5163/1714/38/27 ✓.

### Total evaluations (§7.6)
- Paper: 117,666
- 3 models × 4 exp × 6942 = 83,304
- + 1 model × 3 exp × 6942 = 20,826
- + 1 model × 3 exp × 4512 = 13,536
- Total = **117,666** ✓

---

## 🟡 MINOR ISSUES

### M1. E4→E1 SecFail reduction multipliers slightly off (Table 5 caption / contribution #2)
- Paper: "56× for gpt-4o, 100× for gpt-3.5-turbo-16k, 170× for gpt-5.4"
- Actual: **54× / 93× / 170×** (computed as `SF(E4)/SF(E1)` from exact raw counts)
- Differences come from rounding the SF values before dividing. Fine to keep as "≈" or report 4-decimal SF in the table and re-derive ratios from those.

### M2. Legitimate-allow rate (§8.1, contribution #2)
- Paper: "≈$2.2\%$ legitimate-allow rate"
- Actual per-model: gpt-3.5 = **2.85%**, gpt-4o = **2.17%**, gpt-5.4 = **1.54%**
- The 2.2% figure is the gpt-4o value, not a panel-wide constant. Better wording: "1.5%–2.9% across the panel, ≈2.2% on gpt-4o" or give per-model in App D.

### M3. App D Table 19 "ALW" column for gpt-4o E1 shows 65, but paper text §8.1 says "≈38 are allowed under E1"
- Reconcile: 65 total allows = 27 illegit-allowed (FN) + 38 legit-allowed (TN). The "≈38" refers to legit-allowed only. Make the text explicit: "≈38 of the 1,752 legitimate rows are allowed (TN)" so readers don't confuse it with the 65 total allows in Table 19.

### M4. §8.4 paired-CIs and §8.4 ABAC magnitudes
- Paper Table 8 lists ΔABAC SecFail of -0.014/-0.012/-0.009 across models with CIs.
- Actual: -0.0139 / -0.0118 / -0.0094 ✓ — values match. CI re-derivation (1000 bootstrap) not done in this fact-check; the point values match so CIs likely fine. *(Recommend the paper's analysis script be released; the artifact section promises this.)*

---

## 🔴 CRITICAL ISSUES

### C1. **Table 3 (TS-PHOL Rule Base) — 3 invented rules, 5 real rules omitted, 1 false attribution**

Paper Table 3 lists **10 rules**, but `policies/tsphol_rules.yaml` defines **12 rules** with different names and priorities.

| Paper Table 3 | Actually in tsphol_rules.yaml |
|---|---|
| 130 low_confidence_write_prevention | **DOES NOT EXIST** |
| 125 high_risk_write_confidence_safeguard | **DOES NOT EXIST** |
| 120 task_bundle_domain_mismatch | ✓ 120 |
| — | 115 severe_domain_mismatch_override (missing) |
| 110 validation_failure_denial | ✓ 110 |
| 105 hard_capability_violation | ✓ 105 |
| — | 102 mutation_without_context_read (missing) |
| 100 destructive_write_prevention | ✓ 100 |
| — | 95 bundle_irrelevant_strong (missing) |
| 80 elevated_risk_detection | ✓ 80 |
| 70 elevated_risk_confidence | **DOES NOT EXIST** (actual rule at 70 is `multi_domain_low_alignment`) |
| — | 65 partial_capability_coverage (missing) |
| 60 low_task_alignment | ✓ 60 |
| 60 low_task_alignment_with_tolerance | ✓ 60 |

**Impact:** Anyone trying to re-run the released artifact will see different rule names in the audit trail than the paper claims. Reviewers checking reproducibility will catch this. The denial-attribution numbers in Table 10 (2034/2047/2064 TS-PHOL denials) are correct because they aggregate over whatever rules actually fired — but the paper's narrative about confidence-gating rules (priorities 130, 125, 70) is unsupported because those rules don't exist in the released policy file.

**Fix:** Regenerate Table 3 by running:
```python
import yaml; r = yaml.safe_load(open('policies/tsphol_rules.yaml'))
for x in sorted(r, key=lambda x:-x['priority']): print(x['priority'], x['then'], x['rule_name'])
```
Update any narrative that references confidence-gating rules.

### C2. **§7.10 (Threshold and Parameter Provenance) — 3 of 5 thresholds wrong**

| Paper §7.10 claim | Actually in policies |
|---|---|
| Alignment weights (0.4, 0.4, 0.2) | ✓ `decision_engine.py:320` |
| **c < 0.75 write / c < 0.85 high-risk write / c < 0.90 elevated-risk** | **No confidence-gating rules exist in `tsphol_rules.yaml`** |
| **Task alignment < 0.4 (strict); < 0.3 (tolerance)** | **Actual: strict 0.3, tolerance 0.25** (`low_task_alignment` & `low_task_alignment_with_tolerance`) |
| **Coverage score threshold 0.0 (any coverage suffices)** | **Actual: `partial_capability_coverage` denies when `CapabilityCoverageScore < 0.5`** — hard threshold, not 0.0 |
| BM25 (k1=1.5, b=0.75, top-k=10000) | ✓ |

**Impact:** §7.10 says "All thresholds and parameters were fixed *ex ante*... no parameter tuning was performed on experimental data." But the thresholds listed don't match the policies that produced the results. Either the policies changed since the paper was drafted and §7.10 wasn't updated, or §7.10 was speculative.

**Fix:** Re-derive §7.10 directly from the policy YAML files. Mention there are also five additional alignment/cross-check rules (115, 102, 95, 70, 65) and explain their thresholds (`< 0.4`, `< 0.5`, `< 0.6`).

### C3. **Table 11 paired-cohort RA-ICL comparison does not reproduce — the retraction direction is wrong**

This is the most consequential issue. The paper's centerpiece contribution #5 and conclusion paragraph #4 hinge on the paired-cohort retraction that claims BM25 **degrades** SecFail by +0.047 [+0.017, +0.076].

When properly paired by task fingerprint (using `correct_70_30_seed42_v2.json` which is what the runner actually consumes — `split_service.py:30`), the numbers are very different:

| Variant | Exp | Paper n | Paper F1 | Paper SF | **Actual n** | **Actual F1** | **Actual SF** |
|---|---|---|---|---|---|---|---|
| Baseline (paired) | E1 | 4512 | 0.772 | **0.158** | 4512 ✓ | **0.8223** | **0.2538** |
| +C BM25 (paired) | E1 | 4512 | 0.846 | 0.205 | 4512 ✓ | **0.8461** | **0.2049** |
| **Δ E1** | — | — | +0.074 | **+0.047** | — | **+0.024** | **−0.0489** |

**My ΔSecFail = −0.049 (BM25 IMPROVES security on the paired cohort).**
**Paper ΔSecFail = +0.047 (BM25 DEGRADES security).**
**Direction-of-effect reversed.**

Sanity check: the paired cohort has more adversarial rows (excludes correct-train, keeps all wrong + null) than the full cohort, so baseline restricted-to-paired should have **higher** SecFail than baseline full (0.218). Mine gives **0.254** (higher, as expected). Paper gives **0.158** (lower, implausible from first principles). This strongly suggests the paper's "Baseline (restricted)" numbers were computed against a different cohort than the v2 split defines — most likely a positional/enumeration-order slice of the first 4512 baseline rows, which contains many correct-train rows and is therefore systematically lower-SF.

**Flip ledger (paper §8.7 third bullet):**

| Metric | Paper | Actual (paired by fingerprint) |
|---|---|---|
| ALLOW→DENY total | 895 (341 correct + 554 wrong + 0 null) | **326** (81c + 179w + 66n) |
| DENY→ALLOW total | 645 (264c + 381w + 0n) | **69** (16c + 37w + 16n) |
| no flip | 2972 (65.9%) | **4117 (91.2%)** |

The total flip count is ~74% lower in my paired analysis. The paper's 0 null-flips is also implausible for a properly paired cohort (the cohort definitionally contains all 690 null rows × the same fingerprints → some must flip given the precision lift).

**Tool quality on paired correct slice (Table 12):**

| | Paper | Actual paired |
|---|---|---|
| Baseline n=3474 exact 11.4%, jaccard 0.354 | (full correct slice, NOT paired) | matches full baseline ✓ |
| +C BM25 n=1044 exact 39.1%, jaccard 0.624 | ✓ | ✓ exact |
| **Baseline on paired correct slice (n=1044)** | — | **exact 10.3%, jaccard 0.351** |

So the table's two rows have different cohorts — the +C lift on the strictly paired correct slice is `39.1% − 10.3% = +28.8 pp` exact-match, similar to the paper's claimed `+27.7 pp` but on a defensible apples-to-apples cohort.

**Impact:**
- The retraction in §8.7, §9.4, and conclusion #4 (item 5 in §10) is **based on numbers that don't reproduce from the released artifacts**.
- The correct paired story is more favorable to BM25: it improves SecFail by ~5 pp on the same task set (consistent with the precision lift). The paper's original "BM25 is security-favourable" framing was directionally right; only the magnitude was inflated by the asymmetric cohort.
- This is a reviewer-credibility risk: anyone running the analysis script on the released logs will get my numbers, not the paper's.

**Fix:** Re-run the paired analysis using `_task_fingerprint` from `split_service.py` + `correct_70_30_seed42_v2.json` (matching the actual runner). Replace Table 11's "paired" rows and the flip-ledger numbers. Replace the retraction paragraph with the correct finding: **"Paired cohort confirms +C BM25 lift on both selection quality and security (ΔF1 = +0.024, ΔSecFail = −0.049 on E1). The asymmetric-cohort lift in earlier reports was directionally correct but overstated due to cohort imbalance."**

This is actually a *better* story for the paper — it removes the awkward retraction and shows the result is robust across cohort definitions.

### C4. ABAC categorisation thin
Paper §5.2 says "Three policy categories: Compliance isolation, Clearance enforcement, Temporal controls." Actual `abac_rules.yaml` contains **16 rules** across more granular categories. Not wrong, but the paper text undersells what's deployed. Either widen to "five categories" with a count or qualify as "illustrative categories include...".

### C5. Conclusion #4 (last bold paragraph) needs revision
The phrasing "We retract the prior framing that BM25 was security-favourable: on the same task set, it is security-unfavourable and must be paired with a recall-recovery mechanism" should be rewritten in light of C3. Recommended:

> *"BM25 RA-ICL lifts both selection quality (tool exact-match 3.4×, Jaccard +76%) and downstream security (paired ΔF1 = +0.024, ΔSecFail = −0.049 on E1). The lift is smaller than the original asymmetric-cohort comparison suggested, because the paired cohort over-represents adversarial rows. Precision lifts substantially (+0.190 [+0.165, +0.216]); recall is roughly preserved. The technique should still be deployed with a confidence-margin fall-through for low-similarity queries — see §9.4."*

---

## Recommended next actions (in order of payoff)

1. **(C1, C2)** Regenerate Table 3 and §7.10 directly from `policies/tsphol_rules.yaml` and `decision_engine.py`. 30 min of work, eliminates the largest reproducibility risk.
2. **(C3, C5)** Re-derive Table 11, the flip ledger in §8.7, and rewrite the §8.7/§9.4 paragraphs + conclusion #4. This *improves* the paper's narrative (no awkward retraction).
3. **(M2, M3)** Replace "≈2.2%" with per-model values; clarify "ALW vs legit-allowed".
4. **(M1)** Decide whether to keep the rounded ratios (56×/100×/170×) or use exact (54×/93×/170×).
5. **(C4)** Re-count ABAC categories or hedge to "illustrative".

After (1)–(3), the paper's core architecture, headline numbers, and all but one results table will pass any reviewer's reproducibility audit cleanly.
