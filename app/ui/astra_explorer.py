import streamlit as st
from typing import List
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona

def render_astra_explorer(tasks: List[AstraTask], personas: List[MCPPersona] = None):
    st.title("🔍 ASTRA Task Explorer")

    # --- Filters ---
    st.markdown("### Filters")
    col_f1, col_f2, col_f3 = st.columns(3)

    # Collect all unique MCP servers and match tags
    all_mcps = sorted(set(mcp for t in tasks for mcp in t.candidate_mcp))
    all_tags = sorted(set(t.match_tag for t in tasks if t.match_tag))

    with col_f1:
        mcp_filter = st.selectbox("MCP Server", ["All"] + all_mcps, key="astra_mcp_filter")
    with col_f2:
        tag_filter = st.selectbox("Task Category (Match Tag)", ["All"] + all_tags, key="astra_tag_filter")
    with col_f3:
        search_text = st.text_input("Search task text", key="astra_search", placeholder="keyword...")

    # Apply filters
    filtered = tasks
    if mcp_filter != "All":
        filtered = [t for t in filtered if mcp_filter in t.candidate_mcp]
    if tag_filter != "All":
        filtered = [t for t in filtered if t.match_tag == tag_filter]
    if search_text.strip():
        filtered = [t for t in filtered if search_text.lower() in t.task.lower()]

    st.caption(f"Showing **{len(filtered)}** of {len(tasks)} tasks")
    st.markdown("---")

    if not filtered:
        st.warning("No tasks match the current filters.")
        return

    # --- Task Browser ---
    task_idx = st.number_input("Select Task (filtered)", min_value=0, max_value=len(filtered)-1, value=0)
    task = filtered[task_idx]

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

    # --- Technical Statistics (from Data Health) ---
    st.markdown("---")
    st.markdown("### 📊 Technical Statistics")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.write("**ASTRA Dataset**")
        missing_tags = len([t for t in tasks if not t.match_tag or t.match_tag == "unknown"])
        correct = len([t for t in tasks if t.match_tag == "correct"])
        wrong = len([t for t in tasks if t.match_tag == "wrong"])
        null_tags = len([t for t in tasks if t.match_tag == "null"])
        st.table({
            "Metric": ["Total Tasks", "Correct", "Wrong", "Null/Unknown", "With Candidates", "With Groundtruth"],
            "Count": [len(tasks), correct, wrong, null_tags + missing_tags,
                      len([t for t in tasks if t.candidate_tools]),
                      len([t for t in tasks if t.groundtruth_tools])]
        })

    with col_s2:
        if personas:
            st.write("**MCP Domains**")
            total_tools = sum(len(p.tools) for p in personas)
            st.table({
                "Metric": ["Total Domains", "Total Available Tools", "Avg Tools per Domain"],
                "Count": [len(personas), total_tools, round(total_tools / len(personas), 2) if personas else 0]
            })

        st.write("**MCP Distribution in Dataset**")
        from collections import Counter
        mcp_dist = Counter(mcp for t in tasks for mcp in t.candidate_mcp)
        st.table({
            "MCP Server": list(mcp_dist.keys()),
            "Tasks": list(mcp_dist.values())
        })
