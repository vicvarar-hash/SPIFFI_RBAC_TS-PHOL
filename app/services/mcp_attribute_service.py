import os
from typing import Dict, Any, List
from app.services.policy_loader import PolicyLoader
from app.services.policy_logger_service import PolicyLoggerService

class MCPAttributeService:
    """
    Refined Attribute Service for MCP Resources.
    Replaces the legacy string-only risk levels with rich attribute dictionaries.
    """
    def __init__(self, policy_dir: str = "policies", logger: PolicyLoggerService = None):
        self.file_path = os.path.join(policy_dir, "mcp_attributes.yaml")
        self.logger = logger or PolicyLoggerService()
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.file_path):
            defaults = {
                "mcp_attributes": {
                    "wikipedia-mcp": {
                        "risk_level": "low",
                        "compliance_tier": "General",
                        "data_sensitivity": "Public",
                        "trust_boundary": "Third-Party"
                    },
                    "paper-search": {
                        "risk_level": "low",
                        "compliance_tier": "General",
                        "data_sensitivity": "Public",
                        "trust_boundary": "Third-Party"
                    },
                    "notion": {
                        "risk_level": "medium",
                        "compliance_tier": "General",
                        "data_sensitivity": "Internal",
                        "trust_boundary": "Vetted-Partner"
                    },
                    "grafana": {
                        "risk_level": "medium",
                        "compliance_tier": "Monitoring",
                        "data_sensitivity": "Metadata",
                        "trust_boundary": "Internal"
                    },
                    "atlassian": {
                        "risk_level": "medium",
                        "compliance_tier": "General",
                        "data_sensitivity": "Internal",
                        "trust_boundary": "Vetted-Partner"
                    },
                    "mongodb": {
                        "risk_level": "medium",
                        "compliance_tier": "General",
                        "data_sensitivity": "Financial",
                        "trust_boundary": "Internal"
                    },
                    "azure": {
                        "risk_level": "high",
                        "compliance_tier": "Enterprise",
                        "data_sensitivity": "Infrastructure",
                        "trust_boundary": "Vetted-Partner"
                    },
                    "stripe": {
                        "risk_level": "high",
                        "compliance_tier": "PCI-DSS",
                        "data_sensitivity": "Financial",
                        "trust_boundary": "Vetted-Partner"
                    },
                    "hummingbot-mcp": {
                        "risk_level": "high",
                        "compliance_tier": "Financial",
                        "data_sensitivity": "Private-Key",
                        "trust_boundary": "Experimental"
                    }
                }
            }
            PolicyLoader.save_yaml(self.file_path, defaults)
            self.logger.log_change("MCP_ATTRIBUTES", "create", "Initialized mcp_attributes.yaml with rich metadata.")

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        return PolicyLoader.load_yaml(self.file_path).get("mcp_attributes", {})

    def get_attributes_for_mcp(self, mcp_name: str) -> Dict[str, Any]:
        data = self.get_all()
        # Safe default if MCP is unknown
        return data.get(mcp_name, {
            "risk_level": "medium",
            "compliance_tier": "Unknown",
            "data_sensitivity": "Unknown",
            "trust_boundary": "External"
        })

    def set_attribute(self, mcp_name: str, attr_key: str, attr_value: Any) -> bool:
        data = self.get_all()
        if mcp_name not in data:
            data[mcp_name] = {}
        
        data[mcp_name][attr_key] = attr_value
        success = PolicyLoader.save_yaml(self.file_path, {"mcp_attributes": data})
        if success:
            self.logger.log_change("MCP_ATTRIBUTES", "update", f"Updated {mcp_name}.{attr_key} to {attr_value}")
        return success
