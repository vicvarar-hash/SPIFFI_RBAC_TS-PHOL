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
