"""Ground-truth TRAC trace for specific over-blocked rows, to reconcile the rescue discrepancy.
Computes task_domain exactly as the replay (resolve_required_domain, rbac_universe) then runs the
real engine via transaction_trace and dumps the deciding rule + key predicates + the rescue rel.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.loaders.astra_loader import load_astra_dataset
from app.services.replay_service import (
    _normalize_rows, baseline_policies, _persona_allowed_domains, transaction_trace)
from app.services.task_domain_classifier import resolve_required_domain
from app.services.tool_relevance import bundle_tool_relevance, RESCUE_RELEVANCE, THRESHOLD

RAW = os.path.join("datasets", "llm_inference_logs", "20260613005419_gpt-4o_validation.json")
tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
log = json.load(open(RAW, encoding="utf-8"))
mode = log.get("evaluation_mode") or log.get("mode") or "validation"
rows_in = _normalize_rows(log, "E1", tasks)
pols = baseline_policies()
persona_domains = _persona_allowed_domains(pols[0])
rbac_universe = set().union(*persona_domains.values()) if persona_domains else None

WANT = [("devops_agent", 96), ("devops_agent", 121), ("devops_agent", 37),
        ("devops_agent", 3), ("devops_agent", 8)]


def task_text_of(ti):
    t = tasks[ti]
    return getattr(t, "task", None) or (t["input"]["task"] if isinstance(t, dict) else "")


picked = {}
for r in rows_in:
    key = (r.get("persona"), r.get("task_idx"))
    if key in WANT and r.get("is_legitimate") and key not in picked:
        picked[key] = r

for key in WANT:
    r = picked.get(key)
    if not r:
        print(f"{key}: no legit row found"); continue
    persona, ti = key
    tt = task_text_of(ti)
    tools = r.get("selected_tools") or []
    mcps = r.get("selected_mcps") or []
    td = resolve_required_domain(tt, mcps, allowed=rbac_universe)
    rel = bundle_tool_relevance(tools, tt)
    tr = transaction_trace(persona, ti, tools, mcps, tt, mode, pols,
                           issue_codes=r.get("issue_codes"), task_domain=td)
    P = tr["layers"]["tsphol"]["predicates"]
    print(f"\n=== {persona} · task {ti} ===")
    print(f"  tools={tools}  mcps={mcps[:1]}")
    print(f"  replay task_domain(resolve_required_domain) = {td}")
    print(f"  bundle_tool_relevance = {rel:.3f}   (RESCUE>={RESCUE_RELEVANCE}, THRESH<{THRESHOLD})")
    print(f"  deciding_layer = {tr['deciding_layer']}   tsphol_rule = {tr['layers']['tsphol']['rule']}")
    print(f"  HardCapabilityMissing = {P.get('HardCapabilityMissing')}   "
          f"TaskDomainExpected = {P.get('TaskDomainExpected')}   BundleDomainActual = {P.get('BundleDomainActual')}")
    print(f"  BundleToolsIrrelevant = {P.get('BundleToolsIrrelevant')}   "
          f"MissingHardCapabilities = {P.get('MissingHardCapabilities')}")
