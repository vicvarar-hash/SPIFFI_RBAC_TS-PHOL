import streamlit as st
import json
import yaml
from typing import Any
from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService
from app.services.mcp_attribute_service import MCPAttributeService
from app.services.spiffe_workload_service import SpiffeWorkloadService
from app.services.abac_rule_service import ABACRuleService
from app.services.capability_inference_service import CapabilityInferenceService
from app.services.policy_loader import PolicyLoader

def render_policy_studio():
    st.title("🛡️ Policy Studio")
    st.markdown("Configure identity, access control, and reasoning policies for the agentic system.")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
        "1. SPIFFE Registry",
        "2. Transport Allowlist",
        "3. MCP Attributes",
        "4. RBAC (Identity-Based)",
        "5. ABAC (Attribute-Based)",
        "6. Domain Catalog",
        "7. Capability Ontology",
        "8. Heuristic Logic",
        "9. TS-PHOL Rules",
        "10. Experiments"
    ])

    registry_svc = SpiffeRegistryService()
    allowlist_svc = SpiffeAllowlistService(registry_service=registry_svc)
    rbac_svc = RBACService()
    abac_svc = ABACRuleService()
    tsphol_svc = TSPHOLRuleService()
    attribute_svc = MCPAttributeService()
    cap_inf_svc = CapabilityInferenceService()
    workload_svc = SpiffeWorkloadService()

    with tab1:
        _render_spiffe_registry(registry_svc, workload_svc)

    with tab2:
        _render_transport_allowlist(allowlist_svc)

    with tab3:
        _render_mcp_attributes(attribute_svc)

    with tab4:
        _render_rbac(rbac_svc, registry_svc)

    with tab5:
        _render_abac_baseline(abac_svc)

    with tab6:
        _render_domain_catalog(cap_inf_svc)

    with tab7:
        _render_capability_ontology()

    with tab8:
        from app.services.heuristic_service import HeuristicService
        h_svc = HeuristicService()
        _render_heuristic_logic(h_svc)

    with tab9:
        _render_tsphol(tsphol_svc)

    with tab10:
        _render_experiment_policies()


