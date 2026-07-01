"""
Post-Experiment Lab — deterministic replay engine.

Re-runs the governance deny-gates (RBAC / ABAC / TRAC) over the bundles
recorded in a saved experiment log, WITHOUT any new LLM inference.

Core idea
---------
Each deny-gate is evaluated INDEPENDENTLY (the other gates set to "open"), so the
decision of any layer-subset equals the OR of the included layers' independent
denies. Short-circuit ordering changes only *attribution*, not the allow/deny
outcome. This makes per-layer attribution, Shapley values, and ablations exact
and instant (set algebra over cached booleans).

Validation-mode caveat
----------------------
The two TRAC rules that read the LLM's ``issue_codes``
(``validation_failure_denial``, ``bundle_irrelevant_strong``) cannot be replayed
because issue_codes are not persisted in the row logs. We pass ``issue_codes=[]``
and report fidelity vs. the logged decision so the gap is explicit and measured.
"""

from __future__ import annotations

import os
import glob
import json
from dataclasses import dataclass, asdict, field
from typing import Callable, Dict, List, Optional, Tuple

from app.services.experiment_config import (
    ExperimentConfig, PERSONAS, LEGITIMATE_PAIRINGS, LEGITIMATE_PAIRINGS_NORMALIZED,
    registry_production, allowlist_production,
    rbac_production, abac_production, tsphol_production,
    rbac_open, abac_open, tsphol_open,
)
from app.services.experiment_runner import build_engine_from_policies, cleanup_engine
from app.services.normalization import normalize_mcp_name
from app.loaders.mcp_loader import load_mcp_personas

LOG_DIR = os.path.join("datasets", "experiment_logs")
LLM_INFERENCE_DIR = os.path.join("datasets", "llm_inference_logs")
DENY_STATES = {"DENY", "DECEPTION_ROUTED"}

# Isolated single-layer configurations (the other deny-gates are "open").
ISOLATED_FNS: Dict[str, dict] = {
    "rbac":   dict(rbac_fn="production", abac_fn="open", tsphol_fn="open"),
    "abac":   dict(rbac_fn="open", abac_fn="production", tsphol_fn="open"),
    "tsphol": dict(rbac_fn="open", abac_fn="open", tsphol_fn="production"),
}


def baseline_policies() -> Tuple[dict, dict, dict]:
    """The original (rbac, abac, tsphol) production policy dicts."""
    return (rbac_production(), abac_production(), tsphol_production())


def _persona_allowed_domains(rbac_pol: dict) -> Dict[str, set]:
    """spiffe_id → set of RBAC-entitled (normalized) MCP domains, from the RBAC policy.

    This is a legitimate, non-gold deployment binding (which domains an identity may use), used to
    scope leak-free domain inference — *not* derived from any ground-truth answer.
    """
    out: Dict[str, set] = {}
    for pol in (rbac_pol or {}).get("policies", []):
        allowed = {normalize_mcp_name(r["mcp"]) for r in pol.get("rules", [])
                   if r.get("action") == "allow" and r.get("mcp") not in ("*", None)}
        out[pol.get("spiffe_id")] = allowed
    return out


def _engines_from_policies(mcp_personas, rbac_policy: dict, abac_policy: dict,
                           tsphol_policy: dict) -> Dict[str, object]:
    """Build the 3 isolated single-layer engines from explicit policy dicts.

    Each engine activates exactly one deny-gate (the supplied policy) and leaves
    the other two 'open', so the engine's decision == that layer's independent
    verdict — for original *or* edited policies.
    """
    reg, allow = registry_production(), allowlist_production()

    def _set(r, a, t):
        return {"registry": reg, "allowlist": allow, "rbac": r, "abac": a, "tsphol": t}

    return {
        "rbac":   build_engine_from_policies(_set(rbac_policy, abac_open(), tsphol_open()), mcp_personas),
        "abac":   build_engine_from_policies(_set(rbac_open(), abac_policy, tsphol_open()), mcp_personas),
        "tsphol": build_engine_from_policies(_set(rbac_open(), abac_open(), tsphol_policy), mcp_personas),
    }


