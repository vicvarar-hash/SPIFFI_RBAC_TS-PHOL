# ACM SACMAT 2027 — Reviewer Assessments

**Paper:** PALADIN: Policy-Aware Layered Agentic Decision Intelligence over the Model Context Protocol
**File reviewed:** `paper/main_acm.tex`
**Date:** 2026-06-15

---

## Reviewer #1

**Reviewer recommendation:** **Weak Accept (borderline) — major revision recommended**
**Confidence:** 4 / 5
**Reviewer expertise:** Access control, policy languages, LLM safety

---

## Summary

The paper makes two coupled contributions: (1) a measurement framework for agentic access control (dual-mode validation/selection, two metric conventions, paired bootstrap CIs on layer-marginal ΔSecFail, an explicit dataset ceiling), and (2) PALADIN, a six-stage pipeline (SPIFFE/SPIRE → RBAC → ABAC → fact extraction → TRAC typed predicate engine) evaluated on ASTRA v0.3 (1,157 tasks × 6 personas × 3 OpenAI models = 117,666 evaluations). Headline claim: the deterministic stack collapses SecFail to ≤0.5% across three model generations whose LLM-only F₁ varies by 0.30, and the dominant layer *reverses* (TRAC in validation, RBAC/ABAC in selection).

---

## Strengths

1. **Timely, well-scoped problem.** MCP authorization is a real and under-studied gap; the framing as an *invocation-time admission floor* (explicitly not a replacement for prompt-injection / output-filter defenses, §3.3, §9.1) is more honest than most of the agent-safety literature.
2. **Measurement contribution is the real value.** The dual-mode protocol, the explicit Convention A vs. B distinction, the attribution-paradox demonstration (RBAC fires 66% of denials but contributes ≤1% marginal ΔSecFail), and the dataset-ceiling analysis are methodological points the field needs. These will be reusable independent of PALADIN.
3. **Reproducibility is exemplary.** Raw per-row logs (~146 MB), policy YAML, BM25 retriever, splits file, analysis scripts, Docker runner — and the threshold sweep is regenerable without further LLM calls. This is above average for SACMAT.
4. **Honest negative/null results.** Deception precision of 0.44 acknowledged; per-domain "0.000" RBAC/ABAC contributions reported; cohort-shift in RA-ICL flagged and mitigated with a paired SHA-256 fingerprint join.
5. **External replication.** Independent reproduction of ASTRA's LLM-ResM within 0.075 F₁ under a stricter per-bundle protocol — exactly the kind of cross-paper hygiene SACMAT should reward.
6. **Statistical care.** Paired task-level bootstrap CIs on every Δ; per-model agreement used as robustness check.

---

## Major Concerns

### M1. Access-control novelty is thin relative to a SACMAT bar
The AC formalism is essentially **RBAC + first-match ABAC + an ordered, typed production rule engine** (TRAC). §2.1 disclaims Cedar/Sentinel comparison in prose but provides **no head-to-head empirical evaluation**. The three claimed TRAC advantages (typed continuous-score predicates, ontological subsumption over capabilities, bundle-level decisions) are all expressible in OPA/Rego today, and Cedar 4.x extensions are moving in this direction. Without a Cedar/OPA implementation of the same rule set on the same data, the "TRAC is necessary" claim is not earned. **Action: implement the policy in OPA/Rego, run it through E1, report a direct comparison.**

### M2. The "stack-induced floor" headline rests on one vendor's lineage
Three OpenAI models from one provider is *not* a model panel that can support "the policy stack, not the model, is the source of the guarantee." The authors flag this (§9.2), but it is the paper's central claim. At least one non-OpenAI model (Claude, Llama, Gemini) is needed before publication — the artifact is set up to do this and there is no good reason it isn't done.

### M3. The operating point is extreme and incompletely characterized
At E1, **95–100% of legitimate requests are denied** (1.5–2.9% allow rate). This is reported as a "security-first posture" but in absolute terms the system is close to *deny-all*. The "F₁ = 0.856" headline is driven entirely by recall on the illegitimate class against a heavily illegitimate-skewed test set (5,190/6,942 illegitimate). Without the promised SecFail-vs-legitimate-allow sweep over the four exposed thresholds, the reader cannot tell whether PALADIN can produce a deployable operating point (say, ≥80% legitimate-allow at ≤5% SecFail) or whether the "guarantee" is an artifact of near-total denial. **The sweep is regenerable without LLM calls — run it and put the curve in the paper.**

