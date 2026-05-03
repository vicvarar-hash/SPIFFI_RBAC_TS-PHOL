# ══════════════════════════════════════════════════════════════════════
# PALADIN RBAC Policy — OPA/Rego Translation
#
# Translates policies/rbac.yaml into Rego.
# Evaluates per-tool RBAC: every (mcp, tool) pair must match an
# explicit ALLOW rule for the caller's SPIFFE ID, otherwise DENY.
# ══════════════════════════════════════════════════════════════════════
package paladin.rbac

import rego.v1

# Default: deny unless all tools are explicitly allowed
default decision := "DENY"

# ── DevOps Agent ─────────────────────────────────────────────────────
devops_allowed_mcps := {"grafana", "atlassian", "azure", "mongodb"}

tool_allowed(spiffe_id, mcp, _tool) if {
    spiffe_id == "spiffe://demo.local/agent/devops"
    mcp in devops_allowed_mcps
}

# ── Incident Agent ───────────────────────────────────────────────────
incident_grafana_tools := {
    "fetch_pyroscope_profile", "find_error_pattern_logs", "find_slow_requests",
    "generate_deeplink", "get_alert_rule_by_uid", "get_assertions",
    "get_current_oncall_users", "get_dashboard_by_uid", "get_dashboard_panel_queries",
    "get_dashboard_property", "get_dashboard_summary", "get_datasource_by_name",
    "get_datasource_by_uid", "get_incident", "get_oncall_shift",
    "get_sift_analysis", "get_sift_investigation", "list_alert_rules",
    "list_contact_points", "list_datasources", "list_incidents",
    "list_loki_label_names", "list_loki_label_values", "list_oncall_schedules",
    "list_oncall_teams", "list_oncall_users", "list_prometheus_label_names",
    "list_prometheus_label_values", "list_prometheus_metric_metadata",
    "list_prometheus_metric_names", "list_pyroscope_label_names",
    "list_pyroscope_label_values", "list_pyroscope_profile_types",
    "list_sift_investigations", "list_teams", "list_users_by_org",
    "query_loki_logs", "query_loki_stats", "query_prometheus",
    "search_dashboards", "add_activity_to_incident",
}

incident_atlassian_tools := {
    "confluence_get_comments", "confluence_get_labels", "confluence_get_page",
    "confluence_get_page_children", "confluence_search",
    "jira_batch_get_changelogs", "jira_download_attachments",
    "jira_get_agile_boards", "jira_get_board_issues", "jira_get_issue",
    "jira_get_link_types", "jira_get_project_issues", "jira_get_project_versions",
    "jira_get_sprint_issues", "jira_get_sprints_from_board",
    "jira_get_user_profile", "jira_get_worklog", "jira_search",
    "jira_search_fields", "jira_get_transitions",
    "jira_add_comment", "jira_add_worklog", "jira_transition_issue",
    "jira_link_to_epic", "jira_create_issue_link",
    "confluence_add_comment", "confluence_add_label",
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/agent/incident"
    mcp == "grafana"
    tool in incident_grafana_tools
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/agent/incident"
    mcp == "atlassian"
    tool in incident_atlassian_tools
}

# ── Finance Agent ────────────────────────────────────────────────────
finance_stripe_tools := {
    "finalize_invoice", "list_coupons", "list_customers", "list_invoices",
    "list_payment_intents", "list_prices", "list_products", "list_subscriptions",
    "retrieve_balance", "search_stripe_documentation",
    "create_coupon", "create_customer", "create_invoice", "create_invoice_item",
    "create_payment_link", "create_price", "create_product",
    "list_disputes", "update_dispute", "update_subscription",
}

finance_hummingbot_tools := {
    "explore_controllers", "get_active_bots_status", "get_candles",
    "get_funding_rate", "get_order_book", "get_orders",
    "get_portfolio_balances", "get_positions", "get_prices",
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/agent/finance"
    mcp == "stripe"
    tool in finance_stripe_tools
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/agent/finance"
    mcp == "hummingbot-mcp"
    tool in finance_hummingbot_tools
}

# ── Research Agent ───────────────────────────────────────────────────
research_wikipedia_tools := {
    "extract_key_facts", "get_article", "get_coordinates", "get_links",
    "get_related_topics", "get_sections", "get_summary",
    "search_wikipedia", "summarize_article_for_query", "summarize_article_section",
}

research_notion_tools := {
    "API-get-block-children", "API-get-self", "API-get-user", "API-get-users",
    "API-retrieve-a-block", "API-retrieve-a-comment", "API-retrieve-a-database",
    "API-retrieve-a-page", "API-retrieve-a-page-property",
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/agent/research"
    mcp == "wikipedia-mcp"
    tool in research_wikipedia_tools
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/agent/research"
    mcp == "notion"
    tool in research_notion_tools
}

