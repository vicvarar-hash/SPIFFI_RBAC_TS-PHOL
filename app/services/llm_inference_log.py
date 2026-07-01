"""``llm_inference_v1`` — the LLM Lab's output format.

A pure record of what the **LLM proposer** produced per task — no governance, no
RBAC/ABAC/TRAC decisions. The Post-Experiment Lab (the deterministic *disposer*)
re-derives all governance from these bundles, fanning each task across personas.

Per-task, because the LLM output is persona-independent (verified: across 300 tasks,
selected_tools / is_valid never varied across the 6 personas). Storing it per task
(not per task×persona) is a 6× reduction in LLM calls and log size.

Schema::

    { "schema": "llm_inference_v1", "model": ..., "provider": ..., "mode": ...,
      "dataset": "astra_03_tools.json",
      "retrieval": {"strategy": "none"} | {"strategy":"bm25","k":25,"split":...},
      "created_at": ..., "source_log": <if migrated>,
      "tasks": [ { "task_idx", "selected_tools", "selected_mcps",
                   "is_valid", "issue_codes",          # the LLM verdict (validation)
                   "match_tag", "tool_match", "tool_jaccard", "llm_failed" } ] }
"""
from __future__ import annotations

import datetime
import json
import os
from typing import Dict, List, Optional

SCHEMA = "llm_inference_v1"


def retrieval_meta(strategy: str = "none", k: Optional[int] = None,
                   split: Optional[str] = None) -> dict:
    if strategy in (None, "none", ""):
        return {"strategy": "none"}
    return {"strategy": strategy, "k": k, "split": split}


def build_log(model: str, mode: str, tasks: List[dict], provider: Optional[str] = None,
              retrieval: Optional[dict] = None, dataset: str = "astra_03_tools.json",
              source_log: Optional[str] = None) -> dict:
    rec = {
        "schema": SCHEMA,
        "model": model,
        "provider": provider,
        "mode": mode,
        "dataset": dataset,
        "retrieval": retrieval or {"strategy": "none"},
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "tasks": tasks,
    }
    if source_log:
        rec["source_log"] = source_log
    return rec


def save_log(path: str, log: dict) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    return path


# ── Migration from the legacy experiments[E1..E4] format ───────────────────

_INVALID = ("DENY", "DECEPTION_ROUTED")


def migrate_experiment_log(old: dict, source_name: str) -> dict:
    """Convert a legacy log (experiments E1..E4, per task×persona) into
    ``llm_inference_v1`` (per task). The LLM output is deduped across personas; the
    validation verdict is taken from the E1 row's ``is_valid`` when present, else
    recovered from the E4 (LLM-only) decision.
    """
    mode = old.get("evaluation_mode", "validation")
    exps = old.get("experiments", {})
    e1 = exps.get("E1", {}).get("rows", [])

    # E4 = LLM-only verdict (validation only); recover per task (persona-independent).
    # In SELECTION mode the LLM picks tools rather than ruling valid/invalid, so there
    # is no validity verdict — leave is_valid=None (the lab uses selection accuracy).
    e4_verdict: Dict[int, bool] = {}
    if mode == "validation":
        for r in exps.get("E4", {}).get("rows", []):
            ti = r.get("task_idx")
            if ti is not None and ti not in e4_verdict:
                e4_verdict[ti] = r.get("final_decision") not in _INVALID

    by_task: Dict[int, dict] = {}
    for r in e1:
        ti = r.get("task_idx")
        if ti is not None and ti not in by_task:
            by_task[ti] = r

    tasks_out = []
    for ti, r in sorted(by_task.items()):
        is_valid = r.get("is_valid")
        if is_valid is None and ti in e4_verdict:
            is_valid = e4_verdict[ti]
        tasks_out.append({
            "task_idx": ti,
            "selected_tools": r.get("selected_tools") or [],
            "selected_mcps": r.get("selected_mcps") or [],
            "is_valid": is_valid,
            "issue_codes": r.get("issue_codes"),
            "match_tag": r.get("match_tag"),
            "tool_match": r.get("tool_match"),
            "tool_jaccard": r.get("tool_jaccard"),
            "llm_failed": bool(r.get("llm_failed")),
        })

    ra = old.get("ra_icl")
    if isinstance(ra, dict) and ra.get("enabled"):
        k = ra.get("k_resolved") or ra.get("k")
        split = None
        if ra.get("split_ratio") is not None:
            split = f"{ra.get('split_ratio')}@seed{ra.get('split_seed')}"
        retrieval = retrieval_meta(ra.get("strategy", "bm25"), k, split)
    else:
        retrieval = {"strategy": "none"}

    return build_log(
        model=old.get("llm_model"), mode=mode, tasks=tasks_out,
        provider=old.get("llm_provider"), retrieval=retrieval, source_log=source_name,
    )