### M4. Threat model dodges the threats that make MCP dangerous
The semi-honest agent model (§3.3) covers within-/cross-domain mis-scoping and over-helpful agents. The threats people actually worry about in MCP — **indirect prompt injection via tool outputs, tool-description poisoning, supply-chain compromise** — are out of scope. That is a defensible scoping choice for an admission-layer paper, but the abstract's "security-first authorization layer" framing oversells what the evaluation actually demonstrates. The "16 threat categories" cited (Gupta et al.) are mentioned in motivation and then dropped.

### M5. The selection-mode results contain a definitional artifact
E4 "degenerates to allow-all" in selection because no validation verdict is emitted, so ΔSecFail = 0.80 for E3 essentially measures "no policy = no security." The selection-mode reversal claim therefore rests on RBAC and ABAC each contributing ~0.20 ΔSecFail — both meaningful, but the contrast with validation is partly an artifact of how the modes are defined. The reversal would be more convincing with an LLM-as-validator baseline that *also* operates on the LLM-generated bundle.

### M6. Per-domain results undermine layer-necessity claims
In 7 of 8 domains, ΔRBAC = ΔABAC = 0.000 in validation (Table per_domain_delta). Combined with the attribution paradox, this is evidence that **on this test distribution**, RBAC and ABAC are largely redundant with TRAC. The authors argue ABAC is retained for compliance auditability (§9.2), which is fine, but the security argument for the three-layer composition (over TRAC alone with policy ordering) is weaker than the paper claims.

### M7. Dataset monoculture
All findings rest on ASTRA v0.3, which is itself GPT-4o-generated. Task-level bootstrap CIs do not capture dataset-generation variance. The label-noise admission (~30 mislabelled `null` bundles) further bounds reliability of the differences being reported. At minimum, a second adversarial dataset (e.g., InjecAgent, AgentDojo, ToolEmu scenarios) should be exercised.

---

## Minor Issues

- **Abstract is ~380 words and one paragraph**; ACM convention is 150–250 words. Compress.
- **TRAC acronym** ("Typed, Staged, Predicate-Hierarchical Ordered Logic") is awkward and the disclaimer that it is *not* higher-order logic (§5.2) suggests the name should change.
- **§5 capability ontology is small** (40 entailments, 28 source capabilities); the generality claim should be moderated.
- **§6 (Identity)** is one paragraph for a "six-stage" pipeline whose first two stages are identity/registration. Either evaluate the SPIFFE layer (rotation overhead, attestation failure modes) or move it to an appendix and stop calling it a contribution.
- **Deception routing precision = 0.44 at E1** is, charitably, neutral. Calling it "graduated risk-throttle" is rebranding after the fact; consider removing the feature from the contribution list.
- **§4.7 composition properties** are deferred to appendix; the proof sketches should be in the main text given how much qualitative argument hangs on monotonicity.
- **Anonymization slip:** the repository name leaks identifying terms (`SPIFFI_RBAC_TS-PHOL`); even the anonymous mirror inherits this if the original is public.
- **References** — Gupta 2025, Jamshidi 2025, Chu 2026, Patil 2026, Rampalli 2026 are very recent or in-press; check that all are properly cited and not concurrent submissions that would create double-blind issues.
- **Notation:** Eq. 14 (Alignment) hard-codes weights (0.4, 0.4, 0.2) with no ablation or justification — these should be treated as policy thresholds and added to the sweep.
- **Selection mode RA-ICL** uses BM25 only; a single-model, single-retriever result is overgeneralized as "richer prompting improves safety."

---

## Questions for Authors

1. Can you implement the TRAC rule base in OPA/Rego and report the same E1–E3 numbers? If they match, what is the AC contribution beyond the composition methodology?
2. Run the threshold sweep and report the SecFail-vs-legitimate-allow Pareto curve. Where on the curve is a typical deployment (say, 90% legitimate-allow)?
3. Add one non-OpenAI model. Does the E1 collapse hold?
4. What happens under indirect prompt injection via a tool output that influences the *next* bundle? Is that within or outside the envelope you're defending?
5. How sensitive is the layer-contribution reversal to ASTRA's 80/20 wrong/null mix? Reweight and report.

---

## Bottom Line

A genuinely useful **measurement** paper attached to a system whose access-control novelty is modest. The framework, the attribution-paradox finding, the dataset ceiling, the honest replication of ASTRA, and the reproducibility package are publishable on their own merits. The "stack-induced floor" claim and the headline operating point need (a) cross-vendor models and (b) the threshold sweep before they can be accepted as stated. With M1–M3 addressed in a major revision, this becomes a clear accept; as currently written, it is a borderline weak-accept that some reviewers will reject for insufficient AC novelty.

