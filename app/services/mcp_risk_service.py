import os
from typing import Dict, Any
from app.services.policy_loader import PolicyLoader
from app.services.logger_service import LoggerService

class MCPRiskService:
    def __init__(self, policy_dir: str = "policies", logger: LoggerService = None):
        self.file_path = os.path.join(policy_dir, "mcp_risk_levels.yaml")
        self.logger = logger
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.file_path):
            defaults = {
                "mcp_risk_levels": {
                    "wikipedia-mcp": "low",
                    "paper-search": "low",
                    "notion": "medium",
                    "grafana": "medium",
                    "atlassian": "medium",
                    "mongodb": "medium",
                    "azure": "high",
                    "stripe": "high",
                    "hummingbot-mcp": "high"
                }
            }
            PolicyLoader.save_yaml(self.file_path, defaults)
            if self.logger:
                self.logger.log_policy_change("mcp_risk_levels.yaml", "CREATED_DEFAULT", defaults)

    def get_all(self) -> Dict[str, str]:
        data = PolicyLoader.load_yaml(self.file_path)
        return data.get("mcp_risk_levels", {})

    def get_risk_for_mcp(self, mcp_name: str) -> str:
        data = self.get_all()
        # Default to medium if not defined
        return data.get(mcp_name, "medium")

    def set_risk(self, mcp_name: str, risk_level: str) -> bool:
        if risk_level not in ["low", "medium", "high"]:
            return False
            
        data = PolicyLoader.load_yaml(self.file_path)
        if "mcp_risk_levels" not in data:
            data["mcp_risk_levels"] = {}
            
        data["mcp_risk_levels"][mcp_name] = risk_level
        PolicyLoader.save_yaml(self.file_path, data)
        
        if self.logger:
            self.logger.log_policy_change("mcp_risk_levels.yaml", "UPDATE_RISK", {"mcp": mcp_name, "risk": risk_level})
        return True