def _render_experiment_policies():
    """Show the generated policies for each of the 34 experiment configurations."""
    from app.services.experiment_config import (
        EXPERIMENTS, EXPERIMENT_GROUPS, ExperimentConfig,
    )

    st.header("Experiment Policies")
    st.markdown(
        "Browse the security policies generated for each experiment configuration. "
        "These are the exact policy bundles used in the Experiment Lab evaluations."
    )

    # Group filter
    group_options = ["All Groups"] + [f"Group {g}: {d[:50]}" for g, d in EXPERIMENT_GROUPS.items()]
    selected_group = st.selectbox("Filter by Group", group_options, key="ps_exp_group")

    if selected_group == "All Groups":
        configs = EXPERIMENTS
    else:
        group_letter = selected_group.split(":")[0].replace("Group ", "").strip()
        configs = [e for e in EXPERIMENTS if e.group == group_letter]

    # Config selector
    config_display = [f"{e.name}: {e.description}" for e in configs]
    selected = st.selectbox("Select Configuration", config_display, key="ps_exp_config")

    if not selected:
        return

    config_name = selected.split(":")[0].strip()
    config = next((e for e in configs if e.name == config_name), None)
    if not config:
        return

    # Config metadata
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Name**: {config.name}")
        st.markdown(f"**Group**: {config.group} — {EXPERIMENT_GROUPS[config.group]}")
    with col2:
        st.markdown(f"**Registry**: `{config.registry_fn}`")
        st.markdown(f"**Allowlist**: `{config.allowlist_fn}`")
        st.markdown(f"**RBAC**: `{config.rbac_fn}`")
        st.markdown(f"**ABAC**: `{config.abac_fn}`")
        st.markdown(f"**TS-PHOL**: `{config.tsphol_fn}`")

    st.markdown("---")

    # Generate and display policies
    policies = config.get_policies()

    policy_tabs = st.tabs(["RBAC", "ABAC", "TS-PHOL", "Registry", "Allowlist"])

    with policy_tabs[0]:
        st.subheader("RBAC Policy")
        rbac = policies.get("rbac", {})
        st.metric("Roles defined", len(rbac.get("roles", [])))
        st.code(yaml.dump(rbac, default_flow_style=False, sort_keys=False), language="yaml")

    with policy_tabs[1]:
        st.subheader("ABAC Policy")
        abac = policies.get("abac", {})
        st.metric("Rules defined", len(abac.get("rules", [])))
        st.code(yaml.dump(abac, default_flow_style=False, sort_keys=False), language="yaml")

    with policy_tabs[2]:
        st.subheader("TS-PHOL Rules")
        tsphol = policies.get("tsphol", {})
        st.metric("Rules defined", len(tsphol.get("rules", [])))
        st.code(yaml.dump(tsphol, default_flow_style=False, sort_keys=False), language="yaml")

    with policy_tabs[3]:
        st.subheader("SPIFFE Registry")
        registry = policies.get("registry", {})
        st.metric("Entries", len(registry.get("agents", [])))
        st.code(json.dumps(registry, indent=2), language="json")

    with policy_tabs[4]:
        st.subheader("Transport Allowlist")
        allowlist = policies.get("allowlist", {})
        st.metric("Entries", len(allowlist.get("allowed_transports", [])))
        st.code(json.dumps(allowlist, indent=2), language="json")


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
                    
                    # 6D: Display Attributes directly in card
                    attrs = details.get('attributes', {})
                    if attrs:
                        ac1, ac2, ac3 = st.columns(3)
                        ac1.caption("🏢 **Department**")
                        ac1.write(f"`{attrs.get('department', 'N/A')}`")
                        ac2.caption("🛡️ **Trust Score**")
                        ac2.write(f"`{attrs.get('trust_score', 0.0):.1f}`")
                        ac3.caption("🔑 **Clearance**")
                        ac3.write(f"`{attrs.get('clearance_level', 'L1')}`")
                
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
        
        st.markdown("**Initial Attributes**")
        ac1, ac2 = st.columns(2)
        with ac1:
            new_dept = st.selectbox("Department", ["Engineering", "Finance", "Security", "Medical", "HR", "Sales"])
            new_clearance = st.selectbox("Clearance Level", ["L1", "L2", "L3"])
        with ac2:
            new_trust = st.slider("Trust Score", 0.0, 1.0, 1.0)

        if st.form_submit_button("Add Identity & Register with SPIRE"):
            success, msg = svc.add_identity(new_key, new_name, new_spiffe, new_desc)
            if success:
                # Update attributes since add_identity uses defaults
                svc.registry[new_key]["attributes"] = {
                    "department": new_dept,
                    "clearance_level": new_clearance,
                    "trust_score": new_trust
                }
                PolicyLoader.save_json(svc.filepath, svc.registry)
                st.success(msg); st.rerun()
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
        then_action = (r.get('then') or 'unknown').upper()
        with st.expander(f"[{r.get('priority', 0)}] {r.get('rule_name')} -> {then_action}"):
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


