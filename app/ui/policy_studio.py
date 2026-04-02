import streamlit as st
import json
from typing import Any
from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService
from app.services.mcp_risk_service import MCPRiskService
from app.services.spiffe_workload_service import SpiffeWorkloadService
from app.services.abac_rule_service import ABACRuleService
from app.services.capability_inference_service import CapabilityInferenceService
from app.services.policy_loader import PolicyLoader

def render_policy_studio():
    st.title("🛡️ Policy Studio")
    st.markdown("Configure identity, access control, and reasoning policies for the agentic system.")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "1. MCP Risk Levels",
        "2. SPIFFE Registry", 
        "3. Transport Allowlist", 
        "4. RBAC (Identity-Based)", 
        "5. ABAC (Attribute-Based)",
        "6. TS-PHOL Rules",
        "7. Domain Catalog",
        "8. Heuristic Logic"
    ])

    registry_svc = SpiffeRegistryService()
    allowlist_svc = SpiffeAllowlistService(registry_service=registry_svc)
    rbac_svc = RBACService()
    abac_svc = ABACRuleService()
    tsphol_svc = TSPHOLRuleService()
    risk_svc = MCPRiskService()
    
    cap_inf_svc = CapabilityInferenceService()
    
    workload_svc = SpiffeWorkloadService()

    with tab1:
        _render_mcp_risk_levels(risk_svc)

    with tab2:
        _render_spiffe_registry(registry_svc, workload_svc)

    with tab3:
        _render_transport_allowlist(allowlist_svc)

    with tab4:
        _render_rbac(rbac_svc, registry_svc)
        
    with tab5:
        _render_abac_baseline(abac_svc)
        
    with tab6:
        _render_tsphol(tsphol_svc)
        
    with tab7:
        _render_domain_catalog(cap_inf_svc)
        
    with tab8:
        from app.services.heuristic_service import HeuristicService
        h_svc = HeuristicService()
        _render_heuristic_logic(h_svc)


def _render_spiffe_registry(svc: SpiffeRegistryService, workload_svc: SpiffeWorkloadService):
    st.header("SPIFFE Identity Registry")
    st.markdown("Define agent personas and their corresponding SPIFFE IDs.")
    
    # SPIRE status section
    st.subheader("🌐 SPIRE Infrastructure Status")
    real_id, id_source = workload_svc.fetch_real_identity()
    if real_id:
        st.success(f"✅ Connected to SPIRE Agent")
        with st.expander("View Full Workload SVID Details (X.509)"):
            status_text = workload_svc.fetch_full_svid_status()
            st.code(status_text)
    else:
        st.warning(f"⚠️ SPIRE Agent Offline or No Identity Issued")
        st.caption(f"Reason: {id_source}")

    st.divider()
    
    registry = svc.get_all()
    
    if registry:
        for key, details in registry.items():
            if isinstance(details, str): continue # Skip mid-migration corrupted views
            with st.expander(f"👤 {details.get('display_name', key)}"):
                col_left, col_right = st.columns([2, 1])
                with col_left:
                    st.markdown("**SPIFFE Identity (SVID)**")
                    st.code(details.get('spiffe_id'))
                    st.markdown(f"**Description:** {details.get('description')}")
                
                with col_right:
                    st.markdown("**Registry Key**")
                    st.code(key)
                    if st.button("🗑️ Delete Identity", key=f"del_reg_{key}", use_container_width=True):
                        success, msg = svc.delete_identity(key)
                        if success: st.rerun()
                        else: st.error(msg)
    else:
        st.info("No identities defined.")

    st.divider()
    st.subheader("Add New Persona")
    st.info("💡 Adding a persona here automatically registers a new cryptographic entry in the SPIRE Server with a default Docker selector (`unix:uid:0`).")
    with st.form("add_spiffe_form", clear_on_submit=True):
        new_key = st.text_input("Registry Key (e.g. ops_agent)")
        new_name = st.text_input("Display Name (e.g. Operations Agent)")
        new_spiffe = st.text_input("SPIFFE ID (starts with spiffe://)")
        new_desc = st.text_input("Description")
        if st.form_submit_button("Add Identity & Register with SPIRE"):
            success, msg = svc.add_identity(new_key, new_name, new_spiffe, new_desc)
            if success: st.success(msg); st.rerun()
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
    st.header("TS-PHOL Declarative Policies")
    st.markdown("Define reasoning policies as declarative rules (JSON-driven interpretation).")
    
    rules = svc.get_all()
    # Sort rules by priority for display
    rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)
    
    for r in rules:
        with st.expander(f"[{r.get('priority', 0)}] {r.get('rule_name')} -> {r.get('then').upper()}"):
            st.write(f"*{r.get('description', '')}*")
            st.markdown("**If (Conditions):**")
            st.json(r.get("if", []))
            if r.get("derive"):
                st.info(f"🧬 Derives: `{r.get('derive')}`")
            
            if st.button("Delete Rule", key=f"del_tsp_{r.get('rule_name')}"):
                success, msg = svc.delete_rule(r.get('rule_name'))
                if success: st.rerun()
                else: st.error(msg)

    st.divider()
    st.subheader("Add/Update Declarative Policy")
    with st.form("add_tsp_form", clear_on_submit=False):
        rule_name = st.text_input("Rule Name (e.g. unsafe_write_prevention)")
        desc = st.text_input("Description")
        
        col1, col2 = st.columns(2)
        with col1:
            action = st.selectbox("Action (Then)", ["ALLOW", "DENY"])
        with col2:
            priority = st.number_input("Priority", min_value=0, max_value=1000, value=100)
            
        derivation = st.text_input("Derived Predicate (Optional)", help="e.g. UnsafeWrite")
        
        st.markdown("**Conditions JSON (List of logic dicts)**")
        st.caption('Example: `[{"predicate": "ContainsWrite", "equals": true}, {"predicate": "ContainsRead", "equals": false}]`')
        st.caption('Operators: `equals`, `lt`, `gt`, `includes`, `contains`, `missing`, `not_subset_of`')
        condition_text = st.text_area("Conditions (if)", value="[]")
        
        if st.form_submit_button("Save Policy"):
            try:
                cond_obj = json.loads(condition_text)
                if not isinstance(cond_obj, list):
                    st.error("Conditions must be a JSON array (list).")
                else:
                    success, msg = svc.save_rule(rule_name, desc, cond_obj, action, derivation, priority)
                    if success: st.success(msg); st.rerun()
                    else: st.error(msg)
            except json.JSONDecodeError:
                st.error("Invalid JSON format for conditions.")


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


