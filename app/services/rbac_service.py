from typing import List, Dict, Any, Tuple
from app.services.policy_loader import PolicyLoader
from app.services.policy_logger_service import PolicyLoggerService

class RBACService:
    def __init__(self, filepath: str = "policies/rbac.yaml"):
        self.filepath = filepath
        self.logger = PolicyLoggerService()
        data = PolicyLoader.load_yaml(filepath)
        self.policies = data.get("policies", [])

    def get_all(self) -> List[Dict[str, Any]]:
        return self.policies
        
    def get_policy_for_identity(self, spiffe_id: str) -> Dict[str, Any]:
        for policy in self.policies:
            if policy.get("spiffe_id") == spiffe_id:
                return policy
        return {}

    def save_policy(self, spiffe_id: str, description: str, rules: List[Dict[str, Any]]) -> Tuple[bool, str]:
        # Validate SPIFFE format
        if not spiffe_id.startswith("spiffe://"):
            return False, "SPIFFE ID must start with 'spiffe://'"
            
        # Basic rule validation
        for rule in rules:
            if "mcp" not in rule or "tools" not in rule or "action" not in rule:
                return False, "Rule missing required fields (mcp, tools, action)"
            if rule["action"] not in ["allow", "deny"]:
                return False, "Rule action must be 'allow' or 'deny'"

        existing_idx = -1
        for i, p in enumerate(self.policies):
            if p.get("spiffe_id") == spiffe_id:
                existing_idx = i
                break

        new_policy = {
            "spiffe_id": spiffe_id,
            "description": description,
            "rules": rules
        }

        if existing_idx >= 0:
            self.policies[existing_idx] = new_policy
            action = "update"
        else:
            self.policies.append(new_policy)
            action = "create"

        if self._save():
            self.logger.log_change("RBAC", action, f"Updated policy for {spiffe_id}")
            return True, "Policy saved successfully."
        return False, "Failed to save to disk."

    def delete_policy(self, spiffe_id: str) -> Tuple[bool, str]:
        initial_length = len(self.policies)
        self.policies = [p for p in self.policies if p.get("spiffe_id") != spiffe_id]
        
        if len(self.policies) == initial_length:
            return False, "Policy not found."
            
        if self._save():
            self.logger.log_change("RBAC", "delete", f"Deleted policy for {spiffe_id}")
            return True, "Policy deleted successfully."
        return False, "Failed to save to disk."

    def _save(self) -> bool:
        return PolicyLoader.save_yaml(self.filepath, {"policies": self.policies})
