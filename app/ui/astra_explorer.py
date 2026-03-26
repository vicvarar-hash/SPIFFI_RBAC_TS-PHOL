import streamlit as st
from typing import List
from app.models.astra import AstraTask

def render_astra_explorer(tasks: List[AstraTask]):
    st.title("🔍 ASTRA Task Explorer")
    
    task_idx = st.number_input("Select Task Index", min_value=0, max_value=len(tasks)-1, value=0)
    task = tasks[task_idx]
    
    st.markdown(f"### Task {task_idx}")
    st.markdown(f"**Description:**")
    st.info(task.task)
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Candidate Prediction")
        st.write("**Target Tools:**")
        if task.candidate_tools:
            for tool in task.candidate_tools:
                st.markdown(f"- `{tool}`")
        else:
            st.write("None")
            
        st.write("**Target MCP Servers:**")
        if task.candidate_mcp:
            for mcp in task.candidate_mcp:
                st.markdown(f"- `{mcp}`")
        else:
            st.write("None")
        
    with col2:
        st.subheader("Groundtruth")
        st.write("**Correct Tools:**")
        if task.groundtruth_tools:
            for tool in task.groundtruth_tools:
                st.markdown(f"- `{tool}`")
        else:
            st.write("None")
            
        st.write("**Correct MCP Servers:**")
        if task.groundtruth_mcp:
            for mcp in task.groundtruth_mcp:
                st.markdown(f"- `{mcp}`")
        else:
            st.write("None")
            
    st.markdown("---")
    color = "green" if task.match_tag == "correct" else "orange"
    st.markdown(f"**Match Status:** :{color}[{task.match_tag.upper()}]")