def _render_abac_baseline(svc: ABACRuleService):
    st.header("ABAC Baseline Rules")
    st.markdown("Attribute-Based Access Control baseline rules (Parallel informational layer).")
    
    rules = svc.get_all()
    
    for r in rules:
        with st.expander(f"Rule: {r.get('id')} -> {r.get('action').upper()}"):
            st.write(f"*{r.get('description', '')}*")
            st.json(r)
            if st.button("Delete Rule", key=f"del_abac_{r.get('id')}"):
                success, msg = svc.delete_rule(r.get('id'))
                if success: st.rerun()
                else: st.error(msg)

    st.divider()
    st.subheader("Add/Update ABAC Rule")
    with st.form("add_abac_form", clear_on_submit=False):
        rule_id = st.text_input("Rule ID (e.g. abac_6)")
        
        st.markdown("**Rule JSON (Attributes & Action)**")
        st.caption('Example: `{"condition": "confidence < 0.9", "action": "deny"}` or `{"multi_domain_limit": true, "action": "deny"}`')
        rule_text = st.text_area("Rule Body", value='{"condition": "risk < confidence", "action": "deny"}')
        
        if st.form_submit_button("Save ABAC Rule"):
            try:
                rule_obj = json.loads(rule_text)
                if not isinstance(rule_obj, dict):
                    st.error("Rule must be a JSON object.")
                else:
                    success, msg = svc.save_rule(rule_id, rule_obj)
                    if success: st.success(msg)
                    else: st.error(msg)
            except json.JSONDecodeError:
                st.error("Invalid JSON format.")

