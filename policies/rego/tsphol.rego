# ══════════════════════════════════════════════════════════════════════
# PALADIN TS-PHOL Policy — OPA/Rego Translation
#
# Translates policies/tsphol_rules.yaml into Rego.
# Evaluates predicate-based rules with priority ordering.
#
# KEY LIMITATION: OPA cannot express DECEPTION_ROUTED — a third
# enforcement mode unique to PALADIN. All TS-PHOL denials here
# produce binary DENY.
# ══════════════════════════════════════════════════════════════════════
package paladin.tsphol

import rego.v1

default decision := "ALLOW"

# Priority 130: Low-confidence write prevention
tsphol_deny("low_confidence_write_prevention", 130) if {
    input.predicates.ContainsWrite == true
    input.predicates.ConfidenceValue < 0.75
}

# Priority 125: High-risk write confidence safeguard
tsphol_deny("high_risk_write_confidence_safeguard", 125) if {
    input.predicates.HighestRiskLevel == "high"
    input.predicates.ContainsWrite == true
    input.predicates.ConfidenceValue < 0.85
}

# Priority 120: Task-bundle domain mismatch
tsphol_deny("task_bundle_domain_mismatch", 120) if {
    input.predicates.TaskBundleDomainMismatch == true
    input.predicates.SelectionToleranceActive == false
}

# Priority 110: Validation failure denial
tsphol_deny("validation_failure_denial", 110) if {
    input.predicates.CriticalValidationFailure == true
}

# Priority 105: Hard capability violation
tsphol_deny("hard_capability_violation", 105) if {
    input.predicates.HardCapabilityMissing == true
    input.predicates.SelectionToleranceActive == false
}

# Priority 100: Destructive write without read verification
tsphol_deny("destructive_write_prevention", 100) if {
    input.predicates.ContainsDelete == true
    input.predicates.ContainsRead == false
}

# Priority 70: Elevated risk + low confidence
# (Priority 80 elevated_risk_detection just derives a fact, doesn't deny)
tsphol_deny("elevated_risk_confidence", 70) if {
    input.predicates.HighestRiskLevel == "high"
    input.predicates.MultiDomain == true
    input.predicates.ConfidenceValue < 0.90
}

# Priority 60: Low task alignment
tsphol_deny("low_task_alignment", 60) if {
    input.predicates.AlignmentEvaluated == true
    input.predicates.TaskAlignmentScore < 0.4
    input.predicates.SelectionToleranceActive == false
}

# Priority 60: Low alignment even with tolerance
tsphol_deny("low_task_alignment_with_tolerance", 60) if {
    input.predicates.AlignmentEvaluated == true
    input.predicates.TaskAlignmentScore < 0.3
    input.predicates.SelectionToleranceActive == true
}

# ── Decision aggregation ────────────────────────────────────────────
matched_denials contains {"rule": rule, "priority": p} if {
    tsphol_deny(rule, p)
}

decision := "DENY" if {
    count(matched_denials) > 0
}

# Highest-priority triggered rule
highest_priority_denial := max_p if {
    max_p := max({d.priority | some d in matched_denials})
}
