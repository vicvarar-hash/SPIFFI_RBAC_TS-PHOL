import logging
from typing import List, Dict, Any
from app.services.abac_rule_service import ABACRuleService

logger = logging.getLogger(__name__)

class ABACEngine:
    """
    Attribute-Based Access Control (ABAC) Baseline Engine.
    Evaluates session state against simple attribute-based rules.
    Refined in Iteration 4I with structured reasoning trace.
    """
    
    def __init__(self, rule_svc: ABACRuleService = None):
        if rule_svc:
            self.rule_svc = rule_svc
        else:
            self.rule_svc = ABACRuleService()
            
        self.rules = self.rule_svc.get_all()

    def evaluate(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """
        6C: Enriched ABAC evaluation with semantic reasoning and applicability.
        """
        subject = attributes.get("subject", {})
        resource = attributes.get("resource", {})
        action = attributes.get("action", {})
        env = attributes.get("environment", {})
        
        confidence = env.get("confidence", 0.0)
        risk_level = resource.get("risk_level", "low")
        is_write = action.get("contains_write", False)
        is_multi = action.get("multi_domain", False)
        
        decision = "ALLOW"
        matched_rule = "Default ABAC Baseline"
        allow_reason = "Request met all baseline safety and confidence thresholds"
        failure_reason = ""
        
        trace_data = {
            "risk_level": risk_level,
            "is_write": is_write,
            "confidence": confidence,
            "multi_domain": is_multi,
            "logic_steps": []
        }
        
        self.rules = self.rule_svc.get_all()
        
        for rule in self.rules:
            rule_id = rule.get("id")
            rule_action = rule.get("action", "deny").upper()
            
            # --- 6C: Applicability Filter ---
            is_applicable = True
            
            # Action-aware targeting
            target_act = rule.get("target_action")
            if target_act == "write" and not is_write:
                is_applicable = False
            
            # Risk-aware targeting
            target_risk = rule.get("target_risk")
            if target_risk and risk_level != target_risk:
                is_applicable = False
            
            if not is_applicable:
                continue # Skip non-relevant rules for this context
                
            steps = []
            match = True
            
            # 6C: Rule Evaluation
            if "condition" in rule:
                cond_str = rule["condition"]
                if "confidence < 0.9" in cond_str:
                    is_match = (confidence < 0.9)
                    steps.append({"condition": "LLM confidence < 0.9", "matched": is_match})
                    if not is_match: match = False
                elif "risk < confidence" in cond_str:
                    risk_map = {"high": 0.9, "medium": 0.7, "low": 0.5}
                    threshold = risk_map.get(risk_level, 0.5)
                    is_match = (confidence < threshold)
                    steps.append({"condition": f"confidence < risk_threshold({threshold})", "matched": is_match})
                    if not is_match: match = False
            
            if "multi_domain_limit" in rule:
                is_match = (is_multi and risk_level == "high")
                steps.append({"condition": "Is high-risk multi-domain operation", "matched": is_match})
                if not is_match: match = False
                
            if "role" in rule:
                is_match = (subject.get("role") == rule["role"])
                steps.append({"condition": f"Persona == {rule['role']}", "matched": is_match})
                if not is_match: match = False
                
            # Final Rule Check
            if match and steps:
                decision = rule_action
                matched_rule = rule_id
                failure_reason = rule.get("failure_reason", "Rule triggered")
                allow_reason = "" # Cleared if denied
                trace_data["logic_steps"] = steps
                trace_data["applicable"] = True
                break
        
        # If we reached here without a break, it's an ALLOW
        if decision == "ALLOW":
            trace_data["applicable"] = True # General baseline is always applicable
            trace_data["logic_steps"].append({"condition": "Baseline safety check", "matched": True})

        return {
            "decision": decision,
            "matched_rule": matched_rule,
            "applicable": trace_data.get("applicable", True),
            "reasoning_trace": trace_data,
            "allow_reason": allow_reason,
            "failure_reason": failure_reason,
            "attributes_used": {
                "risk_level": risk_level,
                "is_write": is_write,
                "confidence": confidence,
                "multi_domain": is_multi,
                "role": subject.get("role")
            }
        }
