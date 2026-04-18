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
from app.services.mcp_attribute_service import MCPAttributeService
from app.services.decision_engine import DecisionEngine
from app.services.spiffe_workload_service import SpiffeWorkloadService
from app.services.reasoning_auditor import ReasoningAuditor

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
    auditor = ReasoningAuditor(llm)
    
    # Initialize Policy Services
    registry_svc = SpiffeRegistryService()
    allowlist_svc = SpiffeAllowlistService(registry_service=registry_svc)
    rbac_svc = RBACService()
    tsphol_svc = TSPHOLRuleService()
    attribute_svc = MCPAttributeService()
    
    decision_engine = DecisionEngine(
        registry_svc=registry_svc,
        allowlist_svc=allowlist_svc,
        rbac_svc=rbac_svc,
        tsphol_svc=tsphol_svc,
        attribute_svc=attribute_svc,
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
            
        # Reset results if task context changes
        context_key = f"{selected_mcp_filter}_{selected_filter}_{task_idx_in_filtered}_{selected_mode}"
        if st.session_state.get("last_context_key") != context_key:
            st.session_state["last_run_data"] = None
            st.session_state["last_context_key"] = context_key
        
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

                # Exec results container
                run_data = {"experiment_context": experiment_context}

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
                    
                    run_data.update({
                        "decision": sel_decision,
                        "inference": selection,
                        "comparison": sel_comparison
                    })

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
                            "task_alignment_details": validation.task_alignment_details
                        }
                    else:
                        validation = ValidationResult(is_valid=False, confidence=0.0, reason="Skipped due to Pre-LLM block", issues=["SKIPPED"], raw_output=None)
                        val_comparison = comparer.compare(task.groundtruth_mcp, task.groundtruth_tools, task.candidate_mcp, task.candidate_tools)
                        val_decision = decision_engine.evaluate(val_pre_llm, caller_spiffe_id, task.candidate_mcp, task.candidate_tools, 0.0, {}, task.task)
                        val_decision.llm_executed = False
                    
                    run_data.update({
                        "decision": val_decision,
                        "inference": validation,
                        "comparison": val_comparison
                    })
                
                st.session_state["last_run_data"] = run_data

    # --- Persistent Result Rendering ---
    last_run = st.session_state.get("last_run_data")
    if last_run:
        decision = last_run["decision"]
        inference = last_run["inference"]
        comparison = last_run["comparison"]
        ctx = last_run["experiment_context"]
        
        # Display Architecture
        mode_tag = "selection" if ctx["mode"].startswith("Selection") else "validation"
        title = "🧠 Research Mode: Selection (LLM-ResM)" if mode_tag == "selection" else "🛡️ Research Mode: Validation (Meta-Level)"
        st.header(title)
        
        # Phase 1: Context
        _render_phase_1(decision, caller_display_name, mode=mode_tag)
        st.divider()
        
        # Phase 2: Generation
        if decision.llm_executed:
            _render_phase_2(inference, mode_tag, task=task)
        else:
            st.warning("⚠️ GENERATION LAYER SKIPPED: Pre-LLM checks failed.")
        st.divider()
        
        # Phase 3: Logic
        _render_phase_3(decision, comparison, mode=mode_tag)
        
        # Details & Auditor
        with st.expander("📄 Raw Model Outputs & Details", expanded=False):
            st.subheader("📋 Context Initialization Audit")
            st.json(ctx)
            
            st.divider()
            if ctx["mode"].startswith("Selection"):
                st.subheader("Selection Inference Details")
                st.write("**Inference Justification:**", inference.justification)
                st.write("**Comparison Result:**")
                st.json(comparison.model_dump())
            else:
                st.subheader("Validation Inference Details")
                st.write("**Inference Reason:**", inference.reason)
                st.write("**Detected Issues:**")
                st.json(inference.issues)
            
            st.subheader("Detailed Logical Predicates")
            st.json(decision.context)

        # --- Post-Reasoning Auditor ---
        st.divider()
        st.markdown("### 🔍 Run Assessment & Recommendations")
        
        state_key = f"audit_{ctx['mode']}_{ctx['task_index']}"
        if state_key not in st.session_state:
            st.session_state[state_key] = None
        
        if st.button("🚀 Generate Logic Post-Mortem & Strategic Advice", key=f"btn_{state_key}"):
            with st.spinner("LLoM Auditor analyzing execution trace..."):
                assessment = auditor.generate_assessment(
                    task=task.task,
                    metadata=ctx,
                    decision_data=decision.model_dump(),
                    benchmark_status=comparison.status
                )
                st.session_state[state_key] = assessment
        
        report = st.session_state[state_key]
        if report:
            with st.container(border=True):
                st.markdown(f"#### 📊 Auditor Summary: {report.get('summary')}")
                for section in report.get("sections", []):
                    with st.expander(f"📌 {section.get('title')}", expanded=True):
                        st.markdown(section.get("content"))
                if report.get("recommendations"):
                    st.markdown("---")
                    st.markdown("**💡 Strategic Recommendations:**")
                    for rec in report.get("recommendations", []):
                        st.success(f"- {rec}")

