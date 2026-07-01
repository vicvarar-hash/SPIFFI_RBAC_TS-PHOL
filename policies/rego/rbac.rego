# ══════════════════════════════════════════════════════════════════════
# PALADIN RBAC — generic OPA/Rego evaluator over policies-as-data.
#
# Reads the RBAC allow-lists loaded as the `data.policies` document (from
# policies/rbac.yaml) and applies the literal allow-list semantics of
# app/services/decision_engine._evaluate_rbac: a (mcp, tool) is permitted iff
# some allow rule for the identity matches; the request is ALLOWed iff every
# requested (mcp, tool) is permitted. No code generation — edit rbac.yaml.
#
#   opa eval -d policies/rbac.yaml -d policies/rego/rbac.rego \
#            -i input.json 'data.paladin.rbac.decision'
# ══════════════════════════════════════════════════════════════════════
package paladin.rbac

import rego.v1

default decision := "DENY"

mcp_matches(rule_mcp, _) if rule_mcp == "*"

mcp_matches(rule_mcp, mcp) if rule_mcp == mcp

tool_matches(tools, _) if "*" in tools

tool_matches(tools, tool) if tool in tools

# A (mcp, tool) is permitted iff some allow rule for the identity matches both.
tool_allowed(spiffe, mcp, tool) if {
	some p in data.policies
	p.spiffe_id == spiffe
	some r in p.rules
	r.action == "allow"
	mcp_matches(r.mcp, mcp)
	tool_matches(r.tools, tool)
}

decision := "ALLOW" if {
	count(input.tools) > 0
	every i in numbers.range(0, count(input.tools) - 1) {
		tool_allowed(input.spiffe_id, input.mcps[i], input.tools[i])
	}
}
