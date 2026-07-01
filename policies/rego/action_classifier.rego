# ══════════════════════════════════════════════════════════════════════
# PALADIN — deterministic action classifier in OPA/Rego.
#
# Demonstrates that TRAC's "data dictionary" (the verb lexicon) and its
# classification logic can be expressed in the CNCF-standard policy language.
#
# Separation of concerns (the standard OPA pattern):
#   * Python "evidence extraction" tokenises + lemmatises the tool description and
#     splits the name, producing input.tool.{head_verb, verbs, name_segments,
#     description_lower}. (Rego is not a tokeniser.)
#   * This Rego policy + the action_lexicon DATA document make the decision: it does
#     the lexicon lookup, the read-guard (lightweight SRL), and the escalate-only
#     fusion — all auditable, all data-driven.
#
# Run:  opa eval -d policies/rego/action_classifier.rego \
#                -d policies/rego/data/action_lexicon.json \
#                -i input.json 'data.paladin.action.action_class'
# ══════════════════════════════════════════════════════════════════════
package paladin.action

import rego.v1

lex := data.action_lexicon

# ── Destructive: any description verb OR name segment in the removing class ──
default is_destructive := false

is_destructive if {
	some v in input.tool.verbs
	v in lex.destructive
}

is_destructive if {
	some s in input.tool.name_segments
	s in lex.destructive
}

# ── Read-guard (SRL): an AMBIGUOUS head verb whose object is an information artifact ──
read_guarded if {
	input.tool.head_verb in lex.ambiguous
	some n in lex.read_nouns
	contains(input.tool.description_lower, n)
}

# ── Write: destructive (subsumes), or a write head verb, or an un-guarded ambiguous
#    head verb, or — escalate-only — a write verb anywhere in the name ──
default is_write := false

is_write if is_destructive

is_write if input.tool.head_verb in lex.write

is_write if {
	input.tool.head_verb in lex.ambiguous
	not read_guarded
}

is_write if {
	some s in input.tool.name_segments
	s in lex.write
}

# ── Final operation class (read by default — fail-open to the safe, non-mutating label
#    only when nothing escalates) ──
action_class := "destructive" if {
	is_destructive
} else := "write" if {
	is_write
} else := "read"
