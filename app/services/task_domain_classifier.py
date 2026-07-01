"""Deterministic, ground-truth-free task->domain classifier (the leak-free ``d_inf`` variant).

The baseline harness derives TRAC's ``expected_domain`` from ``gt_mcps[0]`` -- the dataset's
**ground-truth answer** (``groundtruth.mcp_servers``). Reading the answer key to set the required
domain is an oracle-leak that cannot back a real metric, so this module provides the leak-free
alternative: infer the task's domain **from the task text alone**, grounded in the *public MCP tool
catalog* (``mcp_servers/<domain>.json``) -- i.e. the same routing signal a real operator/registry has.

Ranking method: **Okapi BM25** (``rank_bm25.BM25Okapi``) -- the standard lexical IR ranking function
used by Elasticsearch/Lucene, and the same family already used by this repo's RA-ICL selection
baseline. Each MCP's tool *names + descriptions* form one BM25 "document"; the task text is the query;
the top-scoring domain wins. This is a cited, reproducible standard, NOT a bespoke heuristic -- the
novelty in PALADIN is the enforcement stack, not the router.

Method (transparent, fully reproducible, no LLM, no gold label):
  * Build one document per MCP from its tool names + descriptions; tokenise (lowercase, drop
    stop-words / short tokens).
  * Score the task query against every document with BM25 (term saturation + length normalisation
    + corpus IDF are handled by BM25 itself).
  * The top domain wins unless the runner-up is near-tied (ambiguous) or nothing matches -- then the
    result is ``"uncertain"`` and TRAC abstains (``required_capability`` empty -> no deny on a guess).

It is intentionally imperfect (~60-70% exact on ASTRA): text is a weaker signal than a gold MCP, so
the honest secfail/legit-allow numbers under ``d_inf`` are worse than the optimistic gold-domain
numbers. That gap *is* the disclosed limitation, now measurable without cheating.
"""
from __future__ import annotations

import json
import os
import glob
import re
from typing import Dict, List

from rank_bm25 import BM25Okapi

from app.services.normalization import normalize_mcp_name

_MCP_DIR = "mcp_servers"

# Generic verbs / schema words that carry no domain signal -- excluded so they don't dominate.
_STOP = set(
    "the a an of to in for and or on with this that it its your you our we will be is are as by from "
    "at into can please make sure all any new get set list create update delete read write reads writes "
    "tool tools return returns takes argument arguments str int bool float optional required name names id "
    "ids true false value values object string number boolean array null none use used using via able "
    "want need help allow allows given specific current also each per their them they then than".split()
)

_AMBIGUITY = 0.85  # runner-up within 85% of the top score -> too close to call -> "uncertain"


def _tokens(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z][a-z0-9_]+", (s or "").lower())
            if w not in _STOP and len(w) > 2]


def _build_doc_tokens() -> Dict[str, List[str]]:
    """{canonical_mcp: tokenised(tool names + descriptions)} — **auto-discovered** from every
    ``mcp_servers/*.json`` (no hardcoded domain list; canonical name = ``normalize_mcp_name(stem)``).
    Drop in a new MCP catalog file and it is routed to automatically — keeps the classifier agnostic.
    """
    docs: Dict[str, List[str]] = {}
    for path in sorted(glob.glob(os.path.join(_MCP_DIR, "*.json"))):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        mcp = normalize_mcp_name(os.path.splitext(os.path.basename(path))[0])
        text = " ".join((t.get("name", "") + " " + (t.get("description") or ""))
                        for t in data.get("tools", []))
        toks = _tokens(text)
        if toks:
            docs[mcp] = toks
    return docs


_DOC_TOKENS: Dict[str, List[str]] = _build_doc_tokens()
_DOMAINS: List[str] = list(_DOC_TOKENS)
_INDEX_CACHE: Dict = {}


def _index_for(allowed=None):
    """(domains, BM25) built over the in-scope MCP documents. ``allowed`` (the deployment's MCP
    universe, auto-derived from RBAC) restricts which catalog docs are indexed, so BM25's IDF is
    computed over exactly the MCPs the deployment serves — not unrelated catalog files. Cached."""
    if allowed:
        key = frozenset(normalize_mcp_name(a) for a in allowed)
    else:
        key = None
    if key not in _INDEX_CACHE:
        doms = [d for d in _DOMAINS if key is None or d in key]
        bm = BM25Okapi([_DOC_TOKENS[d] for d in doms]) if doms else None
        _INDEX_CACHE[key] = (doms, bm)
    return _INDEX_CACHE[key]


def domain_scores(task_text: str, allowed=None) -> Dict[str, float]:
    """Per-domain BM25 score for ``task_text`` (only strictly-positive domains), within ``allowed``."""
    doms, bm = _index_for(allowed)
    if not bm:
        return {}
    scores = bm.get_scores(_tokens(task_text))
    return {doms[i]: round(float(s), 4) for i, s in enumerate(scores) if s > 0}


def infer_task_domain(task_text: str, allowed=None) -> str:
    """Best-guess canonical MCP domain for a task, from its text alone (no ground truth), via BM25.

    Returns the top-scoring domain, or ``"uncertain"`` when nothing matches or the top two domains
    are within :data:`_AMBIGUITY` of each other. ``"uncertain"`` makes ``required_capability`` empty,
    so TRAC abstains rather than denying on a coin-flip -- the conservative, honest default.

    ``allowed`` (optional) restricts routing to a legitimate, non-gold scope -- the deployment's MCP
    universe (auto-derived from RBAC). BM25's IDF is then computed over exactly those MCPs.
    """
    scores = domain_scores(task_text, allowed)
    if not scores:
        return "uncertain"
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) >= 2 and ranked[1][1] >= _AMBIGUITY * ranked[0][1]:
        return "uncertain"
    return ranked[0][0]


# ── capability_coverage confidence-gate (tunable) ───────────────────────────────────
# The single-best BM25 domain is often *confidently wrong* for business-phrased tasks
# (e.g. a MongoDB task whose text lexically matches "azure"), which over-denies correct
# in-domain bundles. CAPCOV_TOPK relaxes this: a bundle whose own MCP domain is within the
# task's top-K inferred domains is treated as in-domain (not denied). K=1 reproduces the
# original strict top-1 behaviour exactly. Tunable via env for sweeps.
import os as _os

CAPCOV_TOPK = int(_os.environ.get("PALADIN_CAPCOV_TOPK", "1"))


def topk_domains(task_text: str, allowed=None, k: int = 1) -> List[str]:
    """The task's top-``k`` inferred domains by BM25 (within ``allowed``), best first."""
    scores = domain_scores(task_text, allowed)
    if not scores:
        return []
    ranked = [d for d, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]
    return ranked[: max(1, k)]


def resolve_required_domain(task_text: str, bundle_domains, allowed=None, k=None) -> str:
    """Confidence-aware required domain for ``capability_coverage``.

    Keeps the ``"uncertain"`` abstain of :func:`infer_task_domain`, but when the bundle's own
    domain is within the task's top-``k`` inferred domains it returns *that* domain, so a bundle
    that is plausibly in-domain is not over-denied. A genuinely wrong-domain bundle (not in the
    top-k) still falls back to the single best guess and is denied. ``k=1`` == original behaviour;
    the gate can only *relax* coverage, never tighten it.
    """
    k = CAPCOV_TOPK if k is None else k
    best = infer_task_domain(task_text, allowed)
    if best == "uncertain" or k <= 1 or not bundle_domains:
        return best
    bd = {normalize_mcp_name(d) for d in bundle_domains if d}
    for d in topk_domains(task_text, allowed, k):
        if d in bd:
            return d
    return best