def _layer_firing(res, layer: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract (matched_rule, reason) for a denied isolated-layer result."""
    if res.final_decision not in DENY_STATES:
        return (None, None)
    ctx = res.context or {}
    if layer == "rbac":
        ev = ctx.get("rbac_evaluation") or {}
        # The engine stamps a generic "multi_tool_audit" label; the *actual* denying
        # policies (e.g. default_deny, or a named deny rule) are per-tool in rbac_trace.
        denying = []
        for t in ev.get("rbac_trace", []):
            if t.get("decision") in DENY_STATES and t.get("policy") not in denying:
                denying.append(t.get("policy"))
        rule = "+".join(p for p in denying if p) or ev.get("matched_rule")
        return (rule, ev.get("reason") or res.reason)
    if layer == "abac":
        ev = ctx.get("abac_baseline") or {}
        return (ev.get("matched_rule"), res.reason)
    if layer == "tsphol":
        return (_decider_rule(ctx.get("tsphol_logic_trace", [])), res.reason)
    return (None, None)



def list_run_logs(log_dir: str = LOG_DIR, include_legacy: bool = False) -> List[dict]:
    """Enumerate replayable ``llm_inference_v1`` logs with light metadata.

    By default only the LLM Lab's new-format logs (under
    ``datasets/llm_inference_logs``) are listed — every legacy run has an
    identical migrated twin there, so the old ``experiments[E1..E4]`` logs are
    hidden to keep the selector clean. Pass ``include_legacy=True`` to also
    surface the untouched legacy logs under ``datasets/experiment_logs``.
    """
    out = []
    for p in sorted(glob.glob(os.path.join(LLM_INFERENCE_DIR, "*.json")), reverse=True):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if not isinstance(d, dict) or d.get("schema") != "llm_inference_v1":
            continue
        ra = d.get("retrieval") or {}
        out.append({
            "path": p,
            "name": os.path.basename(p),
            "model": d.get("model"),
            "mode": d.get("mode"),
            "experiments": ["E1"],  # synthetic: the new format has no E1..E4 ablations
            "ra_icl": ra.get("strategy") not in (None, "none", ""),
            "schema": "llm_inference_v1",
        })
    if not include_legacy:
        return out
    for p in sorted(glob.glob(os.path.join(log_dir, "*.json")), reverse=True):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if not isinstance(d, dict) or "experiments" not in d:
            continue
        ra = d.get("ra_icl")
        out.append({
            "path": p,
            "name": os.path.basename(p),
            "model": d.get("llm_model"),
            "mode": d.get("evaluation_mode"),
            "experiments": list(d["experiments"].keys()),
            "ra_icl": bool(ra.get("enabled")) if isinstance(ra, dict) else False,
            "schema": "experiments_v0",
        })
    return out


def _build_engines(mcp_personas) -> Dict[str, object]:
    engines = {}
    for layer, fns in ISOLATED_FNS.items():
        cfg = ExperimentConfig(layer, layer, "", **fns)
        engines[layer] = build_engine_from_policies(cfg.get_policies(), mcp_personas)
    return engines


def _release_engines(engines: Dict[str, object]) -> None:
    for e in engines.values():
        try:
            cleanup_engine(e)
        except Exception:
            pass


@dataclass
class RowReplay:
    persona: str
    task_idx: int
    domain: str
    match_tag: str
    is_legitimate: bool
    # independent per-layer denies
    rbac_deny: bool
    abac_deny: bool
    tsphol_deny: bool
    tsphol_rule: Optional[str]
    # ground-truth (from the log) for fidelity
    logged_final_deny: bool
    # bundle signature → key into the predicate cache (for instant re-evaluation)
    sig: str = ""
    # per-layer firing rule + reason (for the comparison + transaction drill-down)
    rbac_rule: Optional[str] = None
    rbac_reason: Optional[str] = None
    abac_rule: Optional[str] = None
    abac_reason: Optional[str] = None
    tsphol_reason: Optional[str] = None
    # cached TRAC facts (for editing / analysis)
    alignment: float = 0.0
    cap_coverage: float = 0.0
    hard_missing: bool = False
    domain_mismatch: bool = False
    contains_write: bool = False
    contains_read: bool = False
    multi_domain: bool = False
    # Assurance advisories: TRAC rules that fired as advisory (alert, not block).
    tsphol_advisory: bool = False
    tsphol_advisory_rule: Optional[str] = None
    tsphol_advisory_rules: List[str] = field(default_factory=list)
    read_intent_mutating: bool = False
    # LLM verdict — validation mode only: True/False = the model judged the bundle
    # valid/invalid (it acts as a gate). None in selection mode (the model is the
    # requester that produced the bundle, not a judge).
    llm_valid: Optional[bool] = None


# Predicate keys the TRAC rules actually read (cached per bundle for re-eval).
_PRED_KEYS = (
    "TaskBundleDomainMismatch", "SelectionToleranceActive", "CriticalValidationFailure",
    "TaskAlignmentScore", "AlignmentEvaluated", "BundleIrrelevantToTask",
    "HardCapabilityMissing", "MissingHardCapabilities", "ContainsDelete", "ContainsRead",
    "ContainsWrite", "ContainsReadBeforeWrite", "HighestRiskLevel", "MultiDomain",
    "CapabilityCoverageScore", "ReadIntentMutatingBundle", "BundleToolsIrrelevant",
)


def _sig(tools, mcps) -> str:
    return "|".join(sorted(tools)) + "##" + "|".join(sorted(mcps))


def _after_hours_flag(task_text: str, spiffe_id: str) -> bool:
    """Replicate the engine's deterministic synthetic-hour `after_hours` env attr.

    Mirrors decision_engine.py: sha256(task_text[:80]+spiffe) % 24, after-hours if
    the pseudo-hour is <6 or >=20. The only task-dependent input to ABAC, so keying
    the ABAC memo on it (rather than the whole task) keeps the replay both correct
    and well-memoized.
    """
    import hashlib
    h = int(hashlib.sha256((task_text[:80] + spiffe_id).encode()).hexdigest()[:4], 16) % 24
    return h < 6 or h >= 20


def _extract_pred_cache(P: dict, components: dict, mode: str) -> dict:
    cache = {}
    for k in _PRED_KEYS:
        v = P.get(k)
        if isinstance(v, set):
            v = list(v)
        cache[k] = v
    cache["mode"] = mode
    # alignment components, so the (0.4,0.4,0.2) weights can be re-tuned instantly
    cache["_domain_score"] = float((components or {}).get("domain_score", 0.0) or 0.0)
    cache["_capability_score"] = float((components or {}).get("capability_score", 0.0) or 0.0)
    cache["_semantic_score"] = float((components or {}).get("semantic_score", 0.0) or 0.0)
    return cache


def _decider_rule(trace: List[dict]) -> Optional[str]:
    for t in trace:
        if t.get("triggered") and str(t.get("action", "")).upper() == "DENY":
            return t.get("rule")
    return None


def _eval(engine, persona_key: str, tools: List[str], mcps: List[str],
          task_text: str, mode: str, issue_codes: Optional[List[str]] = None,
          task_domain: Optional[str] = None):
    spiffe = PERSONAS[persona_key]["spiffe_id"]
    # The TRAC capability check is agnostic and keys on the TASK's declared domain
    # (the MCP scope the agent is given), not the candidate's own MCP. Fall back to the
    # bundle's MCP only when the task domain is unknown.
    scope = task_domain or (mcps[0] if mcps else "All")
    llm_out = {
        "_mode": mode, "issue_codes": list(issue_codes or []), "is_valid": True,
        "selected_tools": tools, "selected_mcps": mcps,
        "expected_domain": normalize_mcp_name(scope) if scope and scope != "All" else "uncertain",
        "id_source": "Replay",
    }
    pre = engine.pre_llm_check(spiffe, mcps, tools)
    return engine.evaluate(
        pre_llm_result=pre, caller_spiffe_id=spiffe, mcps=mcps, tools=tools,
        llm_outputs=llm_out, task_text=task_text, mode=mode, mcp_filter=scope,
    )


def _normalize_rows(log: dict, experiment: str, tasks: list) -> List[dict]:
    """Per-(task, persona) row dicts for BOTH log formats, so the replay loop is
    format-agnostic.

    * Old format: ``experiments[E1].rows`` — already per task×persona (LLM output +
      the original governance decision).
    * New ``llm_inference_v1``: per-task LLM output only; fan it out across every
      persona and recompute ``is_legitimate`` (= the task's candidate domain is
      authorised for the persona AND match_tag == "correct"). There is no logged
      governance decision — the deterministic stack is re-derived here in full.
    """
    if log.get("schema") == "llm_inference_v1":
        rows: List[dict] = []
        for t in log.get("tasks", []):
            ti = t.get("task_idx")
            task = tasks[ti] if (ti is not None and ti < len(tasks)) else None
            mtag = t.get("match_tag")
            if mtag is None and task is not None:
                mtag = getattr(task, "match_tag", "null")
            cand_mcp = getattr(task, "candidate_mcp", None) if task is not None else None
            tdom = normalize_mcp_name(cand_mcp[0]) if cand_mcp else "unknown"
            for persona in PERSONAS:
                legit = (tdom in LEGITIMATE_PAIRINGS_NORMALIZED.get(persona, set())) and mtag == "correct"
                rows.append({
                    "persona": persona, "task_idx": ti,
                    "selected_tools": t.get("selected_tools") or [],
                    "selected_mcps": t.get("selected_mcps") or [],
                    "issue_codes": t.get("issue_codes"),
                    "is_valid": t.get("is_valid"),
                    "is_legitimate": legit, "match_tag": mtag, "domain": tdom,
                    "llm_failed": bool(t.get("llm_failed")),
                    "_no_logged": True,  # no governance decision recorded in this format
                })
        return rows
    return log["experiments"][experiment]["rows"]


def _sample_rows(rows_in: List[dict], limit: Optional[int]) -> List[dict]:
    """Pick a representative ``limit``-row subset, deterministically.

    The ASTRA dataset is ordered correct -> wrong -> null, and rows are grouped by
    task, so a naive ``rows_in[:limit]`` prefix only ever sees the first (all-correct)
    tasks. Instead we **stratify by match_tag**: whole tasks (all personas) are kept,
    allocated across correct/wrong/null in proportion to the dataset, and picked
    evenly-spaced within each class so the sample spans the entire range. The result
    is deterministic (identical for the baseline and modified passes) and ~``limit``
    rows (rounded to whole tasks).
    """
    if not limit or limit >= len(rows_in):
        return rows_in

    from collections import OrderedDict, defaultdict
    by_task: "OrderedDict[object, List[dict]]" = OrderedDict()
    for r in rows_in:
        by_task.setdefault(r.get("task_idx"), []).append(r)
    tasks = list(by_task.items())
    if len(tasks) <= 1:
        return rows_in[:limit]

    rows_per_task = max(1, round(len(rows_in) / len(tasks)))  # ~= number of personas
    n_tasks = max(1, min(len(tasks), round(limit / rows_per_task)))

    groups: "defaultdict[str, List]" = defaultdict(list)
    for ti, grp in tasks:
        groups[grp[0].get("match_tag") or "null"].append((ti, grp))

    # Largest-remainder proportional allocation of n_tasks across match_tag classes.
    total = len(tasks)
    alloc, remainders, assigned = {}, [], 0
    for tag, items in groups.items():
        exact = n_tasks * len(items) / total
        alloc[tag] = int(exact)
        assigned += alloc[tag]
        remainders.append((exact - int(exact), tag))
    for _, tag in sorted(remainders, reverse=True)[:max(0, n_tasks - assigned)]:
        alloc[tag] += 1

    selected = []
    for tag, items in groups.items():
        k = min(alloc.get(tag, 0), len(items))
        if k <= 0:
            continue
        if k == len(items):
            picks = items
        else:
            step = len(items) / k  # evenly spaced across the whole class
            picks = [items[int(i * step)] for i in range(k)]
        selected.extend(picks)

    selected.sort(key=lambda x: (x[0] is None, x[0]))  # stable by task_idx
    out: List[dict] = []
    for _ti, grp in selected:
        out.extend(grp)
    return out


def replay_experiment(
    log_path: str,
    tasks: list,
    experiment: str = "E1",
    mcp_personas=None,
    limit: Optional[int] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    policies: Optional[Tuple[dict, dict, dict]] = None,
    domain_source: str = "inferred",
) -> Tuple[List[RowReplay], dict, Dict[str, dict]]:
    """Replay one experiment's rows through the 3 isolated deny-gates.

    ``policies`` is an optional ``(rbac, abac, tsphol)`` tuple of policy dicts; when
    omitted the original production policies are used (the *baseline* picture). Pass
    edited dicts for the *modified* picture.

    ``domain_source`` selects how TRAC's ``expected_domain`` (the task's required domain) is set.
    Default ``"inferred"`` derives it from the task text alone via BM25 over the MCP tool catalog —
    leak-free (``d_inf``), **zero ground truth**. ``"gold"`` (the disclosed ``d_exp`` oracle proxy,
    ``gt_mcps[0]``) is retained only for offline diagnostics/the paper's optimistic ceiling and is
    never selected by the app.

    Returns (rows, summary, bundle_cache). ``summary`` includes the fidelity of
    the reconstructed full-stack decision vs. the logged decision.
    """
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    mode = log.get("evaluation_mode") or log.get("mode") or "validation"
    rows_in = _normalize_rows(log, experiment, tasks)
    rows_in = _sample_rows(rows_in, limit)

    if mcp_personas is None:
        mcp_personas, _ = load_mcp_personas("mcp_servers")
    rbac_pol, abac_pol, tsphol_pol = policies if policies is not None else baseline_policies()
    engines = _engines_from_policies(mcp_personas, rbac_pol, abac_pol, tsphol_pol)
    # For leak-free inference: spiffe_id -> RBAC-entitled domain set (a legitimate, non-gold
    # deployment binding). The union is the deployment's MCP universe — used to scope the BM25
    # classifier to the MCPs this deployment actually serves (agnostic; never the gold answer).
    persona_domains = (_persona_allowed_domains(rbac_pol)
                       if domain_source in ("inferred", "inferred_scoped") else None)
    rbac_universe = set().union(*persona_domains.values()) if persona_domains else None

    # Memo caches keyed by the actual inputs each layer depends on.
    memo_rbac: Dict[tuple, tuple] = {}
    memo_abac: Dict[tuple, tuple] = {}
    memo_tsphol: Dict[str, tuple] = {}
    bundle_cache: Dict[str, dict] = {}
    has_stored_codes = any("issue_codes" in r for r in rows_in)

    out: List[RowReplay] = []
    total = len(rows_in)
    try:
        for i, r in enumerate(rows_in):
            if r.get("final_decision") == "LLM_FAILED" or r.get("llm_failed"):
                continue
            persona = r.get("persona")
            if persona not in PERSONAS:
                continue
            ti = r.get("task_idx")
            tools = r.get("selected_tools") or []
            mcps = r.get("selected_mcps") or []
            task = tasks[ti]
            task_text = task["input"]["task"] if isinstance(task, dict) else getattr(task, "task", "")
            # Agnostic TRAC keys on the TASK's declared domain. ``domain_source`` chooses the
            # source: "gold" = gt_mcps[0] (the disclosed d_exp oracle proxy); "inferred" = derived
            # from the task text alone (leakage-free d_inf), with the candidate's MCP as a last
            # resort only when gold is requested but absent.
            gt_mcp = getattr(task, "groundtruth_mcp", None)
            if gt_mcp is None and isinstance(task, dict):
                gt_mcp = (task.get("groundtruth") or {}).get("mcp_servers") \
                    or (task.get("expected_output") or {}).get("mcp_servers")
            if domain_source == "inferred":
                from app.services.task_domain_classifier import resolve_required_domain
                # scope to the deployment's MCP universe (auto-derived from RBAC), not the gold answer
                task_domain = resolve_required_domain(task_text, mcps, allowed=rbac_universe)
            elif domain_source == "inferred_scoped":
                from app.services.task_domain_classifier import resolve_required_domain
                sp = PERSONAS.get(persona, {}).get("spiffe_id")
                allowed = persona_domains.get(sp) if persona_domains else None
                task_domain = resolve_required_domain(task_text, mcps, allowed=allowed)
            else:
                task_domain = normalize_mcp_name(gt_mcp[0]) if gt_mcp else (mcps[0] if mcps else None)

            sig = _sig(tools, mcps)
            # RBAC depends on (persona, bundle). ABAC also depends on the synthetic
            # `after_hours` env attr (hashed from task_text+identity), the only
            # task-dependent ABAC input — so key ABAC on (persona, bundle, after_hours)
            # to stay correct *and* memoized. TRAC facts depend on (task, bundle).
            ckey = f"{ti}@@{sig}"
            rbac_key = (persona, sig)
            abac_key = (persona, sig, _after_hours_flag(task_text, PERSONAS[persona]["spiffe_id"]))
            issue_codes = r.get("issue_codes")  # list on new logs, None on old logs

            if rbac_key in memo_rbac:
                rbac_deny, rbac_rule, rbac_reason = memo_rbac[rbac_key]
            else:
                rres = _eval(engines["rbac"], persona, tools, mcps, task_text, mode)
                rbac_deny = rres.final_decision in DENY_STATES
                rbac_rule, rbac_reason = _layer_firing(rres, "rbac")
                memo_rbac[rbac_key] = (rbac_deny, rbac_rule, rbac_reason)
            if abac_key in memo_abac:
                abac_deny, abac_rule, abac_reason = memo_abac[abac_key]
            else:
                ares = _eval(engines["abac"], persona, tools, mcps, task_text, mode)
                abac_deny = ares.final_decision in DENY_STATES
                abac_rule, abac_reason = _layer_firing(ares, "abac")
                memo_abac[abac_key] = (abac_deny, abac_rule, abac_reason)

            if ckey in memo_tsphol:
                tsphol_deny, rule, treason, facts = memo_tsphol[ckey]
            else:
                res = _eval(engines["tsphol"], persona, tools, mcps, task_text, mode,
                            issue_codes=issue_codes, task_domain=task_domain)
                ctx = res.context
                P = ctx.get("tsphol_predicate_set", {})
                tsphol_deny = res.final_decision in DENY_STATES
                rule, treason = _layer_firing(res, "tsphol")
                advisories = [t.get("rule") for t in ctx.get("tsphol_logic_trace", [])
                              if t.get("advisory")]
                facts = {
                    "alignment": float(P.get("TaskAlignmentScore", 0.0) or 0.0),
                    "cap_coverage": float(P.get("CapabilityCoverageScore", 0.0) or 0.0),
                    "hard_missing": bool(P.get("HardCapabilityMissing", False)),
                    "domain_mismatch": bool(P.get("TaskBundleDomainMismatch", False)),
                    "contains_write": bool(P.get("ContainsWrite", False)),
                    "contains_read": bool(P.get("ContainsRead", False)),
                    "multi_domain": bool(P.get("MultiDomain", False)),
                    "read_intent_mutating": bool(P.get("ReadIntentMutatingBundle", False)),
                    "tsphol_advisory": bool(advisories),
                    "tsphol_advisory_rule": advisories[0] if advisories else None,
                    "tsphol_advisory_rules": advisories,
                }
                memo_tsphol[ckey] = (tsphol_deny, rule, treason, facts)
                bundle_cache[ckey] = _extract_pred_cache(P, ctx.get("alignment_components", {}), mode)

            full_deny = rbac_deny or abac_deny or tsphol_deny
            out.append(RowReplay(
                persona=persona, task_idx=ti, domain=r.get("domain", ""),
                match_tag=r.get("match_tag", "null"),
                is_legitimate=bool(r.get("is_legitimate")),
                rbac_deny=rbac_deny, abac_deny=abac_deny, tsphol_deny=tsphol_deny,
                tsphol_rule=rule, sig=ckey,
                rbac_rule=rbac_rule, rbac_reason=rbac_reason,
                abac_rule=abac_rule, abac_reason=abac_reason, tsphol_reason=treason,
                logged_final_deny=(full_deny if r.get("_no_logged")
                                   else (r.get("final_decision") in DENY_STATES)),
                llm_valid=r.get("is_valid"),
                **facts,
            ))
            if progress_cb and (i % 200 == 0 or i == total - 1):
                progress_cb(i + 1, total)
    finally:
        _release_engines(engines)

    # Fidelity: reconstructed full-stack (rbac OR abac OR tsphol) vs logged.
    n = len(out)
    match = sum(1 for x in out if (x.rbac_deny or x.abac_deny or x.tsphol_deny) == x.logged_final_deny)

    # Exact TRAC fidelity diagnostic for VALIDATION logs without stored codes:
    # E3 is TRAC-only (RBAC/ABAC open), so its logged decision is the exact
    # isolated TRAC verdict (incl. the 2 issue-code rules). Compare our
    # recomputed tsphol_deny against it to bound the unstored-issue_codes gap.
    tsphol_anchor_agree = None
    tsphol_source = "stored_issue_codes" if has_stored_codes else "recomputed (issue_codes=[])"
    if not has_stored_codes and mode == "validation" and "E3" in log.get("experiments", {}):
        e3_anchor = {(rr.get("persona"), rr.get("task_idx")): (rr.get("final_decision") in DENY_STATES)
                     for rr in log["experiments"]["E3"]["rows"]}
        comp = [(x.tsphol_deny, e3_anchor.get((x.persona, x.task_idx)))
                for x in out if (x.persona, x.task_idx) in e3_anchor]
        if comp:
            tsphol_anchor_agree = sum(1 for a, b in comp if a == b) / len(comp)

    summary = {
        "log": os.path.basename(log_path),
        "experiment": experiment,
        "mode": mode,
        "n_rows": n,
        "fidelity": (match / n) if n else 0.0,
        "memo_tsphol_unique": len(memo_tsphol),
        "tsphol_source": tsphol_source,
        "tsphol_anchor_agreement": tsphol_anchor_agree,
    }
    return out, summary, bundle_cache


# ──────────────────────────────────────────────────────────────────────────
# Pure analytics over a replayed row set (no engine; instant)
# ──────────────────────────────────────────────────────────────────────────

_LAYERS = ("rbac", "abac", "tsphol")


def _deny(x: RowReplay, layer: str) -> bool:
    return getattr(x, f"{layer}_deny")


def subset_deny(x: RowReplay, active: Tuple[str, ...]) -> bool:
    """Stack decision for a layer subset = OR of the active layers' independent denies."""
    return any(_deny(x, l) for l in active)


