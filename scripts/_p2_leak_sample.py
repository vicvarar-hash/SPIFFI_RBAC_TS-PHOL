"""Sample the same-domain-wrong leaks after the case fix to design intent-specific caps."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services.domain_capability_ontology import (
    DomainCapabilityOntology as O, get_domain_capabilities)
import app.services.domain_capability_ontology as ontmod

LOG = "datasets/experiment_logs/run_20260613_005419_llm_gpt-4o_validation.json"


def _ci_get(d, key):
    if key in d:
        return d[key]
    low = str(key).lower()
    for k in d:
        if str(k).lower() == low:
            return d[k]
    return None


def _ci_fallback(domain):
    fbs = ontmod._get_ontology().get("domain_fallbacks", {})
    hit = _ci_get(fbs, domain)
    return hit if hit is not None else {"hard": ["GenericRead"]}


def _ci_hard(domain, intent):
    di = _ci_get(get_domain_capabilities(), domain) or {}
    data = _ci_get(di, intent)
    if isinstance(data, dict) and "hard" in data:
        return set(data["hard"])
    if isinstance(data, dict):
        return set(data.get("required", []))
    fb = _ci_fallback(domain)
    return set(fb.get("hard", fb.get("required", [])))


O.get_hard_capabilities = staticmethod(_ci_hard)
O.infer_minimum_capabilities = staticmethod(_ci_fallback)

from app.services.experiment_runner import build_engine_from_policies
from app.services.experiment_config import (
    tsphol_production, rbac_production, abac_production,
    registry_production, allowlist_production, PERSONAS)
from app.loaders.mcp_loader import load_mcp_personas

tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
mcp_personas, _ = load_mcp_personas("mcp_servers")
pol = {"registry": registry_production(), "allowlist": allowlist_production(),
       "rbac": rbac_production(), "abac": abac_production(), "tsphol": tsphol_production()}
eng = build_engine_from_policies(pol, mcp_personas)

log = json.load(open(LOG, encoding="utf-8"))
rows = log["experiments"]["E1"]["rows"]

shown = 0
for r in rows:
    if r.get("is_legitimate"):
        continue
    if (r.get("match_tag") or "").lower() != "wrong":
        continue
    persona = r.get("persona")
    if persona not in PERSONAS:
        continue
    ti = r.get("task_idx")
    tools = r.get("selected_tools") or []
    mcps = r.get("selected_mcps") or []
    task = tasks[ti]
    task_text = task.task
    gt = task.groundtruth_tools
    res = rs._eval(eng, persona, tools, mcps, task_text, "validation")
    ctx = res.context
    preds = ctx.get("tsphol_predicate_set", {})
    deny = res.final_decision in ("DENY", "DECEPTION_ROUTED", "BLOCK")
    if deny:
        continue  # only the leaks (allowed)
    intent = preds.get("PrimaryIntent")
    has = sorted(preds.get("HasCapabilities") or [])
    exp_dom = preds.get("TaskDomainExpected")
    act_dom = preds.get("BundleDomainActual")
    mism = preds.get("TaskBundleDomainMismatch")
    hardmiss = preds.get("MissingHardCapabilities")
    print("―" * 78)
    print("TASK:", task_text[:100])
    print("  expected:", exp_dom, "| actual:", act_dom, "| mismatch:", mism, "| intent:", intent)
    print("  GT tools  :", gt)
    print("  candidate :", tools)
    print("  has_caps  :", has)
    print("  HardCapabilityMissing:", preds.get("HardCapabilityMissing"), "| missing:", hardmiss)
    shown += 1
    if shown >= 12:
        break
print("\nshown", shown)