---

## Reviewer #2

**Overall recommendation:** Weak Accept / Borderline Accept

This is a strong and timely SACMAT-style paper. The topic is highly aligned with access control, authorization, policy enforcement, and the emerging security risks around LLM agents and MCP. The paper has improved significantly: it now frames PALADIN less as a universal agent-security solution and more as an invocation-time authorization layer, which is the right scope for SACMAT. The contribution is also clearer: the real novelty is not only the six-stage pipeline, but the measurement framework for separating LLM behavior from deterministic policy-stack effects.

### Summary of contribution

The paper presents PALADIN, a six-stage short-circuiting authorization pipeline over MCP tool requests, combining identity, registration, RBAC, ABAC, fact extraction, and TRAC predicate evaluation. The system explicitly denies at S1–S4, then evaluates typed predicates at S6. The page 3 diagram makes the pipeline easy to understand and is now suitable for a security-systems paper.

The strongest technical contribution is the experimental framing: the paper separates validation mode from selection mode, reports both security-view and permissivity-view metrics, and uses paired task-level bootstrap CIs for marginal layer contributions. This is a meaningful contribution because many LLM-agent benchmarks conflate "choosing tools" with "judging tools."

### Strengths

1. **Strong fit for SACMAT.**
   The work is about authorization, policy composition, RBAC/ABAC, typed predicate enforcement, identity, and auditability. The MCP/agent framing makes the paper current without drifting too far from SACMAT's core.

2. **Much clearer scope.**
   The paper now explicitly says PALADIN is not an end-to-end agent-security solution, not a prompt-injection defense, and not an output-filtering system. That is important. It avoids overclaiming and places the work in the correct layer: invocation-time admission control.

3. **The measurement contribution is publishable.**
   The dual-mode evaluation, metric convention separation, ablation design, and layer-contribution reversal are the paper's best parts. The finding that TRAC dominates validation while RBAC/ABAC dominate selection is interesting and actionable.

4. **Strong empirical scale.**
   The paper evaluates 1,157 tasks, 6 personas, 3 models, and 117,666 policy evaluations. That is a credible experimental base for a SACMAT paper.

5. **Good security posture.**
   The paper makes a defensible argument that deterministic policy layers can create a "security floor" that masks LLM variance. The claim is appropriately bounded to an OpenAI lineage rather than generalized to all vendors.

### Main weaknesses / concerns

1. **The legitimate-allow rate is very low.**
   The reported operating point has SecFail ≤ 0.5%, but only 1.5%–2.9% legitimate allow. That is a very conservative posture. For a security-first system, this can be acceptable, but reviewers may challenge whether the system is practical if it blocks almost all legitimate requests. The paper says this is threshold-governed, but the main body should show at least one curve or table with alternative operating points.

   *What to fix:* Add a compact SecFail-vs-legitimate-allow curve in the main results, not only the claim that it can be regenerated. The abstract says the curve is available from logs, but reviewers need to see the trade-off.

2. **TRAC risks being perceived as "policy engineering," not a new formal model.**
   The paper has improved by disclaiming proof-theoretic higher-order logic, but the name TRAC still sounds mathematically ambitious. Since the implementation is an ordered typed production-rule engine, some reviewers may ask whether the novelty is in the engine or in the measurement/evaluation.

   *What to fix:* Make even clearer that TRAC is the evaluated policy substrate, while the core scientific contribution is the measurement methodology and empirical layer analysis.

3. **Cross-vendor generalization remains weak.**
   The paper uses three OpenAI-generation models. The claim is now properly limited, but SACMAT reviewers may still expect at least one non-OpenAI model, especially because the paper discusses "model variance." The paper itself acknowledges cross-vendor extension as deferred.

   *What to fix:* Add one external model if possible. Even a smaller Claude/Gemini/Llama-family run on a subset would reduce this concern significantly.

4. **Threat model is clean but narrow.**
   The semi-honest agent model is reasonable, and the paper explicitly trusts the policy files, MCP registry, SPIFFE substrate, and deterministic implementation. It also excludes policy compromise, side channels, DoS, MCP supply-chain attacks, active adversarial prompts, and tool-output exfiltration. That honesty is good, but it means the paper should not sound like it "secures MCP." It secures one important decision point.

   *What to fix:* Keep the title/abstract framing as "authorization over MCP tool invocation," not "MCP security" broadly.

