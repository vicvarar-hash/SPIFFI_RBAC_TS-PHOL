import json
import yaml
import os
from typing import Dict, Any

class PolicyLoader:
    """Safe read/write utility for JSON and YAML policy files."""
    
    @staticmethod
    def load_json(filepath: str) -> Dict[str, Any]:
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return {}

    @staticmethod
    def save_json(filepath: str, data: Dict[str, Any]) -> bool:
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving {filepath}: {e}")
            return False

    @staticmethod
    def load_yaml(filepath: str) -> Dict[str, Any]:
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return {}

    @staticmethod
    def save_yaml(filepath: str, data: Dict[str, Any]) -> bool:
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error saving {filepath}: {e}")
            return False