def layer_rates(rows: List[RowReplay]) -> Dict[str, float]:
    n = len(rows) or 1
    return {l: sum(1 for x in rows if _deny(x, l)) / n for l in _LAYERS}


def secfail_legit(rows: List[RowReplay], active: Tuple[str, ...]) -> Dict[str, float]:
    """SecFail and legitimate-allow for a given active-layer subset."""
    illeg = [x for x in rows if not x.is_legitimate]
    legit = [x for x in rows if x.is_legitimate]
    fn = sum(1 for x in illeg if not subset_deny(x, active))     # illegit allowed
    la = sum(1 for x in legit if not subset_deny(x, active))     # legit allowed
    return {
        "secfail": fn / len(illeg) if illeg else 0.0,
        "legit_allow": la / len(legit) if legit else 0.0,
        "n_illegit": len(illeg), "n_legit": len(legit),
    }


def shapley(rows: List[RowReplay]) -> Dict[str, float]:
    """Exact Shapley value of each layer w.r.t. SecFail *reduction* (baseline = no layers)."""
    from itertools import permutations
    base = secfail_legit(rows, ())["secfail"]

    def sf(active):
        return secfail_legit(rows, tuple(active))["secfail"]

    contrib = {l: 0.0 for l in _LAYERS}
    perms = list(permutations(_LAYERS))
    for perm in perms:
        active: List[str] = []
        prev = base
        for l in perm:
            active.append(l)
            cur = sf(active)
            contrib[l] += (prev - cur)   # SecFail reduction this layer added
            prev = cur
    return {l: contrib[l] / len(perms) for l in _LAYERS}


