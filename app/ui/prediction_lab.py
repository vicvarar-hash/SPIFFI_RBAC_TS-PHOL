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
from app.services.spiffe_workload_service import SpiffeWorkloadService

def render_prediction_lab(tasks: List[AstraTask], personas: List[MCPPersona]):
    st.title("🔮 Parallel reasoning lab")
    
    st.markdown("""
    Select an ASTRA task to trigger dual-mode reasoning and run the **Unified Decision Engine**:
    1. **LLM-ResM (Selection)**: Predict **exactly 3 pairs** of (Tool, MCP) from the catalog.
    2. **Validation**: Evaluate the **proposed candidate bundle** from the ASTRA dataset.
    """)
    
    # 5: Initialize Intent & Inference for Selection
    from app.services.intent_engine import IntentEngine
    from app.services.capability_inference_service import CapabilityInferenceService
    inference_svc = CapabilityInferenceService()
    intent_engine = IntentEngine(inference_svc=inference_svc)
    
    # Initialize core services
    llm = LLMProvider()
    predictor = PredictionService(llm, personas, intent_engine=intent_engine)
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
        
        # SPIFFE Workload Identity Hook
        workload_svc = SpiffeWorkloadService()
        real_id, id_source = workload_svc.fetch_real_identity()
        
        with col_c1:
            # Map for simulation
            display_to_id = {}
            for label, data in caller_map.items():
                display_to_id[label] = data["spiffe_id"]
            
            sim_options = list(caller_map.keys())
            
            # Combine with Real Identity Option if available
            final_options = sim_options.copy()
            real_option = "🛡️ Use Real SPIFFE Identity"
            if real_id:
                final_options.insert(0, real_option)
                
            selected_caller_label = st.selectbox("Caller Identity (Authentication Source)", final_options, index=0 if final_options else None)
            
            if selected_caller_label == real_option:
                caller_spiffe_id = real_id
                # Find display name for real ID
                caller_display_name = "Unknown Persona"
                for label, data in caller_map.items():
                    if data["spiffe_id"] == real_id:
                        caller_display_name = data["display_name"]
                        break
                st.caption(f"Connected to SPIRE: `{real_id}`")
                id_source = "SPIRE Workload API"
            elif selected_caller_label:
                caller_spiffe_id = caller_map[selected_caller_label]["spiffe_id"]
                caller_display_name = caller_map[selected_caller_label]["display_name"]
                id_source = "Simulated"
            else:
                caller_spiffe_id = "spiffe://unknown"
                caller_display_name = "Unknown"
                id_source = "None"
        
            st.session_state["current_identity_source"] = id_source
            
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
            
            st.divider()
            # New Iteration 4F: Mode Selection
            selected_mode = st.radio("Experiment Mode", ["Selection (LLM-ResM)", "Validation"], horizontal=True)
            st.session_state["experiment_mode"] = selected_mode
        
        # Dataset Context (ASTRA Candidates & Groundtruth)
        with st.expander("View Dataset Context (ASTRA Validation Details)", expanded=False):
            col_cand, col_gt = st.columns(2)
            with col_cand:
                if selected_mode == "Validation":
                    st.markdown("### 🧪 Candidate Bundle")
                    st.write("**Candidate MCPs:**")
                    st.json(task.candidate_mcp)
                    st.write("**Candidate Tools:**")
                    st.json(task.candidate_tools)
                else:
                    st.markdown("### 🧪 Candidate Bundle")
                    st.info("Hidden in Selection Mode to prevent leakage.")
                    
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
                
                # Context Bundle for Audit
                experiment_context = {
                    "mode": selected_mode,
                    "caller_label": selected_caller_label,
                    "spiffe_id": caller_spiffe_id,
                    "id_source": id_source,
                    "mcp_filter": selected_mcp_filter,
                    "category_filter": selected_filter,
                    "task_index": task_idx_in_filtered,
                    "task_category": task.match_tag
                }

                # 1. Selection Pipeline
                if selected_mode.startswith("Selection"):
                    sel_pre_llm = decision_engine.pre_llm_check(caller_spiffe_id, None, None)
                    if sel_pre_llm["passed"]:
                        selection = predictor.run_selection(task)
                        sel_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, selection.selected_mcp, selection.selected_tools)
                        sel_raw = {}
                        try:
                            if selection.raw_output: sel_raw = json.loads(selection.raw_output)
                        except: pass
                        sel_decision = decision_engine.evaluate(sel_pre_llm, caller_spiffe_id, selection.selected_mcp, selection.selected_tools, selection.confidence, sel_raw, task.task, mode="selection", mcp_filter=selected_mcp_filter)
                        sel_decision.llm_executed = True
                        sel_decision.llm_output = {"selected_mcp": selection.selected_mcp, "selected_tools": selection.selected_tools, "confidence": selection.confidence, "justification": selection.justification}
                    else:
                        selection = SelectionResult(selected_mcp=[], selected_tools=[], justification="Skipped due to Pre-LLM block", confidence=0.0, raw_output=None)
                        sel_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, [], [])
                        sel_decision = decision_engine.evaluate(sel_pre_llm, caller_spiffe_id, [], [], 0.0, {}, task.task)
                        sel_decision.llm_executed = False
                    
                    sel_ctx = sel_decision.model_dump()
                    sel_ctx["caller_display_name"] = caller_display_name
                    sel_ctx["benchmark_result"] = sel_comparison.status
                    sel_ctx["identity_source"] = id_source
                    sel_ctx["experiment_context"] = experiment_context
                    
                    logger.log_prediction("selection", task_idx_in_filtered, task.task, selection.model_dump(), sel_comparison.model_dump())
                    logger.log_decision(task_idx_in_filtered, "selection", selection.model_dump(), sel_ctx)
                    
                    # Display Single Panel
                    st.header("🧠 Selection (LLM-ResM)")
                    with st.container(border=True):
                        if sel_decision.llm_executed:
                            st.subheader("🧠 LLM Inference Summary")
                            st.write("**Predicted MCPs:**")
                            st.json(selection.selected_mcp)
                            st.write("**Predicted Tools:**")
                            st.json(selection.selected_tools)
                            st.markdown(f"**Confidence:** `{selection.confidence}`")
                            st.markdown(f"**Capability Coverage Score:** `{selection.capability_coverage_score}`")
                            if selection.missing_capabilities:
                                st.warning(f"⚠️ **Missing Capabilities:** {', '.join(selection.missing_capabilities)}")
                            else:
                                st.success("✅ **Sufficient Capability Coverage**")
                            st.markdown(f"**Justification:** {selection.justification}")
                        else:
                            st.warning("⚠️ LLM INFERENCE SKIPPED: Pre-LLM checks failed.")
                        st.divider()
                        _render_decision_panel(sel_decision, sel_comparison, caller_display_name, "sel")

                # 2. Validation Pipeline
                elif selected_mode == "Validation":
                    val_pre_llm = decision_engine.pre_llm_check(caller_spiffe_id, task.candidate_mcp, task.candidate_tools)
                    if val_pre_llm["passed"]:
                        validation = validator.run_validation(task)
                        val_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, task.candidate_mcp, task.candidate_tools)
                        val_raw = {}
                        try:
                            if validation.raw_output: val_raw = json.loads(validation.raw_output)
                        except: pass
                        val_decision = decision_engine.evaluate(val_pre_llm, caller_spiffe_id, task.candidate_mcp, task.candidate_tools, validation.confidence, val_raw, task.task, mode="validation", mcp_filter=selected_mcp_filter)
                        val_decision.llm_executed = True
                        val_decision.llm_output = {
                            "is_valid": validation.is_valid, 
                            "confidence": validation.confidence, 
                            "reason": validation.reason, 
                            "issues": validation.issues,
                            "issue_codes": validation.issue_codes,
                            "expected_domain": validation.expected_domain,
                            "actual_domain": validation.actual_domain,
                            "task_alignment_score": validation.task_alignment_score,
                            "task_alignment_details": validation.task_alignment_details # 4O: Transparency
                        }
                    else:
                        validation = ValidationResult(is_valid=False, confidence=0.0, reason="Skipped due to Pre-LLM block", issues=["SKIPPED"], raw_output=None)
                        val_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, task.candidate_mcp, task.candidate_tools)
                        val_decision = decision_engine.evaluate(val_pre_llm, caller_spiffe_id, task.candidate_mcp, task.candidate_tools, 0.0, {}, task.task)
                        val_decision.llm_executed = False
                    
                    val_ctx = val_decision.model_dump()
                    val_ctx["caller_display_name"] = caller_display_name
                    val_ctx["benchmark_result"] = val_comparison.status
                    val_ctx["identity_source"] = id_source
                    val_ctx["experiment_context"] = experiment_context
                    
                    logger.log_prediction("validation", task_idx_in_filtered, task.task, validation.model_dump(), val_comparison.model_dump())
                    logger.log_decision(task_idx_in_filtered, "validation", validation.model_dump(), val_ctx)
                    
                    # Display Single Panel
                    st.header("🛡️ Validation Mode")
                    with st.container(border=True):
                        if val_decision.llm_executed:
                            st.subheader("🧠 LLM Inference Summary")
                            st.write("**Validated MCPs:**")
                            st.json(task.candidate_mcp)
                            st.write("**Validated Tools:**")
                            st.json(task.candidate_tools)
                            st.markdown(f"**Confidence:** `{validation.confidence}`")
                        else:
                            st.warning("⚠️ LLM INFERENCE SKIPPED: Pre-LLM checks failed.")
                        st.divider()
                        _render_decision_panel(val_decision, val_comparison, caller_display_name, "val")
                        
                        # 4M: Task/Bundle Alignment Audit
                        st.divider()
                        st.subheader("🚦 Task/Bundle Alignment Audit")
                        
                        v_out = val_decision.llm_output or {}
                        col_a1, col_a2, col_a3 = st.columns(3)
                        
                        # 4R: Transparency
                        alignment_eval = val_decision.context.get("tsphol_predicate_set", {}).get("AlignmentEvaluated", False)
                        eval_icon = "✅" if alignment_eval else "❌"
                        
                        col_a1.metric("Expected Domain", v_out.get("expected_domain", "Uncertain"))
                        col_a2.metric("Actual Domain", v_out.get("actual_domain", "Uncertain"))
                        
                        score_label = f"Alignment Score ({eval_icon} Evaluated)"
                        col_a3.metric(score_label, f"{v_out.get('task_alignment_score', 0.0):.2f}")
                        
                        # 4S: Alignment Breakdown (Components)
                        components = val_decision.context.get("alignment_components", {})
                        if components:
                            with st.expander("📊 Alignment Breakdown (Weighted Audit)", expanded=True):
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Domain (40%)", f"{components.get('domain_score', 0.0):.2f}")
                                c2.metric("Capability (40%)", f"{components.get('capability_score', 0.0):.2f}")
                                c3.metric("Semantic (20%)", f"{components.get('semantic_score', 0.0):.2f}")
                                
                                st.caption("Formula: `0.4*Domain + 0.4*Cap + 0.2*Semantic`")

                        if v_out.get("issue_codes"):
                            st.write("**Validation Issue Codes:**")
                            st.info(", ".join(v_out.get("issue_codes", [])))
                        
                        if v_out.get("actual_domain") != v_out.get("expected_domain") and v_out.get("expected_domain") != "Uncertain":
                            st.warning("⚠️ Domain Mismatch Detected")
                        elif v_out.get("task_alignment_score", 1.0) < 0.4:
                            st.error("❌ Critical Low Alignment")
                        else:
                            st.success("✅ Mission Alignment Verified")
                
                with st.expander("📄 Raw Model Outputs & Details", expanded=False):
                    st.subheader("📋 Context Initialization Audit")
                    st.json(experiment_context)
                    
                    if selected_mode.startswith("Selection"):
                        st.divider()
                        st.subheader("Selection Inference Details")
                        st.write("**Inference Justification:**", selection.justification)
                        st.write("**Comparison Result:**")
                        st.json(sel_comparison.model_dump())
                        st.write("**Detailed Logical Predicates:**")
                        st.json(sel_decision.context)
                    else:
                        st.divider()
                        st.subheader("Validation Inference Details")
                        st.write("**Inference Reason:**", validation.reason)
                        st.write("**Detected Issues:**")
                        st.json(validation.issues)
                        st.write("**Detailed Logical Predicates:**")
                        st.json(val_decision.context)

