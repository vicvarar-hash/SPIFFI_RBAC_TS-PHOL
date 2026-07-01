"""Deterministic, agnostic, leak-free **tool-relevance** signal used by TRAC.

``capability_coverage`` checks the bundle is in the right *domain*; this is the tool-level analogue:
are the *selected tools* actually relevant to the task? It scores each selected tool's catalog
description against the task text with **Okapi BM25** (the same standard IR ranking used for domain
routing), over the auto-discovered ``mcp_servers/*.json`` tool catalog. No gold label, no hardcoded
domains — drop in a new catalog file and its tools join the corpus automatically.

Empirically the mean selected-tool relevance separates the classes cleanly (ASTRA):
``correct`` ~5.7  ·  ``wrong`` ~2.4  ·  ``null`` ~0.4. So a low mean flags the same-domain wrong-tool
and null bundles the domain check cannot see.

Two consumers, both keyed on this single BM25 score (thresholds env-overridable, see below):
  * the **``tool_relevance``** rule — ENFORCING below :data:`THRESHOLD` (default 1.0): a low mean
    means the tools are lexically irrelevant to the task, so the bundle is denied.
  * **corroborated coverage** — the *high* end (:data:`RESCUE_RELEVANCE`, default 4.0) reverses a
    ``capability_coverage`` domain-mismatch denial, because tools that strongly match the task are
    independent evidence the bundle fits even when the BM25 task->domain router mis-inferred.
"""
from __future__ import annotations

import glob
import json
import os
import statistics
from typing import Dict, List, Optional

from rank_bm25 import BM25Okapi

from app.services.task_domain_classifier import _MCP_DIR, _tokens

# Mean BM25 relevance below this -> the selected tools look irrelevant to the task (advisory flag).
# Tuned on ASTRA: correct median ~5.0, wrong median ~1.6, null median ~0.0.
# Module-level + env-overridable so the enforcing threshold can be retuned/swept without code edits;
# read at call time (see ``tools_irrelevant``). Set to 0 to effectively disable enforcement.
THRESHOLD = float(os.environ.get("PALADIN_TOOLREL_THRESHOLD", "1.0"))
_THRESHOLD = THRESHOLD  # backward-compat alias

# Corroborated coverage: ``capability_coverage`` rescues a domain-mismatch denial when the selected
# tools are at least this relevant to the task (mean BM25). Legit bundles whose task-domain was
# mis-inferred still score high here (~5.7); wrong-domain / null attacks score low (~2.4 / ~0.4) —
# so a high bar reverses false-denies without admitting attacks. ``<= 0`` disables it. Default 4.0
# is the swept Pareto point (gpt-4o val, n=6942): legit-allow 43.3%->43.9%, TRAC over-deny 242->231,
# at a 2-catch / +0.1pp-SecFail cost. Read at call time in ``predicate_engine``; env-overridable.
RESCUE_RELEVANCE = float(os.environ.get("PALADIN_CAPCOV_RESCUE", "4.0"))


def _build():
    """({tool_name: corpus_index}, BM25) over EVERY tool in the catalog (name + description)."""
    names: List[str] = []
    corpus: List[List[str]] = []
    for path in sorted(glob.glob(os.path.join(_MCP_DIR, "*.json"))):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for t in data.get("tools", []):
            nm = t.get("name")
            if nm:
                names.append(nm)
                corpus.append(_tokens((nm or "") + " " + (t.get("description") or "")))
    index = {n: i for i, n in enumerate(names)}
    return index, (BM25Okapi(corpus) if corpus else None)


_INDEX: Dict[str, int]
_INDEX, _BM25 = _build()


def bundle_tool_relevance(tools, task_text: str) -> Optional[float]:
    """Mean BM25 relevance of the selected ``tools`` (by their catalog descriptions) to ``task_text``.

    Returns ``None`` when there is nothing to score (no tools, or none recognised in the catalog),
    so callers can abstain rather than treat "unknown" as "irrelevant".
    """
    if not _BM25 or not tools:
        return None
    scores = _BM25.get_scores(_tokens(task_text))
    sel = [scores[_INDEX[t]] for t in tools if t in _INDEX]
    if not sel:
        return None
    return float(statistics.mean(sel))


def tools_irrelevant(tools, task_text: str, threshold: float = None) -> bool:
    """True iff the selected tools' mean relevance to the task is below ``threshold`` (advisory).

    Conservative: abstains (returns False) when relevance can't be computed, so the advisory never
    fires on missing information. ``threshold`` defaults to the module-level :data:`THRESHOLD`
    (env-overridable), read at call time so it can be retuned/swept at runtime.
    """
    if threshold is None:
        threshold = THRESHOLD
    rel = bundle_tool_relevance(tools, task_text)
    return rel is not None and rel < threshold
