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
        
        # Refine Primary Intent
        if not detected_intents:
            primary_intent = "InformationDiscovery" if is_read else "UnknownIntent"
            secondary_intents = []
        else:
            primary_intent = detected_intents[0]
            secondary_intents = detected_intents[1:]
            
        # 3. Precise Capability Extraction (REFINED 4H)
        # Logic: RequiredCapabilities = ToolCapabilities ∪ (IntentCapabilities | Confidence >= Threshold)
        
        # A. Collect tool-derived capabilities
        tool_capabilities = set()
        for d in tool_metadata:
            for cap in d["capabilities"]:
                tool_capabilities.add(cap)
        
        # B. Use Inference Service for intent-derived and domain-aware requirements
        required_capabilities, cap_audit = self.inference_svc.get_required_capabilities(
            primary_domain.value, task_text, tool_capabilities
        )
        
        # 4. Computed Intent Properties (STRICTLY FROM TOOLS)
        from app.services.tool_classifier import ToolClassifier
        classifier = ToolClassifier()
        aggregates = classifier.get_aggregate_predicates(tool_metadata)
        
        return {
            "primary_intent": primary_intent,
            "secondary_intents": list(secondary_intents),
            "required_capabilities": list(required_capabilities),
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
