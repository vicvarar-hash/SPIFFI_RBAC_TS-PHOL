import logging
from typing import List, Dict, Any
from app.services.abac_rule_service import ABACRuleService

logger = logging.getLogger(__name__)

class ABACEngine:
    """
    Attribute-Based Access Control (ABAC) Baseline Engine.
    Refactored to support generic attribute matching across Subject, Resource, Action, and Environment.
    """
    
    def __init__(self, rule_svc: ABACRuleService = None):
        self.rule_svc = rule_svc or ABACRuleService()
        self.rules = self.rule_svc.get_all()

    def evaluate(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generic ABAC evaluation.
        Iteration 5: Supports declarative attribute matching.
        """
        decision = "ALLOW"
        matched_rule = "Default ABAC Baseline"
        allow_reason = "Request met all static attribute safety policies"
        failure_reason = ""
        logic_steps = []
        
        # Refresh rules in case of disk updates
        self.rules = self.rule_svc.get_all()
        
        for rule in self.rules:
            rule_id = rule.get("id", "unknown")
            rule_action = rule.get("action", "deny").upper()
            
            # 1. Applicability Check (Targeting)
            is_applicable = True
            # Legacy targeting support for backward compatibility if needed, 
            # but preferred way is match_attributes
            target_act = rule.get("target_action")
            if target_act == "write" and not attributes.get("action", {}).get("contains_write"):
                is_applicable = False
            
            if not is_applicable:
                continue

            # 2. Attribute Match Core
            match_specs = rule.get("match_attributes", [])
            if not match_specs and "role" in rule:
                # Support legacy 'role' key
                match_specs.append({"source": "subject", "attribute": "role", "value": rule["role"], "op": "=="})

            if not match_specs:
                continue

            rule_matched = True
            current_steps = []
            
            for spec in match_specs:
                source = spec.get("source")
                attr_name = spec.get("attribute")
                expected_val = spec.get("value")
                op = spec.get("op", "==")
                
                actual_val = self._get_nested_attr(attributes, source, attr_name)
                
                is_match = self._compare(actual_val, expected_val, op)
                current_steps.append({
                    "condition": f"{source}.{attr_name} {op} {expected_val}",
                    "matched": is_match,
                    "actual": str(actual_val)
                })
                
                if not is_match:
                    rule_matched = False
                    # We continue the loop to collect all steps for the trace
            
            if rule_matched:
                decision = rule_action
                matched_rule = rule_id
                failure_reason = rule.get("failure_reason", "Attribute policy violation")
                allow_reason = "" if decision == "DENY" else allow_reason
                
                # Enrich steps with the context of the rule that finalizes them
                for step in current_steps:
                    step["rule_id"] = rule_id
                    step["decision"] = rule_action
                
                logic_steps = current_steps
                break
        
        if decision == "ALLOW" and not logic_steps:
            logic_steps.append({
                "condition": "Static trait baseline", 
                "matched": True, 
                "rule_id": "system_default", 
                "decision": "ALLOW",
                "actual": "N/A"
            })

        return {
            "decision": decision,
            "matched_rule": matched_rule,
            "applicable": True,
            "reasoning_trace": {
                "logic_steps": logic_steps
            },
            "allow_reason": allow_reason,
            "failure_reason": failure_reason,
            "attributes_used": attributes
        }

    def _get_nested_attr(self, data: Dict[str, Any], source: str, path: str) -> Any:
        root = data.get(source, {})
        parts = path.split('.')
        current = root
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _compare(self, actual: Any, expected: Any, op: str) -> bool:
        try:
            if op == "==": return actual == expected
            if op == "!=": return actual != expected
            if op == ">": return float(actual) > float(expected)
            if op == "<": return float(actual) < float(expected)
            if op == "in": return actual in expected if isinstance(expected, list) else expected in str(actual)
            return False
        except (ValueError, TypeError):
            return False