5. **ASTRA dependence may limit external validity.**
   The paper reuses ASTRA's task corpus and labels, which is a good baseline, but the dataset ceiling analysis suggests the benchmark itself may cap exact-match performance. That strengthens the measurement argument, but it also weakens claims about real-world agent behavior.

   *What to fix:* Add a small synthetic or enterprise-style supplemental benchmark, even if smaller, to show the findings are not ASTRA-specific.

### Review scores

| Category             | Score   |
|----------------------|---------|
| Novelty              | 7/10    |
| Technical depth      | 7/10    |
| Experimental rigor   | 8/10    |
| Clarity              | 7/10    |
| SACMAT fit           | 8.5/10  |
| Practical relevance  | 8/10    |
| **Overall**          | **7.5/10** |

### Likely reviewer decision

I would lean **Weak Accept** if artifacts are available and the claims stay scoped. The paper is timely, relevant, and has a real measurement contribution. However, it could fall to Borderline if reviewers focus on the very low legitimate-allow rate, OpenAI-only model panel, or whether TRAC is sufficiently novel beyond a typed rule engine.

### Top three changes before submission

1. Show the operating curve in the main paper: SecFail vs legitimate-allow, with at least 3–5 threshold points.
2. Add one cross-vendor model or subset experiment to strengthen the "policy stack masks model variance" claim.
3. Tone down TRAC novelty language and emphasize the dual-mode measurement framework as the primary scientific contribution.

---

# Round 2 — Updated Reviewer Assessment

**Date:** 2026-06-15
**File reviewed:** `paper/main_acm.tex` (revised: 1,090 lines / 125 KB, up from 1,041 / 112 KB)
**Updated recommendation:** **Accept** (was Weak Accept / borderline)
**Confidence:** 4 / 5

## What changed since Round 1

The revision substantively addresses 5 of the 7 major concerns raised by both reviewers:

| # | Round-1 concern | Round-2 status |
|---|---|---|
| **M1 / R2-#2** | TRAC novelty oversold | **Fixed.** Contribution #2 now explicitly: *"We make no claim of novel formal AC machinery---the engine is policy engineering, comparable in expressive power to a typed Cedar/Rego extension."* Conclusion mirrors this. OPA/Rego head-to-head re-implementation added to future work. |
| **M2 / R2-#3** | Single-vendor LLM panel | **Partially fixed.** New §8.4 *Preliminary Cross-Vendor Data Point: Gemini-2.5-pro* (Table `tab:cross_vendor`): E1 F1 = 0.855, SecFail = 0.009 — inside the OpenAI band. E4 collapses to F1 = 0.004 (largest E1->E4 gap in panel). Honestly labelled "directional" and "preliminary"; Claude-Opus-4.8 attempt with billing failure transparently disclosed. |
| **M3 / R2-#1** | Operating-point sweep missing | **Fixed.** New §8.2 with Table `tab:operating_sweep` — six OP points. **OP2 is the key result**: deception=ALLOW lifts legitimate-allow from 2.2% -> 10.2% while keeping SecFail <= 3%. This single line refutes the "near-deny-all artefact" concern. `scripts/sweep_op_points.py` released. |
| **M5** | Selection-mode E4 definitional artifact | **Acknowledged.** "LLM-as-validator-on-LLM-bundles baseline" now first in future_work under the selection-mode reversal claim. |
| **M7** | Single dataset (ASTRA) | **Acknowledged.** Second adversarial dataset (InjecAgent / AgentDojo / ToolEmu) added to future work with citations. |
| Eq. 14 weights | Hard-coded, unjustified | **Fixed.** §4.6 now justifies the (0.4, 0.4, 0.2) split *ex ante* and lists them as additional sweep axes. |
| Anonymization leak | Repo name reveals identity | **Acknowledged.** Footnote: anonymous mirror used exclusively for review, will rename for camera-ready. Citation hygiene paragraph added. |
| ABAC retention | Weak DeltaSecFail in validation | **Reframed correctly.** Contribution #4 and §9.2 now justify ABAC primarily on compliance-auditability grounds, not marginal security. |

The total evaluation corpus grew from 117,666 -> 145,434 evaluations (28k additional). Results section grew from 7 -> 9 subsections.

## What is still open

