import streamlit as st
from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService
import json

def render_policy_studio():
    st.title("🛡️ Policy Studio")
    st.markdown("Configure identity, access control, and reasoning policies for the agentic system.")

    tab1, tab2, tab3, tab4 = st.tabs([
        "1. SPIFFE Registry", 
        "2. Transport Allowlist", 
        "3. RBAC (Identity-Based)", 
        "4. TS-PHOL Rules"
    ])

    registry_svc = SpiffeRegistryService()
    allowlist_svc = SpiffeAllowlistService(registry_service=registry_svc)
    rbac_svc = RBACService()
    tsphol_svc = TSPHOLRuleService()

    with tab1:
        _render_spiffe_registry(registry_svc)

    with tab2:
        _render_transport_allowlist(allowlist_svc)

    with tab3:
        _render_rbac(rbac_svc, registry_svc)
        
    with tab4:
        _render_tsphol(tsphol_svc)


def _render_spiffe_registry(svc: SpiffeRegistryService):
    st.header("SPIFFE Identity Registry")
    st.markdown("Define application roles and their corresponding SPIFFE IDs.")
    
    registry = svc.get_all()
    
    if registry:
        for name, spiffe_id in registry.items():
            col1, col2, col3 = st.columns([2, 5, 1])
            with col1:
                st.write(f"**{name}**")
            with col2:
                st.code(spiffe_id)
            with col3:
                if st.button("Delete", key=f"del_reg_{name}"):
                    success, msg = svc.delete_identity(name)
                    if success: st.rerun()
                    else: st.error(msg)
    else:
        st.info("No identities defined.")

    st.divider()
    st.subheader("Add New Identity")
    with st.form("add_spiffe_form", clear_on_submit=True):
        new_name = st.text_input("Name (e.g. orchestrator)")
        new_spiffe = st.text_input("SPIFFE ID (starts with spiffe://)")
        if st.form_submit_button("Add Identity"):
            success, msg = svc.add_identity(new_name, new_spiffe)
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
        # Dropdown from registry is better UX
        registry = svc.registry_service.get_all()
        options = list(registry.values())
        if options:
            new_al = st.selectbox("Select SPIFFE ID", options)
            if st.form_submit_button("Allow Caller"):
                success, msg = svc.add_identity(new_al)
                if success: st.rerun()
                else: st.error(msg)
        else:
            st.warning("Please add identities to the Registry first.")
            st.form_submit_button("Allow Caller", disabled=True)


def _render_rbac(svc: RBACService, reg_svc: SpiffeRegistryService):
    st.header("RBAC (Identity-Based)")
    st.markdown("Define authorization rules mapped to SPIFFE identities.")
    
    policies = svc.get_all()
    
    for p in policies:
        with st.expander(f"{p.get('description', 'Policy')} ({p.get('spiffe_id')})"):
            st.json(p.get("rules", []))
            if st.button("Delete Policy", key=f"del_rbac_{p.get('spiffe_id')}"):
                success, msg = svc.delete_policy(p.get('spiffe_id'))
                if success: st.rerun()
                else: st.error(msg)

    st.divider()
    st.subheader("Add/Update Policy")
    with st.form("add_rbac_form", clear_on_submit=False):
        registry = reg_svc.get_all()
        options = list(registry.values())
        
        target_spiffe = st.selectbox("Target SPIFFE ID", options) if options else st.text_input("Target SPIFFE ID")
        desc = st.text_input("Description")
        
        st.markdown("**Rule JSON (List of Dicts)**")
        st.caption('Example: `[{"mcp": "stripe", "tools": ["*"], "action": "deny"}]`')
        rules_text = st.text_area("Rules", value="[]")
        
        if st.form_submit_button("Save Policy"):
            try:
                rules_obj = json.loads(rules_text)
                if not isinstance(rules_obj, list):
                    st.error("Rules must be a JSON array.")
                else:
                    success, msg = svc.save_policy(target_spiffe, desc, rules_obj)
                    if success: st.success(msg)
                    else: st.error(msg)
            except json.JSONDecodeError:
                st.error("Invalid JSON format for rules.")


def _render_tsphol(svc: TSPHOLRuleService):
    st.header("TS-PHOL Rules")
    st.markdown("Define reasoning rules (preview only - execution engine not active).")
    
    rules = svc.get_all()
    
    for r in rules:
        with st.expander(f"{r.get('name')} -> {r.get('decision').upper()}"):
            st.json(r.get("condition", {}))
            if st.button("Delete Rule", key=f"del_tsp_{r.get('name')}"):
                success, msg = svc.delete_rule(r.get('name'))
                if success: st.rerun()
                else: st.error(msg)

    st.divider()
    st.subheader("Add/Update Rule")
    with st.form("add_tsp_form", clear_on_submit=False):
        name = st.text_input("Rule Name (e.g. strict_write_policy)")
        decision = st.selectbox("Decision", ["enforce", "deny", "allow"])
        
        st.markdown("**Condition JSON (Key-Value pairs)**")
        st.caption('Example: `{"action_type": "write", "min_confidence": 0.9}`')
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
