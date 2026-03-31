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
        "get_current_oncall_users": ["read", "oncall"]
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
        "get_current_oncall_users": ["OncallUserInspection"]
    }

    def classify_tools(self, tools: List[str]) -> List[Dict[str, Any]]:
        """
        Classifies each tool into action types and capabilities.
        Returns a list of metadata dictionaries.
        """
        audit_data = []
        for tool in tools:
            actions = self.TOOL_ACTION_MAP.get(tool)
            caps = self.TOOL_TO_CAPABILITY.get(tool)
            
            source = "Curated"
            notes = "Mapping found in catalog"
            
            if actions is None:
                source = "Heuristic"
                actions, fallback_notes = self._heuristic_action_classification(tool)
                notes = fallback_notes
            
            if caps is None:
                source = "Heuristic"
                caps = self._heuristic_capability_mapping(tool)
                
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

    def _heuristic_action_classification(self, tool: str) -> tuple:
        """
        Fallback heuristic based on tool name naming conventions.
        """
        t_low = tool.lower()
        read_keywords = ["get", "list", "query", "search", "retrieve", "fetch", "view", "show", "read", "summar"]
        write_keywords = ["create", "update", "modify", "patch", "delete", "post", "put", "insert", "add", "remove"]
        
        actions = []
        matched_kws = []
        
        if any(kw in t_low for kw in read_keywords):
            actions.append("read")
            matched_kws.append("read-like")
            
        if any(kw in t_low for kw in write_keywords):
            actions.append("write")
            matched_kws.append("write-like")
            
        if "delete" in t_low or "remove" in t_low:
            actions.append("delete")
            
        if not actions:
            return ["unknown"], "No matching keywords"
            
        return actions, f"Heuristic: Based on keywords: {', '.join(matched_kws)}"

    def _heuristic_capability_mapping(self, tool: str) -> List[str]:
        """
        Fallback heuristic for capability mapping.
        """
        t_low = tool.lower()
        if "jira" in t_low or "atlassian" in t_low: return ["IssueManagement"]
        if "wiki" in t_low: return ["KnowledgeDiscovery"]
        if "promo" in t_low or "metric" in t_low or "grafana" in t_low: return ["MetricsQuery"]
        if "sql" in t_low or "db" in t_low: return ["DatabaseAccess"]
        if "slack" in t_low or "notif" in t_low: return ["NotificationSend"]
        
        logger.warning(f"Fallback to GenericToolUse for tool: {tool}")
        return ["GenericToolUse"]
