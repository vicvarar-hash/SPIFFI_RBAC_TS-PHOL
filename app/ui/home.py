import streamlit as st
from typing import List
import pandas as pd
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona

def render_home(tasks: List[AstraTask], personas: List[MCPPersona]):
    # 🚀 Hero Header
    st.markdown("""
        <div style="background-color: #f0f2f6; padding: 30px; border-radius: 15px; margin-bottom: 25px; border-left: 8px solid #4A90E2;">
            <h1 style="color: #1E3A5F; margin: 0;">🛡️ SPIFFI RBACK Research Portal</h1>
            <p style="font-size: 1.2rem; color: #4A5568;">Secure Policy-driven Inference for Federated Identity in Agentic Tool Orchestration</p>
        </div>
    """, unsafe_allow_html=True)

    # 🧐 Section 1: Research Objectives
    st.header("🧐 Problem Statement & Research Questions")
    st.markdown("""
    Modern autonomous agents operate in open, federated ecosystems using protocols like **MCP**. This creates a critical "Security Gap" where 
    probabilistic AI decisions must be grounded by non-repudiable identity and deterministic logic.
    """)
    
    rq1, rq2, rq3 = st.columns(3)
    with rq1:
        st.info("### RQ1: Identity\nHow can federated identity (SPIFFE) anchor autonomous tool-use in a non-repudiable way?")
    with rq2:
        st.info("### RQ2: Logic\nCan Tractable Scoped Probabilistic Higher-Order Logic (TS-PHOL) provide a deterministic safety floor for probabilistic LLM inferences?")
    with rq3:
        st.info("### RQ3: Semantics\nWhat is the impact of semantic grounding on ABAC precision in cross-domain workflows?")

    st.divider()

    # 💡 Section 2: Technical Novelty
    st.header("💡 The Novelty: TS-PHOL")
    col_novelty, col_img = st.columns([2, 1])
    with col_novelty:
        st.markdown("""
        **Tractable Scoped Probabilistic Higher-Order Logic (TS-PHOL)** is our primary contribution.
        Unlike traditional RBAC which asks *"Can this user run this tool?"*, TS-PHOL asks:
        > *"Does the intent of this specific mission align with the security properties of the proposed tool bundle?"*
        
        **Key Features:**
        - **Mission-Permission Decoupling**: Safety is evaluated against the *task intent*, not just the identity.
        - **Predictive Hardening**: Safety is ensured *post-inference but pre-execution*.
        - **Semantic Grounding**: Dynamic classification of tools into capabilities like `MarketDataAnalysis` or `IssueUpdate`.
        """)
    with col_img:
        st.image("https://img.icons8.com/illustrations/external-pack-flat-icons-maxicons/512/external-logic-intelligence-and-intellect-pack-flat-icons-maxicons.png", use_container_width=True)

    st.divider()

    # 📚 Section 3: ASTRA Dataset
    st.header("📚 The ASTRA Dataset")
    st.markdown(f"""
    The **ASTRA Dataset** serves as our primary benchmark for evaluating the engine's precision.
    - **Total Corpus**: {len(tasks)} curated agentic tasks.
    - **Domains**: 9 Heterogeneous MCP Domains (Atlassian, Hummingbot, Wikipedia, MongoDB, etc.).
    - **Evaluations**: Dual-mode coverage for both **Selection** (Generative) and **Validation** (Discriminative) reasoning.
    """)
    
    st.divider()

    # 🛠️ Section 4: Quick Guide
    st.header("🛠️ How to Use this App")
    g1, g2, g3, g4 = st.columns(4)
    g1.markdown("#### 1. Identity\nGo to **Policy Studio** to explore agent personas and their SPIFFE attributes.")
    g2.markdown("#### 2. Policies\nConfigure **TS-PHOL** and **ABAC** rules to define the boundaries of safe tool-use.")
    g3.markdown("#### 3. Prediction\nUse the **Prediction Lab** to run a mission from the ASTRA dataset.")
    g4.markdown("#### 4. Audit\nExpand the **Verified Logic Trace** to see the formal mathematical proof of the decision.")

    st.divider()

    # 📊 Section 5: Current Operational Status
    st.header("📊 Current System State")
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Match Tag Distribution (ASTRA)")
        df_tags = pd.DataFrame([{"Tag": t.match_tag} for t in tasks])
        counts = df_tags["Tag"].value_counts()
        st.bar_chart(counts)
        
    with col_right:
        st.subheader("Loaded MCP Personas")
        persona_names = sorted([p.name for p in personas])
        # Display as columns to save vertical space
        p_cols = st.columns(2)
        for i, name in enumerate(persona_names):
            p_cols[i % 2].markdown(f"- `{name}`")

    # 🔗 Footer
    st.markdown("---")
    st.caption("© 2026 SPIFFI_RBACK_TS-PHOL Research Framework | Built for Advanced Agentic Coding")
