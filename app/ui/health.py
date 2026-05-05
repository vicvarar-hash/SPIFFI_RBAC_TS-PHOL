import streamlit as st
from typing import List
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona

def render_health(tasks: List[AstraTask], personas: List[MCPPersona], mcp_errors: List[str]):
    st.title("🏥 Data Health / Validation")
    
    st.markdown("### Validation Summary")
    
    # MCP Domain Validation
    st.markdown("#### MCP Domain Files")
    persona_names = [p.name for p in personas]
    duplicates = [name for name in set(persona_names) if persona_names.count(name) > 1]
    
    if duplicates:
        st.error(f"Duplicate MCP Domain names found: {', '.join(duplicates)}")
    else:
        st.success("No duplicate MCP Domain names found.")
        
    if mcp_errors:
        st.warning(f"Metadata errors encountered in {len(mcp_errors)} files:")
        for err in mcp_errors:
            st.text(f"• {err}")
    else:
        st.success("All MCP domain files loaded and parsed correctly.")
        
    # ASTRA Task Validation
    st.markdown("#### ASTRA Dataset")
    missing_match_tag = [i for i, t in enumerate(tasks) if not t.match_tag or t.match_tag == "unknown"]
    if missing_match_tag:
        st.warning(f"{len(missing_match_tag)} tasks have missing or unknown match tags.")
    else:
        st.success("All task records contain a valid match tag.")
        
    # Stats Table
    st.markdown("---")
    st.markdown("### Technical Statistics")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("**ASTRA Statistics**")
        st.table({
            "Metric": ["Total Tasks", "Tasks with Predictions", "Tasks with Groundtruth"],
            "Count": [len(tasks), len([t for t in tasks if t.candidate_tools]), len([t for t in tasks if t.groundtruth_tools])]
        })
        
    with col2:
        st.write("**MCP Statistics**")
        total_tools = sum(len(p.tools) for p in personas)
        st.table({
            "Metric": ["Total Personas", "Total Available Tools", "Avg Tools per Persona"],
            "Count": [len(personas), total_tools, round(total_tools/len(personas), 2) if personas else 0]
        })
