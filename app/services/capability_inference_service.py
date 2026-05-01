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

    def get_task_required_capabilities(self, 
                                     domain: str, 
                                     task_text: str,
                                     intent: str = None) -> Tuple[Set[str], Set[str], List[Dict[str, Any]]]:
        """
        4W: Refactored to distinguish between Required (minimal) and Optional (enrichment) capabilities.
        Returns: (required_set, optional_set, audit_metadata)
        """
        from app.services.domain_capability_ontology import DomainCapabilityOntology
        
        # Reload policies to ensure freshness
        self.catalog = PolicyLoader.load_json(self.catalog_path)
        self.rules = PolicyLoader.load_json(self.rules_path)
        self.config = PolicyLoader.load_json(self.config_path)
        
        threshold = self.config.get("confidence_threshold", 0.75)
        
        required_set = set()
        optional_set = set()
        audit_metadata = []
        
        # 1. Ontology-Based Capabilities (Foundational)
        if intent:
            ont_data = DomainCapabilityOntology.get_capabilities_for_intent(domain, intent)
            for cap in ont_data.get("required", []):
                required_set.add(cap)
                audit_metadata.append({
                    "capability": cap,
                    "source": "ontology",
                    "status": "ACCEPTED",
                    "priority": "REQUIRED",
                    "reason": f"Minimal required by ontology for intent: {intent}"
                })
            for cap in ont_data.get("optional", []):
                optional_set.add(cap)
                audit_metadata.append({
                    "capability": cap,
                    "source": "ontology",
                    "status": "ACCEPTED",
                    "priority": "OPTIONAL",
                    "reason": f"Optional enrichment for intent: {intent}"
                })
        
        # 2. Intent-Derived Candidates (Task-Text NLP)
        task_lower = task_text.lower()
        allowed_caps = self.catalog.get(domain, [])
        
        for rule in self.rules:
            if rule.get("domain") != domain:
                continue
                
            keywords = rule.get("keywords_any", [])
            if any(kw in task_lower for kw in keywords):
                confidence = rule.get("confidence", 0.0)
                caps_to_add = rule.get("adds_capabilities", [])
                
                for cap in caps_to_add:
                    if cap not in allowed_caps:
                        continue
                    
                    if confidence >= threshold:
                        if cap not in required_set and cap not in optional_set:
                            # 4W: NLP candidates are 'OPTIONAL' (enrichment) unless they were already required by ontology
                            optional_set.add(cap)
                            audit_metadata.append({
                                "capability": cap,
                                "source": "task_inference",
                                "confidence": confidence,
                                "status": "ACCEPTED",
                                "priority": "OPTIONAL",
                                "reason": f"Inferred enrichment (rule: {rule.get('name')})"
                            })
        
        # 3. 4Q Enforce Non-Empty (Fallback Inference)
        if not required_set and domain != "General":
            fallback_data = DomainCapabilityOntology.infer_minimum_capabilities(domain)
            for cap in fallback_data.get("required", []):
                required_set.add(cap)
                audit_metadata.append({
                    "capability": cap,
                    "source": "fallback_ontology",
                    "status": "ACCEPTED",
                    "priority": "REQUIRED",
                    "reason": "Minimum viable capability for known domain (fallback)"
                })
                            
        # 4L/4T: Abstract Capability Filtering (Centralized authority)
        abstract_caps = DomainCapabilityOntology.get_abstract_capabilities()
        
        final_required = {cap for cap in required_set if cap not in abstract_caps}
        final_optional = {cap for cap in optional_set if cap not in abstract_caps}
        
        # Record filtering in audit metadata
        all_candidates = required_set.union(optional_set)
        for cap in all_candidates:
            if cap in abstract_caps:
                for m in audit_metadata:
                    if m["capability"] == cap:
                        m["status"] = "FILTERED_ABSTRACT"
                        m["reason"] = f"Filtered as abstract/grouping capability: {cap}"
                            
        return final_required, final_optional, audit_metadata

    # --- Persistence Helpers ---
    
    def save_catalog(self, catalog: Dict[str, List[str]]) -> bool:
        return PolicyLoader.save_json(self.catalog_path, catalog)
        
    def save_rules(self, rules: List[Dict[str, Any]]) -> bool:
        return PolicyLoader.save_json(self.rules_path, rules)
        
    def save_config(self, config: Dict[str, Any]) -> bool:
        return PolicyLoader.save_json(self.config_path, config)
