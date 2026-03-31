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
            # Iteration 4C fix: handle 'set' objects
            f.write(json.dumps(log_entry, default=lambda x: list(x) if isinstance(x, set) else str(x)) + "\n")
            
    def log_decision(self, task_idx: int, mode: str, prediction: Dict[str, Any], decision_result: Dict[str, Any]):
        active_rules = []
        if decision_result.get("context") and decision_result["context"].get("step_4_tsphol"):
            # Update for Iteration 4C: use .get("name") instead of .get("rule_name")
            active_rules = [r.get("name") for r in decision_result["context"]["step_4_tsphol"].get("rule_evaluations", []) if isinstance(r, dict) and r.get("triggered")]

        eval_states = decision_result.get("evaluation_states", {})
        
        # Iteration 4C metadata
        context = decision_result.get("context", {})
        intent = context.get("intent_decomposition")
        abac = context.get("abac_baseline")
        predicates = context.get("tsphol_predicate_set")

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "task_idx": task_idx,
            "mode": mode,
            "caller_display_name": decision_result.get("caller_display_name"),
            "spiffe_id": decision_result.get("spiffe_id"),
            "identity_source": decision_result.get("identity_source", "Simulated"),
            "benchmark_result": decision_result.get("benchmark_result"),
            "pre_llm_result": decision_result.get("pre_llm_result"),
            "llm_executed": decision_result.get("llm_executed"),
            "evaluation_states": eval_states,
            "final_decision": decision_result.get("final_decision"),
            "denial_source": decision_result.get("denial_source"),
            "active_tsphol_rules": active_rules,
            "intent_decomposition": intent,
            "abac_baseline": abac,
            "tsphol_predicates": predicates,
            "llm_output": decision_result.get("llm_output"),
            "derived_features": decision_result.get("derived_features"),
            "experiment_context": decision_result.get("experiment_context"),
            "prediction": prediction,
            "decision_payload": decision_result
        }
        with open(self.decision_log_path, "a", encoding="utf-8") as f:
            # Iteration 4C fix: handle 'set' objects (e.g. from PredicateEngine)
            f.write(json.dumps(log_entry, default=lambda x: list(x) if isinstance(x, set) else str(x)) + "\n")

