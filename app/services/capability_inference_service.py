import os
import json
import logging
from typing import List, Dict, Any, Set, Tuple
from app.services.policy_loader import PolicyLoader

logger = logging.getLogger(__name__)

class CapabilityInferenceService:
    """
    Manages domain-aware required capability generation.
    Supports tool-derived and intent-derived requirements with provenance metadata.
    Refined in 4H.1 to be fully dynamic (string-based domain keys).
    """
    
    def __init__(self, 
                 catalog_path: str = "policies/domain_capability_catalog.json",
                 rules_path: str = "policies/required_capability_rules.json",
                 config_path: str = "policies/inference_config.json"):
        self.catalog_path = catalog_path
        self.rules_path = rules_path
        self.config_path = config_path
        self.PolicyLoader = PolicyLoader # For UI accessibility
        
        # Initial Load
        self.catalog = PolicyLoader.load_json(catalog_path)
        self.rules = PolicyLoader.load_json(rules_path)
        self.config = PolicyLoader.load_json(config_path)

    def get_required_capabilities(self, 
                                 domain: str, 
                                 task_text: str, 
                                 tool_capabilities: Set[str]) -> Tuple[Set[str], List[Dict[str, Any]]]:
        """
        Calculates the final set of required capabilities and provides audit metadata.
        Uses string-based domain key for dynamic catalog support.
        """
        # Reload policies to ensure freshness
        self.catalog = PolicyLoader.load_json(self.catalog_path)
        self.rules = PolicyLoader.load_json(self.rules_path)
        self.config = PolicyLoader.load_json(self.config_path)
        
        threshold = self.config.get("confidence_threshold", 0.75)
        
        final_set = set()
        audit_metadata = []
        
        # 1. Tool-Derived Capabilities (Foundational Truth - Always Included)
        for cap in tool_capabilities:
            final_set.add(cap)
            audit_metadata.append({
                "capability": cap,
                "source": "tool",
                "confidence": 1.0,
                "status": "ACCEPTED",
                "reason": "Directly required by selected tools"
            })
            
        # 2. Intent-Derived Candidates (Task-Text NLP)
        task_lower = task_text.lower()
        
        for rule in self.rules:
            # Domain Check (String-based)
            if rule.get("domain") != domain:
                continue
                
            # Keyword Match
            keywords = rule.get("keywords_any", [])
            if any(kw in task_lower for kw in keywords):
                confidence = rule.get("confidence", 0.0)
                caps_to_add = rule.get("adds_capabilities", [])
                
                for cap in caps_to_add:
                    # Filter: Candidate must be in the domain's catalog
                    allowed_caps = self.catalog.get(domain, [])
                    if cap not in allowed_caps:
                        audit_metadata.append({
                            "capability": cap,
                            "source": "intent_text",
                            "confidence": confidence,
                            "status": "REJECTED",
                            "reason": f"Capability not allowed in domain: {domain}"
                        })
                        continue
                    
                    # Accept/Reject based on confidence threshold
                    if confidence >= threshold:
                        if cap not in final_set:
                            final_set.add(cap)
                            audit_metadata.append({
                                "capability": cap,
                                "source": "intent_text",
                                "confidence": confidence,
                                "status": "ACCEPTED",
                                "reason": f"Strong task signal (rule: {rule.get('name')})"
                            })
                    else:
                        if cap not in final_set:
                            audit_metadata.append({
                                "capability": cap,
                                "source": "intent_text",
                                "confidence": confidence,
                                "status": "FILTERED",
                                "reason": f"Confidence {confidence} below threshold {threshold}"
                            })
                            
        return final_set, audit_metadata

    # --- Persistence Helpers ---
    
    def save_catalog(self, catalog: Dict[str, List[str]]) -> bool:
        return PolicyLoader.save_json(self.catalog_path, catalog)
        
    def save_rules(self, rules: List[Dict[str, Any]]) -> bool:
        return PolicyLoader.save_json(self.rules_path, rules)
        
    def save_config(self, config: Dict[str, Any]) -> bool:
        return PolicyLoader.save_json(self.config_path, config)
