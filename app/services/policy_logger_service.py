import json
import os
from datetime import datetime
from typing import Dict, Any

class PolicyLoggerService:
    def __init__(self, log_dir: str = "results", log_filename: str = "policy_changes.jsonl"):
        self.log_path = os.path.join(log_dir, log_filename)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

    def log_change(self, policy_type: str, action: str, details: str):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": policy_type,
            "action": action,
            "details": details
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