# ── Automation Gateway ───────────────────────────────────────────────
# Full access to azure + mongodb (wildcard)
tool_allowed(spiffe_id, mcp, _tool) if {
    spiffe_id == "spiffe://demo.local/service/gateway"
    mcp in {"azure", "mongodb"}
}

# Read-only on grafana (same set as incident)
gateway_grafana_read := {
    "fetch_pyroscope_profile", "find_error_pattern_logs", "find_slow_requests",
    "generate_deeplink", "get_alert_rule_by_uid", "get_assertions",
    "get_current_oncall_users", "get_dashboard_by_uid", "get_dashboard_panel_queries",
    "get_dashboard_property", "get_dashboard_summary", "get_datasource_by_name",
    "get_datasource_by_uid", "get_incident", "get_oncall_shift",
    "get_sift_analysis", "get_sift_investigation", "list_alert_rules",
    "list_contact_points", "list_datasources", "list_incidents",
    "list_loki_label_names", "list_loki_label_values", "list_oncall_schedules",
    "list_oncall_teams", "list_oncall_users", "list_prometheus_label_names",
    "list_prometheus_label_values", "list_prometheus_metric_metadata",
    "list_prometheus_metric_names", "list_pyroscope_label_names",
    "list_pyroscope_label_values", "list_pyroscope_profile_types",
    "list_sift_investigations", "list_teams", "list_users_by_org",
    "query_loki_logs", "query_loki_stats", "query_prometheus",
    "search_dashboards",
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/gateway"
    mcp == "grafana"
    tool in gateway_grafana_read
}

# Read-only on atlassian
gateway_atlassian_read := {
    "confluence_get_comments", "confluence_get_labels", "confluence_get_page",
    "confluence_get_page_children", "confluence_search",
    "jira_batch_get_changelogs", "jira_download_attachments",
    "jira_get_agile_boards", "jira_get_board_issues", "jira_get_issue",
    "jira_get_link_types", "jira_get_project_issues", "jira_get_project_versions",
    "jira_get_sprint_issues", "jira_get_sprints_from_board",
    "jira_get_user_profile", "jira_get_worklog", "jira_search",
    "jira_search_fields",
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/gateway"
    mcp == "atlassian"
    tool in gateway_atlassian_read
}

# Read-only on stripe
gateway_stripe_read := {
    "finalize_invoice", "list_coupons", "list_customers", "list_invoices",
    "list_payment_intents", "list_prices", "list_products", "list_subscriptions",
    "retrieve_balance", "search_stripe_documentation",
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/gateway"
    mcp == "stripe"
    tool in gateway_stripe_read
}

# Read-only on hummingbot
tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/gateway"
    mcp == "hummingbot-mcp"
    tool in finance_hummingbot_tools
}

# Read-only on notion
tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/gateway"
    mcp == "notion"
    tool in research_notion_tools
}

# Read-only on wikipedia
tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/gateway"
    mcp == "wikipedia-mcp"
    tool in research_wikipedia_tools
}

# ── Security Engine ──────────────────────────────────────────────────
# Audit read-only across ALL domains — same read sets as gateway
tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/security"
    mcp == "grafana"
    tool in gateway_grafana_read
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/security"
    mcp == "atlassian"
    tool in gateway_atlassian_read
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/security"
    mcp == "azure"
    tool in security_azure_tools
}

security_azure_tools := {
    "list_databases", "list_clusters", "list_cosmos_accounts",
    "list_key_vaults", "list_resource_groups", "list_storage_accounts",
    "get_cluster", "get_cosmos_account", "get_key_vault",
    "get_resource_group", "get_storage_account",
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/security"
    mcp == "mongodb"
    tool in security_mongodb_tools
}

security_mongodb_tools := {
    "aggregate", "count", "find", "listCollections", "listDatabases",
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/security"
    mcp == "stripe"
    tool in gateway_stripe_read
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/security"
    mcp == "hummingbot-mcp"
    tool in finance_hummingbot_tools
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/security"
    mcp == "notion"
    tool in research_notion_tools
}

tool_allowed(spiffe_id, mcp, tool) if {
    spiffe_id == "spiffe://demo.local/service/security"
    mcp == "wikipedia-mcp"
    tool in research_wikipedia_tools
}

# ── Decision: ALLOW only if ALL (mcp, tool) pairs are allowed ───────
decision := "ALLOW" if {
    every i in numbers.range(0, count(input.tools) - 1) {
        tool_allowed(input.spiffe_id, input.mcps[i], input.tools[i])
    }
    count(input.tools) > 0
}
