# PALADIN — Advisor Meeting Guide
*Virtual meeting · screen-share · keep this open on a second screen / printout*

> Assumptions (change if wrong): ~30–45 min; you share the **compiled PDF** and can
> jump to tables; advisor knows the **PALADIN architecture** but has **not** seen the
> results or the paper. If you have slides instead, the same flow maps over.

---

## 0. Before you join (5-min checklist)
- [ ] Compile the latest PDF; have it open at the abstract.
- [ ] Bookmark / note the page of these tables so you can jump instantly *(numbers match the current compile)*:
  - **Table 3** — Four-model stack guarantee (E1 vs E4)  ← your headline
  - **Table 4** — Six-point operating-point sweep  ← for the "low admission" question
  - **Table 7** — Per-layer marginal Δ (reversal)
  - **Table 9** — RA-ICL security
  - **Newer-is-not-better** paragraph + **Table 6** (permissivity)
- [ ] Have `scripts/sweep_op_points.py` and the `datasets/experiment_logs/` folder ready,
      in case he asks "show me a number regenerate."
- [ ] Share a **single window** (the PDF) to reduce clutter; switch to whole-desktop only
      if you need code/logs.
- [ ] Decide your **one ask**: "Where do you think the weakest point is, and which
      experiment should I prioritize before submission?"

---

## 1. The one sentence to memorize (your thesis)
> "The **deterministic policy stack — not the LLM — is what produces the security
> guarantee**: across four models whose stand-alone judgment varies wildly, the full
> stack holds the security-failure rate in a tiny band. And we show **tool-selection
> correctness is necessary but not sufficient for authorization**."

## 2. 30-second opener (say this first)
"PALADIN you already know. What I'm showing today is the **measurement** side: I ran it
on the ASTRA adversarial benchmark across four LLMs and ~145K policy evaluations, in two
modes — the LLM *judging* a tool bundle, and the LLM *generating* one. The headline is
that the deterministic stack collapses the security-failure rate to under half a percent
no matter which model authors the request, even though the models' own judgment ranges
over 0.30 in F1. I'll walk the results, then the honest limitations, then where I think
this lands for SACMAT."

---

## 3. Suggested flow (time-boxed)

| Min | What to say (1 line) | What to show |
|----:|----------------------|--------------|
| 0–2 | Opener + thesis + "here's the path" | Abstract |
| 2–4 | 60-sec recap: pipeline order + **validation vs selection** | §3–4 pipeline figure/eq |
| 4–8 | Setup: ASTRA, 4 models, dual-mode, **what SecFail means**, two conventions | §6 methodology |
| 8–15 | **Headline:** stack-induced security floor — "stack, not LLM" | **Table 3** |
| 15–22 | **Concept:** semantic ≠ authorization; eligible-correct admission; the tunable floor | **Table 4** |
| 22–30 | **Phenomena:** reversal-by-mode → attribution paradox → RA-ICL safety win → newer-not-better | Tables 7, 9, 6 |
| 30–33 | **Own the limitations** (before he raises them) | §8 limitations |
| 33–35 | SACMAT positioning + next steps + **your ask** | §1.2 contributions / §8.3 |
| 35+ | Q&A | jump to backup tables |

---

## 4. The narrative (the story, in order)

1. **The gap.** MCP gives agents a tool-invocation surface with no native authZ. The open
   question: how much of "safe behavior" comes from the *model* vs the *policy stack*?
2. **The method.** Two modes (judge vs generate), one adversarial dataset (ASTRA: correct
   / same-MCP-wrong / cross-MCP-null), two metric conventions, paired bootstrap CIs.
3. **The headline.** Full stack → SecFail ≤0.5% at F1≈0.856 on all three OpenAI models;
   the four E1 confidence intervals **overlap**, while LLM-alone (E4) F1 swings from 0.47
   to 0.76 (and Gemini collapses to 0.004). ⇒ the stack, not the model, is the guarantee.