def money_metric(rows: List[RowReplay]) -> Dict[str, float]:
    """Value of TRAC *on top of* RBAC+ABAC: incremental catch vs incremental cost."""
    both_allow = [x for x in rows if not x.rbac_deny and not x.abac_deny]
    illeg = [x for x in both_allow if not x.is_legitimate]
    legit = [x for x in both_allow if x.is_legitimate]
    catch = sum(1 for x in illeg if x.tsphol_deny)
    block = sum(1 for x in legit if x.tsphol_deny)
    return {
        "illeg_through_rbac_abac": len(illeg),
        "tsphol_catch": catch,
        "tsphol_catch_rate": catch / len(illeg) if illeg else 0.0,
        "legit_through_rbac_abac": len(legit),
        "tsphol_block": block,
        "tsphol_block_rate": block / len(legit) if legit else 0.0,
    }


def region_counts(rows: List[RowReplay], only: str = "illegit") -> Dict[str, int]:
    """UpSet-style counts of which layer-combo denies each row (on illegit or legit subset)."""
    if only == "illegit":
        sub = [x for x in rows if not x.is_legitimate]
    elif only == "legit":
        sub = [x for x in rows if x.is_legitimate]
    else:
        sub = rows
    regions: Dict[str, int] = {}
    for x in sub:
        key = "+".join(l.upper() for l in _LAYERS if _deny(x, l)) or "(allowed)"
        regions[key] = regions.get(key, 0) + 1
    return dict(sorted(regions.items(), key=lambda kv: -kv[1]))