def _render_mcp_attributes(svc: MCPAttributeService):
    st.header("MCP Resource Attributes")
    st.markdown("Assign rich metadata and operation risks to individual MCP domains.")
    
    attributes = svc.get_all()
    
    for mcp, attrs in attributes.items():
        with st.expander(f"📦 {mcp}"):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Risk Level:** `{attrs.get('risk_level')}`")
                st.write(f"**Compliance:** `{attrs.get('compliance_tier')}`")
            with col2:
                st.write(f"**Sensitivity:** `{attrs.get('data_sensitivity')}`")
                st.write(f"**Boundary:** `{attrs.get('trust_boundary')}`")

    st.divider()
    st.subheader("Add/Update MCP Metadata")
    with st.form("add_attr_form", clear_on_submit=True):
        mcp_name = st.text_input("MCP Name (e.g. stripe)")
        
        c1, c2 = st.columns(2)
        with c1:
            risk = st.selectbox("Risk Level", ["low", "medium", "high"])
            compliance = st.selectbox("Compliance Tier", ["General", "Financial", "Infrastructure", "Enterprise", "Monitoring", "PCI-DSS", "HIPAA"])
        with c2:
            sensitivity = st.selectbox("Data Sensitivity", ["Public", "Internal", "Metadata", "Financial", "Infrastructure", "Private-Key"])
            boundary = st.selectbox("Trust Boundary", ["Third-Party", "Vetted-Partner", "Internal", "Experimental"])
            
        if st.form_submit_button("Save Attributes"):
            svc.set_attribute(mcp_name, "risk_level", risk)
            svc.set_attribute(mcp_name, "compliance_tier", compliance)
            svc.set_attribute(mcp_name, "data_sensitivity", sensitivity)
            svc.set_attribute(mcp_name, "trust_boundary", boundary)
            st.success(f"Attributes updated for {mcp_name}")
            st.rerun()


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
        rule_label = f"Rule: {rule.get('id')}"
        with st.expander(rule_label):
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

            if st.button("🗑️ Delete Action Rule", key=f"del_action_{i}"):
                action_rules.pop(i)
                policy["action_rules"] = action_rules
                if svc.save_policy(policy): st.success("Rule Deleted."); st.rerun()

    st.markdown("#### ➕ Add New Action Rule")
    with st.form("add_action_rule_form", clear_on_submit=True):
        a_id = st.text_input("New Rule ID (e.g. prefix:audit_)")
        a_prefix = st.text_input("Prefix (e.g. audit_)")
        a_actions = st.text_input("Actions (comma separated, e.g. read, audit)")
        if st.form_submit_button("Add Action Rule"):
            if not a_id or not a_prefix:
                st.error("Rule ID and Prefix are required.")
            else:
                new_rule = {
                    "id": a_id,
                    "prefix": a_prefix,
                    "actions": [a.strip() for a in a_actions.split(",") if a.strip()]
                }
                action_rules.append(new_rule)
                policy["action_rules"] = action_rules
                if svc.save_policy(policy): st.success("Rule Added."); st.rerun()

    st.divider()

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

            if st.button("🗑️ Delete Cap Rule", key=f"del_cap_{i}"):
                cap_rules.pop(i)
                policy["capability_rules"] = cap_rules
                if svc.save_policy(policy): st.success("Rule Deleted."); st.rerun()

    st.markdown("#### ➕ Add New Capability Rule")
    with st.form("add_cap_rule_form", clear_on_submit=True):
        c_id = st.text_input("New Rule ID (e.g. domain:stripe)")
        c_kw = st.text_input("Keyword (e.g. stripe)")
        c_caps = st.text_input("Capabilities (comma separated, e.g. PaymentRead)")
        if st.form_submit_button("Add Capability Rule"):
            if not c_id or not c_kw:
                st.error("Rule ID and Keyword are required.")
            else:
                new_rule = {
                    "id": c_id,
                    "keyword": c_kw,
                    "capabilities": [c.strip() for c in c_caps.split(",") if c.strip()]
                }
                cap_rules.append(new_rule)
                policy["capability_rules"] = cap_rules
                if svc.save_policy(policy): st.success("Rule Added."); st.rerun()

    st.divider()

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