4. **The concept.** Why is "legitimate admission" only ~2%? Because **benchmark-correct ≠
   authorized**. A semantically correct bundle can still fail RBAC/ABAC/TRAC. That's the
   access-control point, and it's a **tunable operating point**, not a defect.
5. **The phenomena** the framework surfaces that single-point benchmarks can't:
   the layer that dominates **reverses** by mode; **first-firing attribution lies**;
   **retrieval improves security**; **newer isn't safer**.
6. **The honesty.** Security-first floor, not end-to-end safety; narrow vendor panel;
   one operator-context stand-in in selection mode; custom engine (substrate cost, not
   validity). All artifacts released; every number regenerable from logs.

---

## 5. Key numbers cheat-sheet  *(say the convention out loud — it prevents confusion)*

**Headline (Convention A = security view; positive = illegitimate):**
- Full-stack E1: **F1 ≈ 0.856**, **SecFail ≤ 0.5%** (gpt-3.5 .005 / gpt-4o .005 / gpt-5.4 .004); Gemini **.009**.
- LLM-only E4 SecFail: .500 / .280 / .679 / **.998** (Gemini). Reduction **56×–~170×**.
- "Stack not LLM": four E1 SecFail **CIs fully overlap**; four E4 differ wildly.

**Operating point (Table 4):**
- OP1 (released, strict): **eligible-correct admission 1.5–3.4%**, SecFail ≤0.5%.
- OP1→OP2 (relax deception accounting, 1-line config): admission **~2% → ~10%** at SecFail ≤3%.
- Pareto frontier **OP1→OP2→OP6**; OP3–OP5 dominated.

**Per-layer (validation, paired CIs):**
- TRAC |ΔSecFail| is **25× / 47× / 110×** RBAC (gpt-4o / gpt-3.5 / gpt-5.4).
- Selection inverts: RBAC & ABAC each |ΔSecFail| **≈ 0.20** (CIs exclude 0); TRAC alone not measurable there.

**Attribution paradox:** RBAC **fires 66%** of denials but marginal ΔSecFail **∈ [−0.010, −0.006]** (≤1%).

**RA-ICL (BM25, gpt-5.4, paired 4,512-row cohort):**
- Tool exact-match **10.3% → 39.1%** (3.8×); Jaccard **0.351 → 0.624** (+78%).
- **ΔSecFail = −0.046** [−0.061, −0.032] (security *improves*); net **+257 ALLOW→DENY**, new DENYs correct **74%**.

**Newer-is-not-better (Convention B = ASTRA permissivity view; LLM-only):**
- gpt-3.5 (2023) **0.756** > gpt-5.4 (2026) **0.688** > gpt-4o (2024) **0.595** — non-monotone.

**Scale:** 4 models · 8 domains · 6 personas · 1,157 tasks · 6,942 rows/run · **~145K** evaluations · 0 unrecoverable failures.

**Selection is harder:** full-stack F1 **0.856 (val) → 0.798 (sel)**; tool exact-match only **11.4%**; dataset ceiling **30–40%**.

---

## 6. Anticipated questions — with crisp answers

**Q1 (the big one). "You're denying ~98% of correct requests — is it broken?"**
No — and this is the access-control contribution. There are **two** notions of correctness:
*semantic* (ASTRA says the bundle fits the task) and *authorization* (this persona, in this
context, with these attributes/capabilities, is allowed to run it). A bundle can be
benchmark-correct yet **policy-inadmissible**. My metric (**eligible-correct admission**)
already requires *both* ASTRA-correct *and* persona-eligible; the residual gap is the
deterministic predicate floor (capability coverage, alignment, mutation-without-read). The
released point is a deliberately strict security floor, and it's **tunable**: OP1→OP2 lifts
admission ~2%→~10% at SecFail ≤3%. *"Tool-selection correctness is necessary but not
sufficient for invocation-time authorization."*

