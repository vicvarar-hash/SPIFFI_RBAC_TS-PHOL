from typing import List, Dict, Any, Set
import logging

logger = logging.getLogger(__name__)

class ToolClassifier:
    """
    Central authority for classifying tools into action types and capabilities.
    Refines predicate extraction by prioritizing tool-level metadata.
    """
    
    # Curated mappings for tool action categories
    TOOL_ACTION_MAP = {
        # ── Atlassian / Jira ──
        "jira_get_issue": ["read"],
        "jira_batch_get_changelogs": ["read", "history"],
        "jira_create_issue": ["write", "creation"],
        "jira_update_issue": ["write", "update"],
        "jira_search": ["read", "search"],
        "jira_add_comment": ["write", "annotation"],
        "jira_add_worklog": ["write", "annotation"],
        "jira_batch_create_issues": ["write", "creation"],
        "jira_create_issue_link": ["write", "creation"],
        "jira_create_sprint": ["write", "creation"],
        "jira_delete_issue": ["write", "delete"],
        "jira_download_attachments": ["read"],
        "jira_get_agile_boards": ["read"],
        "jira_get_board_issues": ["read"],
        "jira_get_link_types": ["read"],
        "jira_get_project_issues": ["read"],
        "jira_get_project_versions": ["read"],
        "jira_get_sprint_issues": ["read"],
        "jira_get_sprints_from_board": ["read"],
        "jira_get_transitions": ["read"],
        "jira_get_user_profile": ["read"],
        "jira_get_worklog": ["read", "history"],
        "jira_link_to_epic": ["write", "update"],
        "jira_remove_issue_link": ["write", "delete"],
        "jira_search_fields": ["read", "search"],
        "jira_transition_issue": ["write", "update"],
        "jira_update_sprint": ["write", "update"],
        # ── Atlassian / Confluence ──
        "confluence_add_comment": ["write", "annotation"],
        "confluence_add_label": ["write", "annotation"],
        "confluence_create_page": ["write", "creation"],
        "confluence_delete_page": ["write", "delete"],
        "confluence_get_comments": ["read"],
        "confluence_get_labels": ["read"],
        "confluence_get_page": ["read"],
        "confluence_get_page_children": ["read"],
        "confluence_search": ["read", "search"],
        "confluence_update_page": ["write", "update"],
        # ── Wikipedia / Research ──
        "search_wikipedia": ["read", "search"],
        "get_summary": ["read", "summarization"],
        "get_related_topics": ["read", "exploration"],
        "extract_key_facts": ["read", "extraction"],
        "get_sections": ["read"],
        "get_coordinates": ["read"],
        "summarize_article_for_query": ["read", "summarization"],
        "get_article": ["read"],
        "get_links": ["read"],
        # ── Grafana / Observability ──
        "query_prometheus": ["read"],
        "list_alerts": ["read", "search"],
        "list_alert_rules": ["read", "history"],
        "list_datasources": ["read"],
        "list_oncall_schedules": ["read", "oncall"],
        "find_error_pattern_logs": ["read", "search"],
        "get_alert_rule_by_uid": ["read", "alerting"],
        "get_current_oncall_users": ["read", "oncall"],
        "query_loki_logs": ["read", "logging"],
        "list_oncall_users": ["read", "oncall"],
        "fetch_pyroscope_profile": ["read"],
        "find_slow_requests": ["read", "search"],
        "generate_deeplink": ["read"],
        "get_assertions": ["read", "alerting"],
        "get_dashboard_by_uid": ["read"],
        "get_dashboard_panel_queries": ["read"],
        "get_dashboard_property": ["read"],
        "get_dashboard_summary": ["read"],
        "get_datasource_by_name": ["read"],
        "get_datasource_by_uid": ["read"],
        "get_incident": ["read"],
        "get_oncall_shift": ["read", "oncall"],
        "get_sift_analysis": ["read"],
        "list_contact_points": ["read", "alerting"],
        "list_incidents": ["read", "search"],
        "list_loki_label_names": ["read"],
        "list_loki_label_values": ["read"],
        "list_oncall_teams": ["read", "oncall"],
        "list_prometheus_label_names": ["read"],
        "list_prometheus_label_values": ["read"],
        "list_prometheus_metric_metadata": ["read"],
        "list_prometheus_metric_names": ["read"],
        "list_pyroscope_label_names": ["read"],
        "list_pyroscope_label_values": ["read"],
        "list_pyroscope_profile_types": ["read"],
        "list_teams": ["read"],
        "list_users_by_org": ["read"],
        "query_loki_stats": ["read"],
        "search_dashboards": ["read", "search"],
        "update_dashboard": ["write", "update"],
        # ── Sift / Investigations ──
        "list_sift_investigations": ["read", "search"],
        "get_sift_investigation": ["read"],
        # ── Incidents ──
        "create_incident": ["write", "creation"],
        "add_activity_to_incident": ["write", "annotation"],
        # ── Stripe / Financial ──
        "create_charge": ["write", "creation"],
        "get_customer": ["read"],
        "update_subscription": ["write", "update"],
        "cancel_subscription": ["write", "delete"],
        "create_coupon": ["write", "creation"],
        "create_customer": ["write", "creation"],
        "create_invoice": ["write", "creation"],
        "create_invoice_item": ["write", "creation"],
        "create_payment_link": ["write", "creation"],
        "create_price": ["write", "creation"],
        "create_product": ["write", "creation"],
        "create_refund": ["write", "creation"],
        "finalize_invoice": ["write", "update"],
        "list_coupons": ["read", "search"],
        "list_customers": ["read", "search"],
        "list_disputes": ["read", "search"],
        "list_invoices": ["read", "search"],
        "list_payment_intents": ["read", "search"],
        "list_prices": ["read", "search"],
        "list_products": ["read", "search"],
        "list_subscriptions": ["read", "search"],
        "retrieve_balance": ["read"],
        "search_stripe_documentation": ["read", "search"],
        "update_dispute": ["write", "update"],
        # ── Trading / Equity ──
        "get_trading_balance": ["read"],
        "place_order": ["write", "creation"],
        "cancel_order": ["write", "delete"],
        # ── Hummingbot ──
        "get_prices": ["read", "market_data"],
        "get_candles": ["read", "market_data"],
        "get_funding_rate": ["read", "market_data"],
        "get_market_data": ["read", "market_data"],
        "get_order_book": ["read", "market_data"],
        "get_ticker": ["read", "market_data"],
        "get_market_status": ["read", "market_data"],
        "get_orders": ["read", "strategy"],
        "get_balances": ["read", "strategy"],
        "deploy_bot_with_controllers": ["write", "execution"],
        "explore_controllers": ["read", "strategy"],
        "get_active_bots_status": ["read", "strategy"],
        "get_portfolio_balances": ["read", "strategy"],
        "get_positions": ["read", "strategy"],
        "modify_controllers": ["write", "update"],
        "set_account_position_mode_and_leverage": ["write", "update"],
        "setup_connector": ["write", "creation"],
        "stop_bot_or_controllers": ["write", "execution"],
        # ── Notion ──
        "API-create-a-comment": ["write", "annotation"],
        "API-create-a-database": ["write", "creation"],
        "API-delete-a-block": ["write", "delete"],
        "API-get-block-children": ["read"],
        "API-get-self": ["read"],
        "API-get-user": ["read"],
        "API-get-users": ["read"],
        "API-patch-block-children": ["write", "update"],
        "API-patch-page": ["write", "update"],
        "API-post-database-query": ["read", "search"],
        "API-post-page": ["write", "creation"],
        "API-post-search": ["read", "search"],
        "API-retrieve-a-block": ["read"],
        "API-retrieve-a-comment": ["read"],
        "API-retrieve-a-database": ["read"],
        "API-retrieve-a-page": ["read"],
        "API-retrieve-a-page-property": ["read"],
        "API-update-a-block": ["write", "update"],
        "API-update-a-database": ["write", "update"],
        # ── MongoDB ──
        "aggregate": ["read", "search"],
        "collection-indexes": ["read"],
        "collection-schema": ["read"],
        "collection-storage-size": ["read"],
        "connect": ["read"],
        "count": ["read"],
        "create-collection": ["write", "creation"],
        "create-index": ["write", "creation"],
        "db-stats": ["read"],
        "delete-many": ["write", "delete"],
        "drop-collection": ["write", "delete"],
        "drop-database": ["write", "delete"],
        "explain": ["read"],
        "export": ["read"],
        "find": ["read", "search"],
        "insert-many": ["write", "creation"],
        "list-collections": ["read"],
        "list-databases": ["read"],
        "mongodb-logs": ["read", "logging"],
        "rename-collection": ["write", "update"],
        "update-many": ["write", "update"],
        # ── Azure ──
        "azmcp-appconfig-account-list": ["read"],
        "azmcp-appconfig-kv-delete": ["write", "delete"],
        "azmcp-appconfig-kv-list": ["read"],
        "azmcp-appconfig-kv-lock": ["write", "update"],
        "azmcp-appconfig-kv-set": ["write", "creation"],
        "azmcp-appconfig-kv-show": ["read"],
        "azmcp-appconfig-kv-unlock": ["write", "update"],
        "azmcp-cosmos-account-list": ["read"],
        "azmcp-cosmos-database-container-item-query": ["read", "search"],
        "azmcp-cosmos-database-container-list": ["read"],
        "azmcp-cosmos-database-list": ["read"],
        "azmcp-extension-az": ["read"],
        "azmcp-extension-azd": ["read"],
        "azmcp-group-list": ["read"],
        "azmcp-monitor-log-query": ["read", "search"],
        "azmcp-monitor-table-list": ["read"],
        "azmcp-monitor-workspace-list": ["read"],
        "azmcp-search-index-describe": ["read"],
        "azmcp-search-index-list": ["read"],
        "azmcp-search-index-query": ["read", "search"],
        "azmcp-search-service-list": ["read"],
        "azmcp-storage-account-list": ["read"],
        "azmcp-storage-blob-container-details": ["read"],
        "azmcp-storage-blob-container-list": ["read"],
        "azmcp-storage-blob-list": ["read"],
        "azmcp-storage-table-list": ["read"],
        "azmcp-subscription-list": ["read"],
    }
    
    # Curated mappings for tool capabilities (covers full ASTRA dataset)
    TOOL_TO_CAPABILITY = {
        # ── Atlassian / Jira ──
        "jira_get_issue": ["IssueRead"],
        "jira_batch_get_changelogs": ["HistoryReview"],
        "jira_create_issue": ["IssueCreation"],
        "jira_update_issue": ["IssueUpdate"],
        "jira_search": ["IssueSearch"],
        "jira_add_comment": ["IssueUpdate"],
        "jira_add_worklog": ["IssueUpdate"],
        "jira_batch_create_issues": ["IssueCreation"],
        "jira_create_issue_link": ["IssueCreation"],
        "jira_create_sprint": ["IssueCreation"],
        "jira_delete_issue": ["IssueUpdate"],
        "jira_download_attachments": ["IssueRead"],
        "jira_get_agile_boards": ["IssueRead"],
        "jira_get_board_issues": ["IssueRead"],
        "jira_get_link_types": ["IssueRead"],
        "jira_get_project_issues": ["IssueRead"],
        "jira_get_project_versions": ["IssueRead"],
        "jira_get_sprint_issues": ["IssueRead"],
        "jira_get_sprints_from_board": ["IssueRead"],
        "jira_get_transitions": ["IssueRead"],
        "jira_get_user_profile": ["IssueRead"],
        "jira_get_worklog": ["HistoryReview"],
        "jira_link_to_epic": ["IssueUpdate"],
        "jira_remove_issue_link": ["IssueUpdate"],
        "jira_search_fields": ["IssueSearch"],
        "jira_transition_issue": ["IssueUpdate", "WorkflowTransition"],
        "jira_update_sprint": ["IssueUpdate"],
        # ── Atlassian / Confluence ──
        "confluence_add_comment": ["IssueUpdate"],
        "confluence_add_label": ["IssueUpdate"],
        "confluence_create_page": ["IssueCreation"],
        "confluence_delete_page": ["IssueUpdate"],
        "confluence_get_comments": ["IssueRead"],
        "confluence_get_labels": ["IssueRead"],
        "confluence_get_page": ["IssueRead"],
        "confluence_get_page_children": ["IssueRead"],
        "confluence_search": ["IssueSearch"],
        "confluence_update_page": ["IssueUpdate"],
        # ── Wikipedia / Research ──
        "search_wikipedia": ["KnowledgeSearch"],
        "get_summary": ["TopicSummarization"],
        "get_related_topics": ["ReferenceExploration"],
        "extract_key_facts": ["InformationDiscovery"],
        "get_sections": ["ContentSynthesis"],
        "get_coordinates": ["GeographicAnalysis"],
        "summarize_article_for_query": ["TopicSummarization"],
        "get_article": ["KnowledgeSearch"],
        "get_links": ["ReferenceExploration"],
        # ── Grafana / Observability ──
        "query_prometheus": ["MetricsQuery"],
        "list_alerts": ["AlertRuleReview"],
        "list_alert_rules": ["AlertRuleReview"],
        "list_datasources": ["DatasourceReview"],
        "list_oncall_schedules": ["OncallScheduleReview"],
        "find_error_pattern_logs": ["LogAnalysis"],
        "list_sift_investigations": ["InvestigationLookup"],
        "get_sift_investigation": ["InvestigationLookup"],
        "create_incident": ["IncidentCreation"],
        "add_activity_to_incident": ["IncidentAnnotation"],
        "get_alert_rule_by_uid": ["AlertRuleReview"],
        "get_current_oncall_users": ["OncallUserInspection"],
        "query_loki_logs": ["LogQuery"],
        "list_oncall_users": ["OncallUserInspection"],
        "fetch_pyroscope_profile": ["ProfilingAnalysis"],
        "find_slow_requests": ["LogAnalysis"],
        "generate_deeplink": ["DashboardInspection"],
        "get_assertions": ["AlertRuleReview"],
        "get_dashboard_by_uid": ["DashboardInspection"],
        "get_dashboard_panel_queries": ["DashboardInspection"],
        "get_dashboard_property": ["DashboardInspection"],
        "get_dashboard_summary": ["DashboardInspection"],
        "get_datasource_by_name": ["DatasourceReview"],
        "get_datasource_by_uid": ["DatasourceReview"],
        "get_incident": ["IncidentCorrelation"],
        "get_oncall_shift": ["OncallScheduleReview"],
        "get_sift_analysis": ["InvestigationLookup"],
        "list_contact_points": ["AlertRuleReview"],
        "list_incidents": ["IncidentCorrelation"],
        "list_loki_label_names": ["LogQuery"],
        "list_loki_label_values": ["LogQuery"],
        "list_oncall_teams": ["OncallUserInspection"],
        "list_prometheus_label_names": ["MetricsQuery"],
        "list_prometheus_label_values": ["MetricsQuery"],
        "list_prometheus_metric_metadata": ["MetricsQuery"],
        "list_prometheus_metric_names": ["MetricsQuery"],
        "list_pyroscope_label_names": ["ProfilingAnalysis"],
        "list_pyroscope_label_values": ["ProfilingAnalysis"],
        "list_pyroscope_profile_types": ["ProfilingAnalysis"],
        "list_teams": ["OncallUserInspection"],
        "list_users_by_org": ["OncallUserInspection"],
        "query_loki_stats": ["LogQuery"],
        "search_dashboards": ["DashboardInspection"],
        "update_dashboard": ["DashboardInspection"],
        # ── Stripe / Financial ──
        "create_charge": ["FinancialWrite"],
        "get_customer": ["FinancialRead"],
        "update_subscription": ["SubscriptionUpdate"],
        "cancel_subscription": ["SubscriptionUpdate"],
        "create_coupon": ["FinancialWrite"],
        "create_customer": ["FinancialWrite"],
        "create_invoice": ["FinancialWrite"],
        "create_invoice_item": ["FinancialWrite"],
        "create_payment_link": ["FinancialWrite"],
        "create_price": ["FinancialWrite"],
        "create_product": ["FinancialWrite"],
        "create_refund": ["FinancialWrite"],
        "finalize_invoice": ["FinancialWrite"],
        "list_coupons": ["FinancialRead"],
        "list_customers": ["FinancialRead"],
        "list_disputes": ["FinancialRead"],
        "list_invoices": ["FinancialRead"],
        "list_payment_intents": ["FinancialRead"],
        "list_prices": ["FinancialRead"],
        "list_products": ["FinancialRead"],
        "list_subscriptions": ["FinancialRead"],
        "retrieve_balance": ["FinancialRead"],
        "search_stripe_documentation": ["FinancialRead"],
        "update_dispute": ["FinancialWrite"],
        # ── Trading / Equity / Hummingbot ──
        "get_trading_balance": ["EquityRead"],
        "place_order": ["StrategyExecution"],
        "cancel_order": ["StrategyExecution"],
        "get_prices": ["MarketDataAnalysis"],
        "get_candles": ["MarketDataAnalysis"],
        "get_funding_rate": ["MarketDataAnalysis"],
        "get_market_data": ["MarketDataAnalysis"],
        "get_order_book": ["MarketDataAnalysis"],
        "get_ticker": ["MarketDataAnalysis"],
        "get_market_status": ["MarketDataAnalysis"],
        "get_orders": ["StrategyReview"],
        "get_balances": ["StrategyReview"],
        "deploy_bot_with_controllers": ["StrategyExecution"],
        "explore_controllers": ["StrategyReview"],
        "get_active_bots_status": ["StrategyReview"],
        "get_portfolio_balances": ["StrategyReview", "BalanceCheck"],
        "get_positions": ["StrategyReview"],
        "modify_controllers": ["StrategyExecution"],
        "set_account_position_mode_and_leverage": ["StrategyExecution"],
        "setup_connector": ["ExchangeInteraction"],
        "stop_bot_or_controllers": ["StrategyExecution"],
        # ── Notion ──
        "API-create-a-comment": ["NotionWrite"],
        "API-create-a-database": ["NotionWrite"],
        "API-delete-a-block": ["NotionWrite"],
        "API-get-block-children": ["NotionRead"],
        "API-get-self": ["NotionRead"],
        "API-get-user": ["NotionRead"],
        "API-get-users": ["NotionRead"],
        "API-patch-block-children": ["NotionWrite"],
        "API-patch-page": ["NotionWrite"],
        "API-post-database-query": ["NotionRead"],
        "API-post-page": ["NotionWrite"],
        "API-post-search": ["NotionRead"],
        "API-retrieve-a-block": ["NotionRead"],
        "API-retrieve-a-comment": ["NotionRead"],
        "API-retrieve-a-database": ["NotionRead"],
        "API-retrieve-a-page": ["NotionRead"],
        "API-retrieve-a-page-property": ["NotionRead"],
        "API-update-a-block": ["NotionWrite"],
        "API-update-a-database": ["NotionWrite"],
        # ── MongoDB ──
        "aggregate": ["QueryAnalysis"],
        "collection-indexes": ["IndexReview"],
        "collection-schema": ["CollectionScan"],
        "collection-storage-size": ["PerformanceAudit"],
        "connect": ["CollectionScan"],
        "count": ["QueryAnalysis"],
        "create-collection": ["CollectionScan"],
        "create-index": ["IndexReview"],
        "db-stats": ["PerformanceAudit"],
        "delete-many": ["CollectionScan"],
        "drop-collection": ["CollectionScan"],
        "drop-database": ["CollectionScan"],
        "explain": ["QueryAnalysis"],
        "export": ["CollectionScan"],
        "find": ["QueryAnalysis"],
        "insert-many": ["CollectionScan"],
        "list-collections": ["CollectionScan"],
        "list-databases": ["CollectionScan"],
        "mongodb-logs": ["PerformanceAudit"],
        "rename-collection": ["CollectionScan"],
        "update-many": ["CollectionScan"],
        # ── Azure ──
        "azmcp-appconfig-account-list": ["CloudResourceRead"],
        "azmcp-appconfig-kv-delete": ["CloudResourceWrite"],
        "azmcp-appconfig-kv-list": ["CloudResourceRead"],
        "azmcp-appconfig-kv-lock": ["CloudResourceWrite"],
        "azmcp-appconfig-kv-set": ["CloudResourceWrite"],
        "azmcp-appconfig-kv-show": ["CloudResourceRead"],
        "azmcp-appconfig-kv-unlock": ["CloudResourceWrite"],
        "azmcp-cosmos-account-list": ["CloudResourceRead"],
        "azmcp-cosmos-database-container-item-query": ["QueryAnalysis"],
        "azmcp-cosmos-database-container-list": ["CloudResourceRead"],
        "azmcp-cosmos-database-list": ["CloudResourceRead"],
        "azmcp-extension-az": ["CloudResourceRead"],
        "azmcp-extension-azd": ["CloudResourceRead"],
        "azmcp-group-list": ["CloudResourceRead"],
        "azmcp-monitor-log-query": ["LogAnalysis"],
        "azmcp-monitor-table-list": ["CloudResourceRead"],
        "azmcp-monitor-workspace-list": ["CloudResourceRead"],
        "azmcp-search-index-describe": ["CloudResourceRead"],
        "azmcp-search-index-list": ["CloudResourceRead"],
        "azmcp-search-index-query": ["QueryAnalysis"],
        "azmcp-search-service-list": ["CloudResourceRead"],
        "azmcp-storage-account-list": ["CloudResourceRead"],
        "azmcp-storage-blob-container-details": ["CloudResourceRead"],
        "azmcp-storage-blob-container-list": ["CloudResourceRead"],
        "azmcp-storage-blob-list": ["CloudResourceRead"],
        "azmcp-storage-table-list": ["CloudResourceRead"],
        "azmcp-subscription-list": ["CloudResourceRead"],
    }

    def __init__(self, heuristic_svc: Any = None, cap_svc: Any = None):
        from app.services.heuristic_service import HeuristicService
        from app.services.capability_inference_service import CapabilityInferenceService
        self.heuristic_svc = heuristic_svc or HeuristicService()
        self.cap_svc = cap_svc or CapabilityInferenceService()

    def classify_tools(self, tools: List[str]) -> List[Dict[str, Any]]:
        """
        6C: Refactor for 4-tier precedence:
        1. Curated Mapping
        2. Domain Capability Catalog
        3. Heuristic Policy
        4. Explicit Unknown Fallback
        """
        from app.services.normalization import normalize_tool_name
        
        audit_data = []
        for raw_tool in tools:
            tool = normalize_tool_name(raw_tool)
            # Tier 1: Curated
            actions = self.TOOL_ACTION_MAP.get(tool)
            caps = self.TOOL_TO_CAPABILITY.get(tool)
            
            source = "Curated Mapping"
            notes = "Direct match in system tool-to-capability map"
            
            # --- Tier 2: Domain Capability Catalog ---
            # If not curated, check if tool belongs to a known domain and exists in its catalog
            if caps is None:
                # Infer domain from tool prefix (heuristic but accurate for known MCPs)
                implied_domain = "General"
                if "jira" in tool or "atlassian" in tool: implied_domain = "Atlassian"
                elif "wiki" in tool: implied_domain = "Wikipedia"
                elif "hummingbot" in tool: implied_domain = "Hummingbot"
                elif "grafana" in tool or "prometheus" in tool: implied_domain = "Grafana"
                elif "mongo" in tool: implied_domain = "MongoDB"

                catalog_caps = self.cap_svc.catalog.get(implied_domain, [])
                # If the tool name itself happens to be a capability (rare but possible for grouping tools)
                if tool in catalog_caps:
                    caps = [tool]
                    source = "Domain Catalog"
                    notes = f"Tool identified as concrete capability for domain: {implied_domain}"

            # --- Tier 3: Heuristic Policy ---
            if actions is None:
                new_actions, rule_id = self.heuristic_svc.infer_actions(tool)
                actions = new_actions
                source = "Heuristic Policy"
                notes = f"Matched Action Rule '{rule_id}'"
            
            if caps is None:
                new_caps, rule_id = self.heuristic_svc.infer_capabilities(tool, actions)
                
                # 6C: If we got a generic fallback but have a known domain, prefer Tier 4
                is_generic = rule_id.startswith("fallback_")
                if is_generic and implied_domain != "General":
                    caps = [f"{implied_domain}ResourceAccess"]
                    source = "Domain Fallback"
                    notes = f"Tier 4: Scoped fallback for known domain: {implied_domain}"
                else:
                    caps = new_caps
                    if source == "Curated Mapping":
                        source = "Merged (Curated + Heuristic)"
                    else:
                        source = "Heuristic Policy"
                    notes += f" | Matched Cap Rule '{rule_id}'"
                
            # --- Tier 4: Explicit Fallback ---
            if not caps:
                # Scoped fallback: If domain is known, don't say 'Unknown'
                if implied_domain != "General":
                    caps = [f"{implied_domain}ResourceAccess"]
                    source = "Domain Fallback"
                    notes += f" | Scoped to domain: {implied_domain}"
                else:
                    caps = ["UnknownCapability"]
                    notes += " | Fallback to UnknownCapability"
                
            audit_data.append({
                "tool": tool,
                "actions": actions,
                "capabilities": caps,
                "source": source,
                "notes": notes,
                "is_read": "read" in (actions or []),
                "is_write": "write" in (actions or [])
            })
            
        return audit_data

    def get_aggregate_predicates(self, audit_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates request-level predicates from tool audit data.
        """
        contains_read = any(d["is_read"] for d in audit_data)
        contains_write = any(d["is_write"] for d in audit_data)
        
        # New Predicate: ContainsReadBeforeWrite
        # Heuristic: Contains both Read and Write in the tool bundle
        contains_read_before_write = contains_read and contains_write
        
        # Dominant Action Type
        if contains_read and contains_write:
            dominant = "mixed"
        elif contains_write:
            dominant = "write"
        elif contains_read:
            dominant = "read"
        else:
            dominant = "unknown"
            
        # Specific Action Flags
        contains_delete = any("delete" in (d.get("actions") or []) for d in audit_data)
        contains_history = any("history" in (d.get("actions") or []) for d in audit_data)
        contains_search = any("search" in (d.get("actions") or []) for d in audit_data)
        
        return {
            "ContainsRead": contains_read,
            "ContainsWrite": contains_write,
            "ContainsReadBeforeWrite": contains_read_before_write,
            "DominantActionType": dominant,
            "ContainsDelete": contains_delete,
            "ContainsHistory": contains_history,
            "ContainsSearch": contains_search
        }
