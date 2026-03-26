from typing import List, Dict, Any
from app.models.decision import DecisionResult
from app.models.mcp import MCPPersona
from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService

class DecisionEngine:
    def __init__(self, 
                 registry_svc: SpiffeRegistryService,
                 allowlist_svc: SpiffeAllowlistService,
                 rbac_svc: RBACService,
                 tsphol_svc: TSPHOLRuleService,
                 personas: List[MCPPersona]):
        self.registry_svc = registry_svc
        self.allowlist_svc = allowlist_svc
        self.rbac_svc = rbac_svc
        self.tsphol_svc = tsphol_svc
        self.persona_map = {p.name: p for p in personas}

    def evaluate(self, 
                 caller_spiffe_id: str, 
                 mcps: List[str], 
                 tools: List[str], 
                 confidence: float,
                 tool_match: bool = True) -> DecisionResult:
        
        trace = []
        eval_context = {}
        trace.append(f"Engine initialized. Evaluating request from {caller_spiffe_id}")
        
        # --- Step 1: SPIFFE Identity Check ---
        registry_ids = list(self.registry_svc.get_all().values())
        if caller_spiffe_id not in registry_ids:
            trace.append("SPIFFE Check: Identity not found in Registry. ❌")
            eval_context["step_1_identity"] = {"caller": caller_spiffe_id, "found_in_registry": False}
            return self._finalize(caller_spiffe_id, False, False, False, "deny", "DENY", "Identity not verified", trace, eval_context)
        
        trace.append("SPIFFE Check: Identity verified. ✅")
        spiffe_verified = True
        eval_context["step_1_identity"] = {"caller": caller_spiffe_id, "found_in_registry": True}

        # --- Step 2: Transport Allowlist ---
        allowlist = self.allowlist_svc.get_all()
        if caller_spiffe_id not in allowlist:
            trace.append("Transport Allowlist: Identity not explicitly allowed. ❌")
            eval_context["step_2_transport"] = {"allowed": False}
            return self._finalize(caller_spiffe_id, spiffe_verified, False, False, "deny", "DENY", "Transport blocked", trace, eval_context)
            
        trace.append("Transport Allowlist: Identity allowed. ✅")
        transport_allowed = True
        eval_context["step_2_transport"] = {"allowed": True}

        # --- Step 3: RBAC (Identity-Based wildcard search) ---
        policy = self.rbac_svc.get_policy_for_identity(caller_spiffe_id)
        
        eval_context["step_3_rbac"] = {
            "policy_found": True if policy else False,
            "mcps_checked": mcps,
            "tools_checked": tools
        }

        if not policy:
            trace.append("RBAC Check: No identity policies found. Default Deny. ❌")
            eval_context["step_3_rbac"]["allowed"] = False
            return self._finalize(caller_spiffe_id, spiffe_verified, transport_allowed, False, "deny", "DENY", "No RBAC rules mapped", trace, eval_context)
            
        rules = policy.get("rules", [])
        eval_context["step_3_rbac"]["applicable_rules"] = rules
        rbac_allowed = self._check_rbac(mcps, tools, rules, trace)
        eval_context["step_3_rbac"]["allowed"] = rbac_allowed
        
        if not rbac_allowed:
            return self._finalize(caller_spiffe_id, spiffe_verified, transport_allowed, False, "deny", "DENY", "RBAC block triggered", trace, eval_context)

        # --- Step 4: TS-PHOL Rules (Heuristics execution) ---
        tsphol_rules = self.tsphol_svc.get_all()
        tsphol_decision = "allow"
        
        # Calculate heuristics once
        risk_levels = [self.persona_map[m].risk_level.lower() for m in mcps if m in self.persona_map]
        highest_risk = "low"
        if "high" in risk_levels: highest_risk = "high"
        elif "medium" in risk_levels: highest_risk = "medium"

        read_keywords = ["get", "list", "query", "search", "read", "find"]
        write_keywords = ["create", "update", "delete", "remove", "add", "post", "put"]
        has_write = any(any(wk in t.lower() for wk in write_keywords) for t in tools)
        has_read = any(any(rk in t.lower() for rk in read_keywords) for t in tools)
        action_type = "write" if has_write else ("read" if has_read else "unknown")
        tool_count = len(tools)
        
        eval_context["step_4_tsphol"] = {
            "heuristics_computed": {
                "highest_risk": highest_risk,
                "inferred_action_type": action_type,
                "tool_count": tool_count,
                "confidence_score": confidence,
                "groundtruth_tool_match": tool_match
            },
            "rule_evaluations": []
        }

        if not tool_match:
            trace.append("TS-PHOL: 'tool_match' validation failed -> DENY ❌")
            tsphol_decision = "deny"
            eval_context["step_4_tsphol"]["rule_evaluations"].append("Hard-fail: Prediction tools did not EXACTLY match groundtruth requirements.")
        else:
            for rule in tsphol_rules:
                decision, rule_log = self._evaluate_tsphol_rule(rule, highest_risk, action_type, tool_count, confidence, trace)
                eval_context["step_4_tsphol"]["rule_evaluations"].append(rule_log)
                
                # Treat 'flag' as 'deny' under new strict binary rules
                if decision in ["deny", "flag"]:
                    tsphol_decision = "deny"
                    break
                
        # --- Step 5: Final Decision Synthesis ---
        if tsphol_decision == "deny":
            final_status = "DENY"
            reason = "TS-PHOL rule mandated a denial"
        else:
            final_status = "ALLOW"
            reason = "All security checks passed"
            
        trace.append(f"FINAL: {final_status}")
            
        return self._finalize(caller_spiffe_id, spiffe_verified, transport_allowed, rbac_allowed, tsphol_decision, final_status, reason, trace, eval_context)
        
    def _finalize(self, spiffe_id, verified, transport, rbac, tsphol, final_dec, reason, trace, context) -> DecisionResult:
        if final_dec == "DENY" and "FINAL: DENY" not in trace:
            trace.append("FINAL: DENY")
            
        return DecisionResult(
            spiffe_id=spiffe_id,
            spiffe_verified=verified,
            transport_allowed=transport,
            rbac_allowed=rbac,
            tsphol_decision=tsphol,
            final_decision=final_dec,
            reason=reason,
            trace=trace,
            context=context
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

    def _evaluate_tsphol_rule(self, rule: Dict[str, Any], highest_risk: str, action_type: str, tool_count: int, confidence: float, trace: List[str]) -> tuple[str, dict]:
        condition = rule.get("condition", {})
        decision = rule.get("decision", "allow")
        name = rule.get("name", "Unnamed Rule")
        
        rule_log = {
            "rule_name": name,
            "conditions_expected": condition,
            "triggered": True,
            "failed_on": None,
            "outcome": decision
        }

        # Evaluate logic
        triggered = True
        
        for k, expected_v in condition.items():
            if k == "risk_level" and highest_risk != expected_v.lower():
                triggered = False
                rule_log["failed_on"] = f"risk_level: {highest_risk} != {expected_v}"
            elif k == "min_confidence" and confidence >= expected_v:
                # E.g. min_conf = 0.95. If conf is 0.96 we DONT trigger the rule.
                # It means "confidence < min_confidence triggers the failure mode"
                triggered = False
                rule_log["failed_on"] = f"confidence: {confidence} >= {expected_v} (passes threshold)"
            elif k == "max_tools" and tool_count <= expected_v:
                triggered = False
                rule_log["failed_on"] = f"tool_count: {tool_count} <= {expected_v} (passes limit)"
            elif k == "action_type" and action_type != expected_v.lower():
                triggered = False
                rule_log["failed_on"] = f"action_type: {action_type} != {expected_v}"

        if triggered:
            trace.append(f"TS-PHOL: '{name}' triggered ({k}) -> {decision.upper()} ⚠️")
            return decision, rule_log
            
        rule_log["triggered"] = False
        rule_log["outcome"] = "rule bypassed"
        return "allow", rule_log