def per_rule_firing(rows: List[RowReplay]) -> Dict[str, int]:
    c: Dict[str, int] = {}
    for x in rows:
        if x.tsphol_deny:
            c[x.tsphol_rule or "(unknown)"] = c.get(x.tsphol_rule or "(unknown)", 0) + 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


# ──────────────────────────────────────────────────────────────────────────
# v2 — Before/After comparison + per-layer firing + transaction drill-down
# ──────────────────────────────────────────────────────────────────────────

_LAYER_RULE = {"rbac": "rbac_rule", "abac": "abac_rule", "tsphol": "tsphol_rule"}


def full_stack(x: RowReplay) -> dict:
    """Short-circuit full-stack outcome from the independent layer denies.

    Pipeline order RBAC -> ABAC -> TRAC: the first layer that denies is the
    deciding layer (matches the production engine's attribution).
    """
    for layer in _LAYERS:
        if _deny(x, layer):
            return {"decision": "DENY",
                    "layer": {"rbac": "RBAC", "abac": "ABAC", "tsphol": "TRAC"}.get(layer, layer.upper()),
                    "rule": getattr(x, _LAYER_RULE[layer]),
                    "reason": getattr(x, f"{layer}_reason", None)}
    return {"decision": "ALLOW", "layer": None, "rule": None, "reason": None}


def headline(rows: List[RowReplay]) -> Dict[str, float]:
    """SecFail / legit-allow / deny-rate for the full stack (rbac OR abac OR tsphol)."""
    n = len(rows) or 1
    illeg = [x for x in rows if not x.is_legitimate]
    legit = [x for x in rows if x.is_legitimate]
    denied = [x for x in rows if x.rbac_deny or x.abac_deny or x.tsphol_deny]
    fn = sum(1 for x in illeg if not (x.rbac_deny or x.abac_deny or x.tsphol_deny))
    la = sum(1 for x in legit if not (x.rbac_deny or x.abac_deny or x.tsphol_deny))
    return {
        "secfail": fn / len(illeg) if illeg else 0.0,
        "legit_allow": la / len(legit) if legit else 0.0,
        "deny_rate": len(denied) / n,
        "rbac_deny_rate": sum(1 for x in rows if x.rbac_deny) / n,
        "abac_deny_rate": sum(1 for x in rows if x.abac_deny) / n,
        "tsphol_deny_rate": sum(1 for x in rows if x.tsphol_deny) / n,
        "n": len(rows),
    }


def authz_headline(rows: List[RowReplay]) -> Dict[str, float]:
    """Authorization-conditioned metrics (the accurate baseline).

    SPIFFE/mTLS/RBAC/ABAC decide *authorization*; a request is only a candidate for
    "legit" if they ALLOW it AND the bundle is correct. TRAC is then scored only on the
    traffic the authz layers permit:
      * legit-allow = allow | (authorized ∧ correct)         → TRAC's false-block rate
      * secfail     = allow | (authorized ∧ wrong-DOMAIN)    → TRAC's deterministic scope
    Same-domain wrong-tool is the semantic floor (the LLM's job), reported separately —
    with the deterministic slice the ``action_coherence`` advisory recovers.
    """
    n = len(rows) or 1
    authz = lambda x: not (x.rbac_deny or x.abac_deny)        # SPIFFE/mTLS pass for all rows
    allow = lambda x: not x.tsphol_deny                       # full-stack allow, given authz
    A = [x for x in rows if authz(x)]
    Ac = [x for x in A if x.match_tag == "correct"]                          # legit set
    Aw = [x for x in A if x.match_tag != "correct"]                          # TRAC's job
    wrong_domain = [x for x in Aw if x.hard_missing or x.domain_mismatch]    # TRAC scope
    same_domain = [x for x in Aw if not (x.hard_missing or x.domain_mismatch)]
    same_write = [x for x in same_domain if x.contains_write]                # advisory target
    la = sum(1 for x in Ac if allow(x))
    sf = sum(1 for x in wrong_domain if allow(x))
    adv = sum(1 for x in same_write if x.read_intent_mutating)
    return {
        "n": len(rows),
        "authorized": len(A), "authorized_rate": len(A) / n,
        "legit_n": len(Ac),
        "legit_allow": (la / len(Ac)) if Ac else 1.0,
        "trac_overdeny": (1 - la / len(Ac)) if Ac else 0.0,
        "wrong_domain_n": len(wrong_domain),
        "secfail": (sf / len(wrong_domain)) if wrong_domain else 0.0,
        "wrong_domain_catch": (1 - sf / len(wrong_domain)) if wrong_domain else 0.0,
        "same_domain_n": len(same_domain),
        "same_write_n": len(same_write),
        "advisory_recovered": adv,
    }


def advisory_audit(rows: List[RowReplay]) -> Dict[str, Any]:
    """Split TRAC advisories by whether the transaction was ALREADY denied upstream.

    On an upstream-denied txn (RBAC/ABAC said no) the advisory changes nothing — it is a
    deterministic *warning on the intent* recorded for the audit trail. On an allowed txn
    it is a live alert on something the stack let through. Returns per-rule firing counts
    for each bucket plus the upstream-denied rows (for the 'see why' drill-down).
    """
    from collections import Counter
    on_denied, on_allowed = Counter(), Counter()
    denied_alerts: List[RowReplay] = []
    n_denied_rows = n_allowed_rows = 0
    for x in rows:
        adv = [r for r in (x.tsphol_advisory_rules or []) if r]
        if not adv:
            continue
        if x.rbac_deny or x.abac_deny or x.tsphol_deny:   # finally denied by SOME layer
            for r in adv:
                on_denied[r] += 1
            denied_alerts.append(x)
            n_denied_rows += 1
        else:
            for r in adv:
                on_allowed[r] += 1
            n_allowed_rows += 1
    return {
        "on_denied": dict(on_denied), "on_allowed": dict(on_allowed),
        "n_denied_rows": n_denied_rows, "n_allowed_rows": n_allowed_rows,
        "denied_alerts": denied_alerts,
    }


