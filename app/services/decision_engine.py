from typing import List, Dict, Any
from app.models.decision import DecisionResult
from app.models.mcp import MCPPersona
from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService
from app.services.mcp_risk_service import MCPRiskService

class DecisionEngine:
    def __init__(self, 
                 registry_svc: SpiffeRegistryService,
                 allowlist_svc: SpiffeAllowlistService,
                 rbac_svc: RBACService,
                 tsphol_svc: TSPHOLRuleService,
                 risk_svc: MCPRiskService,
                 personas: List[MCPPersona]):
        self.registry_svc = registry_svc
        self.allowlist_svc = allowlist_svc
        self.rbac_svc = rbac_svc
        self.tsphol_svc = tsphol_svc
        self.risk_svc = risk_svc
        self.persona_map = {p.name: p for p in personas}

    def pre_llm_check(self, caller_spiffe_id: str, mcps: List[str] = None, tools: List[str] = None) -> dict:
        trace = []
        eval_context = {}
        trace.append(f"Engine initialized. Pre-LLM check for {caller_spiffe_id}")
        
        evaluation_states = {
            "identity": "NOT_EVALUATED",
            "transport": "NOT_EVALUATED",
            "rbac": "NOT_EVALUATED",
            "tsphol": "NOT_EVALUATED"
        }
        
        # --- Step 1: SPIFFE Identity Check ---
        evaluation_states["identity"] = "DENY"
        registry_ids = [v.get("spiffe_id") for v in self.registry_svc.get_all().values()]
        if caller_spiffe_id not in registry_ids:
            trace.append("SPIFFE Check: Identity not found in Registry. ❌")
            eval_context["step_1_identity"] = {"caller": caller_spiffe_id, "found_in_registry": False}
            return {
                "passed": False, "decision": "DENY", "reason": "Identity not verified", 
                "denial_source": "Identity", "trace": trace, "context": eval_context, "evaluation_states": evaluation_states
            }
        
        trace.append("SPIFFE Check: Identity verified. ✅")
        evaluation_states["identity"] = "ALLOW"
        eval_context["step_1_identity"] = {"caller": caller_spiffe_id, "found_in_registry": True}

        # --- Step 2: Transport Allowlist ---
        evaluation_states["transport"] = "DENY"
        allowlist = self.allowlist_svc.get_all()
        if caller_spiffe_id not in allowlist:
            trace.append("Transport Allowlist: Identity not explicitly allowed. ❌")
            eval_context["step_2_transport"] = {"allowed": False}
            return {
                "passed": False, "decision": "DENY", "reason": "Transport blocked", 
                "denial_source": "Transport", "trace": trace, "context": eval_context, "evaluation_states": evaluation_states
            }
            
        trace.append("Transport Allowlist: Identity allowed. ✅")
        evaluation_states["transport"] = "ALLOW"
        eval_context["step_2_transport"] = {"allowed": True}

        return {
            "passed": True, "decision": "ALLOW", "reason": "Pre-LLM checks passed", 
            "denial_source": None, "trace": trace, "context": eval_context, "evaluation_states": evaluation_states
        }

    def evaluate(self, 
                 pre_llm_result: dict,
                 caller_spiffe_id: str, 
                 mcps: List[str], 
                 tools: List[str], 
                 confidence: float,
                 llm_outputs: Dict[str, Any],
                 task_text: str = "") -> DecisionResult:
        
        trace = pre_llm_result.get("trace", [])
        eval_context = pre_llm_result.get("context", {})
        evaluation_states = pre_llm_result.get("evaluation_states", {
            "identity": "NOT_EVALUATED", "transport": "NOT_EVALUATED", 
            "rbac": "NOT_EVALUATED", "tsphol": "NOT_EVALUATED"
        }).copy()
        
        if not pre_llm_result.get("passed", False):
            return self._finalize(
                spiffe_id=caller_spiffe_id,
                states=evaluation_states,
                final_dec=pre_llm_result.get("decision", "DENY"),
                reason=pre_llm_result.get("reason", "Pre-LLM block"),
                denial_source=pre_llm_result.get("denial_source", "Pre-LLM"),
                trace=trace,
                context=eval_context,
                pre_llm_result=False,
                llm_executed=False,
                llm_output=None,
                derived_features=None
            )
            
        trace.append("Proceeding to Post-LLM evaluation.")

        # --- Step 3: RBAC (Identity-Based wildcard search) ---
        evaluation_states["rbac"] = "DENY"
        policy = self.rbac_svc.get_policy_for_identity(caller_spiffe_id)
        
        eval_context["step_3_rbac"] = {
            "policy_found": True if policy else False,
            "mcps_checked": mcps,
            "tools_checked": tools
        }

        if not policy:
            trace.append("RBAC Check: No identity policies found. Default Deny. ❌")
            eval_context["step_3_rbac"]["allowed"] = False
            return self._finalize(caller_spiffe_id, evaluation_states, "DENY", "No RBAC rules mapped", "RBAC", trace, eval_context, True, True, llm_outputs, None)
            
        rules = policy.get("rules", [])
        eval_context["step_3_rbac"]["applicable_rules"] = rules
        rbac_allowed = self._check_rbac(mcps, tools, rules, trace)
        eval_context["step_3_rbac"]["allowed"] = rbac_allowed
        
        if not rbac_allowed:
            eval_context["step_4_tsphol"] = {
                "rule_evaluations": ["Not evaluated due to prior RBAC denial."]
            }
            return self._finalize(caller_spiffe_id, evaluation_states, "DENY", "RBAC block triggered", "RBAC", trace, eval_context, True, True, llm_outputs, None)

        evaluation_states["rbac"] = "ALLOW"

        # --- Step 4: TS-PHOL Rules (Heuristics execution) ---
        evaluation_states["tsphol"] = "DENY"
        tsphol_rules = self.tsphol_svc.get_all()
        tsphol_decision = "allow"
        
        risk_levels = [self.risk_svc.get_risk_for_mcp(m) for m in set(mcps)]
        highest_risk = "low"
        if "high" in risk_levels: highest_risk = "high"
        elif "medium" in risk_levels: highest_risk = "medium"

        read_keywords = ["get", "list", "query", "search", "read", "find", "retrieve", "fetch", "extract"]
        write_keywords = ["create", "update", "delete", "remove", "add", "post", "put", "modify", "insert", "patch", "unlock", "lock", "drop"]
        
        write_counts = sum(1 for t in tools if any(wk in t.lower() for wk in write_keywords))
        read_counts = sum(1 for t in tools if any(rk in t.lower() for rk in read_keywords))
        
        contains_write = write_counts > 0
        if write_counts > read_counts:
            dominant_action_type = "write"
        elif read_counts > write_counts:
            dominant_action_type = "read"
        elif write_counts > 0 and read_counts == write_counts:
            dominant_action_type = "mixed"
        else:
            dominant_action_type = "read" # default

        multiple_mcp = len(set(mcps)) > 1
        tool_count = len(tools)
        
        no_prior_read = contains_write and read_counts == 0
        
        task_lower = task_text.lower()
        missing_required_capability = False
        if any(kw in task_lower for kw in ["metric", "alert", "performance", "dashboard"]):
            if not any(kw in t.lower() for kw in ["query", "alert", "dashboard"] for t in tools):
                missing_required_capability = True
        if any(kw in task_lower for kw in ["incident", "escalate", "oncall"]):
            if not any(kw in t.lower() for kw in ["incident", "oncall", "sift"] for t in tools):
                missing_required_capability = True
        if any(kw in task_lower for kw in ["payment", "subscription", "billing", "charge"]):
            if "stripe" not in mcps:
                missing_required_capability = True
                
        irrelevant_tool_detected = False
        if "stripe" in mcps and not any(kw in task_lower for kw in ["stripe", "pay", "bill", "subscription", "charge", "refund"]):
            irrelevant_tool_detected = True
        if "hummingbot" in mcps and not any(kw in task_lower for kw in ["trade", "crypto", "position", "order", "bot"]):
            irrelevant_tool_detected = True
            
        risk_map_scores = {"low": 1, "medium": 2, "high": 3}
        cumulative_risk_score = sum(risk_map_scores.get(self.risk_svc.get_risk_for_mcp(m), 2) for m in set(mcps))
        
        identity_domain_mismatch = False
        if "research" in caller_spiffe_id and any(m in mcps for m in ["stripe", "hummingbot-mcp", "azure"]):
            identity_domain_mismatch = True
        elif "finance" in caller_spiffe_id and any(m in mcps for m in ["grafana"]):
            identity_domain_mismatch = True

        computed_heuristics = {
            "highest_risk": highest_risk,
            "contains_write": contains_write,
            "dominant_action_type": dominant_action_type,
            "multiple_mcp": multiple_mcp,
            "tool_count": tool_count,
            "confidence": confidence,
            "no_prior_read": no_prior_read,
            "missing_required_capability": missing_required_capability,
            "irrelevant_tool_detected": irrelevant_tool_detected,
            "cumulative_risk_score": cumulative_risk_score,
            "identity_domain_mismatch": identity_domain_mismatch
        }

        eval_context["step_4_tsphol"] = {
            "heuristics_computed": computed_heuristics,
            "rule_evaluations": []
        }

        for rule in tsphol_rules:
            decision, rule_log = self._evaluate_tsphol_rule(rule, computed_heuristics, trace)
            eval_context["step_4_tsphol"]["rule_evaluations"].append(rule_log)
            
            if decision in ["deny", "flag"]:
                tsphol_decision = "deny"
                break
                
        # --- Step 5: Final Decision Synthesis ---
        if tsphol_decision == "deny":
            evaluation_states["tsphol"] = "DENY"
            final_status = "DENY"
            reason = "TS-PHOL rule mandated a denial"
            denial_source = "TS-PHOL"
        else:
            evaluation_states["tsphol"] = "ALLOW"
            final_status = "ALLOW"
            reason = "All security checks passed"
            denial_source = None
            
        trace.append(f"FINAL: {final_status}")
            
        return self._finalize(caller_spiffe_id, evaluation_states, final_status, reason, denial_source, trace, eval_context, True, True, llm_outputs, computed_heuristics)
        
    def _finalize(self, spiffe_id, states, final_dec, reason, denial_source, trace, context, pre_llm_result, llm_executed, llm_output, derived_features) -> DecisionResult:
        if final_dec == "DENY" and "FINAL: DENY" not in trace:
            trace.append("FINAL: DENY")
            
        return DecisionResult(
            spiffe_id=spiffe_id,
            evaluation_states=states,
            spiffe_verified=states.get("identity") == "ALLOW",
            transport_allowed=states.get("transport") == "ALLOW",
            rbac_allowed=states.get("rbac") == "ALLOW",
            tsphol_decision=states.get("tsphol", "NOT_EVALUATED").lower(),
            final_decision=final_dec,
            reason=reason,
            denial_source=denial_source,
            trace=trace,
            context=context,
            pre_llm_result=pre_llm_result,
            llm_executed=llm_executed,
            llm_output=llm_output,
            derived_features=derived_features
        )

    def _check_rbac(self, mcps: List[str], tools: List[str], rules: List[Dict[str, Any]], trace: List[str]) -> bool:
        if not mcps or not tools:
            trace.append("RBAC Check: Empty MCP/Tool lists. Skipping. ✅")
            return True
            
        for mcp, tool in zip(mcps, tools):
            matched_action = "deny" # default
            
            # Find matching rule for this pair
            for rule in rules:
                rule_mcp = rule.get("mcp")
                rule_tools = rule.get("tools", [])
                
                # Check MCP match
                if rule_mcp == "*" or rule_mcp == mcp:
                    # Check Tool match
                    if "*" in rule_tools or tool in rule_tools:
                        matched_action = rule.get("action", "deny")
                        if matched_action == "deny":
                            break # Explicit deny immediately halts search
                            
            if matched_action == "deny":
                trace.append(f"RBAC Check: {mcp}.{tool} was DENIED due to an explicit deny or no matching allow rule. ❌")
                return False
            else:
                trace.append(f"RBAC Check: {mcp}.{tool} was ALLOWED. ✅")
                
        return True

    def _evaluate_tsphol_rule(self, rule: Dict[str, Any], computed: Dict[str, Any], trace: List[str]) -> tuple[str, dict]:
        condition = rule.get("condition", {})
        decision = rule.get("decision", "allow")
        name = rule.get("name", "Unnamed Rule")
        
        rule_log = {
            "rule_name": name,
            "computed": computed,
            "triggered": True,
            "reason": None,
            "outcome": decision
        }

        # Evaluate logic
        for k, expected_v in condition.items():
            if k in computed:
                actual_v = computed[k]
                
                # Special handler for min_confidence threshold
                if k == "min_confidence" or k == "min_confidence_global":
                    if actual_v >= expected_v: # Confidence IS high enough
                        rule_log["triggered"] = False
                        rule_log["reason"] = f"confidence: {actual_v} >= {expected_v} (passes threshold)"
                        break
                elif k == "max_tools":
                    if actual_v <= expected_v:
                        rule_log["triggered"] = False
                        rule_log["reason"] = f"tool_count: {actual_v} <= {expected_v} (passes limit)"
                        break
                elif k == "cumulative_risk_score":
                    if actual_v < expected_v:
                        rule_log["triggered"] = False
                        rule_log["reason"] = f"cumulative_risk_score: {actual_v} < {expected_v} (passes limit)"
                        break
                else:
                    # Generic exact match (e.g. contains_write = true)
                    if isinstance(actual_v, str) and isinstance(expected_v, str):
                        if actual_v.lower() != expected_v.lower():
                            rule_log["triggered"] = False
                            rule_log["reason"] = f"{k}: '{actual_v}' != '{expected_v}'"
                            break
                    elif actual_v != expected_v:
                        rule_log["triggered"] = False
                        rule_log["reason"] = f"{k}: {actual_v} != {expected_v}"
                        break
            else:
                rule_log["triggered"] = False
                rule_log["reason"] = f"Condition metric '{k}' not found in computed heuristics"
                break

        if rule_log["triggered"]:
            trace_reason = rule.get("description", f"Condition {k} triggered.")
            rule_log["reason"] = trace_reason
            trace.append(f"TS-PHOL: '{name}' triggered ({k}) -> {decision.upper()} ⚠️")
            return decision, rule_log
            
        rule_log["triggered"] = False
        rule_log["outcome"] = "rule bypassed"
        return "allow", rule_log
