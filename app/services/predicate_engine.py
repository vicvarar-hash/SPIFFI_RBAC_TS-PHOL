from typing import List, Dict, Any, Set, Callable, Tuple
import logging

logger = logging.getLogger(__name__)

class PredicateEngine:
    """
    The Brain of TS-PHOL.
    Converts session context into logical predicates for reasoning.
    Refined in Iteration 4I to ensure strict ToolAggregate consistency.
    """
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.predicates = self._initialize_predicates(context)
        self.derived_predicates = {}
        self.trace = []
        self.trace.append("Predicate initialization complete (Iteration 4I).")

    def _initialize_predicates(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Populates a set of base predicates from the input context.
        Prioritizes tool_aggregates from ToolClassifier to ensure consistency.
        """
        p = {}
        # Identity
        p["CallerId"] = context.get("spiffe_id", "unknown")
        p["Role"] = context.get("role", "guest")
        
        # Tools & MCPs
        p["UsesMCPs"] = set(context.get("mcps", []))
        p["UsesTools"] = set(context.get("tools", []))
        
        # 4T: Keep full set for internal rule logic (SSOT filtering handled in UI/Context)
        p["HasCapabilities"] = set(context.get("has_capabilities", []))
        p["RequiredCapabilities"] = set(context.get("task_required_capabilities", []))

        # Intent Metadata (for tracing)
        intent_info = context.get("intent_info", {})
        p["PrimaryIntent"] = intent_info.get("primary_intent", "Unknown")
        p["SecondaryIntents"] = set(intent_info.get("secondary_intents", []))
        
        # 4I: Use Direct Tool Aggregates for strict consistency
        aggregates = context.get("tool_aggregates", {})
        if aggregates:
            p["ContainsWrite"] = aggregates.get("ContainsWrite", False)
            p["ContainsRead"] = aggregates.get("ContainsRead", False)
            p["ContainsReadBeforeWrite"] = aggregates.get("ContainsReadBeforeWrite", False)
            p["DominantActionType"] = aggregates.get("DominantActionType", "unknown")
            p["MultiDomain"] = aggregates.get("MultiDomain", False)
            p["ContainsDelete"] = aggregates.get("ContainsDelete", False)
            p["ContainsHistory"] = aggregates.get("ContainsHistory", False)
            p["ContainsSearch"] = aggregates.get("ContainsSearch", False)
        else:
            # Fallback to intent info (deprecated in favoring tool_aggregates)
            properties = intent_info.get("intent_properties", {})
            p["ContainsWrite"] = properties.get("contains_write", False)
            p["ContainsRead"] = properties.get("contains_read", False)
            p["ContainsReadBeforeWrite"] = properties.get("contains_read_before_write", False)
            p["DominantActionType"] = properties.get("dominant_action", "unknown")
            p["MultiDomain"] = properties.get("multi_domain", False)
            p["ContainsDelete"] = properties.get("contains_delete", False)
            p["ContainsHistory"] = properties.get("contains_history", False)
            p["ContainsSearch"] = properties.get("contains_search", False)
        
        # Metadata
        p["ConfidenceValue"] = context.get("confidence", 0.0)
        p["HighestRiskLevel"] = context.get("highest_risk", "low")
        
        # 4M: Task/Bundle Alignment Predicates
        p["TaskDomainExpected"] = context.get("expected_domain", "Uncertain")
        p["BundleDomainActual"] = context.get("actual_domain", "Uncertain")
        p["TaskAlignmentScore"] = context.get("task_alignment_score", 0.0)
        
        # 4R: Alignment Reliability & Tolerance
        p["AlignmentEvaluated"] = (p["TaskDomainExpected"] != "Uncertain")
        p["SelectionToleranceActive"] = context.get("selection_tolerance_active", False)
        
        # Logic Flags
        p["TaskBundleDomainMismatch"] = (p["TaskDomainExpected"] != p["BundleDomainActual"]) and (p["TaskDomainExpected"] != "Uncertain")
        
        issue_codes = context.get("issue_codes", [])
        p["ValidationFailed"] = len(issue_codes) > 0
        # 4O/4T: Strict Capability Alignment Logic
        from app.services.domain_capability_ontology import DomainCapabilityOntology
        full_missing = p["RequiredCapabilities"] - p["HasCapabilities"]
        
        # summary list: only concrete for user-facing transparency
        p["MissingCapabilities"] = [c for c in full_missing if DomainCapabilityOntology.is_concrete(c)]
        
        p["CapabilityCoverageSatisfied"] = len(full_missing) == 0
        p["CapabilityCoverageViolation"] = len(full_missing) > 0
        p["BundleIrrelevantToTask"] = "IRRELEVANT_TOOLS" in issue_codes or "WRONG_DOMAIN" in issue_codes
        
        return p

    def has_predicate(self, name: str, value: Any = None) -> bool:
        """
        Check if a predicate exists or matches a value.
        """
        if name not in self.predicates and name not in self.derived_predicates:
            return False
            
        target = self.derived_predicates.get(name) or self.predicates.get(name)
        
        if value is None:
            return bool(target) # Exists logic
            
        if isinstance(target, set):
            return value in target
            
        return target == value

    def exists(self, predicate_name: str, condition: Callable[[Any], bool]) -> bool:
        """
        Logical exists quantifier: ∃x ∈ predicate_set : condition(x)
        """
        items = self.predicates.get(predicate_name, set())
        if not isinstance(items, (set, list)):
            return condition(items)
        return any(condition(i) for i in items)

    def forall(self, predicate_name: str, condition: Callable[[Any], bool]) -> bool:
        """
        Logical forall quantifier: ∀x ∈ predicate_set : condition(x)
        """
        items = self.predicates.get(predicate_name, set())
        if not items:
            return True # Vacuously true
        if not isinstance(items, (set, list)):
            return condition(items)
        return all(condition(i) for i in items)

    def derive(self, name: str, value: Any = True, reason: str = ""):
        """
        Generates a new intermediate predicate during the reasoning process.
        """
        self.derived_predicates[name] = value
        if reason:
            self.trace.append(f"Derived: {name} ({value}) -> {reason}")
        else:
            self.trace.append(f"Derived: {name} ({value})")

    def check_capability_satisfaction(self) -> Tuple[bool, Set[str]]:
        """
        Checks if the request has all the capabilities required by the intent.
        Logic: RequiredCapabilities ⊆ HasCapabilities
        """
        required = self.predicates.get("RequiredCapabilities", set())
        active = self.predicates.get("HasCapabilities", set())
        
        missing = required - active
        if not missing:
            return True, set()
        
        self.derive("IncompleteCapabilities", True, f"Missing: {missing}")
        return False, missing

    def check_intent_consistency(self) -> Tuple[bool, str]:
        """
        Checks if the set of tools and capabilities are consistent with the intents.
        """
        intents = self.predicates.get("SecondaryIntents", set())
        capabilities = self.predicates.get("HasCapabilities", set())
        
        # Rule: DocumentIncident implies we should have already seen/used Investigation tools
        if "DocumentIncident" in intents:
            if "InvestigationLookup" not in capabilities and "LogAnalysis" not in capabilities:
                self.derive("IncompleteIntent", True, "Documenting without investigation context")
                return False, "Documenting without investigation context"
        
        # Rule: Write without Read (UnsafeWrite)
        if self.predicates.get("ContainsWrite") and not self.predicates.get("ContainsRead"):
            self.derive("UnsafeWrite", True, "Write operation without preceding Read/Verification")
            return False, "Write operation without preceding Read/Verification"

        return True, ""

    def get_all_predicates(self) -> Dict[str, Any]:
        """
        Combines base and derived predicates.
        """
        return {**self.predicates, **self.derived_predicates}

    def get_trace(self) -> List[str]:
        """
        Returns the step-by-step logical trace.
        """
        return self.trace
