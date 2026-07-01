from typing import List, Dict, Any, Tuple, Set
import logging

logger = logging.getLogger(__name__)

class TSPHOLInterpreter:
    """
    Generic predicate-rule interpreter for TRAC.
    Evaluates declarative JSON rules against session predicates.
    Refined in Iteration 4K to support full evaluation traces (audit transparency).
    """
    
    def evaluate_rules(self, predicates: Dict[str, Any], rules: List[Dict[str, Any]]) -> Tuple[str, Set[str], List[Dict[str, Any]], float]:
        """
        Orchestrates rule evaluation over predicates based on priority.
        Records evaluation status for EVERY rule and calculates a mathematical certainty probability.
        """
        derived = set()
        trace = []
        final_decision = "ALLOW"
        
        # 4R: Selection vs Validation Consistency Safeguard
        mode = predicates.get("mode", "validation")
        # In this iteration, we treat selection as 'ValidationEquivalent' if it has all caps
        # to ensure it doesn't get blocked by alignment alone.
        skip_alignment_denials = (mode == "selection")

        # Sort rules by priority (highest first)
        sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)

        for rule in sorted_rules:
            rule_name = rule.get("rule_name", "Unnamed Rule")
            conditions = rule.get("if", [])
            action = rule.get("then", "ALLOW")
            derivation = rule.get("derive")
            # Composition mode: enforcing rules can DENY; advisory rules (enforce: false)
            # raise an alert in the trace but never block — the assurance-layer model.
            enforce = rule.get("enforce", True)

            # 4R: Handle Alignment Evaluation Predicate specifically for transparency
            is_alignment_rule = rule_name == "capability_coverage_partial"
            alignment_eval = predicates.get("AlignmentEvaluated", True)
            
            # 4K: Evaluate and get structured reason
            matched, reason = self.evaluate_conditions(conditions, predicates, derived)
            
            # 4R: Transparency - Check if rule was skipped due to missing alignment data
            if is_alignment_rule and not alignment_eval:
                rule_res = {
                    "rule": rule_name,
                    "evaluated": False,
                    "triggered": False,
                    "passed": True,
                    "reason": "Alignment not evaluated (insufficient data)",
                    "action": action,
                    "status": "SKIPPED"
                }
                trace.append(rule_res)
                continue
                
            # 4R: Apply Selection Safeguard
            if is_alignment_rule and skip_alignment_denials and matched and action == "DENY":
                rule_res = {
                    "rule": rule_name,
                    "evaluated": True,
                    "triggered": True,
                    "passed": True, # Overridden by safeguard
                    "reason": f"{reason} | [SAFEGUARD] Deny skipped in selection mode",
                    "action": action,
                    "status": "SAFEGUARDED"
                }
                trace.append(rule_res)
                continue

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
                    if enforce:
                        # The first enforced deny sets the decision, but we DON'T stop: advisory
                        # rules must still assess this bundle so the audit trail — and OPA, which
                        # evaluates every rule independently — stay consistent (assurance model).
                        if final_decision != "DENY":
                            final_decision = "DENY"
                            rule_res["status"] = "ENFORCED"
                            trace.append(rule_res)
                        continue
                    # Advisory: record the alert but do not block, and keep evaluating so
                    # the audit trail captures every assessment on this bundle.
                    rule_res["advisory"] = True
                    rule_res["passed"] = True
                    rule_res["status"] = "ADVISORY"
                    trace.append(rule_res)
                    continue

            trace.append(rule_res)

        # Phase 2: Probabilistic Hardening
        # Mathematical certainty derived from TRAC facts (no LLM-reported confidence).
        certainty = 1.0

        # Penalize certainty for skipped safeguards or multiple derived warnings
        if final_decision == "ALLOW":
            safeguards_skipped = sum(1 for r in trace if r.get("status") == "SAFEGUARDED")
            warnings = len([d for d in derived if d in ["UnsafeWrite"]])
            penalty = (safeguards_skipped * 0.05) + (warnings * 0.1)
            certainty = max(0.5, certainty - penalty)
        # If TRAC mathematically denies, fail-secure: certainty stays at 1.0

        return final_decision, derived, trace, round(certainty, 2)

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
                # 4L: Human-friendly Reasoning
                if p_name == "RequiredCapabilities" and "not_subset_of" in cond:
                    return False, "Rule not triggered: all required capabilities are satisfied"
                if p_name == "ContainsRead" and cond.get("equals") is False:
                    return False, "Rule not triggered: ContainsRead = true → safe write context"
                if p_name == "MultiDomain" and cond.get("equals") is True:
                    return False, "Rule not triggered: request is not multi-domain"
                
                negation = "is not" if "==" in op else "does not satisfy"
                return False, f"{p_name} {negation} condition ({op})"
            
            # Matched Case (Reason Part)
            if p_name == "RequiredCapabilities" and "not_subset_of" in cond:
                diff = actual_val - predicates.get(cond["not_subset_of"], set())
                reason_part = f"Missing required capabilities: {diff}"
            elif p_name == "ContainsWrite" and cond.get("equals") is True:
                reason_part = "Request contains write operations"
            elif p_name == "MultiDomain" and cond.get("equals") is True:
                reason_part = "Request spans multiple domains (Elevated Risk)"
            else:
                reason_part = f"{p_name} matches condition ({op})"
            
            match_details.append(reason_part)

        return True, " & ".join(match_details)