1. **Cross-vendor is still N=1.** One Gemini run inside the OpenAI band is supporting evidence, not generalisation. The paper now states this explicitly ("not a replacement for a proper Claude/Llama/open-weights panel"), so the claim is no longer overstated. A reviewer who wants 3-4 non-OpenAI models for the headline can still reject — but the framing has moved from "OpenAI lineage" to "OpenAI lineage + 1", which is the right epistemic stance.
2. **No OPA/Rego empirical comparison yet** (M1 partial). The reframing makes this less urgent because the paper no longer claims TRAC is the contribution, but a SACMAT reviewer focused on AC substrates may still ask.
3. **ASTRA monoculture.** Second benchmark still future work.
4. **Per-domain RBAC/ABAC = 0 in 7/8 validation domains.** Mathematically unchanged; framing now correct.
5. **Abstract is ~410 words.** Still over ACM convention.
6. **§6 (Identity)** still one paragraph.

None of these alone is a blocker.

## Notable strengths of the revision

- **Honesty under pressure.** The Claude billing-failure disclosure ("89% of requests failed due to a billing-credit limit unrelated to methodology") and the Gemini E4 = 0.004 result (a brutally bad number for the LLM-only baseline that *strengthens* the stack-floor narrative) are reported without spin.
- **Operating-point sweep is the right answer.** OP1->OP2 shifting from 2.2% -> 10.2% legit-allow at SecFail <= 3% (one-line config change) directly refutes the "near-deny-all" objection. OP1->OP6 envelope makes the architectural value visible.
- **Concave-in-the-right-direction Pareto curve** between OP1 and OP6 is exactly what a security architecture should produce.
- **Contribution restructuring** now properly leads with measurement and demotes TRAC to substrate.

## Updated scores

| Category             | Round 1    | Round 2     |
|----------------------|------------|-------------|
| Novelty              | 7/10       | **7.5/10** (re-framed honestly) |
| Technical depth      | 7/10       | 7/10        |
| Experimental rigor   | 8/10       | **9/10** (sweep + cross-vendor) |
| Clarity              | 7/10       | **8/10**    |
| SACMAT fit           | 8.5/10     | 8.5/10      |
| Practical relevance  | 8/10       | **8.5/10**  |
| **Overall**          | **7.5/10** | **8.0/10**  |

## Bottom Line (revised)

The authors substantively addressed both reviewers' top-three asks: operating-point sweep, cross-vendor data point, and TRAC reframing — each handled with appropriate epistemic humility rather than rhetorical patching. **The paper has crossed the line from "borderline / major revision" to "accept with minor revisions."** Remaining gaps (full cross-vendor panel, OPA/Rego comparison, second benchmark) are now correctly positioned as future work rather than overclaimed strengths. Recommend acceptance.

---

## Round 2 — Reviewer #2

**Overall recommendation:** Weak Accept / Borderline Accept leaning Accept

This is a strong SACMAT-fit paper because it targets authorization at the LLM-agent tool invocation boundary, not generic prompt safety. The strongest contribution is not the PALADIN stack itself, but the measurement framework: validation vs. selection, security-view vs. permissivity-view metrics, layer-marginal SecFail analysis, bootstrap CIs, and dataset-ceiling framing. The paper is also unusually self-aware about what it is not claiming: it explicitly positions PALADIN as an invocation-time authorization floor, not a complete agent-security solution or a novel formal access-control model.

### Summary of contribution

The paper proposes PALADIN, a six-stage short-circuit authorization pipeline over MCP tool invocations: SPIFFE/SPIRE identity, registration, RBAC, ABAC, fact extraction, and TRAC predicate evaluation. The architecture is clear, and the figure on page 3 communicates the staged denial semantics effectively.

The paper's best empirical claim is that the deterministic stack reduces SecFail to a narrow band across multiple models while LLM-only behavior varies substantially. The abstract reports approximately 124K evaluations over ASTRA v0.3, 1,157 tasks, six personas, and four models; it also reports layer-reversal behavior, an attribution paradox, and a BM25 RA-ICL security improvement.

### Strengths

1. **Excellent problem framing for SACMAT.**
   The paper speaks directly to access control: authorization, policy enforcement, workload identity, RBAC/ABAC composition, and auditability. The shift from "is the LLM safe?" to "what must be enforced before a tool invocation?" is timely and important.

2. **Measurement contribution is credible and valuable.**
   The dual-mode distinction between validation and selection is a real contribution. Many agent/tool papers blur "judging a proposed tool bundle" and "generating a tool bundle from scratch." Separating them makes the results more interpretable.

