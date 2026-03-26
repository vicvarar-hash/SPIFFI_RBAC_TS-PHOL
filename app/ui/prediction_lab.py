import streamlit as st
from typing import List
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona
from app.models.decision import DecisionResult
from app.services.llm_provider import LLMProvider
from app.services.prediction_service import PredictionService
from app.services.validation_service import ValidationService
from app.services.comparison_service import ComparisonService
from app.services.logger_service import LoggerService

from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService
from app.services.decision_engine import DecisionEngine

def render_prediction_lab(tasks: List[AstraTask], personas: List[MCPPersona]):
    st.title("🔮 Parallel reasoning lab")
    
    st.markdown("""
    Select an ASTRA task to trigger dual-mode reasoning and run the **Unified Decision Engine**:
    1. **LLM-ResM (Selection)**: Predict **exactly 3 pairs** of (Tool, MCP) from the catalog.
    2. **Validation**: Evaluate the **proposed candidate bundle** from the ASTRA dataset.
    """)
    
    # Initialize core services
    llm = LLMProvider()
    predictor = PredictionService(llm, personas)
    validator = ValidationService(llm, personas)
    comparer = ComparisonService()
    logger = LoggerService()
    
    # Initialize Policy Services
    registry_svc = SpiffeRegistryService()
    allowlist_svc = SpiffeAllowlistService(registry_service=registry_svc)
    rbac_svc = RBACService()
    tsphol_svc = TSPHOLRuleService()
    
    decision_engine = DecisionEngine(
        registry_svc=registry_svc,
        allowlist_svc=allowlist_svc,
        rbac_svc=rbac_svc,
        tsphol_svc=tsphol_svc,
        personas=personas
    )
    
    # Task Selection & Context Panel
    with st.container(border=True):
        st.subheader("📋 Context Initialization")
        
        # Caller simulation
        registry = registry_svc.get_all()
        default_caller = registry.get("orchestrator", "spiffe://demo.local/app/orchestrator")
        caller_list = list(registry.values())
        if default_caller not in caller_list: caller_list.append(default_caller)
        
        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            caller_id = st.selectbox("Simulate Caller Identity", caller_list, index=0)
            
        # MCP Filtering logic
        available_mcps = set()
        for t in tasks:
            if t.groundtruth_mcp:
                available_mcps.update(t.groundtruth_mcp)
        available_mcps = sorted(list(available_mcps))
        mcp_filter_options = ["All"] + available_mcps
        
        with col_c1:
            selected_mcp_filter = st.selectbox("Filter by MCP Server", mcp_filter_options)
            
        # Apply MCP filter
        if selected_mcp_filter == "All":
            mcp_filtered_tasks = tasks
        else:
            mcp_filtered_tasks = [t for t in tasks if t.groundtruth_mcp and selected_mcp_filter in t.groundtruth_mcp]
            
        if not mcp_filtered_tasks:
            st.warning("No tasks match the selected MCP Server filter.")
            return

        # Category Filtering logic
        available_tags = sorted(list(set([t.match_tag if t.match_tag else "Null" for t in mcp_filtered_tasks])))
        filter_options = ["All"] + available_tags
        
        with col_c1:
            selected_filter = st.selectbox("Filter by Task Category", filter_options)
        
        # Apply Category filter
        if selected_filter == "All":
            filtered_tasks = mcp_filtered_tasks
        else:
            filtered_tasks = [t for t in mcp_filtered_tasks if (t.match_tag if t.match_tag else "Null") == selected_filter]
            
        if not filtered_tasks:
            st.warning("No tasks match the selected Task Category filter.")
            return

        with col_c2:
            task_idx_in_filtered = st.number_input(f"Task Index (0-{len(filtered_tasks)-1})", min_value=0, max_value=len(filtered_tasks)-1, value=0)
            task = filtered_tasks[task_idx_in_filtered]
            st.info(f"**Task Description:**  \n{task.task}")
            st.caption(f"Category: {task.match_tag if task.match_tag else 'Null'}")
        
        # Dataset Context (Candidates & Groundtruth)
        with st.expander("View Dataset Context (ASTRA Candidates & Groundtruth)", expanded=False):
            col_cand, col_gt = st.columns(2)
            with col_cand:
                st.markdown("### 🧪 Candidate Bundle")
                st.write("**Candidate MCPs:**")
                st.json(task.candidate_mcp)
                st.write("**Candidate Tools:**")
                st.json(task.candidate_tools)
            with col_gt:
                st.markdown("### 🎯 Groundtruth")
                st.write("**Groundtruth MCPs:**")
                st.json(task.groundtruth_mcp)
                st.write("**Groundtruth Tools:**")
                st.json(task.groundtruth_tools)
    
    # Execution Button
    if st.button("🚀 Run Execution Pipeline", use_container_width=True):
        if not llm.is_configured():
            st.error("OpenAI API Key is missing. Please check the sidebar settings.")
        else:
            with st.spinner("Executing LLM Reasoning & Policy Engine..."):
                # 1. Run LLM-ResM Selection
                selection = predictor.run_selection(task)
                sel_comparison = comparer.compare(
                    task.groundtruth_mcp, 
                    task.groundtruth_tools, 
                    selection.selected_mcp, 
                    selection.selected_tools
                )
                
                # 2. Run LLM Validation
                validation = validator.run_validation(task)
                val_comparison = comparer.compare(
                    task.groundtruth_mcp, 
                    task.groundtruth_tools, 
                    task.candidate_mcp, 
                    task.candidate_tools
                )
                
                # 3. Run Decision Engine
                sel_decision = decision_engine.evaluate(caller_id, selection.selected_mcp, selection.selected_tools, selection.confidence, sel_comparison.tool_match)
                val_decision = decision_engine.evaluate(caller_id, task.candidate_mcp, task.candidate_tools, validation.confidence, val_comparison.tool_match)

                
                # Log results
                logger.log_prediction("selection", task_idx_in_filtered, task.task, selection.model_dump(), sel_comparison.model_dump())
                logger.log_prediction("validation", task_idx_in_filtered, task.task, validation.model_dump(), val_comparison.model_dump())
                
                logger.log_decision(task_idx_in_filtered, "selection", selection.model_dump(), sel_decision.model_dump())
                logger.log_decision(task_idx_in_filtered, "validation", validation.model_dump(), val_decision.model_dump())
                
                # Display Dual Panels
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.header("🧠 Selection (LLM-ResM)")
                    with st.container(border=True):
                        st.subheader("Predicted Selections (Exactly 3)")
                        st.write("**Predicted MCPs:**")
                        st.json(selection.selected_mcp)
                        st.write("**Predicted Tools:**")
                        st.json(selection.selected_tools)
                        st.markdown(f"**Confidence:** `{selection.confidence}`")
                        
                        if selection.validation_errors:
                            st.error("❌ Validation Issues:")
                            for err in selection.validation_errors:
                                st.write(f"- {err}")
                        
                        st.divider()
                        
                        # Decision Panel
                        _render_decision_panel(sel_decision)

                with col_right:
                    st.header("🛡️ Validation Mode")
                    with st.container(border=True):
                        st.subheader("Evaluated ASTRA Bundle")
                        st.write("**Validated MCPs:**")
                        st.json(task.candidate_mcp)
                        st.write("**Validated Tools:**")
                        st.json(task.candidate_tools)
                        st.markdown(f"**Confidence:** `{validation.confidence}`")
                        
                        if validation.issues:
                            st.warning("🔎 Identified Issues:")
                            for issue in validation.issues:
                                st.write(f"- {issue}")
                                
                        st.divider()
                        
                        # Decision Panel
                        _render_decision_panel(val_decision)

                with st.expander("📄 Raw Model Outputs & Details"):
                    cols = st.columns(2)
                    with cols[0]:
                        st.subheader("Selection Mode Details")
                        st.write("Comparison:")
                        st.json(sel_comparison.model_dump())
                        st.write("Decision Context (Step-by-Step Metrics):")
                        if sel_decision.context:
                            st.json(sel_decision.context)
                    with cols[1]:
                        st.subheader("Validation Mode Details")
                        st.write("Comparison:")
                        st.json(val_comparison.model_dump())
                        st.write("Decision Context (Step-by-Step Metrics):")
                        if val_decision.context:
                            st.json(val_decision.context)

def _render_decision_panel(decision: DecisionResult):
    st.subheader("🚦 Security Decision Panel")
    
    # Badging
    color_map = {"ALLOW": "green", "DENY": "red"}
    bg_color = color_map.get(decision.final_decision, "gray")

    
    st.markdown(f"""
    <div style="background-color: {bg_color}; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 10px;">
        <h3 style="color: white; margin: 0;">FINAL DECISION: {decision.final_decision}</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # State flags
    cols = st.columns(4)
    cols[0].metric("SPIFFE", "✅" if decision.spiffe_verified else "❌")
    cols[1].metric("Transport", "✅" if decision.transport_allowed else "❌")
    cols[2].metric("RBAC", "✅" if decision.rbac_allowed else "❌")
    cols[3].metric("TS-PHOL", decision.tsphol_decision.upper())
    
    st.info(f"**Reason:** {decision.reason}")
    
    with st.expander("View Decision Trace"):
        for step in decision.trace:
            if "❌" in step or "DENY" in step:
                st.error(step)
            elif "⚠️" in step or "FLAG" in step:
                st.warning(step)
            elif "✅" in step or "ALLOW" in step:
                st.success(step)
            else:
                st.info(step)
