import streamlit as st
import json
from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService
from app.services.mcp_risk_service import MCPRiskService

def render_policy_studio():
    st.title("🛡️ Policy Studio")
    st.markdown("Configure identity, access control, and reasoning policies for the agentic system.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1. SPIFFE Registry", 
        "2. Transport Allowlist", 
        "3. RBAC (Identity-Based)", 
        "4. TS-PHOL Rules",
        "5. MCP Risk Levels"
    ])

    registry_svc = SpiffeRegistryService()
    allowlist_svc = SpiffeAllowlistService(registry_service=registry_svc)
    rbac_svc = RBACService()
    tsphol_svc = TSPHOLRuleService()
    risk_svc = MCPRiskService()

    with tab1:
        _render_spiffe_registry(registry_svc)

    with tab2:
        _render_transport_allowlist(allowlist_svc)

    with tab3:
        _render_rbac(rbac_svc, registry_svc)
        
    with tab4:
        _render_tsphol(tsphol_svc)
        
    with tab5:
        _render_mcp_risk_levels(risk_svc)


def _render_spiffe_registry(svc: SpiffeRegistryService):
    st.header("SPIFFE Identity Registry")
    st.markdown("Define agent personas and their corresponding SPIFFE IDs.")
    
    registry = svc.get_all()
    
    if registry:
        for key, details in registry.items():
            if isinstance(details, str): continue # Skip mid-migration corrupted views
            with st.expander(f"{details.get('display_name', key)} ({details.get('spiffe_id')})"):
                st.write(f"**Key:** `{key}`")
                st.write(f"**Description:** {details.get('description')}")
                if st.button("Delete", key=f"del_reg_{key}"):
                    success, msg = svc.delete_identity(key)
                    if success: st.rerun()
                    else: st.error(msg)
    else:
        st.info("No identities defined.")

    st.divider()
    st.subheader("Add New Persona")
    with st.form("add_spiffe_form", clear_on_submit=True):
        new_key = st.text_input("Registry Key (e.g. ops_agent)")
        new_name = st.text_input("Display Name (e.g. Operations Agent)")
        new_spiffe = st.text_input("SPIFFE ID (starts with spiffe://)")
        new_desc = st.text_input("Description")
        if st.form_submit_button("Add Identity"):
            success, msg = svc.add_identity(new_key, new_name, new_spiffe, new_desc)
            if success: st.rerun()
            else: st.error(msg)


def _render_transport_allowlist(svc: SpiffeAllowlistService):
    st.header("Transport Allowlist (mTLS)")
    st.markdown("List of SPIFFE IDs allowed to connect (requires existing registry entry).")
    
    allowlist = svc.get_all()
    
    if allowlist:
        for spiffe_id in allowlist:
            col1, col2 = st.columns([5, 1])
            with col1:
                st.code(spiffe_id)
            with col2:
                if st.button("Delete", key=f"del_al_{spiffe_id}"):
                    success, msg = svc.remove_identity(spiffe_id)
                    if success: st.rerun()
                    else: st.error(msg)
    else:
        st.info("Allowlist is empty. No connections allowed.")

    st.divider()
    st.subheader("Add Allowed Caller")
    with st.form("add_al_form", clear_on_submit=True):
        registry = svc.registry_service.get_all()
        options = []
        for v in registry.values():
            if isinstance(v, dict) and "spiffe_id" in v:
                options.append(f"{v.get('display_name')} ({v.get('spiffe_id')})")
                
        if options:
            selected = st.selectbox("Select Agent Persona", options)
            if st.form_submit_button("Allow Caller"):
                selected_spiffe = selected.split("(")[-1].strip(")")
                success, msg = svc.add_identity(selected_spiffe)
                if success: st.rerun()
                else: st.error(msg)
        else:
            st.warning("Please add identities to the Registry first.")
            st.form_submit_button("Allow Caller", disabled=True)
            
    if st.button("Reset Allowlist to Default Agents"):
        default_agents = [
            "spiffe://demo.local/agent/devops",
            "spiffe://demo.local/agent/incident",
            "spiffe://demo.local/agent/finance",
            "spiffe://demo.local/agent/research"
        ]
        valid_ids = [v.get("spiffe_id") for v in svc.registry_service.get_all().values() if isinstance(v, dict) and "spiffe_id" in v]
        svc.allowlist = [sid for sid in default_agents if sid in valid_ids]
        svc._save()
        st.rerun()