3. **Strong scoping discipline.**
   The paper repeatedly avoids overclaiming TRAC as a novel formal AC model, instead positioning it as policy engineering comparable to typed Cedar/Rego-style extensions. That honesty strengthens reviewer trust.

4. **Threat model is explicit.**
   The threat model is reasonably well bounded: semi-honest authenticated agent, trusted policy files, trusted registry metadata, no trust in LLM-emitted bundles or confidence scores. The paper also clearly excludes policy-file compromise, side channels, DoS, MCP supply-chain compromise, and output exfiltration.

5. **Reproducibility posture is above average.**
   The draft states that policies, raw logs, BM25 retriever, splits, analysis scripts, and Dockerized runner are released, which will matter positively for SACMAT artifact/reproducibility expectations.

### Main weaknesses reviewers may raise

1. **The legitimate-allow rate is very low.**
   This is the biggest risk. A security-first operating point with only 1.5%-2.9% legitimate allow can be attacked as "near deny-all," even though the paper includes a six-point operating sweep. The paper does acknowledge this as a construct distinct from SecFail, but reviewers may still ask whether the system is operationally useful.

   *What to improve:* make the operating-point sweep more central, not defensive. Add a short paragraph in the intro/results saying: "PALADIN is not optimized for maximum utility; we expose the policy frontier so operators can choose their risk posture." Ideally add one more threshold-grid experiment, even if small.

2. **Cross-vendor evidence is still thin.**
   Three OpenAI models plus one Gemini run is useful, but not enough to claim provider-independent behavior. The paper already admits this and lists Claude, Llama, and open-weights models as future work.

   *What to improve:* change any phrasing like "cross-vendor guarantee" to "preliminary cross-vendor evidence." If possible, add one open-weight model before submission.

3. **Policy dependence remains a core validity issue.**
   The results depend on authored RBAC bindings, ABAC rules, TRAC rules, capability ontology, and tool metadata. The paper is transparent about this, but SACMAT reviewers may still want a perturbation study showing robustness to policy edits.

   *What to improve:* add a lightweight sensitivity experiment: remove or relax specific high-impact TRAC thresholds and show how SecFail and legitimate-allow move.

4. **Missing head-to-head comparison with OPA/Rego or Cedar.**
   The paper says TRAC could be implemented as a typed Cedar/Rego extension and that a direct comparison is future work. That is honest, but a reviewer may ask: "Why not just use Rego/Cedar?"

   *What to improve:* add a small table mapping TRAC features to Cedar/Rego/Sentinel. You do not need a full implementation, but you should make the substrate argument sharper.

5. **The writing is dense and contribution-heavy.**
   The paper has many claims: dual-mode framework, metric conventions, dataset ceiling, deterministic floor, layer reversal, attribution paradox, RA-ICL safety, ASTRA replication, deception routing. This is impressive but can feel overloaded.

   *What to improve:* reduce the abstract and intro claims to three main takeaways:
   - Measurement framework.
   - Deterministic authorization floor.
   - Empirical findings: layer reversal + attribution paradox + RA-ICL result.

### Likely reviewer scores

| Category              | Assessment |
|-----------------------|------------|
| Originality           | High for measurement framing; moderate for policy stack |
| Technical quality     | Strong, but policy sensitivity needs more evidence |
| Relevance to SACMAT   | Very high |
| Empirical evaluation  | Strong scale; weaker external validity |
| Clarity               | Good but too dense |
| Reproducibility       | Strong if artifact link works |
| **Overall**           | **Weak Accept / Borderline Accept leaning Accept** |

### My reviewer-style recommendation

I would argue for Weak Accept if the artifact is available and the logs/scripts reproduce the reported tables. The paper is timely, well scoped, and directly relevant to SACMAT. The main reason it is not a clear accept yet is the utility/security trade-off: the headline SecFail result is compelling, but the low legitimate-allow rate gives skeptical reviewers an easy attack path.

My strongest advice before submission: move the operating-point sweep and policy-sensitivity story forward. That will turn the paper from "a secure but restrictive stack" into "a measurement framework that exposes the operator's security-utility frontier," which is a much stronger SACMAT contribution.

---

# Round 3 — Post-Rebuild Assessment

**Date:** 2026-06-26
**File reviewed:** `paper/main_acm.tex` (961 lines, ~108 KB) — full rebuild from the 12-rule alignment engine to the **agnostic 4-rule engine** (capability_coverage, write_safety, tool_relevance, action_coherence).
**Recommendation:** **Weak Accept / borderline** (down from the Round-2 *Accept*), **recoverable to Accept** with two concrete actions.
**Confidence:** 4 / 5

