import streamlit as st
from typing import List, Any
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
from app.services.mcp_risk_service import MCPRiskService
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
    risk_svc = MCPRiskService()
    
    decision_engine = DecisionEngine(
        registry_svc=registry_svc,
        allowlist_svc=allowlist_svc,
        rbac_svc=rbac_svc,
        tsphol_svc=tsphol_svc,
        risk_svc=risk_svc,
        personas=personas
    )
    
    # Task Selection & Context Panel
    with st.container(border=True):
        st.subheader("📋 Context Initialization")
        
        # Caller simulation mapping
        registry = registry_svc.get_all()
        caller_options = []
        caller_map = {}
        for key, details in registry.items():
            disp_name = details.get("display_name", key)
            spiffe_id = details.get("spiffe_id", "")
            label = f"{disp_name} ({spiffe_id})"
            caller_options.append(label)
            caller_map[label] = {"spiffe_id": spiffe_id, "display_name": disp_name}
            
        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            selected_caller_label = st.selectbox("Simulate Caller Identity", caller_options, index=0 if caller_options else None)
            if selected_caller_label:
                caller_spiffe_id = caller_map[selected_caller_label]["spiffe_id"]
                caller_display_name = caller_map[selected_caller_label]["display_name"]
            else:
                caller_spiffe_id = "spiffe://unknown"
                caller_display_name = "Unknown"
            
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
                from app.models.selection import SelectionResult
                from app.models.validation import ValidationResult
                import json
                
                # 0. Pre-LLM Checks
                sel_pre_llm = decision_engine.pre_llm_check(caller_spiffe_id, None, None)
                val_pre_llm = decision_engine.pre_llm_check(caller_spiffe_id, task.candidate_mcp, task.candidate_tools)

                # 1. Selection Pipeline
                if sel_pre_llm["passed"]:
                    selection = predictor.run_selection(task)
                    sel_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, selection.selected_mcp, selection.selected_tools)
                    sel_raw = {}
                    try:
                        if selection.raw_output: sel_raw = json.loads(selection.raw_output)
                    except: pass
                    sel_decision = decision_engine.evaluate(sel_pre_llm, caller_spiffe_id, selection.selected_mcp, selection.selected_tools, selection.confidence, sel_raw, task.task)
                    sel_decision.llm_executed = True
                    sel_decision.llm_output = {"selected_mcp": selection.selected_mcp, "selected_tools": selection.selected_tools, "confidence": selection.confidence, "justification": selection.justification}
                else:
                    selection = SelectionResult(selected_mcp=[], selected_tools=[], justification="Skipped due to Pre-LLM block", confidence=0.0, raw_output=None)
                    sel_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, [], [])
                    sel_decision = decision_engine.evaluate(sel_pre_llm, caller_spiffe_id, [], [], 0.0, {}, task.task)
                    sel_decision.llm_executed = False

                # 2. Validation Pipeline
                if val_pre_llm["passed"]:
                    validation = validator.run_validation(task)
                    val_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, task.candidate_mcp, task.candidate_tools)
                    val_raw = {}
                    try:
                        if validation.raw_output: val_raw = json.loads(validation.raw_output)
                    except: pass
                    val_decision = decision_engine.evaluate(val_pre_llm, caller_spiffe_id, task.candidate_mcp, task.candidate_tools, validation.confidence, val_raw, task.task)
                    val_decision.llm_executed = True
                    val_decision.llm_output = {"is_valid": validation.is_valid, "confidence": validation.confidence, "reason": validation.reason, "issues": validation.issues}
                else:
                    validation = ValidationResult(is_valid=False, confidence=0.0, reason="Skipped due to Pre-LLM block", issues=["SKIPPED"], raw_output=None)
                    val_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, task.candidate_mcp, task.candidate_tools)
                    val_decision = decision_engine.evaluate(val_pre_llm, caller_spiffe_id, task.candidate_mcp, task.candidate_tools, 0.0, {}, task.task)
                    val_decision.llm_executed = False
                
                # Log results
                sel_ctx = sel_decision.model_dump()
                sel_ctx["caller_display_name"] = caller_display_name
                sel_ctx["benchmark_result"] = sel_comparison.status
                
                val_ctx = val_decision.model_dump()
                val_ctx["caller_display_name"] = caller_display_name
                val_ctx["benchmark_result"] = val_comparison.status
                
                logger.log_prediction("selection", task_idx_in_filtered, task.task, selection.model_dump(), sel_comparison.model_dump())
                logger.log_prediction("validation", task_idx_in_filtered, task.task, validation.model_dump(), val_comparison.model_dump())
                
                logger.log_decision(task_idx_in_filtered, "selection", selection.model_dump(), sel_ctx)
                logger.log_decision(task_idx_in_filtered, "validation", validation.model_dump(), val_ctx)
                
                # Display Dual Panels
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.header("🧠 Selection (LLM-ResM)")
                    with st.container(border=True):
                        if sel_decision.llm_executed:
                            st.subheader("🧠 LLM Inference Summary")
                            st.write("**Predicted MCPs:**")
                            st.json(selection.selected_mcp)
                            st.write("**Predicted Tools:**")
                            st.json(selection.selected_tools)
                            st.markdown(f"**Confidence:** `{selection.confidence}`")
                            st.markdown(f"**Justification:** {selection.justification}")
                            
                            if selection.validation_errors:
                                st.error("❌ Validation Issues:")
                                for err in selection.validation_errors:
                                    st.write(f"- {err}")
                        else:
                            st.warning("⚠️ LLM INFERENCE SKIPPED: Pre-LLM checks failed.")
                        st.divider()
                        
                        # Decision Panel
                        _render_decision_panel(sel_decision, sel_comparison, caller_display_name)

                with col_right:
                    st.header("🛡️ Validation Mode")
                    with st.container(border=True):
                        if val_decision.llm_executed:
                            st.subheader("🧠 LLM Inference Summary")
                            st.write("**Validated MCPs:**")
                            st.json(task.candidate_mcp)
                            st.write("**Validated Tools:**")
                            st.json(task.candidate_tools)
                            st.markdown(f"**Confidence:** `{validation.confidence}`")
                            st.markdown(f"**Reason:** {validation.reason}")
                            
                            if validation.issues:
                                st.warning("🔎 Identified Issues:")
                                for issue in validation.issues:
                                    st.write(f"- {issue}")
                        else:
                            st.warning("⚠️ LLM INFERENCE SKIPPED: Pre-LLM checks failed.")
                        st.divider()
                        
                        # Decision Panel
                        _render_decision_panel(val_decision, val_comparison, caller_display_name)

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

