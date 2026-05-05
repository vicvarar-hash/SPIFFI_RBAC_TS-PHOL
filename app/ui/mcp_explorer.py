import streamlit as st
from typing import List
from app.models.mcp import MCPPersona, MCPTool
import json
import os

def render_mcp_explorer(personas: List[MCPPersona]):
    st.title("🤖 MCP Domain Explorer")
    
    # 6B: Use session state for persona selection and transient updates
    persona_names = sorted([p.name for p in personas])
    selected_name = st.selectbox("Select MCP Domain", persona_names)
    
    # Track the active persona in session state to allow modifications
    if 'mcp_edit_state' not in st.session_state or st.session_state.mcp_edit_state.name != selected_name:
        st.session_state.mcp_edit_state = next(p for p in personas if p.name == selected_name).model_copy(deep=True)
        
    persona = st.session_state.mcp_edit_state
    
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
        
        # 6B: Global Save Button
        from app.loaders.mcp_loader import save_mcp_persona
        if st.button("💾 Save All Changes to Disk", type="primary", use_container_width=True):
            mcp_dir = "mcp_servers"
            if save_mcp_persona(persona, mcp_dir):
                st.success(f"Changes persisted to `{persona.source_file}`")
                # 6B: Invalidate data cache so next reload pulls fresh JSON from disk
                st.cache_data.clear()
                # Update the main personas list in session state
                for i, p in enumerate(st.session_state.personas):
                    if p.name == persona.name:
                        st.session_state.personas[i] = persona.model_copy(deep=True)
                        break
                st.rerun()
            else:
                st.error("Failed to save changes.")
            
    st.markdown("---")
    
    # 6B: Tool Creation
    with st.expander("➕ Add New Tool to Persona", expanded=False):
        with st.form("new_tool_form", clear_on_submit=True):
            new_name = st.text_input("Tool Name (e.g. atlassian_create_issue)")
            new_desc = st.text_area("Description")
            new_schema_str = st.text_area("Input Schema (JSON)", value='{"type": "object", "properties": {}}')
            
            if st.form_submit_button("Add Tool to Inventory"):
                try:
                    schema = json.loads(new_schema_str)
                    # 6B: Use canonical field name 'input_schema'
                    new_tool = MCPTool(name=new_name, description=new_desc, input_schema=schema)
                    persona.tools.append(new_tool)
                    st.success(f"Tool `{new_name}` added to transient state. Remember to SAVE to disk.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Invalid JSON: {str(e)}")

    st.subheader("Tools Inventory")
    
    if not persona.tools:
        st.write("No tools defined for this persona.")
    else:
        for i, tool in enumerate(persona.tools):
            with st.expander(f"🛠️ {tool.name}"):
                with st.form(f"edit_tool_{i}"):
                    u_name = st.text_input("Tool Name", value=tool.name)
                    u_desc = st.text_area("Description", value=tool.description or "")
                    
                    # Schema Editor
                    curr_schema = json.dumps(tool.input_schema, indent=2) if tool.input_schema else "{}"
                    u_schema_str = st.text_area("Input Schema (JSON)", value=curr_schema, height=200)
                    
                    if st.form_submit_button("Update Tool Metadata"):
                        try:
                            tool.name = u_name
                            tool.description = u_desc
                            tool.input_schema = json.loads(u_schema_str)
                            st.success("Metadata updated in transient state.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Invalid JSON: {str(e)}")
                            
                # Deletion Button
                if st.button("🗑️ Delete Tool", key=f"del_{i}", type="secondary"):
                    persona.tools.pop(i)
                    st.warning(f"Tool `{tool.name}` removed from transient state. Remember to SAVE to disk.")
                    st.rerun()
