import streamlit as st
from typing import List
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona
import pandas as pd

def render_home(tasks: List[AstraTask], personas: List[MCPPersona]):
    st.title("🏠 Home / Overview")
    
    st.markdown("""
    Welcome to the **SPIFFI_RBACK_TS-PHOL** research and demo platform. 
    This application is designed to showcase the integration of SPIFFE/SPIRE identity, RBAC, and TS-PHOL for agentic tool selection and authorization.
    """)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total ASTRA Tasks", len(tasks))
    with col2:
        st.metric("Total MCP Personas", len(personas))
    with col3:
        match_tags = [t.match_tag for t in tasks]
        correct_count = match_tags.count("correct")
        st.metric("Correct Tasks", correct_count)

    st.markdown("---")
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Match Tag Distribution")
        df_tags = pd.DataFrame([{"Tag": t.match_tag} for t in tasks])
        counts = df_tags["Tag"].value_counts()
        st.bar_chart(counts)
        
    with col_right:
        st.subheader("MCP Personas Overview")
        # Display as a pretty list in a box
        persona_names = sorted([p.name for p in personas])
        st.write("Loaded personas:")
        for name in persona_names:
            st.markdown(f"- {name}")
        
    st.markdown("---")
    st.subheader("Future Phases")
    cols = st.columns(4)
    with cols[0]:
        st.warning("Phase 2: SPIFFE/SPIRE")
        st.caption("Identity Attestation")
    with cols[1]:
        st.warning("Phase 2: RBAC")
        st.caption("Access Control Policies")
    with cols[2]:
        st.warning("Phase 3: TS-PHOL")
        st.caption("Probabilistic Reasoning")
    with cols[3]:
        st.warning("Phase 3: Evaluation")
        st.caption("Batch Performance Tracking")
