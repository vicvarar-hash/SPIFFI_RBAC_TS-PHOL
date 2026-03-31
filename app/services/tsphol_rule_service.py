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

    def save_rule(self, rule_name: str, description: str, conditions: List[Dict[str, Any]], action: str, derivation: str = None, priority: int = 0) -> Tuple[bool, str]:
        if not rule_name or not conditions or not action:
            return False, "Rule Name, conditions, and action (then) are required."
            
        existing_idx = -1
        for i, r in enumerate(self.rules):
            if r.get("rule_name") == rule_name:
                existing_idx = i
                break

        new_rule = {
            "rule_name": rule_name,
            "description": description,
            "if": conditions,
            "then": action,
            "priority": priority
        }
        if derivation:
            new_rule["derive"] = derivation

        if existing_idx >= 0:
            self.rules[existing_idx] = new_rule
            log_action = "update"
        else:
            self.rules.append(new_rule)
            log_action = "create"

        if self._save():
            self.logger.log_change("TSPHOL", log_action, f"Updated declarative rule {rule_name}")
            return True, "Declarative rule saved successfully."
        return False, "Failed to save to disk."

    def delete_rule(self, rule_name: str) -> Tuple[bool, str]:
        initial_length = len(self.rules)
        self.rules = [r for r in self.rules if r.get("rule_name") != rule_name]
        
        if len(self.rules) == initial_length:
            return False, "Rule not found."
            
        if self._save():
            self.logger.log_change("TSPHOL", "delete", f"Deleted rule {rule_name}")
            return True, "Rule deleted successfully."
        return False, "Failed to save to disk."

    def _save(self) -> bool:
        return PolicyLoader.save_yaml(self.filepath, {"rules": self.rules})
