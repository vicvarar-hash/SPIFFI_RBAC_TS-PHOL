from typing import List, Dict, Set
import json
import os

# Strong Task Capability Ontology (Iteration 4Q)
# Now loaded from policies/domain_capability_ontology.json for editability

_ONTOLOGY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "policies", "domain_capability_ontology.json")

def _load_ontology():
    """Load ontology from JSON file."""
    path = os.path.normpath(_ONTOLOGY_PATH)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"domain_capabilities": {}, "abstract_capabilities": [], "capability_implications": {}, "domain_fallbacks": {}}

def _save_ontology(data: dict) -> bool:
    """Save ontology to JSON file."""
    path = os.path.normpath(_ONTOLOGY_PATH)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
        return True
    except Exception:
        return False

_ontology_cache = None

def _get_ontology():
    global _ontology_cache
    if _ontology_cache is None:
        _ontology_cache = _load_ontology()
    return _ontology_cache

def reload_ontology():
    """Force reload from disk (after edits)."""
    global _ontology_cache
    _ontology_cache = _load_ontology()
    return _ontology_cache

def get_domain_capabilities() -> dict:
    return _get_ontology().get("domain_capabilities", {})

def save_domain_capabilities(caps: dict) -> bool:
    """Save updated domain capabilities to the ontology JSON file."""
    ontology = _get_ontology().copy()
    ontology["domain_capabilities"] = caps
    return _save_ontology(ontology)

# Module-level reference for backward compatibility
DOMAIN_CAPABILITIES = get_domain_capabilities()

class DomainCapabilityOntology:
    @staticmethod
    def get_capabilities_for_intent(domain: str, intent: str) -> Dict[str, List[str]]:
        """
        Retrieves the standard capability set for a given domain and intent.
        Returns: {"required": [...], "optional": [...]}
        """
        caps = get_domain_capabilities()
        domain_intents = caps.get(domain, {})
        data = domain_intents.get(intent)
        if isinstance(data, dict):
            return data
        return {"required": [], "optional": []}

    @staticmethod
    def infer_minimum_capabilities(domain: str) -> Dict[str, List[str]]:
        """
        Fallback mechanism for unknown intents within a known domain.
        Returns: {"required": [...], "optional": [], "hard": [...], "soft": [...]}
        """
        ontology = _get_ontology()
        fallbacks = ontology.get("domain_fallbacks", {})
        if domain in fallbacks:
            return fallbacks[domain]
        return {"required": ["GenericRead"], "optional": [], "hard": ["GenericRead"], "soft": []}

    @staticmethod
    def get_hard_capabilities(domain: str, intent: str) -> Set[str]:
        """
        Returns the set of hard (mission-critical) capabilities for a domain/intent.
        Missing a hard capability = DENY. Missing a soft capability = audit warning.
        """
        caps = get_domain_capabilities()
        domain_intents = caps.get(domain, {})
        data = domain_intents.get(intent)
        if isinstance(data, dict) and "hard" in data:
            return set(data["hard"])
        if isinstance(data, dict):
            return set(data.get("required", []))
        fallback = DomainCapabilityOntology.infer_minimum_capabilities(domain)
        return set(fallback.get("hard", fallback.get("required", [])))

    @staticmethod
    def get_abstract_capabilities() -> Set[str]:
        ontology = _get_ontology()
        return set(ontology.get("abstract_capabilities", []))

    @staticmethod
    def get_capability_implications() -> Dict[str, List[str]]:
        ontology = _get_ontology()
        return ontology.get("capability_implications", {})

    @staticmethod
    def expand_capabilities(caps: Set[str]) -> Set[str]:
        """
        Performs Capability Subsumption:
        Computes the complete semantic closure of capabilities based on hierarchical implication rules.
        """
        implications = DomainCapabilityOntology.get_capability_implications()
        expanded = set(caps)
        changed = True
        while changed:
            changed = False
            for cap in list(expanded):
                for implied in implications.get(cap, []):
                    if implied not in expanded:
                        expanded.add(implied)
                        changed = True
        return expanded

    @staticmethod
    def is_concrete(capability: str) -> bool:
        """
        Filters for visible concrete capabilities (excludes groupings).
        """
        return capability not in DomainCapabilityOntology.get_abstract_capabilities()

    @staticmethod
    def save_domain_capabilities(domain_capabilities: dict) -> bool:
        """Save updated domain capabilities back to the ontology JSON."""
        ontology = _get_ontology()
        ontology["domain_capabilities"] = domain_capabilities
        if _save_ontology(ontology):
            reload_ontology()
            return True
        return False

    @staticmethod
    def save_full_ontology(ontology: dict) -> bool:
        """Save the entire ontology dict."""
        if _save_ontology(ontology):
            reload_ontology()
            return True
        return False