def stack_funnel(rows: List[RowReplay], mode: Optional[str] = None) -> Dict[str, Any]:
    """Sequential approve/deny funnel (SPIFFE → mTLS → RBAC → ABAC → **LLM** → TRAC,
    first-deny-wins) plus TRAC's two contributions:
      * WARNINGS on already-denied txns — advisory alerts that don't change the (deny) outcome.
      * DECISION CHANGES on already-approved txns — TRAC revokes (allow→deny) what the upstream
        layers let through; we also score how many of those revocations were CORRECT (the bundle
        was wrong) vs false blocks (the bundle was correct).

    The **LLM stage** is mode-dependent (auto-detected from the rows unless ``mode`` is given):
      * ``validation`` — the model is a *judge*; it REJECTS bundles it marks invalid
        (``is_valid is False``), so those never reach TRAC. TRAC then only judges (and can only
        revoke) what the LLM *also* approved → "TRAC corrects the LLM."
      * ``selection`` — the model is the *requester* (``is_valid`` is None); it abstains on
        nothing, so the LLM stage is pure pass-through and TRAC governs every survivor.
    """
    if mode is None:
        mode = "validation" if any(x.llm_valid is not None for x in rows) else "selection"
    total = len(rows)
    rbac_d = [x for x in rows if x.rbac_deny]
    after_rbac = [x for x in rows if not x.rbac_deny]
    abac_d = [x for x in after_rbac if x.abac_deny]          # ABAC denies among RBAC survivors
    after_abac = [x for x in after_rbac if not x.abac_deny]  # upstream-approved (RBAC ∧ ABAC allow)
    llm_reject = [x for x in after_abac if x.llm_valid is False]       # LLM-judge rejects (validation)
    after_llm = [x for x in after_abac if x.llm_valid is not False]    # LLM-approved (or N/A in selection)
    trac_d = [x for x in after_llm if x.tsphol_deny]         # TRAC revokes among LLM-approved
    approved = [x for x in after_llm if not x.tsphol_deny]
    # Two TRAC mechanisms: ENFORCE (trac_d, capability_coverage) vs ADVISE (non-blocking
    # write_safety/action_coherence), the latter split by FINAL stack decision.
    def _fin_deny(x):
        return x.rbac_deny or x.abac_deny or (x.llm_valid is False) or x.tsphol_deny
    warn_denied = [x for x in rows if x.tsphol_advisory_rules and _fin_deny(x)]
    warn_allowed = [x for x in rows if x.tsphol_advisory_rules and not _fin_deny(x)]
    redundant = [x for x in rows if x.tsphol_deny and (x.rbac_deny or x.abac_deny or x.llm_valid is False)]
    revoke_correct = sum(1 for x in trac_d if x.match_tag != "correct")  # caught a wrong bundle
    revoke_wrong = sum(1 for x in trac_d if x.match_tag == "correct")    # blocked a correct one
    return {
        "mode": mode,
        "total": total,
        "rbac_deny": len(rbac_d), "after_rbac": len(after_rbac),
        "abac_deny": len(abac_d), "after_abac": len(after_abac),
        "llm_reject": len(llm_reject), "after_llm": len(after_llm),
        "trac_deny": len(trac_d), "approved": len(approved),
        "trac_warn_on_denied": len(warn_denied),
        "trac_warn_on_allowed": len(warn_allowed),
        "trac_advisory_total": len(warn_denied) + len(warn_allowed),
        "trac_redundant": len(redundant),
        "trac_changed_on_approved": len(trac_d),
        "trac_revoke_correct": revoke_correct,
        "trac_revoke_wrong": revoke_wrong,
        "trac_revoke_success": (revoke_correct / len(trac_d)) if trac_d else 1.0,
    }


def revocation_audit(rows: List[RowReplay], mode: Optional[str] = None) -> Dict[str, Any]:
    """ENFORCE-side detail (the mirror of :func:`advisory_audit` for the ADVISE side).

    The upstream-approved transactions TRAC then REVOKED (allow→deny) via ``capability_coverage``
    because the bundle operates outside the task's domain. Each is scored a *correct catch* (bundle
    genuinely wrong) or a *false block* (a correct bundle TRAC wrongly denied), broken down by the
    rule that fired and by what the bundle actually was.

    **Sequential (mode-aware):** in ``validation`` mode the LLM gate already dropped the bundles it
    judged invalid, so TRAC can only revoke ones the LLM *also* approved (``is_valid is not False``)
    — i.e. the revoked set is exactly the transactions "RBAC/ABAC **and** the LLM had approved." In
    ``selection`` mode ``is_valid`` is None, so this reduces to RBAC ∧ ABAC ∧ TRAC-deny as before.
    """
    from collections import Counter
    if mode is None:
        mode = "validation" if any(x.llm_valid is not None for x in rows) else "selection"
    revoked = [x for x in rows
               if not (x.rbac_deny or x.abac_deny) and (x.llm_valid is not False) and x.tsphol_deny]
    by_rule = Counter((x.tsphol_rule or "(unnamed)") for x in revoked)
    by_verdict = Counter((x.match_tag or "—") for x in revoked)
    correct = sum(1 for x in revoked if x.match_tag != "correct")
    wrong = sum(1 for x in revoked if x.match_tag == "correct")
    # Validation-mode context: bundles the LLM ALREADY rejected that TRAC would also deny
    # (defense-in-depth agreement, not a unique TRAC correction).
    redundant_llm = sum(1 for x in rows
                        if not (x.rbac_deny or x.abac_deny) and x.llm_valid is False and x.tsphol_deny)
    return {
        "mode": mode,
        "n_revoked": len(revoked),
        "n_correct": correct,
        "n_wrong": wrong,
        "n_llm_rejected_redundant": redundant_llm,
        "success": (correct / len(revoked)) if revoked else 1.0,
        "by_rule": dict(by_rule.most_common()),
        "by_verdict": dict(by_verdict.most_common()),
    }


def layer_firing_summary(rows: List[RowReplay]) -> Dict[str, Dict[str, int]]:
    """Per-layer independent rule-firing counts: {layer: {rule_name: count}}."""
    out: Dict[str, Dict[str, int]] = {l: {} for l in _LAYERS}
    for x in rows:
        for layer in _LAYERS:
            if _deny(x, layer):
                rname = getattr(x, _LAYER_RULE[layer]) or "(unnamed)"
                out[layer][rname] = out[layer].get(rname, 0) + 1
    return {l: dict(sorted(d.items(), key=lambda kv: -kv[1])) for l, d in out.items()}


def unreproducible_keys(rows: List[RowReplay]) -> set:
    """Rows the deterministic replay cannot faithfully reproduce — **empty by construction**.

    TRAC is now purely deterministic over the cached bundle (it consumes no
    unstored LLM ``issue_codes``), and RBAC/ABAC depend only on cached inputs, so
    every cached row is reproducible. Divergence from a *historical* log is intended
    policy drift (the active stack differs from the one that generated the log), not
    unreproducibility — see :func:`logged_divergence_keys`.
    """
    return set()


