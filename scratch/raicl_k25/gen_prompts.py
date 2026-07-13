"""Generate byte-identical selection prompts for the k=25 RA-ICL exploratory run.

Captures the exact (system, user) prompt that PredictionService would send, via a
FakeLLM that records the prompt instead of calling any real model. NO API keys,
no LLM calls. Factors out the constant MCP catalog so a sub-agent can receive it
once and then process per-task variable suffixes.

Conditions per task:
  - baseline : k=0 (no exemplar block)
  - k25      : k=25 BM25 exemplars (strategy=bm25, seed=42, pad_cross_domain=True)

Output: scratch/raicl_k25/payload.json
"""
from __future__ import annotations

import json
import os

from app.loaders.mcp_loader import load_mcp_personas
from app.loaders.astra_loader import load_astra_dataset
from app.services.split_service import load_or_build_split
from app.services.exemplar_retriever import ExemplarRetriever
from app.services.experiment_runner import _task_fingerprint, _to_astra_task
from app.services.prediction_service import PredictionService
from app.services.intent_engine import IntentEngine

N_CORRECT = 50  # correct-test tasks for the exploratory exact-match read
OUT = os.path.join("scratch", "raicl_k25", "payload.json")


class FakeLLM:
    """Records the (system, user) prompt and returns a benign empty selection."""

    def __init__(self):
        self.last = None

    def is_configured(self):
        return True

    def query(self, system, user):
        self.last = (system, user)
        return ('{"is_valid":true,"justification":"x","selections":[],'
                '"mission_metrics":{"capability_coverage":0.0,"task_alignment":0.0},'
                '"issue_metadata":{"codes":[],"details":[]}}')


def _common_prefix(a: str, b: str) -> str:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return a[:i]


def main():
    personas, _ = load_mcp_personas("mcp_servers")
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    split = load_or_build_split(tasks, ratio=0.7, seed=42)
    train = split.filter_train(tasks)

    retr25 = ExemplarRetriever(train_pool=train, k=25, strategy="bm25", pad_cross_domain=True)

    test_fps = set(split.test_fingerprints)
    correct_test = [t for t in tasks if _task_fingerprint(t) in test_fps]
    # Deterministic order for reproducibility.
    correct_test.sort(key=lambda t: _task_fingerprint(t))
    sample = correct_test[:N_CORRECT]

    fake = FakeLLM()
    svc = PredictionService(llm=fake, personas=personas, intent_engine=IntentEngine())

    # Determine the constant catalog prefix using the first task: the baseline and
    # k25 prompts diverge exactly at the exemplar block (right after the catalog),
    # so their longest common prefix is the catalog portion.
    t0 = sample[0]
    at0 = _to_astra_task(t0)
    svc.run_selection(at0, exemplars=None, allowed_mcps=None)
    sys0, base0 = fake.last
    svc.run_selection(at0, exemplars=retr25.get(t0), allowed_mcps=None)
    _, k25_0 = fake.last
    catalog_prefix = _common_prefix(base0, k25_0)

    records = []
    prefix_ok = True
    for t in sample:
        at = _to_astra_task(t)
        fp = _task_fingerprint(t)

        svc.run_selection(at, exemplars=None, allowed_mcps=None)
        _, u_base = fake.last
        svc.run_selection(at, exemplars=retr25.get(t), allowed_mcps=None)
        _, u_k25 = fake.last

        # Every prompt must start with the same catalog prefix.
        if not (u_base.startswith(catalog_prefix) and u_k25.startswith(catalog_prefix)):
            prefix_ok = False

        records.append({
            "id": fp,
            "match_tag": getattr(t, "match_tag", None),
            "candidate_mcp": list(at.candidate_mcp or []),
            "gold_tools": list(getattr(t, "groundtruth_tools", []) or []),
            "gold_mcp": list(getattr(t, "groundtruth_mcp", []) or []),
            "n_exemplars_k25": len(retr25.get(t)),
            "var_baseline": u_base[len(catalog_prefix):],
            "var_k25": u_k25[len(catalog_prefix):],
        })

    payload = {
        "system_prompt": sys0,
        "catalog_prefix": catalog_prefix,
        "n_tasks": len(records),
        "catalog_chars": len(catalog_prefix),
        "tasks": records,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    print("prefix_ok (catalog constant across all prompts):", prefix_ok)
    print("system chars:", len(sys0), "catalog chars:", len(catalog_prefix))
    print("tasks:", len(records))
    ex_var = records[0]
    print("sample var_baseline chars:", len(ex_var["var_baseline"]),
          "var_k25 chars:", len(ex_var["var_k25"]))
    print("sample task var_baseline tail:\n", ex_var["var_baseline"][:400])


if __name__ == "__main__":
    main()
