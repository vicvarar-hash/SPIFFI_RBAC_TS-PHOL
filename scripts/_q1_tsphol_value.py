"""Q1: TRAC marginal value (beyond RBAC+ABAC), BEFORE vs AFTER, selection + validation.

"Value of TRAC" = what it adds on rows where RBAC+ABAC already ALLOW (the only place
it can change the outcome):
  - incremental security  = # ILLEGIT bundles RBAC+ABAC allow that TRAC DENIES
  - incremental cost       = # LEGIT  bundles RBAC+ABAC allow that TRAC DENIES

BEFORE = the state that generated the logs/paper: 12-rule TRAC + the case-sensitive
ontology (GenericRead blanket-deny) + ABAC with after_hours (backup policies).
AFTER  = shipped: 3-rule TRAC + case-insensitive ontology + ABAC without after_hours.
"""
import os
import sys
import yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services.domain_capability_ontology import (
    DomainCapabilityOntology as O, get_domain_capabilities)
import app.services.domain_capability_ontology as ontmod

BK = "policies/_backup_20260618_130619"
VAL = "datasets/experiment_logs/run_20260613_005419_llm_gpt-4o_validation.json"
SEL = "datasets/experiment_logs/run_20260528_191204_llm_gpt-4o_selection.json"

# Save the real (shipped, case-insensitive) implementations.
_real_hard = O.get_hard_capabilities
_real_fallback = O.infer_minimum_capabilities


def _before_fallback(domain):
    fbs = ontmod._get_ontology().get("domain_fallbacks", {})
    if domain in fbs:                       # case-SENSITIVE (original bug)
        return fbs[domain]
    return {"required": ["GenericRead"], "optional": [], "hard": ["GenericRead"], "soft": []}


def _before_hard(domain, intent):
    di = get_domain_capabilities().get(domain, {})   # case-SENSITIVE
    data = di.get(intent)
    if isinstance(data, dict) and "hard" in data:
        return set(data["hard"])
    if isinstance(data, dict):
        return set(data.get("required", []))
    fb = _before_fallback(domain)
    return set(fb.get("hard", fb.get("required", [])))


def _y(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def value(rows):
    open_rows = [x for x in rows if not x.rbac_deny and not x.abac_deny]
    illeg = [x for x in open_rows if not x.is_legitimate]
    legit = [x for x in open_rows if x.is_legitimate]
    catch = [x for x in illeg if x.tsphol_deny]
    over = [x for x in legit if x.tsphol_deny]
    return len(illeg), len(catch), len(legit), len(over)


def report(tag, rows):
    h = rs.headline(rows)
    ni, nc, nl, no = value(rows)
    print(f"  [{tag}] tsphol-deny {h['tsphol_deny_rate']*100:4.1f}%  | "
          f"of RBAC+ABAC-ALLOW rows: illegit-open={ni} -> TRAC CATCHES {nc} "
          f"({100*nc/max(ni,1):.1f}%)  |  legit-open={nl} -> TRAC OVER-BLOCKS {no} "
          f"({100*no/max(nl,1):.1f}%)")


tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
before_pol = (_y(f"{BK}/rbac.yaml"), _y(f"{BK}/abac_rules.yaml"), _y(f"{BK}/trac_rules.yaml"))

for mode, log in (("VALIDATION", VAL), ("SELECTION", SEL)):
    print(f"\n=== {mode} :: {os.path.basename(log)} ===")
    # BEFORE: case-sensitive ontology + backup (12-rule, after_hours) policies
    O.get_hard_capabilities = staticmethod(_before_hard)
    O.infer_minimum_capabilities = staticmethod(_before_fallback)
    rb, _s, _b = rs.replay_experiment(log, tasks, experiment="E1", policies=before_pol)
    report("BEFORE 12-rule+bug", rb)
    # AFTER: real ontology + shipped policies
    O.get_hard_capabilities = _real_hard
    O.infer_minimum_capabilities = _real_fallback
    ra, _s2, _b2 = rs.replay_experiment(log, tasks, experiment="E1", policies=None)
    report("AFTER  3-rule+fix ", ra)