def logged_divergence_keys(rows: List[RowReplay]) -> set:
    """(persona, task_idx) keys where the deterministic replay's full-stack decision
    differs from the decision recorded in the log.

    When the active policies match the log's, this is the genuine replay gap; after a
    policy change it is the intended **policy drift** between the active stack and the
    one that generated the log (e.g. the simplified 3-rule TRAC vs. the original 12).
    """
    return {(x.persona, x.task_idx) for x in rows
            if (x.rbac_deny or x.abac_deny or x.tsphol_deny) != x.logged_final_deny}


def drop_keys(rows: List[RowReplay], keys: set) -> List[RowReplay]:
    return [x for x in rows if (x.persona, x.task_idx) not in keys]


def compare(baseline: List[RowReplay], modified: List[RowReplay]) -> List[dict]:
    """Per-row diff aligned by (persona, task_idx). Marks decision/layer changes."""
    bmap = {(x.persona, x.task_idx): x for x in baseline}
    rows = []
    for m in modified:
        b = bmap.get((m.persona, m.task_idx))
        if b is None:
            continue
        fb, fm = full_stack(b), full_stack(m)
        rows.append({
            "persona": m.persona, "task_idx": m.task_idx, "domain": m.domain,
            "match_tag": m.match_tag, "is_legitimate": m.is_legitimate,
            "base_decision": fb["decision"], "base_layer": fb["layer"], "base_rule": fb["rule"],
            "mod_decision": fm["decision"], "mod_layer": fm["layer"], "mod_rule": fm["rule"],
            "changed": (fb["decision"] != fm["decision"]) or (fb["layer"] != fm["layer"]) or (fb["rule"] != fm["rule"]),
            "decision_changed": fb["decision"] != fm["decision"],
        })
    return rows


def build_modified_policies(rbac_rules: list, abac_rules: list, tsphol_rules: list) -> Tuple[dict, dict, dict]:
    """Wrap edited rule lists into the policy-dict shapes the engine expects."""
    return ({"policies": rbac_rules}, {"rules": abac_rules}, {"rules": tsphol_rules})


def transaction_trace(persona: str, task_idx: int, tools: List[str], mcps: List[str],
                      task_text: str, mode: str, policies: Tuple[dict, dict, dict],
                      mcp_personas=None, issue_codes: Optional[List[str]] = None,
                      task_domain: Optional[str] = None) -> dict:
    """Full per-layer detailed trace for ONE (persona, bundle), for drill-down.

    Runs the 3 isolated engines and extracts each layer's decision, matched rule,
    reason, and the layer-specific reasoning trace (RBAC per-tool, ABAC per-condition,
    TRAC per-rule + predicates). ``task_domain`` is the task's declared MCP scope,
    on which the agnostic TRAC capability check keys (must match the replay).
    """
    if mcp_personas is None:
        mcp_personas, _ = load_mcp_personas("mcp_servers")
    rbac_pol, abac_pol, tsphol_pol = policies
    engines = _engines_from_policies(mcp_personas, rbac_pol, abac_pol, tsphol_pol)
    try:
        rres = _eval(engines["rbac"], persona, tools, mcps, task_text, mode)
        ares = _eval(engines["abac"], persona, tools, mcps, task_text, mode)
        tres = _eval(engines["tsphol"], persona, tools, mcps, task_text, mode,
                     issue_codes=issue_codes, task_domain=task_domain)
        rctx, actx, tctx = rres.context or {}, ares.context or {}, tres.context or {}
        layers = {
            "rbac": {
                "decision": rres.final_decision, "denied": rres.final_decision in DENY_STATES,
                "rule": _layer_firing(rres, "rbac")[0], "reason": rres.reason,
                "trace": (rctx.get("rbac_evaluation") or {}).get("rbac_trace", []),
            },
            "abac": {
                "decision": ares.final_decision, "denied": ares.final_decision in DENY_STATES,
                "rule": _layer_firing(ares, "abac")[0], "reason": ares.reason,
                "trace": ((actx.get("abac_baseline") or {}).get("reasoning_trace", {}) or {}).get("logic_steps", []),
            },
            "tsphol": {
                "decision": tres.final_decision, "denied": tres.final_decision in DENY_STATES,
                "rule": _layer_firing(tres, "tsphol")[0], "reason": tres.reason,
                "trace": [t for t in tctx.get("tsphol_logic_trace", []) if t.get("triggered")],
                "predicates": tctx.get("tsphol_predicate_set", {}),
            },
        }
        # Full-stack attribution (first-firing in pipeline order).
        deciding = next((l for l in _LAYERS if layers[l]["denied"]), None)
        return {"persona": persona, "task_idx": task_idx, "tools": tools, "mcps": mcps,
                "deciding_layer": deciding, "layers": layers}
    finally:
        _release_engines(engines)


# ──────────────────────────────────────────────────────────────────────────
# Instant re-evaluation over the cached predicate set (P2 / P3)
# ──────────────────────────────────────────────────────────────────────────

# The default production TRAC thresholds, as authored in trac_rules.yaml.
DEFAULT_WEIGHTS = (0.4, 0.4, 0.2)   # domain, capability, semantic


def _interp_decide(pred: dict, rules: list) -> Tuple[bool, Optional[str], List[str]]:
    """Run the TRAC interpreter over a (copied) predicate dict; return
    (deny, deciding_rule, advisory_rules)."""
    from app.services.tsphol_interpreter import TSPHOLInterpreter
    final, _derived, trace, _certainty = TSPHOLInterpreter().evaluate_rules(dict(pred), rules)
    deny = final == "DENY"
    rule = _decider_rule(trace) if deny else None
    advisories = [t.get("rule") for t in trace if t.get("advisory")]
    return deny, rule, advisories


def reevaluate(
    rows: List[RowReplay],
    bundle_cache: Dict[str, dict],
    rules: list,
    weights: Optional[Tuple[float, float, float]] = None,
    ontology_fix: bool = False,
) -> List[RowReplay]:
    """Recompute each row's TRAC decision over cached predicates with edited
    rules / alignment weights / ontology fix. RBAC and ABAC are untouched.

    ``ontology_fix``: simulate "a concrete read satisfies the abstract GenericRead
    hard-capability" — i.e. drop GenericRead from the missing-hard set when the
    bundle performs a read. This is the targeted fix for the dominant
    ``hard_capability_violation`` over-blocking.
    """
    # Re-decide per unique bundle, then broadcast to rows.
    decisions: Dict[str, Tuple[bool, Optional[str], List[str]]] = {}
    for sig, base_pred in bundle_cache.items():
        pred = dict(base_pred)
        if weights is not None:
            wd, wc, ws = weights
            pred["TaskAlignmentScore"] = (
                wd * pred.get("_domain_score", 0.0)
                + wc * pred.get("_capability_score", 0.0)
                + ws * pred.get("_semantic_score", 0.0)
            )
        if ontology_fix:
            missing = list(pred.get("MissingHardCapabilities") or [])
            if pred.get("ContainsRead"):
                missing = [c for c in missing if c != "GenericRead"]
            pred["HardCapabilityMissing"] = len(missing) > 0
            pred["MissingHardCapabilities"] = missing
        decisions[sig] = _interp_decide(pred, rules)

    new_rows: List[RowReplay] = []
    for x in rows:
        deny, rule, advisories = decisions.get(
            x.sig, (x.tsphol_deny, x.tsphol_rule, x.tsphol_advisory_rules))
        nx = RowReplay(**{**x.__dict__})
        nx.tsphol_deny = deny
        nx.tsphol_rule = rule
        nx.tsphol_advisory_rules = advisories
        nx.tsphol_advisory = bool(advisories)
        nx.tsphol_advisory_rule = advisories[0] if advisories else None
        new_rows.append(nx)
    return new_rows


