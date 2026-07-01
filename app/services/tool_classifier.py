from typing import List, Dict, Any, Set
import logging

logger = logging.getLogger(__name__)

class ToolClassifier:
    """
    Central authority for classifying tools into action types and capabilities.
    Refines predicate extraction by prioritizing tool-level metadata.
    """
    
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

            # --- Action: the VerbNet-grounded lexicon is the SINGLE authoritative source ---
            # read / write / destructive is decided solely by the Levin/VerbNet/FrameNet lexicon
            # over (tool name + MCP description). Every rule keyed on the action — ABAC
            # `contains_write` / `contains_destructive_write`; TRAC `write_safety` / `action_coherence`;
            # the agnostic `{domain}:{action}` capability — rests on this one auditable, standards-based
            # classifier. Read by default (availability-safe). No name-prefix rules, no per-tool action map.
            from app.services.verb_action_classifier import classify_action, tool_description
            v_write, v_destructive, v_verb = classify_action(raw_tool, tool_description(raw_tool))
            if v_destructive:
                actions = ["write", "delete"]
            elif v_write:
                actions = ["write"]
            else:
                actions = ["read"]
            notes = f"action:verbnet({v_verb or 'default-read'})"

            # --- Capability NAME (display / alignment only; does NOT drive read/write) ---
            caps = self.TOOL_TO_CAPABILITY.get(tool)
            source = "Curated capability" if caps is not None else None

            implied_domain = "General"
            if "jira" in tool or "atlassian" in tool: implied_domain = "Atlassian"
            elif "wiki" in tool: implied_domain = "Wikipedia"
            elif "hummingbot" in tool: implied_domain = "Hummingbot"
            elif "grafana" in tool or "prometheus" in tool: implied_domain = "Grafana"
            elif "mongo" in tool: implied_domain = "MongoDB"

            if caps is None:
                catalog_caps = self.cap_svc.catalog.get(implied_domain, [])
                if tool in catalog_caps:
                    caps = [tool]
                    source = "Domain catalog"
            if caps is None:
                new_caps, rule_id = self.heuristic_svc.infer_capabilities(tool, actions)
                if rule_id.startswith("fallback_") and implied_domain != "General":
                    caps = [f"{implied_domain}ResourceAccess"]
                    source = "Domain fallback"
                else:
                    caps = new_caps
                    source = source or "Generic capability"
            if not caps:
                caps = ([f"{implied_domain}ResourceAccess"] if implied_domain != "General"
                        else ["UnknownCapability"])
                source = source or "Fallback"

            audit_data.append({
                "tool": tool,
                "actions": actions,
                "capabilities": caps,
                "source": source or "VerbNet action",
                "notes": notes,
                "is_read": "read" in actions,
                "is_write": "write" in actions,
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