## What changed since Round 2 (this is a different paper)

The system itself was re-baselined, not just the prose:
- **Engine:** alignment-threshold scoring → agnostic `{domain}:{action}` capability model; TRAC = "Task-Relational Access Control" (TRAC name retired everywhere).
- **Oracle leak (M5) resolved at the source:** `expected_domain`/`gt_mcps[0]` removed; task domain now BM25-inferred from task text. The leaky alignment predicates that consumed it no longer exist.
- **Operating point (M3):** headline moved from SecFail ≤0.5% @ ~2.2% admission to **SecFail 10.7% @ 43.9% eligible-correct admission** — a genuine, deployable point, no longer "near-deny-all."
- **OP2 deception-as-ALLOW trick removed;** Table 4 redefined as real configs OP1–OP5.
- **Gemini removed** (author no longer trusts those results) → panel is **3 OpenAI generations, N=0 non-OpenAI**.
- All result tables and the entire Appendix D regenerated from per-row dumps and cross-verified.

## Net effect on the Round-2 *Accept* (the critical point)

Round 2 reached Accept (8.0) because the revision "addressed 5 of 7 concerns." **Two of those fixes no longer exist in this version:**

1. **M3 was credited to OP2** ("deception=ALLOW lifts 2.2%→10.2% … refutes near-deny-all"). OP2 is gone. It is now resolved *more honestly* by a real 43.9% admission — but the specific line the reviewer praised is removed.
2. **M2 was partially credited to the Gemini data point** (E1 in-band; E4=0.004 "strengthens the floor narrative"). Gemini is gone. **M2 reverts to fully open — the reviewers' explicit "before publication" requirement.**

**Bottom line of the trade:** scientific integrity went **up** (no metric trick, no oracle leak, model-independent floor by construction), but the two crutches that earned the Accept were kicked out, and the single most-cited weakness (vendor monoculture) is now *worse* than in Round 2.

## Concern scorecard (vs Round 2)

| # | Concern | Round-2 status | Round-3 status |
|---|---|---|---|
| **M2** | Single-vendor panel | Partially fixed (Gemini) | 🔴 **Regressed — OpenAI-only, N=0 non-OpenAI.** Highest reject risk. |
| **M3** | Extreme operating point | Fixed (via OP2 trick) | ✅ **Fixed honestly** (43.9% real admission + real-config sweep). |
| **M5** | Selection-mode leak / artifact | Acknowledged | ✅ **Resolved at source** (BM25 task-text inference). |
| **M6** | RBAC/ABAC redundant (7/8 domains) | Framing-only | ✅ **Resolved** — ΔRBAC −0.207, ΔABAC −0.236 (large); a *consequence* of removing the leaky alignment predicate. |
| **M1** | AC novelty thin | Reframed | 🟡 **Unchanged; venue-critical.** New TRAC-vs-Cedar/Rego/Sentinel table helps; OPA/Rego head-to-head still future work. The rebuild leans *harder* into "no AC novelty," which is the riskiest possible framing for an AC venue. |
| **M4** | Threat model narrow | OK (scoping) | ✅ Still adequately scoped. |
| **M7** | ASTRA monoculture | Acknowledged | 🟡 Unchanged. |

## Inconsistencies the rebuild introduced — found and FIXED in this pass

The rebuild left retired-engine residue contradicting the new agnostic claims; all corrected in this revision:
- **§5.1** described the retired 40-edge capability ontology + hard/soft tiers + "alignment score" — replaced with the VerbNet-grounded action classifier + agnostic `{domain}:{action}` capability.
- **§4.5** referenced the cut "per-domain dominance map" — repointed to the attribution-paradox analysis.
- **Related Work (§2.1)** claimed "ontological subsumption over capability hierarchies" — reframed to the task-relational coverage predicate.
- **Appendix B/C** still documented `SemanticSim` (embeddings, unused), `RequiredCapabilities`/`Capability Entailment` (retired ontology), and "Frozen thresholds" (the entire `0.4/0.4/0.2` + `<0.3/0.25/0.35/0.4` alignment engine) — all rewritten to the agnostic mechanism (BM25 TaskToolRelevance, domain floor, the three swept knobs).

Integrity verified: every `\ref` resolves, all float environments balanced, all result numbers recomputed from `scratch/canonical_rows/`.

## Still open / regressed

