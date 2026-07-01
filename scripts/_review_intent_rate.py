"""Measure: how often does get_hard_capabilities return an intent-specific hard cap
that DIFFERS from the per-domain fallback? (If rarely -> collapse ontology to 1 cap/domain.)"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter
from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services.domain_capability_ontology import (
    DomainCapabilityOntology as O, _get_ontology)

_real = O.get_hard_capabilities
tally = Counter()


def _instrumented(domain, intent):
    res = _real(domain, intent)
    fb = _get_ontology()["domain_fallbacks"]
    fbhard = None
    for k, v in fb.items():
        if str(k).lower() == str(domain).lower():
            fbhard = set(v.get("hard", v.get("required", [])))
            break
    if fbhard is None:
        tally["unknown_domain"] += 1
    elif res == fbhard:
        tally["fallback (per-domain)"] += 1
    else:
        tally["intent-specific (differs)"] += 1
        pairs[f"{domain}/{intent} -> {sorted(res)}"] += 1
    return res


pairs = Counter()
O.get_hard_capabilities = staticmethod(_instrumented)

tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
log = "datasets/experiment_logs/run_20260613_005419_llm_gpt-4o_validation.json"
rs.replay_experiment(log, tasks, experiment="E1", limit=2000)

total = sum(tally.values())
print(f"get_hard_capabilities calls (n={total}):")
for k, n in tally.most_common():
    print(f"   {n:5d} ({100*n/max(total,1):.1f}%)  {k}")
print("\nintent-specific overrides that actually FIRE-and-DIFFER:")
for k, n in pairs.most_common():
    print(f"   {n:5d}  {k}")