def scenario_metrics(rows: List[RowReplay]) -> Dict[str, float]:
    """Headline metrics for a (re-evaluated) row set under the full stack."""
    sl = secfail_legit(rows, _LAYERS)
    mm = money_metric(rows)
    return {
        "secfail": sl["secfail"],
        "legit_allow": sl["legit_allow"],
        "tsphol_deny_rate": layer_rates(rows)["tsphol"],
        "tsphol_catch_rate": mm["tsphol_catch_rate"],
        "tsphol_block_rate": mm["tsphol_block_rate"],
    }


def per_rule_ablation(rows: List[RowReplay], bundle_cache: Dict[str, dict],
                      rules: list, weights: Optional[Tuple[float, float, float]] = None,
                      ontology_fix: bool = False) -> List[dict]:
    """Disable each DENY rule in turn; report the resulting SecFail / legit-allow shift.

    Operates on the supplied ``rules`` set (the active config), so rules already
    disabled upstream are not candidates and never re-introduced.
    """
    base = scenario_metrics(reevaluate(rows, bundle_cache, rules, weights, ontology_fix))
    out = [{"rule": "(baseline: active config)", "secfail": base["secfail"],
            "legit_allow": base["legit_allow"], "d_secfail": 0.0, "d_legit_allow": 0.0}]
    deny_rules = [r for r in rules if str(r.get("then", "")).upper() == "DENY"]
    for r in deny_rules:
        kept = [rr for rr in rules if rr.get("rule_name") != r.get("rule_name")]
        m = scenario_metrics(reevaluate(rows, bundle_cache, kept, weights, ontology_fix))
        out.append({
            "rule": r.get("rule_name"),
            "secfail": m["secfail"], "legit_allow": m["legit_allow"],
            "d_secfail": m["secfail"] - base["secfail"],
            "d_legit_allow": m["legit_allow"] - base["legit_allow"],
        })
    return out


def sweep_rule_threshold(rows: List[RowReplay], bundle_cache: Dict[str, dict],
                         rules: list, rule_name: str, predicate: str,
                         values: List[float], weights: Optional[Tuple[float, float, float]] = None,
                         ontology_fix: bool = False) -> List[dict]:
    """Sweep one rule's `lt` threshold over a range → SecFail-vs-legit-allow points.

    Holds the rest of the active config (other rules, weights, ontology fix) fixed.
    """
    import copy
    pts = []
    for v in values:
        mod = copy.deepcopy(rules)
        for rr in mod:
            if rr.get("rule_name") == rule_name:
                for c in rr.get("if", []):
                    if c.get("predicate") == predicate and "lt" in c:
                        c["lt"] = v
        m = scenario_metrics(reevaluate(rows, bundle_cache, mod, weights, ontology_fix))
        pts.append({"threshold": v, "secfail": m["secfail"], "legit_allow": m["legit_allow"]})
    return pts


if __name__ == "__main__":
    import sys
    from app.loaders.astra_loader import load_astra_dataset
    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    log = sys.argv[1] if len(sys.argv) > 1 else \
        "datasets/experiment_logs/run_20260613_005419_llm_gpt-4o_validation.json"
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
    rows, summ, bundle_cache = replay_experiment(log, tasks, experiment="E1", limit=lim,
                                                 progress_cb=lambda c, t: print(f"  {c}/{t}", end="\r"))
    print("\n", json.dumps(summ, indent=2))
    # quick per-layer independent deny rates + TRAC-only catch
    n = len(rows)
    def rate(f):
        return sum(1 for x in rows if f(x)) / n if n else 0
    print("rbac_deny   : %.3f" % rate(lambda x: x.rbac_deny))
    print("abac_deny   : %.3f" % rate(lambda x: x.abac_deny))
    print("tsphol_deny : %.3f" % rate(lambda x: x.tsphol_deny))

    # --- Money metric: value of TRAC ON TOP of RBAC+ABAC ---
    # Restrict to rows RBAC and ABAC both ALLOW (the only place TRAC can add value).
    rb_abac_allow = [x for x in rows if not x.rbac_deny and not x.abac_deny]
    illeg_open = [x for x in rb_abac_allow if not x.is_legitimate]
    legit_open = [x for x in rb_abac_allow if x.is_legitimate]
    ts_catch = [x for x in illeg_open if x.tsphol_deny]
    ts_block_legit = [x for x in legit_open if x.tsphol_deny]
    print("\n--- Value of TRAC beyond RBAC+ABAC (rows both allow) ---")
    print("  illegit RBAC+ABAC let through : %d" % len(illeg_open))
    print("    TRAC catches             : %d (%.1f%%)  <- incremental security"
          % (len(ts_catch), 100 * len(ts_catch) / len(illeg_open) if illeg_open else 0))
    print("  legit RBAC+ABAC let through   : %d" % len(legit_open))
    print("    TRAC wrongly blocks      : %d (%.1f%%)  <- incremental cost"
          % (len(ts_block_legit), 100 * len(ts_block_legit) / len(legit_open) if legit_open else 0))

    print("\n--- Shapley value (avg marginal SecFail reduction) ---")
    print({k: round(v, 4) for k, v in shapley(rows).items()})
    print("\n--- UpSet regions on illegitimate rows (who denies) ---")
    print(region_counts(rows, only="illegit"))
    print("\n--- TRAC per-rule firing ---")
    print(per_rule_firing(rows))

    # --- P2/P3 re-evaluation checks (instant, over cached predicates) ---
    from app.services.tsphol_rule_service import TSPHOLRuleService
    rules = TSPHOLRuleService().get_all()
    base = scenario_metrics(rows)
    print("\n--- BASELINE re-eval (should match engine replay) ---")
    print({k: round(v, 4) for k, v in base.items()})
    # faithfulness: cached-predicate re-eval must reproduce the engine's tsphol decisions
    rb = reevaluate(rows, bundle_cache, rules)
    agree = sum(1 for a, b in zip(rows, rb) if a.tsphol_deny == b.tsphol_deny) / len(rows)
    print("  cached-reeval agreement with engine tsphol_deny: %.1f%%" % (100 * agree))

    fixed = reevaluate(rows, bundle_cache, rules, ontology_fix=True)
    fm = scenario_metrics(fixed)
    print("\n--- P3 ONTOLOGY FIX (concrete read satisfies GenericRead) ---")
    print({k: round(v, 4) for k, v in fm.items()})
    print("  legit-allow %.1f%% -> %.1f%% | secfail %.3f -> %.3f"
          % (100*base["legit_allow"], 100*fm["legit_allow"], base["secfail"], fm["secfail"]))

    print("\n--- P2 per-rule ablation (top rows) ---")
    for r in per_rule_ablation(rows, bundle_cache, rules)[:5]:
        print("  %-34s secfail=%.3f (d=%+.3f) legit=%.3f (d=%+.3f)"
              % (r["rule"], r["secfail"], r["d_secfail"], r["legit_allow"], r["d_legit_allow"]))
