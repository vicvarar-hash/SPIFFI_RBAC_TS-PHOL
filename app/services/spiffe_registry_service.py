from typing import Dict, Tuple
from app.services.policy_loader import PolicyLoader
from app.services.policy_logger_service import PolicyLoggerService

class SpiffeRegistryService:
    def __init__(self, filepath: str = "policies/spiffe_registry.json"):
        self.filepath = filepath
        self.logger = PolicyLoggerService()
        self.registry = PolicyLoader.load_json(filepath)

    def get_all(self) -> Dict[str, str]:
        return self.registry

    def add_identity(self, name: str, spiffe_id: str) -> Tuple[bool, str]:
        if not spiffe_id.startswith("spiffe://"):
            return False, "SPIFFE ID must start with 'spiffe://'"
        if name in self.registry:
            return False, f"Identity name '{name}' already exists."
        if spiffe_id in self.registry.values():
            return False, f"SPIFFE ID '{spiffe_id}' already exists."

        self.registry[name] = spiffe_id
        success = PolicyLoader.save_json(self.filepath, self.registry)
        if success:
            self.logger.log_change("SPIFFE_REGISTRY", "create", f"Added {name}: {spiffe_id}")
            return True, "Identity added successfully."
        return False, "Failed to save to disk."

    def update_identity(self, old_name: str, new_name: str, new_spiffe_id: str) -> Tuple[bool, str]:
        if old_name not in self.registry:
            return False, "Identity does not exist."
        if not new_spiffe_id.startswith("spiffe://"):
            return False, "SPIFFE ID must start with 'spiffe://'"
        
        # Check for duplicates if name or id changed
        if new_name != old_name and new_name in self.registry:
            return False, f"Identity name '{new_name}' already exists."
            
        # Check values but ignore the current one we are modifying
        other_values = [v for k, v in self.registry.items() if k != old_name]
        if new_spiffe_id in other_values:
            return False, f"SPIFFE ID '{new_spiffe_id}' already exists."

        del self.registry[old_name]
        self.registry[new_name] = new_spiffe_id
        
        success = PolicyLoader.save_json(self.filepath, self.registry)
        if success:
            self.logger.log_change("SPIFFE_REGISTRY", "update", f"Updated {old_name} -> {new_name}: {new_spiffe_id}")
            return True, "Identity updated successfully."
        return False, "Failed to save to disk."

    def delete_identity(self, name: str) -> Tuple[bool, str]:
        if name not in self.registry:
            return False, "Identity does not exist."
        
        spiffe_id = self.registry.pop(name)
        success = PolicyLoader.save_json(self.filepath, self.registry)
        if success:
            self.logger.log_change("SPIFFE_REGISTRY", "delete", f"Deleted {name}: {spiffe_id}")
            return True, "Identity deleted successfully."
        return False, "Failed to save to disk."