def _render_authorization_trace(decision: DecisionResult):
    """
    Helper to render the RBAC and ABAC status and trace.
    Used in Phase I for Validation and Phase III for Selection.
    """
    rbac_status = decision.evaluation_states.get("rbac", "NOT_EVALUATED")
    abac_status = decision.evaluation_states.get("abac", "NOT_EVALUATED")

    with st.expander("⚖️ View Baseline Authority Trace (RBAC/ABAC)"):
        # Display Subject Attributes
        from app.services.spiffe_registry_service import SpiffeRegistryService
        registry = SpiffeRegistryService().get_all()
        persona_data = next((v for k, v in registry.items() if v.get("spiffe_id") == decision.spiffe_id), {})
        attrs = persona_data.get("attributes", {})
        if attrs:
            col1, col2, col3 = st.columns(3)
            col1.write(f"**Dept:** {attrs.get('department', 'Unknown')}")
            col2.write(f"**Clearance:** {attrs.get('clearance_level', 'L1')}")
            col3.write(f"**Trust:** {attrs.get('trust_score', 0.5):.1f}")
            st.divider()

        rbac_audit = decision.context.get("rbac_evaluation", {})
        if rbac_audit:
            st.markdown(f"**Overall RBAC Result:** `{rbac_audit.get('decision')}` | Policy: `Persona Role`")
            st.caption(rbac_audit.get("reason", ""))
            
            # Detailed Tool Breakdown
            rbac_trace = rbac_audit.get("rbac_trace", [])
            if rbac_trace:
                import pandas as pd
                st.markdown("**Per-Tool Authorization Trace:**")
                rdf = pd.DataFrame(rbac_trace)
                rdf.columns = ["Tool", "MCP", "Decision", "Matched Rule", "Rationale"]
                st.table(rdf)
        
        st.divider()
        abac = decision.context.get("abac_baseline", {})
        if abac:
            st.markdown(f"**ABAC Evaluation Status:** `{abac.get('decision')}` | Rule: `{abac.get('matched_rule')}`")
            
            # ABAC Attribute Mapping Detail (6D Detailed Trace)
            trace_steps = abac.get("reasoning_trace", {}).get("logic_steps", [])
            if trace_steps:
                import pandas as pd
                st.markdown("**Attribute Authority Evidence:**")
                
                # Transform logic steps into display rows
                rows = []
                for s in trace_steps:
                    rows.append({
                        "Condition": s.get("condition"),
                        "Value": s.get("actual"),
                        "Decision": s.get("decision", "ALLOW"),
                        "Rule ID": s.get("rule_id", "baseline")
                    })
                
                st.table(pd.DataFrame(rows))
            
            if abac.get("failure_reason"):
                st.error(f"ABAC Denial Rationale: {abac.get('failure_reason')}")
        else:
            st.info("No ABAC status available.")

