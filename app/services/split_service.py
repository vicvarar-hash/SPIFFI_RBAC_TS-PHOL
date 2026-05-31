"""
Train / test split utility for in-context few-shot learning experiments.

Builds a deterministic, stratified-by-MCP split of `correct`-tagged ASTRA
tasks. Only `correct` tasks are eligible (they have trustworthy groundtruth
bundles). `wrong` and `null` tasks are returned as a separate cohort so
callers can evaluate adversarial / out-of-distribution behaviour
independently.

The split is persisted to disk (default
``datasets/splits/correct_70_30_seed42.json``) so both the Prediction Lab
and the Experiment Lab see the same train / test partition.

The split is keyed by *task fingerprint* (the same 16-char hash the
experiment runner uses for LLM cache deduplication), so callers can
classify any task in O(1) regardless of representation.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_SPLIT_DIR = os.path.join("datasets", "splits")
DEFAULT_SPLIT_PATH = os.path.join(DEFAULT_SPLIT_DIR, "correct_70_30_seed42_v2.json")


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _task_fingerprint(task: Any) -> str:
    """Stable 16-char fingerprint matching experiment_runner._task_fingerprint.

    Includes ``match_tag`` so that a task with identical (text, mcps) but
    different bundle category (correct vs wrong vs null) maps to distinct
    fingerprints. Without this, the train/test/other partitions overlap
    in fingerprint space (same text+mcps can appear in both correct and
    wrong rows of the ASTRA dataset).
    """
    if isinstance(task, dict):
        text = task["input"]["task"]
        mcps = task["input"]["mcp_servers"] or []
        tag = task.get("match_tag") or "null"
    else:
        text = task.task
        mcps = task.candidate_mcp or []
        tag = getattr(task, "match_tag", None) or "null"
    raw = f"{text}|{','.join(sorted(mcps))}|{tag}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _primary_mcp(task: Any) -> str:
    if isinstance(task, dict):
        mcps = task.get("input", {}).get("mcp_servers") or []
    else:
        mcps = task.candidate_mcp or []
    return mcps[0] if mcps else "<none>"


def _match_tag(task: Any) -> str:
    if isinstance(task, dict):
        return task.get("match_tag") or "null"
    return getattr(task, "match_tag", None) or "null"


# ─────────────────────────────────────────────────────────────────────────
# Split data class
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class TaskSplit:
    """A reproducible train/test partition."""

    ratio: float
    seed: int
    train_fingerprints: List[str] = field(default_factory=list)
    test_fingerprints: List[str] = field(default_factory=list)
    other_fingerprints: List[str] = field(default_factory=list)  # wrong/null
    per_mcp_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def train_set(self) -> set:
        return set(self.train_fingerprints)

    @property
    def test_set(self) -> set:
        return set(self.test_fingerprints)

    @property
    def other_set(self) -> set:
        return set(self.other_fingerprints)

    def classify(self, task: Any) -> str:
        """Return 'train', 'test', or 'other' for a task."""
        fp = _task_fingerprint(task)
        if fp in self.train_set:
            return "train"
        if fp in self.test_set:
            return "test"
        return "other"

    def filter_train(self, tasks: Iterable[Any]) -> List[Any]:
        s = self.train_set
        return [t for t in tasks if _task_fingerprint(t) in s]

    def filter_test(self, tasks: Iterable[Any]) -> List[Any]:
        s = self.test_set
        return [t for t in tasks if _task_fingerprint(t) in s]

    def filter_other(self, tasks: Iterable[Any]) -> List[Any]:
        s = self.other_set
        return [t for t in tasks if _task_fingerprint(t) in s]

    def to_dict(self) -> dict:
        return {
            "ratio": self.ratio,
            "seed": self.seed,
            "train_fingerprints": self.train_fingerprints,
            "test_fingerprints": self.test_fingerprints,
            "other_fingerprints": self.other_fingerprints,
            "per_mcp_counts": self.per_mcp_counts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskSplit":
        return cls(
            ratio=float(data.get("ratio", 0.7)),
            seed=int(data.get("seed", 42)),
            train_fingerprints=list(data.get("train_fingerprints", [])),
            test_fingerprints=list(data.get("test_fingerprints", [])),
            other_fingerprints=list(data.get("other_fingerprints", [])),
            per_mcp_counts=dict(data.get("per_mcp_counts", {})),
        )


# ─────────────────────────────────────────────────────────────────────────
# Build / load
# ─────────────────────────────────────────────────────────────────────────

def build_split(tasks: List[Any], ratio: float = 0.7, seed: int = 42) -> TaskSplit:
    """Build a deterministic stratified (by primary MCP) split.

    Only ``match_tag == "correct"`` tasks enter the train/test cohorts.
    Within each MCP bucket we sort fingerprints, then deterministically
    shuffle with ``seed`` and take the first ``ratio`` for training.
    """
    if not 0.0 < ratio < 1.0:
        raise ValueError(f"ratio must be in (0, 1), got {ratio}")

    correct_by_mcp: Dict[str, List[Tuple[str, Any]]] = defaultdict(list)
    other_fps: List[str] = []

    for t in tasks:
        fp = _task_fingerprint(t)
        if _match_tag(t) == "correct":
            correct_by_mcp[_primary_mcp(t)].append((fp, t))
        else:
            other_fps.append(fp)

    train_fps: List[str] = []
    test_fps: List[str] = []
    per_mcp_counts: Dict[str, Dict[str, int]] = {}

    rng = random.Random(seed)
    for mcp in sorted(correct_by_mcp.keys()):
        bucket = sorted(correct_by_mcp[mcp], key=lambda x: x[0])  # deterministic order
        rng.shuffle(bucket)
        n = len(bucket)
        n_train = max(1, int(round(n * ratio))) if n > 1 else n
        n_train = min(n_train, n - 1) if n > 1 else n  # leave at least 1 for test if possible
        train_part = bucket[:n_train]
        test_part = bucket[n_train:]
        train_fps.extend(fp for fp, _ in train_part)
        test_fps.extend(fp for fp, _ in test_part)
        per_mcp_counts[mcp] = {
            "total": n,
            "train": len(train_part),
            "test": len(test_part),
        }

    return TaskSplit(
        ratio=ratio,
        seed=seed,
        train_fingerprints=sorted(train_fps),
        test_fingerprints=sorted(test_fps),
        other_fingerprints=sorted(other_fps),
        per_mcp_counts=per_mcp_counts,
    )


def load_or_build_split(
    tasks: List[Any],
    path: str = DEFAULT_SPLIT_PATH,
    ratio: float = 0.7,
    seed: int = 42,
    force_rebuild: bool = False,
) -> TaskSplit:
    """Load a persisted split or build + persist one if missing."""
    if not force_rebuild and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            split = TaskSplit.from_dict(data)
            if abs(split.ratio - ratio) < 1e-9 and split.seed == seed:
                return split
        except (json.JSONDecodeError, KeyError, ValueError):
            pass  # fall through and rebuild

    split = build_split(tasks, ratio=ratio, seed=seed)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(split.to_dict(), f, indent=2)
    return split
