from typing import List, Dict, Any, Tuple
import os
from app.services.policy_loader import PolicyLoader
from app.services.policy_logger_service import PolicyLoggerService

class ABACRuleService:
    def __init__(self, filepath: str = "policies/abac_rules.yaml"):
        self.filepath = filepath
        self.logger = PolicyLoggerService()
        data = PolicyLoader.load_yaml(filepath)
        self.rules = data.get("rules", [])

    def get_all(self) -> List[Dict[str, Any]]:
        return self.rules

    def save_rule(self, rule_id: str, rule_data: Dict[str, Any]) -> Tuple[bool, str]:
        if not rule_id or not rule_data:
            return False, "Rule ID and data are required."
            
        existing_idx = -1
        for i, r in enumerate(self.rules):
            if r.get("id") == rule_id:
                existing_idx = i
                break

        new_rule = {"id": rule_id, **rule_data}

        if existing_idx >= 0:
            self.rules[existing_idx] = new_rule
            action = "update"
        else:
            self.rules.append(new_rule)
            action = "create"

        if self._save():
            self.logger.log_change("ABAC", action, f"Updated rule {rule_id}")
            return True, "Rule saved successfully."
        return False, "Failed to save to disk."

    def delete_rule(self, rule_id: str) -> Tuple[bool, str]:
        initial_length = len(self.rules)
        self.rules = [r for r in self.rules if r.get("id") != rule_id]
        
        if len(self.rules) == initial_length:
            return False, "Rule not found."
            
        if self._save():
            self.logger.log_change("ABAC", "delete", f"Deleted rule {rule_id}")
            return True, "Rule deleted successfully."
        return False, "Failed to save to disk."

    def _save(self) -> bool:
        return PolicyLoader.save_yaml(self.filepath, {"rules": self.rules})
