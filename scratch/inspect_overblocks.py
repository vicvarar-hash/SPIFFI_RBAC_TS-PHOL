"""Reconstruct the actual denied requests behind the 21% admissible over-block, so each TRAC
BM25 denial can be judged by hand: task text, selected tools, real domain vs BM25-inferred domain,
per-domain BM25 scores, and the mean tool-relevance BM25 score.

Admissible = correct AND authorized (is_legitimate AND not rbac_deny AND not abac_deny), taken from
the canonical rows; the BM25 detail is recomputed with the shipped leak-free classifier.
"""
import os
import sys
import json
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.loaders.astra_loader import load_astra_dataset
from app.services.replay_service import _normalize_rows, baseline_policies, _persona_allowed_domains
from app.services.task_domain_classifier import (
    resolve_required_domain, domain_scores, infer_task_domain, topk_domains)
from app.services.tool_relevance import bundle_tool_relevance, THRESHOLD, RESCUE_RELEVANCE
from app.services.normalization import normalize_mcp_name

RAW = os.path.join("datasets", "llm_inference_logs", "20260613005419_gpt-4o_validation.json")
CANON = os.path.join("scratch", "canonical_rows", "val_gpt-4o_r4.json")

tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
log = json.load(open(RAW, encoding="utf-8"))
rows_in = _normalize_rows(log, "E1", tasks)

rbac_pol, _, _ = baseline_policies()
persona_domains = _persona_allowed_domains(rbac_pol)
rbac_universe = set().union(*persona_domains.values()) if persona_domains else None

canon = json.load(open(CANON, encoding="utf-8"))
target = {}
for x in canon:
    if x["is_legitimate"] and not x["rbac_deny"] and not x["abac_deny"] and x["tsphol_deny"]:
        target[(x["persona"], x["task_idx"], x["domain"])] = x["tsphol_rule"]


def task_text_of(ti):
    t = tasks[ti]
    return getattr(t, "task", None) or (t["input"]["task"] if isinstance(t, dict) else "")


detail = []
seen = set()
for r in rows_in:
    k = (r.get("persona"), r.get("task_idx"), r.get("domain"))
    # Match ONLY the legitimate (correct + authorized) bundle — a (persona,task,domain) can also
    # have wrong/null variants with different tool sets; matching those would reconstruct the wrong
    # bundle. The target set is is_legitimate, so require it on the raw row too.
    if k in target and k not in seen and r.get("is_legitimate"):
        seen.add(k)
        ti = r.get("task_idx")
        tt = task_text_of(ti)
        tools = r.get("selected_tools") or []
        mcps = r.get("selected_mcps") or []
        real = [normalize_mcp_name(m) for m in mcps]
        real_set = {d for d in real if d}
        scores = domain_scores(tt, allowed=rbac_universe)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        req = resolve_required_domain(tt, mcps, allowed=rbac_universe)
        rel = bundle_tool_relevance(tools, tt)
        # Reproduce the rule locally (priority: capability_coverage 105 > tool_relevance 95):
        rescued = rel is not None and rel >= RESCUE_RELEVANCE
        hard_missing = (req not in ("uncertain", None)) and (req not in real_set) and not rescued
        toolrel_deny = rel is not None and rel < THRESHOLD
        if hard_missing:
            repro = "capability_coverage"
        elif toolrel_deny:
            repro = "tool_relevance"
        else:
            repro = "ALLOW(!)"
        detail.append(dict(
            persona=r.get("persona"), task_idx=ti, rule=target[k], repro=repro,
            match=r.get("match_tag"), real_domain=real,
            inferred=req, top1=infer_task_domain(tt, allowed=rbac_universe),
            top_scores=ranked[:4], rel=rel,
            n_tools=len(tools), tools=tools, task=tt))

print(f"targets in canonical: {len(target)}   reconstructed: {len(detail)}")
print("by canonical rule:", dict(collections.Counter(d["rule"] for d in detail)))
mismatch = [d for d in detail if d["rule"] != d["repro"]]
print(f"reproduction mismatches (repro != canonical rule): {len(mismatch)}")
for d in mismatch[:8]:
    print(f"   MISMATCH {d['persona']}/{d['task_idx']} canon={d['rule']} repro={d['repro']} "
          f"rel={d['rel']} inferred={d['inferred']} real={d['real_domain'][:1]} match={d['match']}")
print(f"tool_relevance THRESHOLD = {THRESHOLD}   RESCUE_RELEVANCE = {RESCUE_RELEVANCE}\n")


def show(rule, n):
    sub = [d for d in detail if d["rule"] == rule]
    print("=" * 100)
    print(f"{rule}: {len(sub)} denials — showing {min(n, len(sub))}")
    print("=" * 100)
    for d in sub[:n]:
        print(f"\n[{d['persona']} · task {d['task_idx']}]  real_domain={d['real_domain']}  "
              f"inferred={d['inferred']}  (top1={d['top1']})  match_tag={d['match']}")
        rel = d["rel"]
        print(f"  tool_rel(mean BM25)={rel:.3f}  {'< THRESH -> IRRELEVANT' if rel is not None and rel < THRESHOLD else ''}")
        print(f"  BM25 domain scores (top4): {[(dm, round(s,2)) for dm,s in d['top_scores']]}")
        print(f"  tools ({d['n_tools']}): {d['tools']}")
        print(f"  TASK: {d['task'][:320]}")


show("capability_coverage", 10)
show("tool_relevance", 10)

json.dump(detail, open(os.path.join("scratch", "overblock_detail.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("\nsaved -> scratch/overblock_detail.json")
