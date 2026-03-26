import streamlit as st
from typing import List
from app.models.mcp import MCPPersona

def render_mcp_explorer(personas: List[MCPPersona]):
    st.title("🤖 MCP Persona Explorer")
    
    persona_names = sorted([p.name for p in personas])
    selected_name = st.selectbox("Select MCP Persona", persona_names)
    
    persona = next(p for p in personas if p.name == selected_name)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"Persona: {persona.name}")
        if persona.description:
            st.markdown(f"**Description:**  \n{persona.description}")
        else:
            st.write("No description provided.")
            
    with col2:
        st.info(f"**Source File:** `{persona.source_file}`")
        st.info(f"**Risk Level:** `{persona.risk_level.title()}`")
        st.info(f"**Available Tools:** `{len(persona.tools)}`")
        
    st.markdown("---")
    st.subheader("Tools Inventory")
    
    if not persona.tools:
        st.write("No tools defined for this persona.")
    else:
        for tool in persona.tools:
            with st.expander(f"🛠️ {tool.name}"):
                if tool.description:
                    st.markdown("**Description:**")
                    st.write(tool.description)
                
                if tool.input_schema:
                    st.write("**Input Schema:**")
                    st.json(tool.input_schema)
                else:
                    st.write("No input schema defined.")
