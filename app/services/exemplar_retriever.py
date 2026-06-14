"""
Exemplar retriever for in-context RA-ICL learning.

Given a pool of training tasks (with trustworthy groundtruth bundles),
this returns K exemplars for a given test task. The default retrieval
strategy is **random in-domain**: pick K tasks uniformly at random from
the same primary MCP as the test task, falling back to other domains
only if the in-domain pool is exhausted.

Each exemplar is represented as a uniform tuple-like dict::

    {"task": <task text>, "mcp": <primary mcp>, "tools": [<gt tools>]}

regardless of whether the input pool was raw ASTRA dicts or AstraTask
objects.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    """Lowercase + alphanumeric tokenize. Drops very short tokens."""
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 2]


class _BM25Index:
    """Minimal BM25 (Okapi) index. Built once, reused per query."""

    def __init__(self, docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.N = len(docs)
        self.doc_lens = [len(d) for d in docs]
        self.avgdl = (sum(self.doc_lens) / self.N) if self.N else 0.0
        # term frequencies per doc
        self.tfs: List[Counter] = [Counter(d) for d in docs]
        # document frequency per term
        df: Counter = Counter()
        for d in self.tfs:
            for term in d:
                df[term] += 1
        # idf using BM25 idf with +1 smoothing (always positive)
        self.idf: Dict[str, float] = {
            term: math.log(1.0 + (self.N - n + 0.5) / (n + 0.5))
            for term, n in df.items()
        }

    def score(self, query_tokens: List[str], doc_idx: int) -> float:
        tf = self.tfs[doc_idx]
        dl = self.doc_lens[doc_idx]
        denom_norm = (1.0 - self.b + self.b * (dl / self.avgdl)) if self.avgdl else 1.0
        s = 0.0
        for term in query_tokens:
            f = tf.get(term, 0)
            if f == 0:
                continue
            idf = self.idf.get(term, 0.0)
            s += idf * (f * (self.k1 + 1.0)) / (f + self.k1 * denom_norm)
        return s

    def topk(self, query_tokens: List[str], k: int,
             exclude_idxs: Optional[set] = None) -> List[Tuple[int, float]]:
        excl = exclude_idxs or set()
        scored = [
            (i, self.score(query_tokens, i))
            for i in range(self.N) if i not in excl
        ]
        # Sort by score desc, then by index asc for deterministic tiebreak.
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]


def _to_exemplar(task: Any) -> Optional[Dict[str, Any]]:
    """Normalize an input task to {task, mcp, tools} or None if unusable."""
    if isinstance(task, dict):
        text = task.get("input", {}).get("task")
        # Prefer expected_output for groundtruth bundle when present
        expected = task.get("expected_output") or {}
        gt_tools = expected.get("tools") or task.get("input", {}).get("tools") or []
        gt_mcps = expected.get("mcp_servers") or task.get("input", {}).get("mcp_servers") or []
    else:
        text = getattr(task, "task", None)
        gt_tools = list(getattr(task, "groundtruth_tools", []) or [])
        gt_mcps = list(getattr(task, "groundtruth_mcp", []) or [])

    if not text or not gt_tools:
        return None
    mcp = gt_mcps[0] if gt_mcps else "<none>"
    return {"task": text, "mcp": mcp, "tools": list(gt_tools)}


def _task_text(task: Any) -> str:
    if isinstance(task, dict):
        return task.get("input", {}).get("task", "")
    return getattr(task, "task", "")


class ExemplarRetriever:
    """Retrieves K exemplars per test task from a training pool.

    Parameters
    ----------
    train_pool : list
        Tasks (raw ASTRA dicts or AstraTask) with trustworthy groundtruth.
        Typically the ``correct``-tagged tasks from the train split.
    k : int
        Number of exemplars to return per query.
    strategy : str
        Currently ``"random_in_domain"`` is supported.
    seed : int
        RNG seed (each ``get`` call uses a per-task derived seed so that
        the same test task always retrieves the same exemplars within a
        single retriever instance).
    """

    def __init__(
        self,
        train_pool: Iterable[Any],
        k: int = 3,
        strategy: str = "random_in_domain",
        seed: int = 42,
        pad_cross_domain: bool = True,
    ):
        if k < 0:
            raise ValueError("k must be >= 0")
        if strategy not in ("random_in_domain", "random_any", "bm25"):
            raise ValueError(f"unsupported strategy: {strategy}")
        self.k = k
        self.strategy = strategy
        self.seed = seed
        # When False and strategy is random_in_domain, do NOT top up with
        # cross-domain candidates if the in-domain pool is smaller than k.
        # Use this for "all in-domain" mode where we want pure topical
        # relevance and accept a variable exemplar count per query.
        self.pad_cross_domain = pad_cross_domain
        self._by_mcp: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._all: List[Dict[str, Any]] = []
        for t in train_pool:
            ex = _to_exemplar(t)
            if ex is None:
                continue
            self._by_mcp[ex["mcp"]].append(ex)
            self._all.append(ex)

        # BM25 index over self._all (parallel to _all). Built lazily on first use.
        self._bm25_index: Optional[_BM25Index] = None
        if self.strategy == "bm25" and self._all:
            tokenized = [_tokenize(e["task"]) for e in self._all]
            self._bm25_index = _BM25Index(tokenized)

    @property
    def domains(self) -> List[str]:
        return sorted(self._by_mcp.keys())

    def size(self, mcp: Optional[str] = None) -> int:
        if mcp is None:
            return len(self._all)
        return len(self._by_mcp.get(mcp, []))

    def get(self, task: Any) -> List[Dict[str, Any]]:
        """Return up to ``self.k`` exemplars for ``task``.

        Excludes any pool entry whose task text exactly matches the query
        (defensive: the train and test sets should already be disjoint by
        construction, but this protects against accidental pool pollution).
        """
        if self.k == 0 or not self._all:
            return []

        query_text = _task_text(task)
        query_mcp = "<none>"
        if isinstance(task, dict):
            mcps = task.get("input", {}).get("mcp_servers") or []
        else:
            mcps = getattr(task, "candidate_mcp", None) or []
        if mcps:
            query_mcp = mcps[0]

        # Build candidate list
        if self.strategy == "random_in_domain":
            candidates = [
                e for e in self._by_mcp.get(query_mcp, []) if e["task"] != query_text
            ]
            if len(candidates) < self.k and self.pad_cross_domain:
                # Top up with any-domain candidates (excluding already chosen + self)
                already = {id(c) for c in candidates}
                extra = [
                    e for e in self._all
                    if e["task"] != query_text and id(e) not in already
                ]
                rng_extra = random.Random(f"{self.seed}|{query_text}|extra")
                rng_extra.shuffle(extra)
                candidates = candidates + extra
        elif self.strategy == "bm25":
            # Score every pool entry against the query, return top-K by BM25.
            if self._bm25_index is None or self._bm25_index.N == 0:
                return []
            q_tokens = _tokenize(query_text)
            if not q_tokens:
                return []
            # Exclude any exact text match (defensive)
            exclude = {i for i, e in enumerate(self._all) if e["task"] == query_text}
            scored = self._bm25_index.topk(q_tokens, self.k, exclude_idxs=exclude)
            return [self._all[i] for i, _ in scored if _ > 0.0]
        else:  # random_any
            candidates = [e for e in self._all if e["task"] != query_text]

        # Deterministic per-task selection
        rng = random.Random(f"{self.seed}|{query_text}")
        rng.shuffle(candidates)
        return candidates[: self.k]
