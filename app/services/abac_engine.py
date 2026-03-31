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
        Evaluates the session based on nested attributes:
        subject, resource, action, environment
        """
        subject = attributes.get("subject", {})
        resource = attributes.get("resource", {})
        action = attributes.get("action", {})
        env = attributes.get("environment", {})
        
        confidence = env.get("confidence", 0.0)
        risk_level = resource.get("risk_level", "low")
        is_write = action.get("contains_write", False)
        
        decision = "ALLOW"
        matched_rule = "Calibrated Baseline ALLOW"
        
        # 4I: Reasoning Trace Initialization
        trace_data = {
            "risk_level": risk_level,
            "is_write": is_write,
            "confidence": confidence,
            "multi_domain": action.get("multi_domain", False),
            "logic_steps": []
        }
        
        # 1. Calibrated Threshold Logic (Iteration 4G)
        if is_write:
            if risk_level == "high" and confidence < 0.95:
                decision = "DENY"
                matched_rule = "ABAC Rule: High risk write requires extreme confidence (>= 0.95)"
                trace_data["logic_steps"].append({"condition": "risk_level == high and confidence < 0.95", "matched": True})
            elif risk_level == "medium" and confidence < 0.9:
                decision = "DENY"
                matched_rule = "ABAC Rule: Medium risk write requires high confidence (>= 0.9)"
                trace_data["logic_steps"].append({"condition": "risk_level == medium and confidence < 0.90", "matched": True})
            elif risk_level == "low" and confidence < 0.8:
                decision = "DENY"
                matched_rule = "ABAC Rule: Low risk write requires moderate confidence (>= 0.8)"
                trace_data["logic_steps"].append({"condition": "risk_level == low and confidence < 0.80", "matched": True})
            else:
                trace_data["logic_steps"].append({"condition": f"confidence >= threshold for risk {risk_level} write", "matched": True})
        else:
            # Read-only operations are more permissive
            if risk_level == "high" and confidence < 0.85:
                decision = "DENY"
                matched_rule = "ABAC Rule: High risk read requires solid confidence (>= 0.85)"
                trace_data["logic_steps"].append({"condition": "risk_level == high and confidence < 0.85", "matched": True})
            elif risk_level == "medium" and confidence < 0.75:
                decision = "DENY"
                matched_rule = "ABAC Rule: Medium risk read requires basic confidence (>= 0.75)"
                trace_data["logic_steps"].append({"condition": "risk_level == medium and confidence < 0.75", "matched": True})
            elif risk_level == "low" and confidence < 0.6:
                decision = "DENY"
                matched_rule = "ABAC Rule: Low risk read requires minimal confidence (>= 0.6)"
                trace_data["logic_steps"].append({"condition": "risk_level == low and confidence < 0.60", "matched": True})
            else:
                trace_data["logic_steps"].append({"condition": f"confidence >= threshold for risk {risk_level} read", "matched": True})

        # 2. Multi-domain risk constraint (Keep as secondary check)
        if decision == "ALLOW" and action.get("multi_domain") and risk_level == "high":
            decision = "DENY"
            matched_rule = "ABAC Rule: Multi-domain high risk access restricted"
            trace_data["logic_steps"].append({"condition": "is_multi_domain and risk_level == high", "matched": True})

        # 3. Explicit Role Deny (Keep for flexibility)
        if decision == "ALLOW":
            self.rules = self.rule_svc.get_all()
            for rule in self.rules:
                if rule.get("role") == subject.get("role") and rule.get("action") == "deny":
                    decision = "DENY"
                    matched_rule = f"ABAC Rule: Explicit Deny for Role {subject.get('role')}"
                    trace_data["logic_steps"].append({"condition": f"explicit_deny_role_{subject.get('role')}", "matched": True})
                    break
        
        # Log final ABAC result (4I Criterion)
        logger.info(f"ABAC evaluation result: {decision} ({matched_rule})")
        
        return {
            "decision": decision,
            "matched_rule": matched_rule,
            "reasoning_trace": trace_data, # Detailed 4I Trace
            "attributes_used": {
                "risk_level": risk_level,
                "is_write": is_write,
                "confidence": confidence,
                "multi_domain": action.get("multi_domain", False)
            }
        }
