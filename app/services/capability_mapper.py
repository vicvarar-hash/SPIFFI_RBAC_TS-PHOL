import logging
from typing import List, Dict, Any, Set
from app.services.tool_classifier import ToolClassifier

logger = logging.getLogger(__name__)

class CapabilityMapper:
    """
    Maps specific tools to abstract capabilities.
    Now delegates to ToolClassifier for curated and heuristic mapping.
    Refined in Iteration 4I with hierarchy and enrichment.
    """
    
    # 4T: Hierarchical logic moved to ontology/classifier where possible. 
    # Mapper focuses on expanding tools to capabilities.
    MAPPER_HIERARCHY = {
        "IssueRead": "AtlassianRead",
        "HistoryReview": "AtlassianRead",
        "IssueSearch": "AtlassianRead",
        "IssueUpdate": "AtlassianWrite",
        "IssueCreation": "AtlassianWrite",
        "AlertRuleReview": "ObservabilityRead",
        "DatasourceReview": "ObservabilityRead",
        "MetricsQuery": "ObservabilityRead"
    }

    def __init__(self):
        self.classifier = ToolClassifier()

    def extract_capabilities(self, tools: List[str]) -> Set[str]:
        """
        Extracts high-level capabilities from a list of tools.
        Delegates to ToolClassifier and applies hierarchy enrichment.
        """
        final_capabilities = set()
        audit_data = self.classifier.classify_tools(tools)
        
        for d in audit_data:
            tool_caps = d["capabilities"]
            
            # Logging & Warning for Failures (4I Criterion)
            if not tool_caps or "GenericToolUse" in tool_caps:
                logger.warning(f"Fallback capability used: GenericToolUse for tool '{d['tool']}'")
            
            for cap in tool_caps:
                final_capabilities.add(cap)
                
                # Hierarchy Enrichment (4I Criterion)
                abstract_cap = self.MAPPER_HIERARCHY.get(cap)
                if abstract_cap:
                    final_capabilities.add(abstract_cap)
                    
        # Log final capability set (4I Criterion)
        logger.info(f"Capability enrichment applied. Final set: {final_capabilities}")
        return final_capabilities
