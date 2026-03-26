from typing import List, Tuple
from app.services.policy_loader import PolicyLoader
from app.services.policy_logger_service import PolicyLoggerService
from app.services.spiffe_registry_service import SpiffeRegistryService

class SpiffeAllowlistService:
    def __init__(self, filepath: str = "policies/spiffe_allowlist.json", registry_service: SpiffeRegistryService = None):
        self.filepath = filepath
        self.logger = PolicyLoggerService()
        self.registry_service = registry_service or SpiffeRegistryService()
        
        data = PolicyLoader.load_json(filepath)
        self.allowlist = data.get("allowed_callers", [])

    def get_all(self) -> List[str]:
        return self.allowlist

    def add_identity(self, spiffe_id: str) -> Tuple[bool, str]:
        if not spiffe_id.startswith("spiffe://"):
            return False, "SPIFFE ID must start with 'spiffe://'"
            
        # Validate against registry
        registry_ids = list(self.registry_service.get_all().values())
        if spiffe_id not in registry_ids:
            return False, "SPIFFE ID must be defined in the Registry first."
            
        if spiffe_id in self.allowlist:
            return False, "SPIFFE ID is already in the allowlist."

        self.allowlist.append(spiffe_id)
        if self._save():
            self.logger.log_change("TRANSPORT_ALLOWLIST", "add", f"Added {spiffe_id}")
            return True, "Identity added to allowlist."
        return False, "Failed to save to disk."

    def remove_identity(self, spiffe_id: str) -> Tuple[bool, str]:
        if spiffe_id not in self.allowlist:
            return False, "Identity not in allowlist."
            
        self.allowlist.remove(spiffe_id)
        if self._save():
            self.logger.log_change("TRANSPORT_ALLOWLIST", "remove", f"Removed {spiffe_id}")
            return True, "Identity removed from allowlist."
        return False, "Failed to save to disk."
        
    def _save(self) -> bool:
        return PolicyLoader.save_json(self.filepath, {"allowed_callers": self.allowlist})