**Q2. "What's the scientific contribution — isn't PALADIN just engineering?"**
Exactly the point I'm careful about: the **contribution is the measurement methodology**,
not the system. Four parts: (a) the **dual-mode** protocol (judge vs generate) that most
task-tool benchmarks conflate; (b) **two metric conventions** that systematically *disagree*
on which layer matters; (c) **paired task-level bootstrap CIs** on per-layer marginal
SecFail; (d) a **dataset-ceiling** analysis. PALADIN exists to make those measurements
concrete. I explicitly *decline* to claim novel formal AC machinery.

**Q3. "Isn't this circular — PALADIN grading its own homework?"**
Ground truth comes from **ASTRA's labels + persona allow-lists, not the policy stack**, to
avoid self-consistency circularity. One honest caveat I disclose: in **selection** mode the
alignment predicate needs an "expected domain," which the harness fills from the gold MCP as
an **operator-context stand-in** (no real operator exists at benchmark time). **Validation
mode is unaffected** (expected = actual trivially). LLM-inferred domain is future work.

**Q4. "Only four models, three from OpenAI — how general is this?"**
I'm deliberately modest: three OpenAI generations are a **within-lineage capability span**,
and Gemini-2.5-pro is **one directional cross-vendor point** that happens to land inside the
OpenAI E1 band. I call it **directional cross-vendor evidence, not a general guarantee**. A
broader Claude/Llama/open-weights panel is the most important deferred experiment.

**Q5. "Why a custom engine (TRAC) instead of Cedar or OPA/Rego?"**
The engine is **policy engineering comparable to a typed Cedar/Rego extension** — I make no
novelty claim there; it's the substrate that lets the measurements run end-to-end. A
Cedar/OPA-Rego reimplementation is future work to **quantify substrate cost** — but that
**concerns substrate cost, not the validity of the measurement framework**.

**Q6. "Explain the layer reversal."**
**Which layer dominates depends on the input distribution, not the model.** Validation is
fed adversarial bundles (80% same-MCP wrong + 20% cross-MCP null) that exercise capability
and trust predicates → **TRAC dominates (25–110×)**. Selection is fed LLM-generated
bundles whose failure mode is persona/role misalignment → **RBAC/ABAC dominate (≈0.20
each)**. Implication: **single-layer designs catastrophically fail in at least one mode**;
only the composed stack holds ≤0.5% SecFail in both.

**Q7. "The attribution paradox — what is it?"**
First-firing charts (which layer fires first under short-circuit) credit **RBAC with 66%**
of denials. But its **marginal** contribution is **≤1%** — remove RBAC and ABAC/TRAC
catch the same rows. So "who fires first" **overstates necessity**; you must report *both*
attribution and marginal ΔSecFail. It's a methodological pitfall in a lot of agent-safety
papers.

**Q8. "Retrieval improves security? That's counterintuitive."**
Yes. BM25 retrieval-augmented in-context learning improves **both** tool selection
(exact-match 10.3%→39.1%) **and** security (paired **ΔSecFail = −0.046**, CI excludes zero).
Mechanism: a net **+257 ALLOW→DENY** shift on the adversarial slice where new DENYs are
correct 74% of the time. Contradicts "richer prompting trades safety for capability."
Caveat I state up front: single model, single retriever.

**Q9. "Newer models aren't safer — why?"**
LLM-only validator F1 is **non-monotone** in recency (gpt-3.5 0.756 > gpt-5.4 0.688 >
gpt-4o 0.595). gpt-5.4 is very permissive on hard same-MCP "wrong" bundles (41–100% by
domain). Consistent with **RLHF helpfulness-optimization** making models more permissive,
but I don't have a controlled fine-tune to claim causation. Operational takeaway: **you
can't assume a single-LLM validator improves as base models advance** — hence the stack.

**Q10. "Why do I see two different F1 numbers for the same model?"** *(he may catch this)*
Because of the **two conventions**. Convention A (security view, positive = illegitimate)
gives the E4 numbers in Table 3; Convention B (ASTRA permissivity view, positive =
legitimate) gives the newer-not-better numbers. They **disagree on purpose** — showing they
disagree is one of my contributions. Every table flags which convention applies.

