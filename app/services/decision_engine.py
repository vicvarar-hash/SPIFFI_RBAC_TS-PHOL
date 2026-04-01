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
                 task_text: str = "",
                 mode: str = "selection",
                 mcp_filter: str = "All") -> DecisionResult:
        
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
            
        trace.append(f"Proceeding to Post-LLM evaluation (Mode: {mode}).")

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
        
        # 4R: Hierarchical Domain Inference
        if mcp_filter and mcp_filter != "All":
            expected_domain = mcp_filter
        elif intent_info.get("domain") and intent_info.get("domain") != "Unknown":
            expected_domain = intent_info.get("domain")
        else:
            expected_domain = llm_outputs.get("expected_domain", "Uncertain")
            
        if expected_domain == "Unknown": expected_domain = "Uncertain"
        
        # 4R: Bundle Domain Inference (Patch)
        if mode == "selection":
            if mcps:
                unique_mcps = set(mcps)
                if len(unique_mcps) == 1:
                    actual_domain = list(unique_mcps)[0]
                else:
                    actual_domain = "multi-domain"
            else:
                actual_domain = "Uncertain"
        else:
            actual_domain = llm_outputs.get("actual_domain", "Uncertain")
        
        if actual_domain == "Unknown": actual_domain = "Uncertain"
        
        # 4T: Deterministic Alignment Score Computation (Weighted Formula)
        domain_match = (expected_domain.lower() == actual_domain.lower()) if expected_domain != "Uncertain" else True
        domain_score = 1.0 if domain_match else 0.0
        
        req_caps = set(intent_info.get("task_required_capabilities", []))
        has_caps = set(capabilities)
        if req_caps:
            cap_score = len(req_caps.intersection(has_caps)) / len(req_caps)
        else:
            cap_score = 1.0 # Vacuously aligned if no caps required
            
        # 4T: New Heuristic Semantic Score
        semantic_score = self._compute_semantic_score(task_text, tool_audit)
        
        # 40% Domain, 40% Cap, 20% Semantic
        final_alignment_score = (0.4 * domain_score) + (0.4 * cap_score) + (0.2 * semantic_score)
        
        # 4T: Filter for SSOT (Concrete only for UI/Audit)
        from app.services.domain_capability_ontology import DomainCapabilityOntology
        concrete_required = [c for c in req_caps if DomainCapabilityOntology.is_concrete(c)]
        concrete_has = [c for c in has_caps if DomainCapabilityOntology.is_concrete(c)]
        missing_concrete = [c for c in concrete_required if c not in concrete_has]
        
        pred_context = {
            "spiffe_id": caller_spiffe_id,
            "role": persona_key,
            "mcps": mcps,
            "tools": tools,
            "has_capabilities": list(has_caps), # Internal full set
            "task_required_capabilities": list(req_caps), # Internal full set
            "concrete_has": concrete_has, # SSOT Display set
            "concrete_required": concrete_required, # SSOT Display set
            "missing_concrete": missing_concrete, # SSOT Display set
            "intent_info": intent_info,
            "tool_aggregates": tool_aggregates, # 4I: Direct aggregate sync
            "confidence": confidence,
            "highest_risk": highest_risk,
            # 4M: Validation-Aware Context
            "expected_domain": expected_domain,
            "actual_domain": actual_domain,
            "task_alignment_score": final_alignment_score,
            "alignment_components": {
                "domain_score": domain_score,
                "capability_score": cap_score,
                "semantic_score": semantic_score
            },
            "issue_codes": llm_outputs.get("issue_codes", []),
            "mode": mode # 4R
        }
        
        predicate_engine = PredicateEngine(pred_context)
        all_predicates = predicate_engine.get_all_predicates()

        # 4T Audit Patch: Sync UI with engine's filtered capabilities (Single Source of Truth)
        # Use CONCRETE caps for the primary UI display keys
        eval_context["task_required_capabilities"] = concrete_required
        eval_context["has_capabilities"] = concrete_has
        eval_context["missing_capabilities"] = missing_concrete
        eval_context["alignment_components"] = pred_context["alignment_components"]
        
        # Internal diagnostics
        eval_context["all_required_capabilities"] = list(req_caps)
        eval_context["all_has_capabilities"] = list(has_caps)
        
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
            "final_status": final_status,
            "final_decision": final_status,  # Compatibility
            "reason": "No rule violations detected" if final_status == "ALLOW" else "Security policy violation"
        }

        # 4T: Positive Explainability for ALLOW cases (from Concrete sets)
        if final_status == "ALLOW":
            findings = []
            
            # Check for concrete coverage
            if not missing_concrete:
                findings.append("Capability coverage satisfied")
                derived_set.add("CapabilityCoverageSatisfied")
            
            if all_predicates.get("ContainsWrite") and all_predicates.get("ContainsRead"):
                findings.append("Safe read-write sequence")
                derived_set.add("SafeWriteContext")
                
            if not all_predicates.get("MultiDomain"):
                findings.append("Single-domain request")
                derived_set.add("SingleDomainRequest")
                
            if all_predicates.get("PrimaryIntent") != "UnknownIntent":
                findings.append("Intent satisfied")
                derived_set.add("IntentSatisfied")
                
            eval_context["tsphol_summary"]["positive_findings"] = findings
            eval_context["tsphol_derived_predicates"] = list(derived_set)

        # 4S: Synthesis - TS-PHOL IS THE FINAL AUTHORITY
        evaluation_states["tsphol"] = final_status
        reason = "TS-PHOL approved access" if final_status == "ALLOW" else "TS-PHOL formal logical denial"
        # Label ABAC as advisory
        eval_context["abac_baseline"]["advisory"] = True
        
        trace.append(f"TS-PHOL evaluated {len(tsphol_rules)} declarative rules. FINAL STATUS: {final_status}")
        trace.append(f"Authority Check: TS-PHOL overrides context. Decision: {final_status}")
        
        return self._finalize(
            caller_spiffe_id, 
            evaluation_states, 
            final_status, # Authoritative decision
            reason, 
            "TS-PHOL" if final_status == "DENY" else None, 
            trace, 
            eval_context, 
            True, True, llm_outputs, all_predicates
        )

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

    def _compute_semantic_score(self, task_text: str, tool_audit: List[Dict[str, Any]]) -> float:
        """
        4T: Deterministic lightweight semantic relevance score.
        Computes overlap between task keywords and tool metadata.
        """
        if not task_text or not tool_audit:
            return 0.0
            
        import re
        # Small set of stop words to ignore
        STOP_WORDS = {"the", "and", "for", "with", "this", "that", "from", "you", "your", "has", "was"}
        
        def tokenize(text):
            # Split by non-alphanumeric and keep meaningful words
            words = re.findall(r'\b\w{3,}\b', text.lower())
            return {w for w in words if w not in STOP_WORDS}
            
        task_tokens = tokenize(task_text)
        if not task_tokens:
            return 0.0
            
        # Collect all tool-related tokens
        tool_tokens = set()
        for d in tool_audit:
            # Tool name tokens
            tool_tokens.update(tokenize(d["tool"].replace("_", " ")))
            # Action tokens
            for action in d.get("actions", []):
                tool_tokens.update(tokenize(action))
            # Capability tokens
            for cap in d.get("capabilities", []):
                # CamelCase split
                cap_split = re.sub('([a-z0-9])([A-Z])', r'\1 \2', cap)
                tool_tokens.update(tokenize(cap_split))
                
        intersection = task_tokens.intersection(tool_tokens)
        
        # Scoring: Score based on how many task keywords are covered by tool metadata.
        # We divide by the number of task tokens (up to a limit)
        # 1-2 matches in a complex task is good semantic proof.
        match_count = len(intersection)
        if match_count == 0: return 0.0
        
        # Exact match of a specific tool name in the task text should give high priority
        for d in tool_audit:
            if d["tool"].lower() in task_text.lower():
                return 1.0
        
        # Heuristic ratio
        base_score = match_count / min(len(task_tokens), 5) 
        
        return min(1.0, round(base_score, 2))
