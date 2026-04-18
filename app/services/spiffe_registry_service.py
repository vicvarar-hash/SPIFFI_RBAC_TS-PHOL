from typing import Dict, Tuple, Any
from app.services.policy_loader import PolicyLoader
from app.services.policy_logger_service import PolicyLoggerService

class SpiffeRegistryService:
    def __init__(self, filepath: str = "policies/spiffe_registry.json"):
        self.filepath = filepath
        self.logger = PolicyLoggerService()
        self.registry = PolicyLoader.load_json(filepath)
        self._migrate_schema()

    def _migrate_schema(self):
        migrated = False
        for k, v in list(self.registry.items()):
            if isinstance(v, str):
                self.registry[k] = {
                    "display_name": k.replace("_", " ").title(),
                    "spiffe_id": v,
                    "description": "Auto-migrated identity"
                }
                migrated = True
        if migrated:
            PolicyLoader.save_json(self.filepath, self.registry)
            self.logger.log_change("SPIFFE_REGISTRY", "migrate", "Migrated legacy strings to persona dictionary format.")

    def get_all(self) -> Dict[str, Dict[str, str]]:
        return self.registry

    def add_identity(self, name: str, display_name: str, spiffe_id: str, description: str) -> Tuple[bool, str]:
        if not spiffe_id.startswith("spiffe://"):
            return False, "SPIFFE ID must start with 'spiffe://'"
        if name in self.registry:
            return False, f"Identity key '{name}' already exists."
            
        existing_spiffe_ids = [v.get("spiffe_id") for v in self.registry.values()]
        if spiffe_id in existing_spiffe_ids:
            return False, f"SPIFFE ID '{spiffe_id}' already exists."

        # Attempt to register in SPIRE as well
        from app.services.spiffe_workload_service import SpiffeWorkloadService
        workload_svc = SpiffeWorkloadService()
        spire_success, spire_msg = workload_svc.register_spiffe_entry(spiffe_id)
        if not spire_success:
             return False, f"Identity rejected by SPIRE: {spire_msg}"

        self.registry[name] = {
            "display_name": display_name,
            "spiffe_id": spiffe_id,
            "description": description,
            "attributes": {
                "clearance_level": "L1",
                "department": "Engineering",
                "trust_score": 1.0
            }
        }
        success = PolicyLoader.save_json(self.filepath, self.registry)
        if success:
            self.logger.log_change("SPIFFE_REGISTRY", "create", f"Added {name}: {spiffe_id} (SPIRE Registered)")
            return True, "Identity added successfully and registered in SPIRE."
        return False, "Failed to save to disk."

    def update_identity(self, old_name: str, new_name: str, display_name: str, new_spiffe_id: str, description: str) -> Tuple[bool, str]:
        if old_name not in self.registry:
            return False, "Identity does not exist."
        if not new_spiffe_id.startswith("spiffe://"):
            return False, "SPIFFE ID must start with 'spiffe://'"
        
        if new_name != old_name and new_name in self.registry:
            return False, f"Identity key '{new_name}' already exists."
            
        other_spiffe_ids = [v.get("spiffe_id") for k, v in self.registry.items() if k != old_name]
        if new_spiffe_id in other_spiffe_ids:
            return False, f"SPIFFE ID '{new_spiffe_id}' already exists."

        del self.registry[old_name]
        self.registry[new_name] = {
            "display_name": display_name,
            "spiffe_id": new_spiffe_id,
            "description": description
        }
        
        success = PolicyLoader.save_json(self.filepath, self.registry)
        if success:
            self.logger.log_change("SPIFFE_REGISTRY", "update", f"Updated {old_name} -> {new_name}: {new_spiffe_id}")
            return True, "Identity updated successfully."
        return False, "Failed to save to disk."

    def delete_identity(self, name: str) -> Tuple[bool, str]:
        if name not in self.registry:
            return False, "Identity does not exist."
        
        removed = self.registry.pop(name)
        success = PolicyLoader.save_json(self.filepath, self.registry)
        if success:
            self.logger.log_change("SPIFFE_REGISTRY", "delete", f"Deleted {name}: {removed.get('spiffe_id')}")
            return True, "Identity deleted successfully."
        return False, "Failed to save to disk."
