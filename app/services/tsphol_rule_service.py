from typing import List, Dict, Any, Tuple
from app.services.policy_loader import PolicyLoader
from app.services.policy_logger_service import PolicyLoggerService

class TSPHOLRuleService:
    def __init__(self, filepath: str = "policies/tsphol_rules.yaml"):
        self.filepath = filepath
        self.logger = PolicyLoggerService()
        data = PolicyLoader.load_yaml(filepath)
        self.rules = data.get("rules", [])

    def get_all(self) -> List[Dict[str, Any]]:
        return self.rules

    def save_rule(self, name: str, condition: Dict[str, Any], decision: str) -> Tuple[bool, str]:
        if not name or not condition or not decision:
            return False, "Name, condition, and decision are required."
            
        existing_idx = -1
        for i, r in enumerate(self.rules):
            if r.get("name") == name:
                existing_idx = i
                break

        new_rule = {
            "name": name,
            "condition": condition,
            "decision": decision
        }

        if existing_idx >= 0:
            self.rules[existing_idx] = new_rule
            action = "update"
        else:
            self.rules.append(new_rule)
            action = "create"

        if self._save():
            self.logger.log_change("TSPHOL", action, f"Updated rule {name}")
            return True, "Rule saved successfully."
        return False, "Failed to save to disk."

    def delete_rule(self, name: str) -> Tuple[bool, str]:
        initial_length = len(self.rules)
        self.rules = [r for r in self.rules if r.get("name") != name]
        
        if len(self.rules) == initial_length:
            return False, "Rule not found."
            
        if self._save():
            self.logger.log_change("TSPHOL", "delete", f"Deleted rule {name}")
            return True, "Rule deleted successfully."
        return False, "Failed to save to disk."

    def _save(self) -> bool:
        return PolicyLoader.save_yaml(self.filepath, {"rules": self.rules})
