# ══════════════════════════════════════════════════════════════════════
# PALADIN ABAC — generic OPA/Rego evaluator over rules-as-data.
#
# This policy contains NO rule-specific logic. It evaluates the attribute
# rules loaded as the `data.rules` document (from policies/abac_rules.yaml),
# mirroring app/services/abac_engine.ABACEngine. Editing rules never touches
# this file — that is the point of the rules-as-data pattern (OPA's canonical
# "policy is generic, facts are data" Document Model).
#
#   opa eval -d policies/abac_rules.yaml -d policies/rego/abac.rego \
#            -i input.json 'data.paladin.abac.decision'
#
# A rule DENIES when every condition in its match_attributes holds; the
# request is DENIED if any deny rule fires.
# ══════════════════════════════════════════════════════════════════════
package paladin.abac

import rego.v1

# Resolve a condition's actual value: input[source] then the dot-split nested
# path, normalising a missing value to null so comparisons mirror the Python
# comparator (where a missing attribute is None).
actual_value(c) := v if {
	src := object.get(input, [c.source], {})
	v := object.get(src, split(c.attribute, "."), null)
}

# matches(actual, op, expected) — mirrors ABACEngine._compare. Numeric ops
# guard null because OPA's to_number(null) is 0 (Python raises -> no match).
matches(a, "==", b) if a == b

matches(a, "!=", b) if a != b

matches(a, ">", b) if {
	a != null
	to_number(a) > to_number(b)
}

matches(a, "<", b) if {
	a != null
	to_number(a) < to_number(b)
}

matches(a, ">=", b) if {
	a != null
	to_number(a) >= to_number(b)
}

matches(a, "<=", b) if {
	a != null
	to_number(a) <= to_number(b)
}

matches(a, "in", b) if {
	is_array(b)
	a in b
}

matches(a, "in", b) if {
	not is_array(b)
	contains(sprintf("%v", [a]), sprintf("%v", [b]))
}

condition_holds(c) if matches(actual_value(c), object.get(c, "op", "=="), c.value)

rule_fires(r) if {
	count(r.match_attributes) > 0
	every c in r.match_attributes {
		condition_holds(c)
	}
}

# Set of deny-rule ids that fire on this request.
deny_rules contains r.id if {
	some r in data.rules
	r.action == "deny"
	rule_fires(r)
}

default decision := "ALLOW"

decision := "DENY" if count(deny_rules) > 0