def _render_domain_catalog(svc: CapabilityInferenceService):
    st.header("🧬 Domain Capability Catalog")
    st.markdown("Define which capabilities are allowed per domain. Inference will filter out non-catalog items.")
    
    # Reload for freshest UI data
    svc.catalog = PolicyLoader.load_json(svc.catalog_path)

    for domain, caps in list(svc.catalog.items()):
        with st.expander(f"📚 Domain: {domain}"):
            st.write(f"**Allowed Capabilities:** {', '.join(caps)}")
            new_caps_text = st.text_area(f"Edit Catalog for {domain} (JSON list)", value=json.dumps(caps), key=f"cat_edit_{domain}")
            
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button(f"Update {domain} Catalog"):
                    try:
                        new_caps = json.loads(new_caps_text)
                        if isinstance(new_caps, list):
                            svc.catalog[domain] = new_caps
                            if svc.save_catalog(svc.catalog): st.rerun()
                        else: st.error("Must be a list.")
                    except: st.error("Invalid JSON.")
            with c2:
                if st.button(f"🗑️ Delete {domain} Domain"):
                    del svc.catalog[domain]
                    if svc.save_catalog(svc.catalog): st.rerun()

    st.divider()
    st.subheader("➕ Add New Domain to Catalog")
    with st.form("add_domain_form", clear_on_submit=True):
        new_domain_name = st.text_input("New Domain Name (e.g. MongoDB)")
        new_domain_caps = st.text_area("Initial Capabilities (JSON list)", value='["ResourceRead", "ResourceWrite"]')
        if st.form_submit_button("Add Domain"):
            if not new_domain_name:
                st.error("Domain name is required.")
            else:
                try:
                    caps_list = json.loads(new_domain_caps)
                    if isinstance(caps_list, list):
                        svc.catalog[new_domain_name] = caps_list
                        if svc.save_catalog(svc.catalog): st.rerun()
                    else: st.error("Capabilities must be a JSON list.")
                except: st.error("Invalid JSON for capabilities.")

def _render_heuristic_logic(svc: Any):
    st.header("🧠 Heuristic Inference Rules")
    st.markdown("Expose and edit the keyword-based inference rules used for tool classification.")
    
    policy = svc.get_all()
    
    # 1. Action Rules
    st.subheader("1. Action Inference Rules (Prefix-based)")
    action_rules = policy.get("action_rules", [])
    
    for i, rule in enumerate(action_rules):
        with st.expander(f"Rule: {rule.get('id')}"):
            with st.form(f"edit_action_rule_{i}"):
                col1, col2 = st.columns(2)
                with col1:
                    u_id = st.text_input("Rule ID", value=rule.get("id"))
                    u_prefix = st.text_input("Prefix", value=rule.get("prefix"))
                with col2:
                    u_actions = st.text_input("Actions (comma separated)", value=", ".join(rule.get("actions", [])))
                
                if st.form_submit_button("Update Action Rule"):
                    action_rules[i] = {
                        "id": u_id,
                        "prefix": u_prefix,
                        "actions": [a.strip() for a in u_actions.split(",") if a.strip()]
                    }
                    policy["action_rules"] = action_rules
                    if svc.save_policy(policy): st.success("Saved."); st.rerun()

    # 2. Capability Rules
    st.subheader("2. Capability Inference Rules (Keyword-based)")
    cap_rules = policy.get("capability_rules", [])
    
    for i, rule in enumerate(cap_rules):
        with st.expander(f"Rule: {rule.get('id')}"):
            with st.form(f"edit_cap_rule_{i}"):
                col1, col2 = st.columns(2)
                with col1:
                    u_id = st.text_input("Rule ID", value=rule.get("id"))
                    u_kw = st.text_input("Keyword", value=rule.get("keyword"))
                with col2:
                    u_caps = st.text_input("Capabilities (comma separated)", value=", ".join(rule.get("capabilities", [])))
                
                if st.form_submit_button("Update Cap Rule"):
                    cap_rules[i] = {
                        "id": u_id,
                        "keyword": u_kw,
                        "capabilities": [c.strip() for c in u_caps.split(",") if c.strip()]
                    }
                    policy["capability_rules"] = cap_rules
                    if svc.save_policy(policy): st.success("Saved."); st.rerun()

    # 3. Fallbacks
    st.subheader("3. Fallback Registry")
    fallbacks = policy.get("fallbacks", {})
    with st.form("fallback_form"):
        f_read = st.text_input("Read-like Fallback", value=fallbacks.get("read_like", ""))
        f_write = st.text_input("Write-like Fallback", value=fallbacks.get("write_like", ""))
        f_default = st.text_input("Default Fallback", value=fallbacks.get("default", ""))
        
        if st.form_submit_button("Save Fallbacks"):
            policy["fallbacks"] = {
                "read_like": f_read,
                "write_like": f_write,
                "default": f_default
            }
            if svc.save_policy(policy): st.success("Saved."); st.rerun()