**Q11. "How statistically solid is this?"**
Every Δ carries a **paired task-level bootstrap 95% CI (1,000 resamples)**. The four E1
SecFail CIs overlap (guarantee is model-robust); per-layer effects I claim have CIs that
**exclude zero**; RA-ICL's CI excludes zero. Zero unrecoverable inference failures across
117,666 OpenAI-panel rows.

**Q12. "One dataset (ASTRA) — is that enough?"**
Honest limitation — **all findings rest on ASTRA v0.3**. A second adversarial dataset
(InjecAgent / AgentDojo / ToolEmu) is in future work. ASTRA gives a principled negative
structure (hard within-domain "wrong" + gross cross-domain "null").

**Q13. "What's the threat model? What's out of scope?"**
A **semi-honest agent**: authenticated, follows MCP mechanically, but may emit
out-of-scope / cross-domain / mutation-without-read invocations. **Out of scope** (by
design, meant to *compose* with PALADIN): prompt-injection, policy-file compromise,
supply-chain, DoS, side channels, output exfiltration.

**Q14. "Selection is much worse than validation — why include it?"**
Because **selection is the realistic deployment mode** (the agent generates the bundle) and
it's where the reversal and the RA-ICL win live. It's strictly harder (F1 0.798 vs 0.856;
exact-match 11.4%; ceiling 30–40%). I'm explicit that it's harder — that honesty is part of
the framework.

**Q15. "Is it production-ready / what's next?"**
It's a **security-first admission floor, not end-to-end agent security**. Next: broader
vendor panel, a continuous threshold-grid sweep, a second dataset, the Cedar/OPA substrate
comparison, and composition with prompt-injection / output-filter defenses.

---

## 7. Own these *before* he raises them (credibility move)
- "Eligible-correct admission is low **on purpose** — it's a strict operating point, and
  Table 4 shows the whole envelope."
- "Cross-vendor is **directional**, one Gemini run — not a generalization claim."
- "Selection mode uses an **operator-context stand-in** for expected domain; validation is
  clean. LLM-inferred version is future work."
- "TRAC is **not** a new formal logic — it's a typed production-rule engine; the
  contribution is the measurement, not the substrate."
- "Everything is **regenerable** from released logs without re-calling any LLM (except the
  threshold-grid sweep, which needs the verdict cache repopulated)."

## 8. Framing discipline — phrases to avoid
- ❌ "novel access-control model" → ✅ "measurement framework + a deliberately un-novel substrate"
- ❌ "we generalize across vendors" → ✅ "directional cross-vendor evidence"
- ❌ "we block 98% of bad requests" → ✅ "we admit only persona-eligible, policy-admissible bundles"
- ❌ "RBAC catches most attacks" → ✅ "RBAC *fires* first most often, but its *marginal* value is ≤1%"

## 9. Turn it into a productive meeting — ask him
1. "Which result is the **strongest** for a SACMAT audience — the stack guarantee, the
   reversal, or the semantic-vs-authorization framing?"
2. "Where's the **weakest** point a reviewer will attack first?"
3. "If I can run **one** more experiment before submission, which: broader vendor panel,
   threshold-grid sweep, or a second dataset?"
4. "Is the **honest framing** of the low admission rate convincing, or does it still read as
   a weakness?"

## 10. Backup (have ready; don't lead with)
- Per-domain dominance (**Table 8**): 7/8 domains ΔRBAC=ΔABAC=0; only mongodb separates.
- Deception-routing precision (~0.44 at E1, **Table 16**) — framed as operational, not a security claim.
- Confusion matrices (**Tables 13–14**), persona FP-rate (**Table 20**).
- `scripts/sweep_op_points.py` live run if he wants to see OP1–OP6 regenerate.

---
*Tip: after each result, pause — "does that land?" He hasn't seen any of this, so give him
room to react. You drive; the PDF supports.*