def _render_rbac(svc: RBACService, reg_svc: SpiffeRegistryService):
    st.header("RBAC (Identity-Based)")
    st.markdown("Define authorization rules mapped to SPIFFE identities.")
    
    policies = svc.get_all()
    
    agents = [p for p in policies if "/agent/" in p.get("spiffe_id", "")]
    services = [p for p in policies if "/service/" in p.get("spiffe_id", "")]
    
    if agents:
        st.subheader("Agent Personas")
        for p in agents:
            with st.expander(f"{p.get('description', 'Policy')} ({p.get('spiffe_id')})"):
                if not p.get("rules"):
                    st.warning("⚠️ This persona has no executable permissions. All tasks will be denied by default.")
                st.json(p.get("rules", []))
                if st.button("Delete Policy", key=f"del_rbac_{p.get('spiffe_id')}"):
                    success, msg = svc.delete_policy(p.get('spiffe_id'))
                    if success: st.rerun()
                    else: st.error(msg)
                    
    if services:
        st.subheader("Service Identities")
        for p in services:
            with st.expander(f"{p.get('description', 'Policy')} ({p.get('spiffe_id')})"):
                if not p.get("rules"):
                    st.warning("⚠️ This service is explicitly restrictive. All tasks will be denied.")
                st.json(p.get("rules", []))
                if st.button("Delete Policy", key=f"del_rbac_{p.get('spiffe_id')}"):
                    success, msg = svc.delete_policy(p.get('spiffe_id'))
                    if success: st.rerun()
                    else: st.error(msg)

    st.divider()
    st.subheader("Add/Update Policy")
    with st.form("add_rbac_form", clear_on_submit=False):
        registry = reg_svc.get_all()
        options = []
        for v in registry.values():
            if isinstance(v, dict) and "spiffe_id" in v:
                options.append(f"{v.get('display_name')} ({v.get('spiffe_id')})")
        
        target_display = st.selectbox("Target Agent Persona", options) if options else st.text_input("Target SPIFFE ID")
        desc = st.text_input("Policy Description")
        
        st.markdown("**Rule JSON (List of Dicts)**")
        st.caption('Example: `[{"mcp": "stripe", "tools": ["*"], "action": "deny"}]`')
        rules_text = st.text_area("Rules", value="[]")
        
        if st.form_submit_button("Save Policy"):
            try:
                rules_obj = json.loads(rules_text)
                if not isinstance(rules_obj, list):
                    st.error("Rules must be a JSON array.")
                else:
                    if target_display and "(" in target_display:
                        target_spiffe = target_display.split("(")[-1].strip(")")
                    else:
                        target_spiffe = target_display
                        
                    success, msg = svc.save_policy(target_spiffe, desc, rules_obj)
                    if success: st.success(msg)
                    else: st.error(msg)
            except json.JSONDecodeError:
                st.error("Invalid JSON format for rules.")


def _render_tsphol(svc: TSPHOLRuleService):
    st.header("TS-PHOL Rules")
    st.markdown("Define reasoning rules decoupled from benchmark groundtruth.")
    
    rules = svc.get_all()
    
    for r in rules:
        with st.expander(f"{r.get('name')} -> {r.get('decision').upper()}"):
            st.write(f"*{r.get('description', '')}*")
            st.json(r.get("condition", {}))
            if st.button("Delete Rule", key=f"del_tsp_{r.get('name')}"):
                success, msg = svc.delete_rule(r.get('name'))
                if success: st.rerun()
                else: st.error(msg)

    st.divider()
    st.subheader("Add/Update Rule")
    with st.form("add_tsp_form", clear_on_submit=False):
        name = st.text_input("Rule Name (e.g. strict_write_policy)")
        decision = st.selectbox("Decision", ["allow", "deny"])
        
        st.markdown("**Condition JSON (Key-Value pairs)**")
        st.caption('Example: `{"contains_write": true, "min_confidence": 0.9}`')
        condition_text = st.text_area("Condition", value="{}")
        
        if st.form_submit_button("Save Rule"):
            try:
                cond_obj = json.loads(condition_text)
                if not isinstance(cond_obj, dict):
                    st.error("Condition must be a JSON object.")
                else:
                    success, msg = svc.save_rule(name, cond_obj, decision)
                    if success: st.success(msg)
                    else: st.error(msg)
            except json.JSONDecodeError:
                st.error("Invalid JSON format for condition.")


def _render_mcp_risk_levels(svc: MCPRiskService):
    st.header("MCP Risk Levels")
    st.markdown("Assign explicit operation risks to individual MCP domains.")
    
    risks = svc.get_all()
    
    for mcp, level in risks.items():
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.write(f"**{mcp}**")
        with col2:
            st.write(f"Risk: `{level}`")
        with col3:
            pass # We overwrite rather than delete
            
    st.divider()
    st.subheader("Add/Update MCP Risk")
    with st.form("add_risk_form", clear_on_submit=True):
        mcp_name = st.text_input("MCP Name (e.g. github)")
        risk_level = st.selectbox("Risk Level", ["low", "medium", "high"])
        if st.form_submit_button("Set Risk"):
            success = svc.set_risk(mcp_name, risk_level)
            if success: st.rerun()
            else: st.error("Failed to update risk level.")
