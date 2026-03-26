import json
import os
from datetime import datetime
from typing import Dict, Any

class LoggerService:
    def __init__(self, log_dir: str = "results", log_filename: str = "prediction_logs.jsonl", decision_log_filename: str = "decision_logs.jsonl"):
        self.log_path = os.path.join(log_dir, log_filename)
        self.decision_log_path = os.path.join(log_dir, decision_log_filename)
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

    def log_prediction(self, mode: str, task_idx: int, task_text: str, output: Dict[str, Any], comparison: Dict[str, Any]):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "task_idx": task_idx,
            "task_text": task_text,
            "output": output,
            "comparison": comparison
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    def log_decision(self, task_idx: int, mode: str, prediction: Dict[str, Any], decision_result: Dict[str, Any]):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "task_idx": task_idx,
            "mode": mode,
            "prediction": prediction,
            "decision": decision_result
        }
        with open(self.decision_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

