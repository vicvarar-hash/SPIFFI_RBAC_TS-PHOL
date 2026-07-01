import streamlit as st
from typing import List
import pandas as pd
import altair as alt
import os
import json
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona


def render_home(tasks: List[AstraTask], personas: List[MCPPersona]):
    # ── Hero Header ──
    st.markdown("""
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
                    padding: 35px 40px; border-radius: 16px; margin-bottom: 30px;
                    border-left: 6px solid #e94560;">
            <h1 style="color: #ffffff; margin: 0 0 8px 0; font-size: 2.4rem;">
                🛡️ PALADIN
            </h1>
            <p style="font-size: 1.3rem; color: #a8d8ea; margin: 0 0 4px 0; font-weight: 500;">
                Policy-Aware Layered Agentic Decision Intelligence
            </p>
            <p style="font-size: 0.95rem; color: #8899aa; margin: 0;">
                A composable governance framework for securing LLM-based agentic tool selection
                through layered identity, attribute, and formal logic policies.
            </p>
        </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # Problem Statement & Research Questions
    # ════════════════════════════════════════════════════════════════════
    st.header("🧐 Problem Statement & Research Questions")
    st.markdown("""
    Modern autonomous AI agents operate in open, federated ecosystems using protocols like the
    **Model Context Protocol (MCP)**. These agents select and invoke tools on behalf of users —
    but current security models offer only **flat RBAC** ("can this agent use this tool?") or
    **prompt-level guardrails** that are brittle and non-auditable.

    This creates a critical **governance gap**: probabilistic LLM decisions must be grounded by
    **non-repudiable identity**, **contextual risk awareness**, and **formal logic verification**
    — all *before* any tool is executed. No single access-control layer is sufficient.
    """)

    rq1, rq2, rq3 = st.columns(3)
    with rq1:
        st.info(
            "### RQ1: Layered Value\n"
            "Does a composable governance stack (RBAC → ABAC → TRAC) provide "
            "measurably superior security over any single layer alone?"
        )
    with rq2:
        st.info(
            "### RQ2: Formal Logic\n"
            "Can a deterministic, typed predicate layer (TRAC) provide a "
            "reproducible safety floor over probabilistic LLM inferences?"
        )
    with rq3:
        st.info(
            "### RQ3: Auditability\n"
            "Does PALADIN produce complete predicate traces sufficient for "
            "post-hoc audit of every tool-use decision? "
            "*(Evidence: trace logs in the Post-Experiment Lab detail every predicate "
            "evaluation per task.)*"
        )

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # Governance Layers Defined
    # ════════════════════════════════════════════════════════════════════
    st.header("📖 Governance Layers Defined")
    st.markdown(
        "PALADIN composes three governance layers that ask progressively richer "
        "questions of every tool-invocation request. Each layer catches a class "
        "of failure the previous layer has no language to express. Examples "
        "below are drawn from the **ASTRA dataset** (8 MCP domains: "
        "`atlassian`, `azure`, `grafana`, `hummingbot-mcp`, `mongodb`, "
        "`notion`, `stripe`, `wikipedia-mcp`)."
    )

    d1, d2, d3 = st.columns(3)
    with d1:
        st.success(
            "### 1️⃣ RBAC\n"
            "**Role-Based Access Control**\n\n"
            "*Reasons over:* `(persona, tool_id)`\n\n"
            '> *"Is this agent\'s role allowed to use this tool?"*\n\n'
            "**✅ Catches** — a `marketing_analyst` invoking "
            "`stripe.refunds.create`: not in role → DENY.\n\n"
            "**❌ Cannot catch** — a `finance_ops` persona who *is* "
            "permitted to call `stripe.refunds.create` but issues the "
            "refund at 3 AM, against a `wikipedia-mcp` task, or as part "
            "of an incoherent 3-tool bundle. Every tool is individually "
            "permitted; RBAC waves it through."
        )
    with d2:
        st.success(
            "### 2️⃣ ABAC\n"
            "**Attribute-Based Access Control**\n\n"
            "*Reasons over:* `(persona, tool, context)` — time, "
            "risk tier, MFA, source domain, action class.\n\n"
            '> *"Under the current conditions, may this action proceed?"*\n\n'
            "**✅ Catches** — a `dba` calling `mongodb.create-collection` "
            "from an unauthorized environment, or `azure.azmcp-group-list` "
            "outside business hours: contextual predicate fires → DENY.\n\n"
            "**❌ Cannot catch** — all three tools in a bundle pass "
            "every contextual rule, yet the *bundle as a whole* doesn't "
            "accomplish (or actively misaccomplishes) the task. ABAC "
            "still reasons one (subject, object, context) triple at a "
            "time — it has no view of the bundle."
        )
    with d3:
        st.success(
            "### 3️⃣ TRAC\n"
            "**Task-Relational Access Control** *(formerly TRAC)*\n\n"
            "*Reasons over:* the **entire bundle** + **task domain** "
            "via agnostic typed predicates "
            "(`HardCapabilityMissing` = bundle not in the task's domain, "
            "`ContainsDelete ∧ ¬ContainsReadBeforeWrite`). Action class is derived "
            "deterministically from the tool name + description by a VerbNet-grounded "
            "classifier; the rules are expressible in standard OPA/Rego.\n\n"
            '> *"Does this set of tools coherently and safely accomplish '
            'this task?"*\n\n'
            "**✅ Catches** — bundle-level incoherence that is invisible "
            "to RBAC/ABAC (see worked examples below).\n\n"
            "**Why \"predicate-hierarchical\"** — derived predicates feed "
            "downstream rules, forming a DAG over the predicate signature "
            "(e.g. `ElevatedRisk` is derived by one rule and consumed as a "
            "guard by alignment/isolation rules; capability coverage is "
            "evaluated over the *set* of bundle tools and the *set* of "
            "task-required capabilities). RBAC/ABAC predicates are "
            "first-order over a single (subject, object, context) triple "
            "and cannot express this."
        )

    st.markdown("##### 🔎 Worked examples from ASTRA — where TRAC is the only layer that fires")

    ex1, ex2, ex3 = st.columns(3)
    with ex1:
        st.info(
            "**Wrong-domain bundle** *(`null` tag)*\n\n"
            "**Task:** *Check the history of adjustments in the quarterly "
            "financial review tasks on Jira and set up a tracking issue…*\n\n"
            "**LLM picked:** `hummingbot-mcp` "
            "→ `[get_orders, place_order, explore_controllers]` "
            "(a crypto-trading MCP).\n\n"
            "- **RBAC:** ALLOW (trading persona has these tools)\n"
            "- **ABAC:** ALLOW (no contextual rule fires)\n"
            "- **TRAC:** **DENY** — `capability_coverage` "
            "(a crypto bundle does not operate in the task's `atlassian` "
            "domain). `write_safety` would also raise an **advisory alert** if a "
            "destructive op had no preceding read."
        )
    with ex2:
        st.info(
            "**Wrong-domain selection** *(`wrong` tag)*\n\n"
            "**Task:** *Create a tracking issue for the release in Jira…* "
            "(targets `atlassian`).\n\n"
            "**LLM picked:** `grafana` → `[list_alert_rules, query_prometheus]` "
            "— right idea, wrong domain.\n\n"
            "- **RBAC:** ALLOW (SRE persona has Grafana)\n"
            "- **ABAC:** ALLOW (read-only, right environment)\n"
            "- **TRAC:** **DENY** — `capability_coverage` "
            "(the task's domain is `atlassian:read`; the bundle only "
            "provides `grafana:read` — wrong domain)."
        )
    with ex3:
        st.info(
            "**Destructive without read** *(advisory)*\n\n"
            "**Task:** *Clear out the deprecated records from the staging "
            "database…*\n\n"
            "**LLM picked:** `mongodb` → "
            "`[drop-database, delete-many]` — no verifying read.\n\n"
            "- **RBAC:** ALLOW (DBA persona)\n"
            "- **ABAC:** ALLOW (no time/risk gate fires)\n"
            "- **TRAC:** **ADVISORY ALERT** — `write_safety` "
            "(destructive `delete-many` with no preceding read). Flagged for "
            "review/escalation but **not auto-blocked**: a legitimately-requested "
            "cleanup is deterministically indistinguishable from a dangerous one."
        )

    st.caption(
        "💡 The `wrong` + `null` rows in ASTRA are precisely **RBAC-"
        "passable but task-incoherent** bundles — a class of failure that "
        "only emerges with LLM-driven tool composition. TRAC catches the "
        "deterministically-checkable subset (wrong-domain capability gaps and "
        "unsafe writes); same-domain selection errors remain the model's to own."
    )

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # Technical Novelty
    # ════════════════════════════════════════════════════════════════════
    st.header("💡 Novelty: What Makes PALADIN Different")

    nov1, nov2 = st.columns(2)
    with nov1:
        st.markdown("""
        **1. Composable Layered Governance**

        Unlike flat RBAC systems, PALADIN enforces three complementary security layers
        with distinct failure modes — each catching threats the others miss:

        | Layer | Catches | Real ASTRA example |
        |---|---|---|
        | **RBAC** | Role-tool mismatch | `marketing` persona invoking `stripe.refunds.create` |
        | **ABAC** | Contextual violation | `dba` calling `mongodb.create-collection` from an unauthorized environment |
        | **TRAC** | Bundle-level incoherence | Jira task answered with a `hummingbot-mcp` crypto bundle (domain mismatch + write-without-read) |

        Our ablation experiments prove each layer provides **irreplaceable value** —
        removing any one leaves exploitable gaps.
        """)

    with nov2:
        st.markdown("""
        **2. TRAC: Task-Relational Access Control (TRAC)**

        TRAC doesn't just ask *"Can this agent use this tool?"* — it asks:
        > *"Does the selected tool bundle satisfy the mission's capability requirements
        > with correct domain alignment?"*

        **Key innovations:**
        - **Agnostic capability model** — a capability is simply `{domain}:{action}`
          (the tool's MCP + read/write); no per-MCP vocabulary, catalog or tool map.
        - **VerbNet-grounded action** — read/write/destructive from one Levin/VerbNet/
          FrameNet lexicon (validated 100% write · 98.8% destructive vs MCP annotations).
        - **2 enforcing + 2 advisory** — `capability_coverage` & `tool_relevance` *enforce*;
          `write_safety` & `action_coherence` *advise* (alert without blocking).
        - **Corroborated coverage** — a domain-mismatch denial is reversed when the tools
          are strongly task-relevant (BM25), recovering legitimate work at near-zero
          security cost (a measured Pareto improvement).
        - **Rules-as-data** — predicates run identically in Python and standard OPA/Rego.
        - **Complete predicate traces** — every decision is formally auditable.
        """)

    nov3, nov4 = st.columns(2)
    with nov3:
        st.markdown("""
        **3. OPA Baseline Validation**

        PALADIN runs **policy-as-code on the CNCF-graduated Open Policy Agent (OPA)**.
        Following OPA's Document Model, policy logic lives in **generic Rego** while the
        RBAC / ABAC / TRAC rules are loaded as **`data` documents** — the same YAML the
        Python engines read, with no code generation:

        - **Rule equivalence** — real `opa eval` matches the Python RBAC / ABAC / TRAC
          decisions with **0 mismatches**
        - **Single source of truth** — editing a rule (or Policy Studio) updates both
          Python and OPA at once
        - **Layered advantage** — TRAC's deterministic capability / destructiveness
          predicates add an auditable safety-net over the flat allow/deny model

        The generic Rego policies + the data documents live in `policies/rego/` and
        `policies/`, and are shown — with a one-click **Verify parity** and an optional
        live OPA server — in **🛡️ Policy Studio**.
        """)

    with nov4:
        st.markdown("""
        **4. Mission-Permission Decoupling**

        Unlike every existing RBAC/ABAC framework — which asks *"Is this caller allowed
        to invoke this tool?"* — PALADIN evaluates tool selections against **task intent
        and capability requirements**, not just caller identity.

        TRAC predicates verify that the *selected tool bundle* satisfies the
        *mission's capability profile*: correct domain alignment and sufficient action
        coverage — independently of who the caller is.
        This means a legitimately authorized agent can still be denied if its tool
        choice is wrong *for the task at hand*, closing a class of over-privilege
        vulnerabilities that identity-only models cannot detect.
        """)

    st.caption(
        "**Limitations:** directional cross-vendor evidence (GPT-4o, GPT-5.4, Gemini-2.5-Pro, "
        "GPT-3.5-turbo-16k — no open-weight model yet), purpose-built dataset (ASTRA), and no "
        "production-scale latency benchmarks. See paper §8 for full discussion."
    )

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # Headline Results
    # ════════════════════════════════════════════════════════════════════
    st.header("📈 Headline Results")
    st.markdown(
        "Evaluation matrix: **1,157 ASTRA tasks × 6 SPIFFE personas = 6,942 decisions** per model "
        "(leak-free `d_inf` domain inference — no ground-truth domain)."
    )
    res1, res2 = st.columns(2)
    with res1:
        st.markdown("""
        **Security comes from the stack, not the model**

        The deterministic stack (RBAC ∧ ABAC ∧ TRAC) holds **security-failure rate ≤ 1%** on
        **all four** models at the full pipeline (E1). The **LLM alone** (E4) swings
        **28 – 100 %** — *56 – 170× worse*. Identity + attributes + task-relational logic, not
        the probabilistic model, deliver the safety floor.

        **Layered ablation (each layer is irreplaceable)** — removing any layer reopens a gap;
        the unified sign convention is Δ\u2098(Sₖ) = metric(Π) − metric(Π∖Sₖ).
        """)
    with res2:
        st.markdown("""
        **Operating-point sweep** (gpt-4o validation, SecFail / eligible-correct admission):

        | Point | Config | SecFail | Admit |
        |---|---|---|---|
        | **OP1** | full stack (headline) | **0.5 %** | 2.2 % |
        | OP2 | + deception→ALLOW | 2.7 % | 10.2 % |
        | OP6 | LLM only (E4) | 28.0 % | 50.2 % |

        Pareto frontier **OP1 → OP2 → OP6** (OP1 F1 = 0.856).

        **RA-ICL (BM25 retrieval)** lifts exact tool-selection **10.3 % → 39.1 %** (3.8×);
        paired ΔSecFail = −0.046 (bootstrap CI excludes 0).
        """)
    st.caption(
        "**Corroborated coverage** (this build, default `PALADIN_CAPCOV_RESCUE=4.0`): a Pareto "
        "tweak — eligible-correct admission 43.3 % → 43.9 %, TRAC over-denials 242 → 231, at "
        "+0.1 pp SecFail (−2 catches). Tunable/reversible via env (`=0` restores the prior point)."
    )

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # Governance Pipeline Architecture
    # ════════════════════════════════════════════════════════════════════
    st.header("🏗️ Governance Pipeline")

    st.image("assets/paladin_pipeline.png", use_container_width=True)

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # Data & Policy Foundations
    # ════════════════════════════════════════════════════════════════════
    st.header("📦 Data & Policy Foundations")
    st.markdown("""
    PALADIN's governance decisions are grounded in **9 policy and data layers**,
    each independently configurable through the Policy Studio. Together they form the
    complete security context for every agentic decision.
    """)

    # Row 1: ASTRA + Identity
    st.subheader("🔬 Evaluation Baseline")
    base_col1, base_col2 = st.columns(2)
    with base_col1:
        task_count = len(tasks)
        tag_counts = {}
        for t in tasks:
            tag_counts[t.match_tag] = tag_counts.get(t.match_tag, 0) + 1
        mcp_domains = len(set(m for t in tasks for m in t.candidate_mcp))

        st.markdown(f"""
        **ASTRA Dataset** — *Agentic Security Tool Recommendation Assessment*

        The primary evaluation benchmark containing curated agentic tasks with
        groundtruth tool bundles across heterogeneous MCP domains.

        | Property | Value |
        |---|---|
        | Total Tasks | **{task_count:,}** |
        | MCP Domains | **{mcp_domains}** |
        | Correct (aligned) | **{tag_counts.get('correct', 0):,}** |
        | Wrong (adversarial) | **{tag_counts.get('wrong', 0):,}** |
        | Null (untagged) | **{tag_counts.get('null', 0):,}** |
        | Tools per task | **3** (standardized) |
        """)

    with base_col2:
        persona_count = len(personas)
        total_tools = sum(len(p.tools) for p in personas)
        st.markdown(f"""
        **MCP Domain Catalog** — *Tool Provider Registry*

        The set of MCP server domains that define available tools, their
        descriptions, and capability scope. Each domain represents a distinct
        tooling provider (e.g., Atlassian, GitHub, MongoDB).

        | Property | Value |
        |---|---|
        | MCP Domains | **{persona_count}** |
        | Total Tools | **{total_tools:,}** |
        | Examples | Grafana, Atlassian, GitHub, Slack, Hummingbot, MongoDB, etc. |

        **Loaded Domains:**
        {', '.join(f'`{p.name}`' for p in sorted(personas, key=lambda x: x.name))}
        """)

    st.markdown("---")

    # Row 2: Identity & Transport (Pre-LLM)
    st.subheader("🔐 Identity & Transport (Pre-LLM Gates)")
    id_col1, id_col2 = st.columns(2)
    with id_col1:
        _render_policy_card(
            "1️⃣ SPIFFE Registry",
            "Cryptographic identity anchoring for every agentic caller. Maps SPIFFE IDs "
            "to roles, trust scores, clearance levels, and organizational attributes.",
            "policies/spiffe_registry.json",
            [
                ("Purpose", "Non-repudiable agent identification"),
                ("Protocol", "SPIFFE (Secure Production Identity Framework)"),
                ("ID Format", "`spiffe://demo.local/agent/{name}`"),
            ]
        )
    with id_col2:
        _render_policy_card(
            "2️⃣ Transport Allowlist",
            "Controls which SPIFFE identities are permitted to submit requests. "
            "Acts as a first-pass gate before any inference occurs.",
            "policies/spiffe_allowlist.json",
            [
                ("Purpose", "Pre-LLM identity gate"),
                ("Effect", "DENY if caller not in allowlist"),
                ("Scope", "All callers must pass before Phase II"),
            ]
        )

    st.markdown("---")

    # Row 3: RBAC + ABAC + MCP Attributes
    st.subheader("⚖️ Authorization Layers (Post-LLM)")
    auth_col1, auth_col2, auth_col3 = st.columns(3)
    with auth_col1:
        _render_policy_card(
            "3️⃣ MCP Attributes",
            "Risk metadata for each MCP server — risk levels, compliance tiers, "
            "data sensitivity, and trust boundaries.",
            "policies/mcp_attributes.yaml",
            [
                ("Purpose", "Resource attributes for ABAC evaluation"),
                ("Examples", "risk_level: high, sensitivity: PII"),
            ]
        )
    with auth_col2:
        _render_policy_card(
            "4️⃣ RBAC Policies",
            "Role-based access control — maps each persona role to permitted "
            "MCP domains and tools. Supports wildcard (`*`) grants.",
            "policies/rbac.yaml",
            [
                ("Purpose", "Identity → tool permission mapping"),
                ("Catches", "Wrong persona accessing wrong domain"),
                ("Impact", "Primary denial source (~93% of denials)"),
            ]
        )
    with auth_col3:
        _render_policy_card(
            "5️⃣ ABAC Rules",
            "Attribute-based contextual rules — evaluates and **enforces** decisions based on "
            "subject, resource, action, and environment attributes.",
            "policies/abac_rules.yaml",
            [
                ("Purpose", "Context-aware access enforcement"),
                ("Catches", "After-hours writes, low-trust high-risk ops"),
                ("Impact", "Independent enforcement layer between RBAC and TRAC"),
            ]
        )

    st.markdown("---")

    # Row 4: Semantic Grounding
    st.subheader("🧬 Semantic Grounding (Capability Layer)")
    sem_col1, sem_col2, sem_col3 = st.columns(3)
    with sem_col1:
        _render_policy_card(
            "6️⃣ Domain Catalog",
            "Maps tools to their MCP domain and action types. Provides the "
            "structural foundation for capability inference.",
            "policies/domain_capability_catalog.json",
            [
                ("Purpose", "Tool → domain → action classification"),
                ("Content", "Tool names, action types, MCP mappings"),
            ]
        )
    with sem_col2:
        _render_policy_card(
            "7️⃣ Capability Ontology",
            "Defines the relationship between task intents and required capabilities. "
            "Used to verify that selected tools can actually fulfill the mission.",
            "policies/domain_capability_ontology.json",
            [
                ("Purpose", "Intent → required capabilities mapping"),
                ("Key concept", "Capability coverage score (0–100%)"),
                ("Effect", "Missing hard caps → coverage violation"),
            ]
        )
    with sem_col3:
        _render_policy_card(
            "8️⃣ Action Lexicon",
            "VerbNet/Levin/FrameNet-grounded verb lexicon — classifies every tool as "
            "read / write / destructive from its name + MCP description. Agnostic: no per-MCP "
            "vocabulary, no name-prefix rules, no per-tool action map.",
            "app/services/verb_action_classifier.py",
            [
                ("Purpose", "Single source for tool action read/write/destructive"),
                ("Method", "Levin/VerbNet/FrameNet verb classes + read-guard"),
                ("Feeds", "ABAC contains_write/destructive · TRAC write_safety"),
            ]
        )

    st.markdown("---")

    # Row 5: TRAC
    st.subheader("🧠 Formal Logic Layer")
    tsphol_col1, tsphol_col2 = st.columns([2, 1])
    with tsphol_col1:
        _render_policy_card(
            "9️⃣ TRAC Rules (TRAC)",
            "Task-Relational Access Control over the proposed tool bundle — a typed, ordered "
            "production-rule engine (implemented here as TRAC) that evaluates declarative "
            "predicates over the full context. Agnostic: a capability is just `{domain}:{action}` "
            "(the tool's MCP + read/write), so there is no per-MCP vocabulary. Every decision "
            "produces an auditable predicate trace.",
            "policies/trac_rules.yaml",
            [
                ("Purpose", "Task↔bundle assurance RBAC/ABAC structurally cannot express"),
                ("Rules", "4 — 2 enforcing (capability_coverage, tool_relevance), 2 advisory (write_safety, action_coherence)"),
                ("Domain check", "Leak-free BM25 task→domain + top-K gate (CAPCOV_TOPK)"),
                ("Corroborated coverage", "Rescues a domain-mismatch denial when tools are strongly task-relevant (BM25 ≥ 4.0) — Pareto win"),
                ("Action source", "VerbNet/Levin/FrameNet lexicon (read/write/destructive)"),
            ]
        )
    with tsphol_col2:
        st.markdown("""
        **TRAC Rule Examples:**

        ```yaml
        # ENFORCING: deny when the bundle is not in the
        # task's inferred domain (required {domain}:read absent)
        - name: capability_coverage
          condition: HardCapabilityMissing == true
          action: DENY
          enforce: true
          # corroborated rescue: reversed when mean tool↔task
          # BM25 ≥ 4.0  (+ CAPCOV_TOPK domain-membership gate)

        # ENFORCING: deny when the selected tools are
        # lexically irrelevant to the task (mean BM25 < 1.0)
        - name: tool_relevance
          condition: BundleToolsIrrelevant == true
          action: DENY
          enforce: true

        # ADVISORY: alert on a destructive op with no
        # preceding read (raises an alert, does NOT block)
        - name: write_safety
          condition: ContainsDelete == true
                     AND ContainsReadBeforeWrite == false
          action: DENY
          enforce: false
        ```
        """)

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # How to Use
    # ════════════════════════════════════════════════════════════════════
    st.header("🛠️ How to Use PALADIN")

    steps = [
        ("1. **Policy Studio**", "🛡️",
         "Configure and inspect all policy layers. Edit RBAC rules, ABAC conditions, "
         "TRAC rules, and agnostic read/write action rules. Changes take effect immediately."),
        ("2. **MCP Domain Explorer**", "🤖",
         "Browse the MCP server catalog — see available tools, descriptions, and "
         "capability scope for each domain."),
        ("3. **ASTRA Task Explorer**", "🔍",
         "Explore the evaluation dataset. Filter by MCP server, task category, and "
         "match tag. View groundtruth bundles and technical statistics."),
        ("4. **Prediction Lab**", "🔮",
         "Run individual tasks through the full governance pipeline. Select a persona, "
         "pick a task, and watch the decision flow through all phases with detailed "
         "predicate traces."),
        ("5. **Experiment LLM Lab**", "🧪",
         "Collect LLM inferences for every task — *selection* (the LLM picks the bundle) "
         "or *validation* (the LLM judges the candidate). Optional BM25 retrieval-augmented "
         "exemplars (K=25, 70/30 split). Saves an `llm_inference_v1` log; no governance runs here."),
        ("6. **Post-Experiment Lab**", "📊",
         "Re-derive the full RBAC · ABAC · TRAC stack over the recorded bundles — no new "
         "inference. Edit policies across all three layers and compare **baseline vs modified** "
         "(SecFail, legit-allow, per-rule firing, per-transaction traces)."),
    ]

    for title, icon, desc in steps:
        st.markdown(f"**{title}** — {desc}")

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # Current System State
    # ════════════════════════════════════════════════════════════════════
    st.header("📊 Current System State")

    # Key metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ASTRA Tasks", f"{len(tasks):,}")
    m2.metric("MCP Domains", f"{len(personas)}")
    m3.metric("Total Tools", f"{sum(len(p.tools) for p in personas):,}")

    # Experiment results if available
    results_path = os.path.join("datasets", "experiment_results.json")
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                exp_data = json.load(f)
            exp_count = len(exp_data.get("experiments", []))
            m4.metric("Experiments", f"{exp_count} configs")
        except Exception:
            m4.metric("Experiments", "—")
    else:
        m4.metric("Experiments", "Not run")

    # Match tag distribution
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Match Tag Distribution")
        df_tags = pd.DataFrame([{"Tag": t.match_tag} for t in tasks])
        counts = df_tags["Tag"].value_counts().reset_index()
        counts.columns = ["Tag", "Count"]
        chart_tags = alt.Chart(counts).mark_bar().encode(
            x=alt.X("Tag:N", sort="-y"),
            y=alt.Y("Count:Q"),
        ).properties(height=300).configure_view(strokeWidth=0)
        st.altair_chart(chart_tags, use_container_width=True)

    with col_right:
        st.subheader("Tools per MCP Domain")
        domain_tools = {}
        for p in personas:
            domain_tools[p.name] = len(p.tools)
        df_domains = pd.DataFrame(
            [{"Domain": k, "Tools": v} for k, v in sorted(domain_tools.items())]
        )
        chart_domains = alt.Chart(df_domains).mark_bar().encode(
            x=alt.X("Domain:N", sort="-y"),
            y=alt.Y("Tools:Q"),
        ).properties(height=300).configure_view(strokeWidth=0)
        st.altair_chart(chart_domains, use_container_width=True)

    # ── Footer ──
    st.markdown("---")
    st.caption(
        "© 2026 PALADIN — Policy-Aware Layered Agentic Decision Intelligence | "
        "Built for Advanced Agentic Security Research"
    )


def _render_policy_card(title: str, description: str, file_path: str,
                         properties: list):
    """Render a styled policy card with file status indicator."""
    exists = os.path.exists(file_path)
    status = "✅" if exists else "⚠️ Missing"

    st.markdown(f"**{title}** {status}")
    st.caption(description)
    for key, val in properties:
        st.markdown(f"- **{key}:** {val}", unsafe_allow_html=True)