def _render_phase_1(decision: DecisionResult, caller_display_name: str, mode: str = "validation"):
    """
    PHASE 1: PRE-LLM CONTEXT & IDENTITY
    """
    st.markdown("### 🏛️ Phase I: Context & Identity (Pre-LLM)")
    with st.container(border=True):
        st.write(f"**Subject Caller:** {caller_display_name}")
        st.code(decision.spiffe_id)
        
        id_source = st.session_state.get("current_identity_source", "Unknown")
        if "api" in id_source.lower() or "real" in id_source.lower():
            st.success(f"**Identity Source:** {id_source} | 🛡️ Real SPIFFE ID")
        else:
            st.info(f"**Identity Source:** {id_source} (Simulated)")
            
        id_status = decision.evaluation_states.get("identity", "NOT_EVALUATED")
        tr_status = decision.evaluation_states.get("transport", "NOT_EVALUATED")
        
        if mode == "selection":
            c1, c2 = st.columns(2)
            c1.metric("Identity Verified", "ALLOW" if id_status == "ALLOW" else "DENY")
            c2.metric("mTLS Transport", "ALLOW" if tr_status == "ALLOW" else "DENY")
        else:
            rbac_status = decision.evaluation_states.get("rbac", "NOT_EVALUATED")
            abac_status = decision.evaluation_states.get("abac", "NOT_EVALUATED")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Identity Verified", "ALLOW" if id_status == "ALLOW" else "DENY")
            c2.metric("mTLS Transport", "ALLOW" if tr_status == "ALLOW" else "DENY")
            c3.metric("RBAC Status", rbac_status)
            c4.metric("ABAC Status", abac_status)
            
            if rbac_status == "DENY":
                st.error(f"RBAC Denial: {decision.reason}")
            
            _render_authorization_trace(decision)

def _render_phase_2(result: Any, mode: str, task: Any = None):
    """
    PHASE 2: LLM INFERENCE (GENERATION LAYER)
    Displays the LLoM logic hypotheses and alignment scores.
    """
    st.markdown("### 🧠 Phase II: LLoM Generation (Inference)")
    with st.container(border=True):
        if mode == "selection":
            st.subheader("Logic Hypothesis (Tools Selection)")
            st.write("**Predicted MCPs:**")
            st.json(result.selected_mcp)
            st.write("**Predicted Tools:**")
            st.json(result.selected_tools)
            
            c1, c2 = st.columns(2)
            c1.metric("Model Confidence", f"{result.confidence:.0%}")
            c2.metric("Capability Coverage", f"{result.capability_coverage_score:.0%}")
            
            if result.missing_capabilities:
                st.warning(f"⚠️ **Missing Capabilities:** {', '.join(result.missing_capabilities)}")
            else:
                st.success("✅ **Sufficient Capability Coverage Hypothesized**")
            st.markdown(f"**Model Justification:** {result.justification}")
            
        else:
            st.subheader("Meta-Level Logic Verification")
            st.write("**Grounded Bundle for Validation:**")
            st.json({"MCPs": task.candidate_mcp, "Tools": task.candidate_tools})
            
            v_out = result.model_dump() if hasattr(result, "model_dump") else result
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Model Confidence", f"{v_out.get('confidence', 0.0):.0%}")
            
            alignment_score = v_out.get("task_alignment_score", 0.0)
            eval_eval = "✅" if alignment_score > 0 else "❌" # Simulated indicator
            c2.metric(f"Alignment Score {eval_eval}", f"{alignment_score:.2f}")
            
            is_valid = v_out.get("is_valid", False)
            c3.metric("Logical Validity", "VALID" if is_valid else "INVALID")
            
            if v_out.get("issue_codes"):
                st.write("**Detected Issue Codes:**")
                st.warning(", ".join(v_out.get("issue_codes", [])))
            
            st.markdown(f"**Validator Reasoning:** {v_out.get('reason')}")
            
            components = v_out.get("task_alignment_details", {})
            if components:
                with st.expander("📊 Alignment Breakdown (Weighted Reasoning)"):
                    st.json(components)

