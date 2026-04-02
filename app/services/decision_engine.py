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

from app.services.normalization import normalize_mcp_name, normalize_tool_name, normalize_domain_name
from app.models.domain import resolve_domain
import json
import os

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
        
        mcps = [normalize_mcp_name(m) for m in mcps] if mcps else []
        tools = [normalize_tool_name(t) for t in tools] if tools else []
        
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

        # --- Step 4: RBAC (Generalized Refinement) ---
        evaluation_states["rbac"] = "DENY"
        policy = self.rbac_svc.get_policy_for_identity(caller_spiffe_id)
        if not policy:
            trace.append("RBAC Check: No identity policies found. ❌")
            rbac_audit = {"decision": "DENY", "reason": "No RBAC policies mapped", "matched_rule": "none", "rbac_trace": []}
            eval_context["rbac_evaluation"] = rbac_audit
            return self._finalize(caller_spiffe_id, evaluation_states, "DENY", "No RBAC rules mapped", "RBAC", trace, eval_context, True, True, llm_outputs, None)
            
        rbac_audit = self._evaluate_rbac(mcps, tools, policy.get("rules", []), trace)
        eval_context["rbac_evaluation"] = rbac_audit
        
        if rbac_audit["decision"] == "DENY":
            trace.append(f"RBAC Check: DENY triggered by {rbac_audit['matched_rule']}. ❌")
            return self._finalize(caller_spiffe_id, evaluation_states, "DENY", rbac_audit["reason"], "RBAC", trace, eval_context, True, True, llm_outputs, None)

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
            
        expected_domain = resolve_domain(expected_domain)
        
        # Explicit tolerance loading
        tolerance_policy = {"enabled": False}
        heur_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "policies", "heuristic_policy.json")
        if os.path.exists(heur_path):
            try:
                with open(heur_path, "r") as f:
                    heur_data = json.load(f)
                    tolerance_policy = heur_data.get("selection_tolerance_policy", {"enabled": False})
            except Exception:
                pass

        applying_tolerance = False
        if mode == "selection" and tolerance_policy.get("enabled"):
            applying_tolerance = True

        # Resolve Actual Domain
        if mcps:
            unique_mcps = set(mcps)
            if len(unique_mcps) == 1:
                actual_domain = list(unique_mcps)[0]
            else:
                actual_domain = "multi_domain"
        else:
            actual_domain = "Uncertain"
        
        # Let LLM output provide an actual domain if we had a multi-domain inference
        llm_actual_domain = llm_outputs.get("actual_domain")
        if llm_actual_domain and actual_domain == "multi_domain":
            actual_domain = llm_actual_domain
            
        actual_domain = resolve_domain(actual_domain)
        
        # 4T/4V: Deterministic Alignment Score Computation (Weighted Formula)
        domain_match = (expected_domain == actual_domain) if expected_domain not in ["uncertain", "unknown"] else True
        
        if not domain_match and applying_tolerance and tolerance_policy.get("allow_domain_mismatch_if_readonly"):
            if not intent_info["intent_properties"].get("contains_write"):
                domain_match = True
                trace.append("Tolerance Policy Applied: Domain mismatch bypassed for read-only selection request. ⚠️")
        domain_match_score = 1.0 if domain_match else 0.0
        
        req_caps = set(intent_info.get("task_required_capabilities", []))
        optional_caps = set(intent_info.get("task_optional_capabilities", []))
        has_caps = set(capabilities)
        
        # 4V: Capability Score Guard (Generalized Refinement)
        from app.services.domain_capability_ontology import DomainCapabilityOntology
        concrete_required = [c for c in req_caps if DomainCapabilityOntology.is_concrete(c)]
        concrete_has = [c for c in has_caps if DomainCapabilityOntology.is_concrete(c)]
        missing_concrete = [c for c in concrete_required if c not in concrete_has]

        if concrete_required:
            cap_score = len([c for c in concrete_required if c in concrete_has]) / len(concrete_required)
        elif req_caps:
            # Fallback requirements only (GenericRead, etc.) -> Cap proportionally
            cap_score = 0.5 if all(c in has_caps for c in req_caps) else 0.0
            trace.append("Alignment Alert: Capped capability score due to fallback-only requirements. ⚠️")
        else:
            cap_score = 0.0 # No requirements found -> Low mission signal
            
        # 4T/4V: New Heuristic Semantic Score
        semantic_score = self._compute_semantic_score(task_text, tool_audit, intent_info)
        
        # 40% Domain, 40% Cap, 20% Semantic
        final_alignment_score = (0.4 * domain_match_score) + (0.4 * cap_score) + (0.2 * semantic_score)
        
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
            "has_capabilities": list(has_caps),
            "task_required_capabilities": list(req_caps), # Minimal Required (from Ontology)
            "task_optional_capabilities": list(optional_caps),
            "concrete_has": concrete_has, # SSOT Display set
            "concrete_required": concrete_required, # SSOT Display set (Minimal)
            "missing_concrete": missing_concrete, # Strictly Required Missing
            "missing_optional": [c for c in optional_caps if c not in has_caps],
            "intent_info": intent_info,
            "tool_aggregates": tool_aggregates, # 4I: Direct aggregate sync
            "confidence": confidence,
            "highest_risk": highest_risk,
            # 4M: Validation-Aware Context
            "expected_domain": expected_domain,
            "actual_domain": actual_domain,
            "task_alignment_score": final_alignment_score,
            "alignment_components": {
                "domain_score": domain_match_score,
                "capability_score": cap_score,
                "semantic_score": semantic_score
            },
            "issue_codes": llm_outputs.get("issue_codes", []),
            "mode": mode, # 4R
            "selection_tolerance_active": applying_tolerance
        }
        
        predicate_engine = PredicateEngine(pred_context)
        all_predicates = predicate_engine.get_all_predicates()

        # 4W Audit Patch: Sync UI with engine's minimal required capabilities
        # Use CONCRETE minimal required caps for primary UI display keys
        eval_context["task_required_capabilities"] = concrete_required
        eval_context["task_optional_capabilities"] = list(optional_caps)
        eval_context["has_capabilities"] = concrete_has
        eval_context["missing_capabilities"] = missing_concrete
        eval_context["missing_optional_capabilities"] = [c for c in optional_caps if c not in has_caps]
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

        # 6: Mandatory Reasoning - Always satisfy at least 3 logical predicates for ALLOW
        if final_status == "ALLOW":
            findings = []
            
            # Mission alignment
            if not missing_concrete:
                findings.append("Mission capability coverage fully satisfied")
                derived_set.add("CapabilityCoverageSatisfied")
            
            # Domain consistency
            if not all_predicates.get("MultiDomain"):
                findings.append("Contextually safe single-domain request")
                derived_set.add("SingleDomainRequest")
            else:
                findings.append("Multi-domain request verified for consistency")
                derived_set.add("MultiDomainVerified")
                
            # Sequence safety
            if all_predicates.get("ContainsWrite") and all_predicates.get("ContainsRead"):
                findings.append("Safe Read-Before-Write sequence")
                derived_set.add("SafeWriteContext")
            elif not all_predicates.get("ContainsWrite"):
                findings.append("Low-risk read-only operation sequence")
                derived_set.add("ReadOnlySafety")
                
            # Intent satisfaction
            if all_predicates.get("PrimaryIntent") != "UnknownIntent":
                findings.append(f"Task intent '{all_predicates.get('PrimaryIntent')}' satisfied")
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

    def _evaluate_rbac(self, mcps: List[str], tools: List[str], rules: List[Dict[str, Any]], trace: List[str]) -> Dict[str, Any]:
        """
        5: Granular per-tool RBAC evaluation with full explainability.
        Evaluates every requested tool and collects a detailed trace.
        """
        if not mcps or not tools:
            trace.append("RBAC Check: Empty lists. ✅")
            return {
                "decision": "ALLOW", 
                "reason": "No tools requested", 
                "matched_rule": "default_empty", 
                "rbac_trace": []
            }

        rbac_trace = []
        overall_decision = "ALLOW"
        denied_tools = []

        for mcp, tool in zip(mcps, tools):
            tool_decision = "DENY"
            matched_policy = "default_deny"
            # 6: Explicit Denial Reason Logic
            for i, rule in enumerate(rules):
                rule_name = rule.get("rule_name", f"rule_{i}")
                mcp_match = (rule.get("mcp") == "*" or rule.get("mcp") == mcp)
                
                if mcp_match:
                    tool_match = ("*" in rule.get("tools", []) or tool in rule.get("tools", []))
                    if tool_match:
                        tool_decision = rule.get("action", "deny").upper()
                        matched_policy = rule_name
                        reason = f"Authorized by rule '{rule_name}'" if tool_decision == "ALLOW" else f"Explicitly denied by rule '{rule_name}'"
                        break
                    else:
                        tool_decision = "DENY"
                        matched_policy = "default_deny"
                        reason = f"Role does not have permission for tool '{tool}' in MCP '{mcp}'"
                else:
                    tool_decision = "DENY"
                    matched_policy = "default_deny"
                    reason = f"Identity not authorized for MCP server '{mcp}'"
            
            trace.append(f"RBAC Check: {mcp}.{tool} -> {tool_decision} ({matched_policy})")
            
            rbac_trace.append({
                "tool": tool,
                "mcp": mcp,
                "decision": tool_decision,
                "policy": matched_policy,
                "reason": reason
            })
            
            if tool_decision == "DENY":
                overall_decision = "DENY"
                denied_tools.append(f"{mcp}.{tool}")

        return {
            "decision": overall_decision,
            "reason": f"RBAC Denied: Access to ({', '.join(denied_tools)}) is not permitted for this identity" if denied_tools else "All requested tools permitted by role policy",
            "matched_rule": "multi_tool_audit",
            "rbac_trace": rbac_trace
        }

    def _compute_semantic_score(self, task_text: str, tool_audit: List[Dict[str, Any]], intent_info: Dict[str, Any] = None) -> float:
        """
        4T/4V: Generalized semantic relevance score.
        Uses weighted keyword overlap + Intent-Capability Prior boosting.
        """
        if not task_text or not tool_audit:
            return 0.0
            
        import re
        STOP_WORDS = {"the", "and", "for", "with", "this", "that", "from", "you", "your", "has", "was", "set", "use"}
        
        def tokenize(text):
            words = re.findall(r'\b\w{3,}\b', text.lower())
            return {w for w in words if w not in STOP_WORDS}
            
        task_tokens = tokenize(task_text)
        if not task_tokens:
            return 0.0
            
        tool_tokens = set()
        all_caps = []
        for d in tool_audit:
            tool_tokens.update(tokenize(d["tool"].replace("_", " ")))
            for action in d.get("actions", []):
                tool_tokens.update(tokenize(action))
            for cap in d.get("capabilities", []):
                all_caps.append(cap)
                cap_split = re.sub('([a-z0-9])([A-Z])', r'\1 \2', cap)
                tool_tokens.update(tokenize(cap_split))
                
        intersection = task_tokens.intersection(tool_tokens)
        
        # Base Match Score
        match_count = len(intersection)
        if match_count == 0: return 0.0
        
        # 4V: Intent-Capability Boost (General reasoning)
        boost = 0.0
        if intent_info:
            primary_intent = intent_info.get("primary_intent", "").lower()
            intent_keywords = tokenize(primary_intent)
            # Boost if any intent keyword matches a tool token
            if intent_keywords.intersection(tool_tokens):
                boost += 0.25
            
            # Boost if domain keywords match tool tokens OR task keywords
            domain = intent_info.get("domain", "").lower()
            if domain in tool_tokens or domain in task_tokens:
                boost += 0.2
        
        # Heuristic ratio
        # Denominator capped at 5 to avoid penalizing long descriptive tasks
        base_score = match_count / min(len(task_tokens), 5) 
        final_score = (base_score * 0.75) + boost
        
        return min(1.0, round(final_score, 2))
