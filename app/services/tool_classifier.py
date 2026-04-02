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
        # Atlassian / Jira
        "jira_get_issue": ["read"],
        "jira_batch_get_changelogs": ["read", "history"],
        "jira_create_issue": ["write", "creation"],
        "jira_update_issue": ["write", "update"],
        "jira_search": ["read", "search"],
        # Wikipedia / Research
        "search_wikipedia": ["read", "search"],
        "get_summary": ["read", "summarization"],
        "get_related_topics": ["read", "exploration"],
        # Grafana / Observability
        "query_prometheus": ["read"],
        "list_alerts": ["read", "search"],
        "list_alert_rules": ["read", "history"],
        "list_datasources": ["read"],
        "list_oncall_schedules": ["read", "oncall"],
        "find_error_pattern_logs": ["read", "search"],
        # Sift / Investigations
        "list_sift_investigations": ["read", "search"],
        "get_sift_investigation": ["read"],
        # Incidents
        "create_incident": ["write", "creation"],
        "add_activity_to_incident": ["write", "annotation"],
        # Financial / Payments
        "create_charge": ["write", "creation"],
        "get_customer": ["read"],
        "update_subscription": ["write", "update"],
        # Trading / Equity
        "get_trading_balance": ["read"],
        "place_order": ["write", "creation"],
        "cancel_order": ["write", "delete"],
        # Grafana New (4I)
        "get_alert_rule_by_uid": ["read", "alerting"],
        "get_current_oncall_users": ["read", "oncall"],
        "query_loki_logs": ["read", "logging"],
        "list_oncall_users": ["read", "oncall"],
        # Hummingbot (6C Curated)
        "get_prices": ["read", "market_data"],
        "get_candles": ["read", "market_data"],
        "get_funding_rate": ["read", "market_data"],
        "get_market_data": ["read", "market_data"],
        "get_orders": ["read", "strategy"],
        "get_balances": ["read", "strategy"],
        "place_order": ["write", "execution"],
        "cancel_order": ["write", "execution"]
    }
    
    # Curated mappings for tool capabilities
    TOOL_TO_CAPABILITY = {
        "jira_get_issue": ["IssueRead"],
        "jira_batch_get_changelogs": ["HistoryReview"],
        "jira_create_issue": ["IssueCreation"],
        "jira_update_issue": ["IssueUpdate"],
        "jira_search": ["IssueSearch"],
        "search_wikipedia": ["KnowledgeSearch"],
        "get_summary": ["TopicSummarization"],
        "get_related_topics": ["ReferenceExploration"],
        "query_prometheus": ["MetricsQuery"],
        "list_alerts": ["MetricsQuery"],
        "list_alert_rules": ["AlertRuleReview"],
        "list_datasources": ["DatasourceReview"],
        "list_oncall_schedules": ["OncallScheduleReview"],
        "find_error_pattern_logs": ["LogAnalysis"],
        "list_sift_investigations": ["InvestigationLookup"],
        "get_sift_investigation": ["InvestigationLookup"],
        "create_incident": ["IncidentCreation"],
        "add_activity_to_incident": ["IncidentAnnotation"],
        "create_charge": ["FinancialWrite"],
        "get_customer": ["FinancialRead"],
        "update_subscription": ["SubscriptionUpdate"],
        "get_trading_balance": ["EquityRead"],
        "place_order": ["EquityWrite"],
        "cancel_order": ["EquityWrite"],
        # Grafana New (4I)
        "get_alert_rule_by_uid": ["AlertRuleReview"],
        "get_current_oncall_users": ["OncallUserInspection"],
        "query_loki_logs": ["LogQuery"],
        "list_oncall_users": ["OncallUserInspection"],
        # Hummingbot (6C Curated)
        "get_prices": ["MarketDataAnalysis"],
        "get_candles": ["MarketDataAnalysis"],
        "get_funding_rate": ["MarketDataAnalysis"],
        "get_market_data": ["MarketDataAnalysis"],
        "get_orders": ["StrategyReview"],
        "get_balances": ["StrategyReview"],
        "place_order": ["StrategyExecution"],
        "cancel_order": ["StrategyExecution"]
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
