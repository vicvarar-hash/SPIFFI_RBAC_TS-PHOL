import streamlit as st
from typing import List
import pandas as pd
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
            "Does a composable governance stack (RBAC → ABAC → TS-PHOL) provide "
            "measurably superior security over any single layer alone?"
        )
    with rq2:
        st.info(
            "### RQ2: Formal Logic\n"
            "Can Typed Security Policy Higher-Order Logic (TS-PHOL) provide a "
            "deterministic safety floor for probabilistic LLM inferences, including "
            "deception routing?"
        )
    with rq3:
        st.info(
            "### RQ3: Auditability\n"
            "Can every agentic tool-use decision produce a complete, auditable "
            "predicate trace from identity through authorization to final verdict?"
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

        Unlike flat RBAC systems, PALADIN enforces three independent, non-overlapping
        security layers — each catching threats the others miss:

        | Layer | Catches | Example |
        |---|---|---|
        | **RBAC** | Identity mismatches | Finance agent → DevOps tools |
        | **ABAC** | Contextual risk | Right role but after-hours + high-risk write |
        | **TS-PHOL** | Logical inconsistency | Domain mismatch, capability gaps |

        Our ablation experiments prove each layer provides **irreplaceable value** —
        removing any one leaves exploitable gaps.
        """)

    with nov2:
        st.markdown("""
        **2. TS-PHOL: Typed Formal Logic for Agentic Security**

        TS-PHOL doesn't just ask *"Can this agent use this tool?"* — it asks:
        > *"Does the selected tool bundle satisfy the mission's capability requirements
        > with sufficient confidence and domain alignment?"*

        **Key innovations:**
        - **Post-inference, pre-execution** verification gate
        - **Deception routing** — a third enforcement mode beyond ALLOW/DENY
          that honeypots suspicious requests for threat intelligence
        - **Mission-permission decoupling** — safety evaluated against *task intent*,
          not just identity
        - **Complete predicate traces** — every decision is formally auditable
        """)

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # Governance Pipeline Architecture
    # ════════════════════════════════════════════════════════════════════
    st.header("🏗️ Governance Pipeline")
    st.markdown("""
    Every tool-use request flows through a **layered pipeline** where each layer independently
    evaluates and can deny or redirect the request:
    """)

    st.markdown("""
    ```
    ┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
    │  Phase I:        │     │  Phase II:        │     │  Phase III:       │
    │  Pre-LLM         │ ──► │  LLM Inference    │ ──► │  Post-LLM Logic   │
    │                  │     │                   │     │                   │
    │  ◆ SPIFFE ID     │     │  ◆ Tool Selection │     │  ◆ RBAC Check     │
    │  ◆ Registry      │     │  ◆ Confidence     │     │  ◆ ABAC Rules     │
    │  ◆ Allowlist     │     │  ◆ Justification  │     │  ◆ Fact Extraction│
    │                  │     │                   │     │  ◆ TS-PHOL Rules  │
    └─────────────────┘     └──────────────────┘     └──────────────────┘
                                                              │
                                                    ┌────────┼────────┐
                                                    ▼        ▼        ▼
                                                  ALLOW    DENY   DECEPTION
    ```
    """)

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
        **MCP Persona Catalog** — *Tool Provider Registry*

        The set of MCP server personas that define available tools, their
        descriptions, and domain scope. Each persona represents a distinct
        capability domain.

        | Property | Value |
        |---|---|
        | MCP Personas | **{persona_count}** |
        | Total Tools | **{total_tools:,}** |
        | Domains | Grafana, Atlassian, GitHub, Slack, Hummingbot, MongoDB, etc. |

        **Loaded Personas:**
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
            "Attribute-based contextual rules — evaluates combinations of "
            "subject, resource, action, and environment attributes.",
            "policies/abac_rules.yaml",
            [
                ("Purpose", "Context-aware access decisions"),
                ("Catches", "After-hours writes, low-trust high-risk ops"),
                ("Impact", "Catches ~6% of denials that RBAC misses"),
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
            "8️⃣ Heuristic Logic",
            "Fallback classification rules using verb-prefix matching and keyword "
            "detection for tools not covered by curated mappings.",
            "policies/heuristic_policy.json",
            [
                ("Purpose", "Tool classification when curated map missing"),
                ("Method", "Prefix matching (get_, list_, create_, delete_)"),
                ("Fallback", "Produces 'Unknown' caps → lower coverage"),
            ]
        )

    st.markdown("---")

    # Row 5: TS-PHOL
    st.subheader("🧠 Formal Logic Layer")
    tsphol_col1, tsphol_col2 = st.columns([2, 1])
    with tsphol_col1:
        _render_policy_card(
            "9️⃣ TS-PHOL Rules",
            "Typed Security Policy Higher-Order Logic — the formal rule engine that "
            "evaluates declarative security predicates over the full evaluation context. "
            "Each rule has typed conditions, a trigger action (ALLOW/DENY/DECEPTION), "
            "and produces an auditable evaluation trace.",
            "policies/tsphol_rules.yaml",
            [
                ("Purpose", "Formal logic safety verification"),
                ("Rules", "11 typed declarative rules"),
                ("Unique", "DECEPTION_ROUTED enforcement mode"),
                ("Key rules", "low_confidence_write, domain_mismatch, capability_violation, abac_failure_denial"),
                ("Impact", "Catches logical inconsistencies + routes 177 deceptions in E1"),
            ]
        )
    with tsphol_col2:
        st.markdown("""
        **TS-PHOL Rule Examples:**

        ```yaml
        # Block low-confidence write operations
        - name: low_confidence_write_prevention
          condition: ContainsWrite == true
                     AND ConfidenceValue < 0.70
          action: DENY

        # Route domain mismatches to honeypot
        - name: task_bundle_domain_mismatch
          condition: TaskBundleDomainMismatch == true
          action: DECEPTION_ROUTED

        # Propagate ABAC denials
        - name: abac_failure_denial
          condition: ABACDenied == true
          action: DENY
        ```
        """)

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # How to Use
    # ════════════════════════════════════════════════════════════════════
    st.header("🛠️ How to Use PALADIN")

    steps = [
        ("1. **Policy Studio**", "🛡️",
         "Configure and inspect all 9 policy layers. Edit RBAC rules, ABAC conditions, "
         "TS-PHOL logic, capability ontology, and more. Changes take effect immediately."),
        ("2. **MCP Persona Explorer**", "🤖",
         "Browse the MCP server catalog — see available tools, descriptions, and "
         "domain scope for each persona."),
        ("3. **ASTRA Task Explorer**", "🔍",
         "Explore the evaluation dataset. Filter by MCP server, task category, and "
         "match tag. View groundtruth bundles and technical statistics."),
        ("4. **Prediction Lab**", "🔮",
         "Run individual tasks through the full governance pipeline. Select a persona, "
         "pick a task, and watch the decision flow through all phases with detailed "
         "predicate traces."),
        ("5. **Experiment Lab**", "🧪",
         "Run batch experiments (E1–E4) with ablation analysis. Compare simulation "
         "vs real LLM inference. Explore the Access Decision Matrix (6,942 rows). "
         "Generate AI-powered assessments of results."),
    ]

    for title, icon, desc in steps:
        st.markdown(f"**{title}** — {desc}")

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # Current System State
    # ════════════════════════════════════════════════════════════════════
    st.header("📊 Current System State")

    # Key metrics row
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("ASTRA Tasks", f"{len(tasks):,}")
    m2.metric("MCP Personas", f"{len(personas)}")
    m3.metric("Total Tools", f"{sum(len(p.tools) for p in personas):,}")

    # Matrix stats if available
    matrix_path = os.path.join("datasets", "access_decision_matrix.json")
    if os.path.exists(matrix_path):
        try:
            with open(matrix_path, "r", encoding="utf-8") as f:
                matrix = json.load(f)
            row_count = len(matrix.get("rows", []))
            m4.metric("Matrix Rows", f"{row_count:,}")
        except Exception:
            m4.metric("Matrix Rows", "—")
    else:
        m4.metric("Matrix Rows", "Not generated")

    # Experiment results if available
    results_path = os.path.join("datasets", "experiment_results.json")
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                exp_data = json.load(f)
            exp_count = len(exp_data.get("experiments", []))
            m5.metric("Experiments", f"{exp_count} configs")
        except Exception:
            m5.metric("Experiments", "—")
    else:
        m5.metric("Experiments", "Not run")

    # Match tag distribution
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Match Tag Distribution")
        df_tags = pd.DataFrame([{"Tag": t.match_tag} for t in tasks])
        counts = df_tags["Tag"].value_counts()
        st.bar_chart(counts)

    with col_right:
        st.subheader("Tools per MCP Domain")
        domain_tools = {}
        for p in personas:
            domain_tools[p.name] = len(p.tools)
        df_domains = pd.DataFrame(
            [{"Domain": k, "Tools": v} for k, v in sorted(domain_tools.items())]
        ).set_index("Domain")
        st.bar_chart(df_domains)

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