def _render_capability_ontology():
    from app.services.domain_capability_ontology import (
        DOMAIN_CAPABILITIES, DomainCapabilityOntology,
        get_domain_capabilities, save_domain_capabilities, reload_ontology
    )

    st.header("🧬 Capability Ontology")
    st.markdown(
        "Defines **hard/soft capability requirements** per domain intent. "
        "This drives the two-tier coverage logic in the decision engine."
    )
    st.info(
        "🔴 **Hard** = mission-critical — missing triggers a **violation/deny**.  \n"
        "🟡 **Soft** = advisory — missing lowers coverage score but only produces an **audit warning**."
    )

    caps = get_domain_capabilities()
    domains = sorted(caps.keys())
    selected_domain = st.selectbox("Select Domain", domains, key="ontology_domain")

    intents = caps.get(selected_domain, {})

    # --- Add New Intent ---
    with st.expander("➕ Add New Intent", expanded=False):
        new_intent = st.text_input("Intent Name", key="new_intent_name", placeholder="e.g., SecurityAudit")
        col1, col2 = st.columns(2)
        with col1:
            new_hard = st.text_input("Hard Capabilities (comma-separated)", key="new_hard_caps")
            new_required = st.text_input("Required Capabilities (comma-separated)", key="new_req_caps")
        with col2:
            new_soft = st.text_input("Soft Capabilities (comma-separated)", key="new_soft_caps")
            new_optional = st.text_input("Optional Capabilities (comma-separated)", key="new_opt_caps")

        if st.button("💾 Save New Intent", key="save_new_intent"):
            if new_intent.strip():
                parse = lambda s: [x.strip() for x in s.split(",") if x.strip()]
                caps.setdefault(selected_domain, {})[new_intent.strip()] = {
                    "hard": parse(new_hard),
                    "soft": parse(new_soft),
                    "required": parse(new_required),
                    "optional": parse(new_optional)
                }
                save_domain_capabilities(caps)
                reload_ontology()
                st.success(f"✅ Intent '{new_intent.strip()}' added to {selected_domain}")
                st.rerun()
            else:
                st.error("Intent name cannot be empty.")

    if not intents:
        st.warning("No intents defined for this domain.")
        return

    # --- Display & Edit Existing Intents ---
    for intent_name, intent_caps in intents.items():
        with st.expander(f"🎯 Intent: **{intent_name}**", expanded=True):
            hard_set = set(intent_caps.get("hard", []))
            soft_set = set(intent_caps.get("soft", []))
            required_set = set(intent_caps.get("required", []))
            optional_set = set(intent_caps.get("optional", []))

            all_caps_list = sorted(hard_set | soft_set | required_set | optional_set)
            concrete_caps = [
                c for c in all_caps_list if DomainCapabilityOntology.is_concrete(c)
            ]

            if concrete_caps:
                header = "| Capability | Criticality | Obligation |"
                separator = "|:---|:---:|:---:|"
                rows = []
                for cap in concrete_caps:
                    crit = "🔴 Hard" if cap in hard_set else "🟡 Soft"
                    oblig = "**Required**" if cap in required_set else "Optional"
                    rows.append(f"| `{cap}` | {crit} | {oblig} |")
                st.markdown("\n".join([header, separator] + rows))

            # Edit form
            edit_key = f"edit_{selected_domain}_{intent_name}"
            col_e1, col_e2, col_e3 = st.columns([3, 3, 1])
            with col_e1:
                edited_hard = st.text_input(
                    "Hard", value=", ".join(intent_caps.get("hard", [])), key=f"{edit_key}_hard"
                )
                edited_required = st.text_input(
                    "Required", value=", ".join(intent_caps.get("required", [])), key=f"{edit_key}_req"
                )
            with col_e2:
                edited_soft = st.text_input(
                    "Soft", value=", ".join(intent_caps.get("soft", [])), key=f"{edit_key}_soft"
                )
                edited_optional = st.text_input(
                    "Optional", value=", ".join(intent_caps.get("optional", [])), key=f"{edit_key}_opt"
                )
            with col_e3:
                st.write("")
                st.write("")
                if st.button("💾", key=f"{edit_key}_save", help="Save changes"):
                    parse = lambda s: [x.strip() for x in s.split(",") if x.strip()]
                    caps[selected_domain][intent_name] = {
                        "hard": parse(edited_hard),
                        "soft": parse(edited_soft),
                        "required": parse(edited_required),
                        "optional": parse(edited_optional)
                    }
                    save_domain_capabilities(caps)
                    reload_ontology()
                    st.success(f"✅ Updated '{intent_name}'")
                    st.rerun()
                if st.button("🗑️", key=f"{edit_key}_del", help="Delete intent"):
                    del caps[selected_domain][intent_name]
                    save_domain_capabilities(caps)
                    reload_ontology()
                    st.success(f"🗑️ Deleted '{intent_name}'")
                    st.rerun()
