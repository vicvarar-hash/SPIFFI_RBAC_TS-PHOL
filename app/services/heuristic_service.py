import logging
from typing import List, Dict, Any, Tuple
from app.services.policy_loader import PolicyLoader

logger = logging.getLogger(__name__)

class HeuristicService:
    """
    6B: Managed Heuristic Inference Service.
    Loads rules from heuristic_policy.json and evaluates them for
    tool-to-action and tool-to-capability mapping.
    """
    
    def __init__(self, filepath: str = "policies/heuristic_policy.json"):
        self.filepath = filepath
        self.policy = PolicyLoader.load_json(filepath)
        
    def get_all(self) -> Dict[str, Any]:
        """Returns the full policy object."""
        return self.policy
        
    def save_policy(self, data: Dict[str, Any]) -> bool:
        """Saves updated policy to disk."""
        if PolicyLoader.save_json(self.filepath, data):
            self.policy = data
            return True
        return False

    def infer_actions(self, tool: str) -> Tuple[List[str], str]:
        """
        Evaluates prefix rules to determine tool actions.
        Returns: (actions_list, matched_rule_id)
        """
        t_low = tool.lower()
        rules = self.policy.get("action_rules", [])
        
        for rule in rules:
            prefix = rule.get("prefix")
            # Improved matching: startswith OR contains as a separated part (e.g. jira_get_issue)
            if prefix and (t_low.startswith(prefix) or f"_{prefix}" in t_low or f".{prefix}" in t_low):
                return rule.get("actions", ["unknown"]), rule.get("id", rule.get("id", "prefix_match"))
                
        # Default fallback if no prefix matches
        return ["unknown"], "no_matching_prefix"

    def infer_capabilities(self, tool: str, actions: List[str] = None) -> Tuple[List[str], str]:
        """
        Evaluates keyword rules to determine tool capabilities.
        Returns: (capabilities_list, matched_rule_id)
        """
        t_low = tool.lower()
        rules = self.policy.get("capability_rules", [])
        
        for rule in rules:
            keyword = rule.get("keyword")
            if keyword and keyword in t_low:
                return rule.get("capabilities", []), rule.get("id", "keyword_match")
                
        # Final Fallback Logic
        fallbacks = self.policy.get("fallbacks", {})
        if actions:
            if "write" in actions:
                return [fallbacks.get("write_like", "UnknownWriteCapability")], "fallback_write"
            if "read" in actions:
                return [fallbacks.get("read_like", "UnknownReadCapability")], "fallback_read"
                
        return [fallbacks.get("default", "GenericRead")], "fallback_default"