def _render_phase_3(decision: DecisionResult, comparison: Any, mode: str = "validation"):
    """
    PHASE 3: VERIFIED LOGIC TRACE (POST-LLM)
    Displays the final grounding, TS-PHOL audit, and verified decision.
    """
    st.markdown("### 🚦 Phase III: Verified Logic Trace (Post-LLM)")
    with st.container(border=True):
        st.markdown("#### D. Fact Extraction & Audit")
        audit_data = decision.context.get("tool_audit", [])
        intent = decision.context.get("intent_decomposition", {})
        
        with st.expander("🔍 Domain-Aware Predicate Audit", expanded=True):
            if audit_data:
                import pandas as pd
                df = pd.DataFrame(audit_data)
                # Filter caps
                from app.services.domain_capability_ontology import DomainCapabilityOntology
                df["capabilities"] = df["capabilities"].apply(lambda caps: [c for c in caps if DomainCapabilityOntology.is_concrete(c)])
                df_disp = df[["tool", "source", "actions", "capabilities", "notes"]].copy()
                df_disp.columns = ["Tool Name", "Classification Authority", "Action Types", "Concrete Caps", "Grounding Rationale"]
                st.table(df_disp)
                st.caption("💡 **Classification Authority**: Where the mapping comes from (Curated, Heuristic, or Catalog).")
                st.caption("💡 **Grounding Rationale**: Detailed evidence for the identified capabilities.")
            else:
                st.info("No tool audit data available.")
        
        if mode == "selection":
            st.divider()
            st.markdown("#### E.2 Authorization Status (Post-Inference)")
            rbac_status = decision.evaluation_states.get("rbac", "NOT_EVALUATED")
            abac_status = decision.evaluation_states.get("abac", "NOT_EVALUATED")
            c1, c2 = st.columns(2)
            c1.metric("RBAC Status", rbac_status)
            c2.metric("ABAC Status", abac_status)
            
            if rbac_status == "DENY":
                st.error(f"RBAC Denial: {decision.reason}")
            
            _render_authorization_trace(decision)

        st.divider()
        st.markdown("#### E. TS-PHOL Final Authority")
        tsphol_status = decision.evaluation_states.get("tsphol", "NOT_EVALUATED")
        summary = decision.context.get("tsphol_summary", {})
        
        if tsphol_status == "NOT_EVALUATED":
            st.info("TS-PHOL not reached (Pre-LLM Block)")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Rules Evaluated", summary.get("evaluated_rules", 0))
            c2.metric("Rules Triggered", summary.get("triggered_rules", 0))
            c3.metric("Math Certainty", f"{summary.get('certainty', 1.0):.0%}")
            
            with st.expander("🔍 Detailed Logic Evaluation Trace"):
                l_trace = decision.context.get("tsphol_logic_trace", [])
                for entry in l_trace:
                    icon = "✅ Pass" if entry["passed"] else "❌ Triggered"
                    st.write(f"{icon}: `{entry['rule']}`")
                    st.caption(f"↳ {entry['reason']}")
            
            # 6D: Redundant positive findings removed as per user request
            pass

        st.divider()
        st.markdown("#### F. Final Result")
        color_map = {"ALLOW": "green", "DENY": "red", "DECEPTION_ROUTED": "#FF8C00"}
        bg_color = color_map.get(decision.final_decision, "gray")
        display_text = "SANDBOXED / DECEIVED" if decision.deception_routed else decision.final_decision
        
        st.markdown(f"""
        <div style="background-color: {bg_color}; padding: 15px; border-radius: 8px; text-align: center;">
            <h2 style="color: white; margin: 0;">{display_text}</h2>
        </div>
        """, unsafe_allow_html=True)
        st.info(f"**Conclusion:** {decision.reason}")
        
        # Benchmark Evaluation Section (Moved to end for clarity)
        st.divider()
        st.markdown("### 📊 Benchmark Assessment (Reference Only)")
        st_color = {"exact_match": "green", "partial_match": "orange", "mismatch": "red"}.get(comparison.status, "gray")
        st.markdown(f"**Groundtruth Alignment Status:** :{st_color}[{comparison.status.upper()}]")
        st.caption("⚠️ **Research Disclaimer**: This assessment reflects a direct comparison against the ASTRA dataset. This data is **NOT** shared with the LLM and is not used in the logical decision pipeline. It is provided purely for benchmark analysis.")

        with st.expander("View Full Pipeline Trace"):
            for step in decision.trace:
                if "DECEPTION" in step:
                    st.warning(step)
                elif "❌" in step or "DENY" in step:
                    st.error(step)
                elif "⚠️" in step or "FLAG" in step:
                    st.warning(step)
                elif "✅" in step or "ALLOW" in step:
                    st.success(step)
                else:
                    st.info(step)
