import logging
from typing import List, Dict, Any, Tuple
from app.models.decision import DecisionResult
from app.models.mcp import MCPPersona
from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService
from app.services.mcp_risk_service import MCPRiskService

# New Services for Iteration 4C & 4E
from app.services.intent_engine import IntentEngine
from app.services.capability_mapper import CapabilityMapper
from app.services.predicate_engine import PredicateEngine
from app.services.abac_engine import ABACEngine
from app.services.tsphol_interpreter import TSPHOLInterpreter
from app.services.tool_classifier import ToolClassifier

logger = logging.getLogger(__name__)

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
        
        # Initialize new engines
        self.intent_engine = IntentEngine()
        self.capability_mapper = CapabilityMapper()
        self.abac_engine = ABACEngine()
        self.tsphol_interpreter = TSPHOLInterpreter()
        self.tool_classifier = ToolClassifier()

    def pre_llm_check(self, caller_spiffe_id: str, mcps: List[str] = None, tools: List[str] = None) -> dict:
        trace = []
        eval_context = {}
        trace.append(f"Engine initialized. Pre-LLM check for {caller_spiffe_id}")
        
        evaluation_states = {
            "identity": "NOT_EVALUATED",
            "transport": "NOT_EVALUATED",
            "rbac": "NOT_EVALUATED",
            "abac": "NOT_EVALUATED",
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
        evaluation_states = pre_llm_result.get("evaluation_states", {}).copy()
        
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

        # --- Step 3: Tool Classification, Intent Decomposition & Capability Mapping ---
        justification = llm_outputs.get("justification", "") or llm_outputs.get("reason", "")
        
        # Iteration 4G: Domain-Aware Fact Extraction
        tool_audit = self.tool_classifier.classify_tools(tools)
        intent_info = self.intent_engine.decompose_intent(task_text, tools, mcps, tool_audit, justification)
        capabilities = self.capability_mapper.extract_capabilities(tools)
        
        # Request-level aggregates from tools
        tool_aggregates = self.tool_classifier.get_aggregate_predicates(tool_audit)
        
        risk_levels = [self.risk_svc.get_risk_for_mcp(m) for m in set(mcps)]
        highest_risk = "low"
        if "high" in risk_levels: highest_risk = "high"
        elif "medium" in risk_levels: highest_risk = "medium"
        
        # Check for multi-domain (intent refinement)
        is_multi_domain = len(set(mcps)) > 1
        intent_info["intent_properties"]["multi_domain"] = is_multi_domain
        tool_aggregates["MultiDomain"] = is_multi_domain
            
        eval_context["tool_audit"] = tool_audit
        eval_context["tool_aggregates"] = tool_aggregates
        eval_context["intent_decomposition"] = intent_info
        eval_context["capability_mapping"] = list(capabilities)
        trace.append(f"Fact Extraction: Domain -> {intent_info['domain']}, Intent -> {intent_info['primary_intent']}. ✅")

        # --- Step 4: RBAC ---
        evaluation_states["rbac"] = "DENY"
        policy = self.rbac_svc.get_policy_for_identity(caller_spiffe_id)
        if not policy:
            trace.append("RBAC Check: No identity policies found. ❌")
            return self._finalize(caller_spiffe_id, evaluation_states, "DENY", "No RBAC rules mapped", "RBAC", trace, eval_context, True, True, llm_outputs, None)
            
        rbac_allowed = self._check_rbac(mcps, tools, policy.get("rules", []), trace)
        if not rbac_allowed:
            return self._finalize(caller_spiffe_id, evaluation_states, "DENY", "RBAC block triggered", "RBAC", trace, eval_context, True, True, llm_outputs, None)

        evaluation_states["rbac"] = "ALLOW"

        # --- Step 5: ABAC Baseline (Parallel/Informational) ---
        registry = self.registry_svc.get_all()
        persona_key = next((k for k, v in registry.items() if v.get("spiffe_id") == caller_spiffe_id), "unknown")
        
        # New Iteration 4D Nested ABAC Model
        abac_attrs = {
            "subject": {"role": persona_key},
            "resource": {
                "mcps": mcps,
                "risk_level": highest_risk
            },
            "action": {
                "tools": tools,
                "tool_count": len(tools),
                "contains_write": intent_info["intent_properties"]["contains_write"],
                "multi_domain": intent_info["intent_properties"]["multi_domain"]
            },
            "environment": {
                "confidence": confidence
            }
        }
        abac_result = self.abac_engine.evaluate(abac_attrs)
        evaluation_states["abac"] = abac_result["decision"]
        eval_context["abac_baseline"] = abac_result
        trace.append(f"ABAC baseline evaluated: {abac_result['decision']} (matched: {abac_result['matched_rule']})")

        # --- Step 6: TS-PHOL Policy-Driven Reasoning (Iteration 4E) ---
        evaluation_states["tsphol"] = "DENY"
        
        pred_context = {
            "spiffe_id": caller_spiffe_id,
            "role": persona_key,
            "mcps": mcps,
            "tools": tools,
            "capabilities": list(capabilities),
            "intent_info": intent_info,
            "tool_aggregates": tool_aggregates, # 4I: Direct aggregate sync
            "confidence": confidence,
            "highest_risk": highest_risk
        }
        
        predicate_engine = PredicateEngine(pred_context)
        all_predicates = predicate_engine.get_all_predicates()
        
        tsphol_rules = self.tsphol_svc.get_all()
        
        # Execute Declarative Interpreter (Restored after accidental deletion)
        final_status, derived_set, logic_trace = self.tsphol_interpreter.evaluate_rules(all_predicates, tsphol_rules)
        
        eval_context["tsphol_predicate_set"] = all_predicates
        eval_context["tsphol_logic_trace"] = logic_trace
        eval_context["tsphol_derived_predicates"] = list(derived_set)
        
        # 4K: TS-PHOL Rule Summary for audit
        eval_context["tsphol_summary"] = {
            "evaluated_rules": len(logic_trace),
            "triggered_rules": len([r for r in logic_trace if r["triggered"]]),
            "final_decision": final_status,
            "reason": "No rule violations detected" if final_status == "ALLOW" else "Security policy violation"
        }

        # Synthesis
        if final_status == "DENY":
            evaluation_states["tsphol"] = "DENY"
            reason = "TS-PHOL formal logical denial"
            denial_source = "TS-PHOL"
        else:
            evaluation_states["tsphol"] = "ALLOW"
            reason = "All security policies satisfied"
            denial_source = None
            
        trace.append(f"TS-PHOL evaluated {len(tsphol_rules)} declarative rules. FINAL: {final_status}")
        trace.append(f"FINAL: {final_status}")
        return self._finalize(caller_spiffe_id, evaluation_states, final_status, reason, denial_source, trace, eval_context, True, True, llm_outputs, all_predicates)

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
            trace.append("RBAC Check: Empty lists. ✅")
            return True
        for mcp, tool in zip(mcps, tools):
            matched = "deny"
            for rule in rules:
                if (rule.get("mcp") == "*" or rule.get("mcp") == mcp) and ("*" in rule.get("tools", []) or tool in rule.get("tools", [])):
                    matched = rule.get("action", "deny")
                    if matched == "deny": break
            if matched == "deny":
                trace.append(f"RBAC Check: {mcp}.{tool} DENIED. ❌")
                return False
            trace.append(f"RBAC Check: {mcp}.{tool} ALLOWED. ✅")
        return True
