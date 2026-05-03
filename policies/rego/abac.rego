# ══════════════════════════════════════════════════════════════════════
# PALADIN ABAC Policy — OPA/Rego Translation
#
# Translates policies/abac_rules.yaml into Rego.
# Evaluates attribute-based deny rules. ALL conditions in a rule must
# match for the rule to fire. First matching deny rule wins.
# ══════════════════════════════════════════════════════════════════════
package paladin.abac

import rego.v1

default decision := "ALLOW"
default denial_rule := ""

# ── Department Isolation ─────────────────────────────────────────────

# abac_finance_isolation: Financial compliance restricted to Finance dept
abac_deny("abac_finance_isolation") if {
    input.resource.compliance_tier == "Financial"
    input.subject.department != "Finance"
}

# abac_pci_isolation: PCI-DSS restricted to Finance dept
abac_deny("abac_pci_isolation") if {
    input.resource.compliance_tier == "PCI-DSS"
    input.subject.department != "Finance"
}

# abac_hipaa_restriction: HIPAA restricted to Medical dept
abac_deny("abac_hipaa_restriction") if {
    input.resource.compliance_tier == "HIPAA"
    input.subject.department != "Medical"
}

# abac_infrastructure_write_isolation: Infra writes require Eng/Infra dept
abac_deny("abac_infrastructure_write_isolation") if {
    input.resource.data_sensitivity == "Infrastructure"
    input.action.contains_write == true
    input.subject.department != "Engineering"
    input.subject.department != "Infrastructure"
}

# ── Financial Write Isolation ────────────────────────────────────────

# abac_financial_write_requires_finance: Financial writes require Finance dept
abac_deny("abac_financial_write_requires_finance") if {
    input.resource.domain in {"stripe", "hummingbot-mcp"}
    input.action.contains_write == true
    input.subject.department != "Finance"
}

# ── Clearance-Based Access ───────────────────────────────────────────

# abac_destructive_write_requires_L3: Destructive ops need L3
abac_deny("abac_destructive_write_requires_L3") if {
    input.action.contains_destructive_write == true
    input.subject.clearance_level != "L3"
}

# abac_clearance_write_high_risk: High-risk writes need L3
abac_deny("abac_clearance_write_high_risk") if {
    input.resource.risk_level == "high"
    input.action.contains_write == true
    input.subject.clearance_level != "L3"
}

# abac_clearance_read_high_risk: High-risk reads need at least L2
abac_deny("abac_clearance_read_high_risk") if {
    input.resource.risk_level == "high"
    input.subject.clearance_level == "L1"
}

# ── Trust Score Gating ───────────────────────────────────────────────

# abac_low_trust_write: Low trust blocks writes
abac_deny("abac_low_trust_write") if {
    input.action.contains_write == true
    to_number(input.subject.trust_score) < 0.8
}

# abac_low_trust_privileged_write: Privileged writes need 0.9+ trust
abac_deny("abac_low_trust_privileged_write") if {
    input.action.contains_privileged_write == true
    to_number(input.subject.trust_score) < 0.9
}

# abac_beta_trust_denial: Experimental tools need 0.85+ trust
abac_deny("abac_beta_trust_denial") if {
    input.resource.trust_boundary == "Experimental"
    to_number(input.subject.trust_score) < 0.85
}

# ── Multi-Tool Write Gating ─────────────────────────────────────────

# abac_multi_tool_write_high_trust: 3+ write tools need 0.9+ trust
abac_deny("abac_multi_tool_write_high_trust") if {
    to_number(input.action.write_tool_count) >= 3
    to_number(input.subject.trust_score) < 0.9
}

# ── Temporal Controls ────────────────────────────────────────────────

# abac_after_hours_write: High-risk writes blocked outside business hours
abac_deny("abac_after_hours_write") if {
    input.resource.risk_level == "high"
    input.action.contains_write == true
    input.environment.after_hours == true
}

# ── Decision aggregation ────────────────────────────────────────────
# Collect all matching deny rules
matched_denials contains rule if {
    abac_deny(rule)
}

decision := "DENY" if {
    count(matched_denials) > 0
}

denial_rule := rule if {
    some rule in matched_denials
}