def _render_decision_panel(decision: DecisionResult, comparison: Any, caller_display_name: str, key_prefix: str = ""):
    st.subheader("🚦 Execution Pipeline")
    
    # Block A: Benchmark Evaluation
    st.markdown("#### A. Benchmark Evaluation")
    st_color = {"exact_match": "green", "partial_match": "orange", "mismatch": "red"}.get(comparison.status, "gray")
    st.markdown(f"**Status:** :{st_color}[{comparison.status.upper()}]")
    st.caption(comparison.details)
    cols_b = st.columns(2)
    cols_b[0].metric("MCP Match", "MATCH" if comparison.mcp_match else "MISMATCH")
    cols_b[1].metric("Tool Match", "MATCH" if comparison.tool_match else "MISMATCH")
    
    st.divider()
    
    # Block B: Identity & Transport
    st.markdown("#### B. Identity & Transport")
    
    # Render caller and source
    st.write(f"**Caller:** {caller_display_name}")
    st.code(decision.spiffe_id)
    
    # Attempt to pull from session state to display real identity badge
    _id_source = st.session_state.get("current_identity_source", "Simulated")
    if "api" in _id_source.lower() or "real" in _id_source.lower():
        st.success(f"**Source:** {_id_source}  \n🛡️ Real SPIFFE Identity")
    else:
        st.info(f"**Source:** {_id_source}")
    
    id_status = decision.evaluation_states.get("identity", "NOT_EVALUATED")
    tr_status = decision.evaluation_states.get("transport", "NOT_EVALUATED")
    
    cols_i = st.columns(2)
    cols_i[0].metric("Registry Verified", "YES" if id_status == "ALLOW" else "NO")
    cols_i[1].metric("mTLS Allowed", "YES" if tr_status == "ALLOW" else ("NO" if tr_status == "DENY" else "NOT EVALUATED"))
    
    if decision.denial_source in ["Identity", "Transport"]:
        st.error(f"Execution halted at {decision.denial_source}.")
        
    st.divider()

    # Block C: RBAC Authorization (Iteration 4V Expanded)
    st.markdown("#### C. RBAC Authorization")
    rbac_status = decision.evaluation_states.get("rbac", "NOT_EVALUATED")
    rbac_audit = decision.context.get("rbac_evaluation", {})
    
    st.metric("RBAC Allowed", "✅ Yes" if rbac_status == "ALLOW" else ("❌ No" if rbac_status == "DENY" else "NOT EVALUATED"))
    
    if rbac_audit:
        with st.expander("⚖️ RBAC Reasoning Trace", expanded=(rbac_status == "DENY")):
            st.markdown(f"**Matched Rule:** `{rbac_audit.get('matched_rule')}`")
            st.markdown(f"**Decision:** `{rbac_audit.get('decision')}`")
            st.markdown(f"**Reason:** {rbac_audit.get('reason')}")
            
            trace_data = rbac_audit.get("rbac_trace", [])
            if trace_data:
                import pandas as pd
                df_rbac = pd.DataFrame(trace_data)
                # Select and rename columns for cleaner display
                df_disp = df_rbac[["tool", "mcp", "decision", "policy", "reason"]].copy()
                df_disp.columns = ["Tool Name", "MCP Server", "Decision", "Policy ID", "Reason"]
                
                # Apply color styling (optional, but good for UX)
                st.table(df_disp)
            else:
                st.caption("No per-tool trace available.")
    
    if rbac_status == "DENY":
        st.error(f"Denial Reason: {decision.reason}")
        
    st.divider()

    # Block D: Fact Extraction & Audit (Iteration 4G)
    st.markdown("#### D. Fact Extraction & Audit (4G)")
    
    # 1. Tool Audit Table
    audit_data = decision.context.get("tool_audit", [])
    aggregates = decision.context.get("tool_aggregates", {})
    intent = decision.context.get("intent_decomposition", {})
    
    with st.expander("🔍 Domain-Aware Predicate Audit", expanded=True):
        if audit_data:
            import pandas as pd
            df = pd.DataFrame(audit_data)
            # 4T Hide abstract capabilities from audit table
            from app.services.domain_capability_ontology import DomainCapabilityOntology
            df["capabilities"] = df["capabilities"].apply(lambda caps: [c for c in caps if DomainCapabilityOntology.is_concrete(c)])
            
            df_disp = df[["tool", "source", "actions", "capabilities", "notes"]].copy()
            df_disp.columns = ["Tool Name", "Source", "Action Classes", "Capabilities", "Notes"]
            st.table(df_disp)
            
            # Summary Metrics
            m_cols = st.columns(5)
            m_cols[0].metric("Detected Domain", intent.get("domain", "GENERAL").upper())
            m_cols[1].metric("Read-Before-Write", "YES" if aggregates.get("ContainsReadBeforeWrite") else "NO")
            m_cols[2].metric("Dominant", aggregates.get("DominantActionType", "unknown").upper())
            m_cols[3].metric("Multi-Domain", "YES" if aggregates.get("MultiDomain") else "NO")
            m_cols[4].metric("Risk Level", decision.context.get("tsphol_predicate_set", {}).get("HighestRiskLevel", "low").upper())
        else:
            st.info("No tool audit data available (Pre-LLM or Baseline only).")

    # 2. Intent & Baseline
    col_ib1, col_ib2 = st.columns([2, 1])
    
    with col_ib1:
        with st.expander("🧠 Intent Decomposition", expanded=True):
            if intent:
                st.markdown(f"**Domain Context:** `{intent.get('domain', 'GENERAL')}`")
                st.markdown(f"**Primary Intent:** `{intent.get('primary_intent')}`")
                st.markdown(f"**Secondary Intents:** {', '.join(intent.get('secondary_intents', [])) or 'None'}")
                
                # 4W: Minimal Sufficient Coverage Split
                task_reqs = decision.context.get("task_required_capabilities", [])
                task_opts = decision.context.get("task_optional_capabilities", [])
                
                st.info(f"**Required Mission Capabilities:** {', '.join(task_reqs) or 'None'}")
                if task_opts:
                    st.caption(f"**Optional Enrichment Capabilities:** {', '.join(task_opts)}")
            else:
                st.info("Intent not decomposed.")
                
    with col_ib2:
        with st.expander("⚖️ ABAC Baseline (Advisory)", expanded=True):
            abac = decision.context.get("abac_baseline", {})
            if abac:
                abac_decision = abac.get("decision", "NOT_EVALUATED")
                st_color = "green" if abac_decision == "ALLOW" else "red"
                st.markdown(f"**Result:** :{st_color}[{abac_decision}]")
                st.caption(f"Rule: {abac.get('matched_rule')}")

                # 6C: Enriched ABAC Reasoning Trace
                if "reasoning_trace" in abac:
                    st.divider()
                    st.markdown("**⚖️ ABAC Reasoning Trace**")
                    trace = abac["reasoning_trace"]
                    
                    app_label = "YES" if abac.get("applicable") else "NO"
                    st.markdown(f"**Applicable:** `{app_label}`")
                    st.markdown(f"**Matched Rule:** `{abac.get('matched_rule')}`")
                    
                    if abac.get("decision") == "ALLOW":
                        st.success(f"**Allow Reason:** {abac.get('allow_reason', 'Passed baseline')}")
                    else:
                        st.error(f"**Failure Reason:** {abac.get('failure_reason', 'Denied by policy')}")
                    
                    st.markdown("**Logic Steps:**")
                    for step in trace.get("logic_steps", []):
                        icon = "✅ Match" if step["matched"] else "❌ No Match"
                        st.caption(f"{icon}: {step['condition']}")
            else:
                st.info("ABAC not evaluated.")

    # 3. Required Capability Audit (New 4H)
    st.markdown("##### 🧪 Required Capability Audit (4H)")
    metadata = intent.get("required_capability_metadata", [])
    if metadata:
        from app.services.domain_capability_ontology import DomainCapabilityOntology
        # Filter out abstract capabilities from provenance view for cleanliness
        visible_metadata = [m for m in metadata if DomainCapabilityOntology.is_concrete(m["capability"])]
        
        if visible_metadata:
            with st.expander("View Requirement Provenance"):
                for m in visible_metadata:
                    icon = "✅" if m["status"] == "ACCEPTED" else ("⚠️" if m["status"] == "FILTERED" else "❌")
                    status = m["status"]
                    source = m["source"]
                    cap = m["capability"]
                    conf = m.get("confidence", 1.0)
                    reason = m.get("reason", "")
                    priority = f"[{m.get('priority', 'REQUIRED')}]"
                    
                    st.markdown(f"{icon} {priority} **{cap}**")
                    st.caption(f"↳ Source: {source} | Status: {status} | Conf: {conf} | {reason}")
        else:
            st.caption("No concrete capability requirements derived.")
    # 4. 🧠 Task Capability Requirements (Iteration 4Q: Mission vs. Mechanism)
    st.divider()
    st.markdown("#### 🧠 Task Capability Requirements (4Q Audit)")
    
    req_caps = set(decision.context.get("task_required_capabilities", []))
    opt_caps = set(decision.context.get("task_optional_capabilities", []))
    has_caps = set(decision.context.get("has_capabilities", []))
    all_mentioned = req_caps.union(has_caps).union(opt_caps)
    
    if all_mentioned:
        comp_data = []
        for cap in sorted(list(all_mentioned)):
            is_req = cap in req_caps
            is_opt = cap in opt_caps
            is_has = cap in has_caps
            
            # Simple status icon
            if is_req: status = "✅ Satisfied" if is_has else "❌ MISSING"
            elif is_opt: status = "✅ Provided" if is_has else "ℹ️ Missing (Optional)"
            else: status = "➕ Extra"
            
            comp_data.append({
                "Capability": cap,
                "Minimal (Required)": "Yes" if is_req else "No",
                "Optional (Enrichment)": "Yes" if is_opt else "No",
                "Provided (Tools)": "Yes" if is_has else "No",
                "Status": status
            })
        st.table(comp_data)
        
        # Error Summary (Only for Required)
        missing_req = req_caps - has_caps
        missing_opt = opt_caps - has_caps
        
        if missing_req:
            st.error(f"⚠️ **Mission Critical Failure:** The following minimal required capabilities are missing: `{', '.join(missing_req)}`")
        else:
            st.success("✨ **Sufficient Capability Alignment:** All minimal mission requirements are present in the bundle.")
            
        if missing_opt:
            st.info(f"ℹ️ **Optional Enrichment Missing:** `{', '.join(missing_opt)}` (This does not affect authorization).")
    else:
        st.info("No capability requirements or provisions detected.")

    st.divider()

    # Block E: TS-PHOL Final Authority
    st.markdown("#### E. TS-PHOL Final Authority")
    tsphol_status = decision.evaluation_states.get("tsphol", "NOT_EVALUATED")
    if tsphol_status == "NOT_EVALUATED":
        st.info("Status: NOT EVALUATED (Prior RBAC Block)")
    else:
        with st.expander("🔍 Logical Predicate Trace", expanded=True):
            st.markdown("**1. Base & Derived Predicates**")
            # 4T: Filter abstract predicates for visible trace
            from app.services.domain_capability_ontology import DomainCapabilityOntology
            base_p = decision.context.get("tsphol_predicate_set", {})
            clean_p = {}
            for k, v in base_p.items():
                if k.startswith("_"): continue
                
                # Filter capability sets
                if k in ["RequiredCapabilities", "HasCapabilities"] and isinstance(v, (set, list)):
                    v = sorted([c for c in v if DomainCapabilityOntology.is_concrete(c)])
                elif isinstance(v, (set, list)): 
                    v = sorted(list(v))
                
                clean_p[k] = v
            st.json(clean_p)
            
            st.markdown("**2. TS-PHOL Rule Evaluation Audit (4K)**")
            summary = decision.context.get("tsphol_summary", {})
            if summary:
                c1, c2, c3 = st.columns(3)
                c1.metric("Rules Evaluated", summary.get("evaluated_rules", 0))
                c2.metric("Rules Triggered", summary.get("triggered_rules", 0))
                
                # Check for both possible keys (fix for KeyError)
                f_status = summary.get("final_status") or summary.get("final_decision", "UNKNOWN")
                c3.metric("Final Status", f_status)
            
            l_trace = decision.context.get("tsphol_logic_trace", [])
            if l_trace:
                for entry in l_trace:
                    with st.container(border=True):
                        # Result column-like layout
                        r1, r2 = st.columns([4, 1])
                        with r1:
                            st.markdown(f"**Rule:** `{entry['rule']}`")
                        with r2:
                            if entry["passed"]: st.success("✔ Passed")
                            else: st.error("✖ Triggered")
                            
                        st.caption(f"↳ Reasoning: {entry['reason']}")
                        if entry.get("derived"):
                            st.info(f"🧬 Derived: `{entry['derived']}`")
                        
                        # Show trigger indicator if applicable
                        if entry["triggered"]:
                            icon = "🔴" if entry["action"] == "DENY" else "🟢"
                            st.caption(f"{icon} Action triggered: {entry['action']}")
            else:
                st.info("No rules evaluated.")
                
            # 4L: Positive Findings Display
            findings = summary.get("positive_findings", [])
            if findings:
                st.divider()
                st.markdown("**✅ Positive Findings**")
                for f in findings:
                    st.success(f"↳ {f}")

        st.metric("Final TS-PHOL Decision", tsphol_status, delta="Authority Layer", delta_color="off")
        if decision.denial_source == "TS-PHOL":
            st.error(f"Denial Reason: {decision.reason}")
        
    st.divider()

    # Block F: Final Decision
    st.markdown("#### F. Final Result")
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