def _render_decision_panel(decision: DecisionResult, comparison: Any, caller_display_name: str):
    st.subheader("🚦 Execution Pipeline")
    
    # Block A: Benchmark Evaluation
    st.markdown("#### A. Benchmark Evaluation")
    st_color = {"exact_match": "green", "partial_match": "orange", "mismatch": "red"}.get(comparison.status, "gray")
    st.markdown(f"**Status:** :{st_color}[{comparison.status.upper()}]")
    st.caption(comparison.details)
    cols_b = st.columns(2)
    cols_b[0].metric("MCP Match", "✅" if comparison.mcp_match else "❌")
    cols_b[1].metric("Tool Match", "✅" if comparison.tool_match else "❌")
    
    st.divider()
    
    # Block B: Identity & Transport
    st.markdown("#### B. Identity & Transport")
    st.write(f"**Caller:** {caller_display_name}  \n`{decision.spiffe_id}`")
    
    id_status = decision.evaluation_states.get("identity", "NOT_EVALUATED")
    tr_status = decision.evaluation_states.get("transport", "NOT_EVALUATED")
    
    cols_i = st.columns(2)
    cols_i[0].metric("Registry Verified", "✅" if id_status == "ALLOW" else "❌")
    cols_i[1].metric("mTLS Allowed", "✅" if tr_status == "ALLOW" else ("❌" if tr_status == "DENY" else "NOT EVALUATED"))
    
    if decision.denial_source in ["Identity", "Transport"]:
        st.error(f"Execution halted at {decision.denial_source}.")
        
    st.divider()

    # Block C: RBAC Authorization
    st.markdown("#### C. RBAC Authorization")
    rbac_status = decision.evaluation_states.get("rbac", "NOT_EVALUATED")
    st.metric("RBAC Allowed", "✅ Yes" if rbac_status == "ALLOW" else ("❌ No" if rbac_status == "DENY" else "NOT EVALUATED"))
    if decision.denial_source == "RBAC":
        st.error(f"Denial Reason: {decision.reason}")
        
    st.divider()

    # Block D: TS-PHOL Decision
    st.markdown("#### D. TS-PHOL Reasoning")
    tsphol_status = decision.evaluation_states.get("tsphol", "NOT_EVALUATED")
    if tsphol_status == "NOT_EVALUATED":
        st.info("Status: NOT EVALUATED")
    else:
        st.markdown("**⚙️ Derived Runtime Features**")
        st.json(decision.derived_features or {})
        st.metric("TS-PHOL Execution", tsphol_status.upper())
        if decision.denial_source == "TS-PHOL":
            st.error(f"Denial Reason: {decision.reason}")
            
    st.divider()

    # Block E: Final Decision
    st.markdown("#### E. Final Result")
    color_map = {"ALLOW": "green", "DENY": "red"}
    bg_color = color_map.get(decision.final_decision, "gray")
    
    st.markdown(f"""
    <div style="background-color: {bg_color}; padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 10px;">
        <h2 style="color: white; margin: 0;">{decision.final_decision}</h2>
    </div>
    """, unsafe_allow_html=True)
    
    st.info(f"**Pipeline Conclusion:** {decision.reason}")
    
    with st.expander("View Logic Trace"):
        for step in decision.trace:
            if "❌" in step or "DENY" in step:
                st.error(step)
            elif "⚠️" in step or "FLAG" in step:
                st.warning(step)
            elif "✅" in step or "ALLOW" in step:
                st.success(step)
            else:
                st.info(step)
