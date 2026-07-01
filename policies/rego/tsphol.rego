# ══════════════════════════════════════════════════════════════════════
# PALADIN TRAC — generic OPA/Rego evaluator over rules-as-data.
#
# Like rbac.rego / abac.rego, this contains NO rule-specific logic. It evaluates
# the TRAC predicate rules loaded as the `data.tsphol_rules` document (from
# policies/trac_rules.yaml), mirroring app/services/tsphol_interpreter:
# a rule fires when every condition in its `if` holds; the request is DENIED if
# any ENFORCING deny-rule fires; advisory rules (enforce: false) raise an alert
# without changing the decision. Editing the YAML in Policy Studio updates the
# Python engine AND OPA — no code generation, no hand-syncing this file.
#
#   opa eval -d policies/trac_rules.yaml -d policies/rego/tsphol.rego \
#            -i input.json 'data.paladin.tsphol'
#
# Predicates (HardCapabilityMissing, ContainsDelete, ContainsReadBeforeWrite, …)
# are computed by the Python evidence-extraction step and passed as
# input.predicates (the agnostic {domain}:{action} capability model + the
# VerbNet-grounded action class).
# ══════════════════════════════════════════════════════════════════════
package paladin.tsphol

import rego.v1

# ── condition matcher (mirrors tsphol_interpreter.evaluate_conditions) ──────
# Each condition carries exactly one operator key; the non-matching clauses fail
# on the undefined operator value, so only the present operator can hold.
cond_holds(c) if c.equals == input.predicates[c.predicate]

cond_holds(c) if input.predicates[c.predicate] < c.lt

cond_holds(c) if input.predicates[c.predicate] > c.gt

cond_holds(c) if {
	val := input.predicates[c.predicate]
	is_array(val)
	c.includes in val
}

cond_holds(c) if {
	val := input.predicates[c.predicate]
	not is_array(val)
	val == c.includes
}

cond_holds(c) if {
	val := input.predicates[c.predicate]
	is_array(val)
	not (c.missing in val)
}

cond_holds(c) if {
	val := input.predicates[c.predicate]
	not is_array(val)
	val != c.missing
}

# A rule fires when every condition holds (vacuously true if it has none).
rule_fires(r) if {
	every c in object.get(r, "if", []) {
		cond_holds(c)
	}
}

# Enforcing deny-rules that fire change the decision; advisory ones only alert.
enforced_denials contains r.rule_name if {
	some r in data.tsphol_rules
	upper(r.then) == "DENY"
	object.get(r, "enforce", true) == true
	rule_fires(r)
}

advisory_denials contains r.rule_name if {
	some r in data.tsphol_rules
	upper(r.then) == "DENY"
	object.get(r, "enforce", true) == false
	rule_fires(r)
}

# ── outputs ─────────────────────────────────────────────────────────────
default decision := "ALLOW"

decision := "DENY" if count(enforced_denials) > 0

deny := count(enforced_denials) > 0

# Alerts reported for audit — every fired deny-rule (enforcing or advisory).
advisories contains name if some name in enforced_denials

advisories contains name if some name in advisory_denials

default write_safety_alert := false

write_safety_alert if "write_safety" in advisory_denials
