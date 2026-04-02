import json
import logging
from typing import List, Dict, Any, Set
from app.services.intent_taxonomy import Domain, IntentTaxonomy
from app.services.capability_inference_service import CapabilityInferenceService

logger = logging.getLogger(__name__)

class IntentEngine:
    """
    Decomposes task intent based on tool usage, domain context, and NLP heuristics.
    Refined in Iteration 4H to be domain-aware, tool-grounded, and transparent.
    """
    
    # Generic fallbacks if domain-specific intents don't match
    GENERIC_INTENTS = {
        "InformationDiscovery": ["list", "search", "read", "find", "retrieve", "fetch", "view", "show"],
        "FinancialOperation": ["charge", "payment", "subscription", "bill", "refund", "invoice", "transaction"],
        "SystemUpdate": ["create", "update", "modify", "patch", "delete", "post", "put", "insert"]
    }

    def __init__(self, inference_svc: CapabilityInferenceService = None):
        self.inference_svc = inference_svc or CapabilityInferenceService()

    def decompose_intent(self, task_text: str, tools: List[str], mcps: List[str], tool_metadata: List[Dict[str, Any]], llm_justification: str = "") -> Dict[str, Any]:
        """
        Decomposes task intent by combining tool-centric facts, domain context, and conservative NLP heuristics.
        """
        task_lower = task_text.lower()
        justification_lower = llm_justification.lower() if llm_justification else ""
        combined_context = f"{task_lower} {justification_lower}"
        
        # 1. Domain Detection (From MCPs)
        primary_domain = Domain.GENERAL
        if mcps:
            # For simplicity, take the domain of the first MCP (or handle multi-domain)
            primary_domain = IntentTaxonomy.get_domain_for_mcp(mcps[0])
        
        # 2. Tool-Based Intent Inference (Primary Truth)
        is_write = any(d["is_write"] for d in tool_metadata)
        is_read = any(d["is_read"] for d in tool_metadata)
        
        detected_intents = []
        domain_tax = IntentTaxonomy.get_intents_for_domain(primary_domain)
        
        # Match Domain-Specific Intents
        for intent, keywords in domain_tax.items():
            if any(kw in combined_context for kw in keywords):
                detected_intents.append(intent)
        
        # Fallback to Generic if no domain intents matched
        if not detected_intents:
            for intent, keywords in self.GENERIC_INTENTS.items():
                if any(kw in combined_context for kw in keywords):
                    detected_intents.append(intent)
        
        # Refine Primary Intent and Filter Secondary (Iteration 4L)
        if not detected_intents:
            primary_intent = "InformationDiscovery" if is_read else "UnknownIntent"
            secondary_intents = []
        else:
            primary_intent = detected_intents[0]
            # 4L: Filter secondary intents by tool support
            raw_secondary = detected_intents[1:]
            secondary_intents = []
            
            tool_caps_lower = {c.lower() for d in tool_metadata for c in d.get("capabilities", [])}
            tool_actions_lower = {a.lower() for d in tool_metadata for a in d.get("actions", [])}
            combined_tool_signals = tool_caps_lower.union(tool_actions_lower)
            
            for intent in raw_secondary:
                # Rule: Intent keywords must overlap with tool capabilities/actions 
                # OR be strongly supported by primary intent domain
                intent_keywords = domain_tax.get(intent, [])
                if any(kw.lower() in combined_tool_signals for kw in intent_keywords):
                    secondary_intents.append(intent)
                elif intent in ["InformationDiscovery", "SystemUpdate"]: # Generic exceptions
                    secondary_intents.append(intent)
            
        # 3. Precise Task-Derived Capability Extraction (Iteration 4W Refactor)
        # Logic: Distinguish between REQUIRED and OPTIONAL capabilities.
        
        # Call the refactored task-driven inference service
        task_required_capabilities, task_optional_capabilities, cap_audit = self.inference_svc.get_task_required_capabilities(
            primary_domain.value, task_text, intent=primary_intent
        )
        
        # 4. Computed Intent Properties (STRICTLY FROM TOOLS)
        from app.services.tool_classifier import ToolClassifier
        classifier = ToolClassifier()
        aggregates = classifier.get_aggregate_predicates(tool_metadata)
        
        return {
            "primary_intent": primary_intent,
            "secondary_intents": list(secondary_intents),
            "task_required_capabilities": list(task_required_capabilities),
            "task_optional_capabilities": list(task_optional_capabilities),
            "required_capability_metadata": cap_audit,  # New 4H Audit Metadata
            "domain": primary_domain.value,
            "intent_properties": {
                "contains_read": aggregates["ContainsRead"],
                "contains_write": aggregates["ContainsWrite"],
                "contains_read_before_write": aggregates["ContainsReadBeforeWrite"],
                "dominant_action": aggregates["DominantActionType"],
                "multi_domain": False # Handled in Decision Engine / Aggregates
            }
        }