1. **M2 — no non-OpenAI model (highest risk).** A non-OpenAI E4 run was attempted to re-close this: **Claude is billing-blocked at the account level** (HTTP 400 "credit balance too low" — same failure that killed the earlier Claude run; verified it silently coerces to `is_valid=False`, so any reported Claude number would be a parsing artifact, not judgment). **Gemini is reachable and parses correctly**, but was removed by author decision. → *Decision required* (see recommendation).
2. **M1 — AC novelty / no OPA/Rego empirical comparison.** Substrate *feature* table added; empirical head-to-head still deferred.
3. **M7 — second dataset** still future work.
4. **Abstract** ~380 words (ACM convention 150–250).
5. **§6 Identity** still one paragraph.

## Strengths of the rebuild

- **The model-independent floor is now a cleaner, stronger claim than the old one:** E1 is *bit-identical* across models by construction (verified), so "the stack, not the model, is the guarantee" is now provable rather than empirical-coincidence.
- **Honest resolution of M3/M5/M6** without rhetorical patching. The "attribution paradox" (RBAC fires on 82% of denials; ABAC, firing on 4%, carries the largest marginal) survives and is well-supported.
- **Leak-free end to end**, which closes the reviewer audit thread that produced the M5 concern.

## Updated scores

| Category | Round 2 | Round 3 |
|---|---|---|
| Novelty | 7.5 | 7.0 (leans harder into "no AC novelty") |
| Technical depth | 7.0 | 7.5 (agnostic engine cleaner, fully consistent) |
| Experimental rigor | 9.0 | 8.0 (sweep honest; **but lost the cross-vendor point**) |
| Clarity | 8.0 | 8.0 |
| SACMAT fit | 8.5 | 8.0 (measurement-first framing vs AC venue) |
| Practical relevance | 8.5 | 8.5 (43.9% admission is a real deployable point) |
| **Overall** | **8.0** | **7.0–7.5 (borderline), recoverable to 8.0+** |

## Bottom line

The rebuild is the right scientific move — it trades two fragile crutches (a deception-accounting trick and a single distrusted cross-vendor run) for an honest, internally-consistent, leak-free system whose central claim is now provable by construction. But in pure acceptance terms it **re-opens M2**, which both reviewers flagged as a pre-publication requirement, and doubles down on the "no AC novelty" framing that a SACMAT substrate reviewer can reject on.

**Two actions return it to clear Accept:**
1. **One non-OpenAI E4 run.** Because the deterministic floor is now model-independent, only the LLM-only (E4) column is needed from a non-OpenAI model to restore the cross-vendor claim — *cheaper and stronger* than the old Gemini point. Claude is billing-blocked; the available options are (a) a **fresh, verified Gemini-2.5 run** (different from the old distrusted number — verdicts confirmed to parse correctly), (b) top up Anthropic credits and run Claude, or (c) keep M2 as documented future work and accept the reject risk.
2. **Lean into "task-relational access control"** as a modest conceptual AC contribution rather than retreating to "measurement framework only" — venue-aligned, and costs nothing.

Then trim the abstract and expand §6 (both minor).

### Round 3 addendum (2026-06-26) — M2 partially re-closed

After the assessment above, the non-OpenAI run was completed with **Claude Opus 4.8** (Anthropic) as the validator on a **blind, stratified 45-task subset** (15 correct / 20 wrong / 10 null), judging each candidate bundle against the harness's `ValidationService` rubric with verdicts frozen before scoring and released. New **§7.2 "Cross-Vendor Evidence"** + Table `tab:cross_vendor` report all four models on the identical 45 tasks:

- Claude E4 (LLM-only): F1 0.704, SecFail 0.457 — **inside** the OpenAI E4 band (SecFail 0.231–0.606); blind agreement with `match_tag` 35/45 (15/15 correct, 10/10 null, 10/20 hard `wrong`).
- Model-independent floor (E1 SecFail 0.054 on the subset) bounds all four E4s by 4–11×.
- FULL converges across both vendors to F1 0.902–0.921 / SecFail 0.018–0.036.

**Effect on M2:** moves from "OpenAI-only, N=0 non-OpenAI" to a genuine non-OpenAI data point (Claude Opus 4.8) that supports the central claim across vendors. **Scope (disclosed in-paper):** N=45 directional subset, so the subset floor ≠ the full-set headline; per-task verdicts released for verification. Scaling to a full multi-model panel (Claude/Llama/open-weights) remains the right camera-ready upgrade. Net: M2 risk materially reduced; recommendation moves back toward Accept.

