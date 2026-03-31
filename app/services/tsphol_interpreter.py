from typing import List, Dict, Any, Tuple, Set
import logging

logger = logging.getLogger(__name__)

class TSPHOLInterpreter:
    """
    Generic predicate-rule interpreter for TS-PHOL.
    Evaluates declarative JSON rules against session predicates.
    Refined in Iteration 4K to support full evaluation traces (audit transparency).
    """
    
    def evaluate_rules(self, predicates: Dict[str, Any], rules: List[Dict[str, Any]]) -> Tuple[str, Set[str], List[Dict[str, Any]]]:
        """
        Orchestrates rule evaluation over predicates based on priority.
        Records evaluation status for EVERY rule.
        """
        derived = set()
        trace = []
        final_decision = "ALLOW"

        # Sort rules by priority (highest first)
        sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)

        for rule in sorted_rules:
            rule_name = rule.get("rule_name", "Unnamed Rule")
            conditions = rule.get("if", [])
            action = rule.get("then", "ALLOW")
            derivation = rule.get("derive")

            # 4K: Evaluate and get structured reason
            matched, reason = self.evaluate_conditions(conditions, predicates, derived)
            
            # Rule Result Schema (4K Standard)
            rule_res = {
                "rule": rule_name,
                "evaluated": True,
                "triggered": matched,
                "passed": not (matched and action.upper() == "DENY"),
                "reason": reason,
                "action": action
            }

            if matched:
                if derivation:
                    derived.add(derivation)
                    # Update predicates to allow subsequent rules to use derived ones
                    predicates[derivation] = True
                    rule_res["derived"] = derivation

                if action.upper() == "DENY":
                    final_decision = "DENY"
                    trace.append(rule_res)
                    # Stop on first DENY, but we have recorded all evaluations up to this point
                    break
            
            trace.append(rule_res)

        return final_decision, derived, trace

    def evaluate_conditions(self, conditions: List[Dict[str, Any]], predicates: Dict[str, Any], derived: Set[str]) -> Tuple[bool, str]:
        """
        Evaluates a set of 'if' conditions against base and derived predicates.
        Refined in 4K to return human-readable reasoning for both success and failure.
        """
        match_details = []
        
        # If no conditions, rules trigger by default (usually used for catch-alls)
        if not conditions:
            return True, "No conditions specified (Default Trigger)"

        for cond in conditions:
            p_name = cond.get("predicate")
            if not p_name:
                continue
                
            actual_val = predicates.get(p_name)
            if actual_val is None and p_name in derived:
                actual_val = True

            matched = False
            op = "equals"
            
            # Operator mapping & execution
            if "equals" in cond:
                op = "=="
                matched = (actual_val == cond["equals"])
                reason_part = f"{p_name}({actual_val}) {op} {cond['equals']}"
            elif "lt" in cond:
                op = "<"
                matched = (actual_val < cond["lt"]) if actual_val is not None else False
                reason_part = f"{p_name}({actual_val}) {op} {cond['lt']}"
            elif "gt" in cond:
                op = ">"
                matched = (actual_val > cond["gt"]) if actual_val is not None else False
                reason_part = f"{p_name}({actual_val}) {op} {cond['gt']}"
            elif "includes" in cond or "contains" in cond:
                op = "includes"
                target = cond.get("includes") or cond.get("contains")
                if isinstance(actual_val, (set, list)):
                    matched = target in actual_val
                else:
                    matched = (actual_val == target)
                reason_part = f"{p_name} includes '{target}'"
            elif "missing" in cond:
                op = "missing"
                target = cond["missing"]
                if isinstance(actual_val, (set, list)):
                    matched = target not in actual_val
                else:
                    matched = (actual_val != target)
                reason_part = f"{p_name} missing '{target}'"
            elif "not_subset_of" in cond:
                op = "⊈"
                subset_name = cond["not_subset_of"]
                superset_val = predicates.get(subset_name, set())
                if isinstance(actual_val, set) and isinstance(superset_val, set):
                    matched = not actual_val.issubset(superset_val)
                    diff = actual_val - superset_val
                    reason_part = f"{p_name} missing {diff} from {subset_name}" if matched else f"{p_name} satisfies {subset_name}"
                else:
                    matched = False
                    reason_part = f"Invalid set comparison for {p_name}"
            else:
                return False, f"Unsupported operator in rule for predicate: {p_name}"
            
            if not matched:
                # Return failure reason immediately
                # 4K Human-readable tweak
                negation = "is not" if "==" in op else "does not satisfy"
                return False, f"{p_name} {negation} condition ({op})"
            
            match_details.append(reason_part)

        return True, " & ".join(match_details)
