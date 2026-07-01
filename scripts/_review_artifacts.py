"""Review: do the Domain Catalog, Capability Ontology, and Heuristic add value to the 3-rule TRAC?

(A) Tool-classification source distribution over ALL ASTRA tools -> heuristic/catalog value.
(B) Ontology intent-match rate: does get_hard_capabilities hit an intent-specific entry or the
    per-domain fallback? -> is the per-intent ontology granularity used?
(C) capability_implications impact: does expand_capabilities ever flip HardCapabilityMissing?
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter
from app.loaders.astra_loader import load_astra_dataset
from app.services.tool_classifier import ToolClassifier
from app.services.domain_capability_ontology import (
    DomainCapabilityOntology as O, get_domain_capabilities, _get_ontology)

tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))

# All unique tools that appear anywhere (candidate or ground truth).
tools = set()
for t in tasks:
    tools.update(t.candidate_tools or [])
    tools.update(t.groundtruth_tools or [])
tools = sorted(tools)

# (A) source distribution
tc = ToolClassifier()
src = Counter()
cap_src = Counter()
examples = {}
for d in tc.classify_tools(tools):
    src[d["source"]] += 1
    examples.setdefault(d["source"], d["tool"])
print(f"(A) {len(tools)} unique ASTRA tools — classification source:")
for s, n in src.most_common():
    print(f"   {n:4d}  {s:28s} e.g. {examples[s]}")

# (B) ontology intent-match: for every (domain,intent) in the catalog, is it a real entry?
dc = get_domain_capabilities()
print("\n(B) ontology per-domain intents (do tasks' intents match these?):")
for dom, intents in dc.items():
    print(f"   {dom:12s} intents={list(intents.keys())}  fallback={_get_ontology()['domain_fallbacks'].get(dom,{}).get('hard')}")

# (C) implication impact: for each domain fallback hard cap, can a *concrete* tool cap satisfy
# it WITHOUT implications? i.e. is the implication graph load-bearing for coverage?
impl = O.get_capability_implications()
print(f"\n(C) capability_implications: {len(impl)} rules. Checking if any domain hard-cap can ONLY")
print("    be satisfied via an implication (vs a direct concrete tool cap):")
# Build tool->caps for all tools, expanded vs raw
from app.services.capability_mapper import CapabilityMapper
cm = CapabilityMapper()
raw_caps_all = set()
for d in tc.classify_tools(tools):
    raw_caps_all.update(d["capabilities"])
expanded_all = O.expand_capabilities(raw_caps_all)
implied_only = expanded_all - raw_caps_all
print(f"    raw tool caps={len(raw_caps_all)}, after expand={len(expanded_all)}, implied-only={sorted(implied_only)}")
# Which domain hard caps are in implied-only (i.e. need implications to be covered)?
hard_caps_used = set()
for dom, intents in dc.items():
    fb = _get_ontology()['domain_fallbacks'].get(dom, {})
    hard_caps_used.update(fb.get('hard', []))
    for data in intents.values():
        hard_caps_used.update(data.get('hard', []) if isinstance(data, dict) else [])
need_impl = hard_caps_used & implied_only
print(f"    domain hard caps that are ONLY reachable via implication: {sorted(need_impl) or 'NONE'}")
