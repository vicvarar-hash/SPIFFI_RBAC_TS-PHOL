"""Producer→consumer contract test (no real LLM).

Mocks build_llm_cache to validate that produce_inference_log assembles a correct
llm_inference_v1 log (task_idx, tool_match/jaccard, verdict) and that the
Post-Experiment Lab consumer (replay_experiment) governs it without error.
"""
import os
import sys
import tempfile

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

import app.services.llm_inference_producer as prod
from app.services.experiment_runner import _task_fingerprint, llm_cache_key
from app.services.llm_inference_log import save_log
from app.services import replay_service as rs
from app.loaders.astra_loader import load_astra_dataset
from app.loaders.mcp_loader import load_mcp_personas


def _fake_cache_factory(mode):
    def fake_build_llm_cache(infer_tasks, personas, **kw):
        cache = {}
        for t in infer_tasks:
            key = llm_cache_key(_task_fingerprint(t), None)
            cand_tools = list(getattr(t, "candidate_tools", []) or [])
            cand_mcp = list(getattr(t, "candidate_mcp", []) or [])
            if mode == "selection":
                cache[key] = {"_mode": "selection",
                              "selected_tools": cand_tools[:2],
                              "selected_mcps": cand_mcp[:1]}
            else:
                cache[key] = {"_mode": "validation",
                              "selected_tools": cand_tools,
                              "selected_mcps": cand_mcp,
                              "is_valid": getattr(t, "match_tag", "null") == "correct",
                              "issue_codes": []}
        return cache
    return fake_build_llm_cache


def run(mode):
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    personas, _ = load_mcp_personas("mcp_servers")
    sub = tasks[:60]  # task_idx 0..59 == full-dataset indices

    prod.build_llm_cache = _fake_cache_factory(mode)
    log = prod.produce_inference_log(sub, personas, model="mock-model",
                                     provider="mock", api_key="x", mode=mode)

    assert log["schema"] == "llm_inference_v1"
    assert log["mode"] == mode and log["model"] == "mock-model"
    assert len(log["tasks"]) == len(sub), f"{len(log['tasks'])} != {len(sub)}"
    idxs = [t["task_idx"] for t in log["tasks"]]
    assert idxs == list(range(len(sub))), "task_idx must be the dataset index"
    for t in log["tasks"]:
        assert set(t) >= {"task_idx", "selected_tools", "selected_mcps", "is_valid",
                          "issue_codes", "match_tag", "tool_match", "tool_jaccard", "llm_failed"}
        if mode == "validation":
            assert t["tool_match"] is True  # selected == candidate
            assert t["is_valid"] is not None
        else:
            assert t["is_valid"] is None  # selection has no verdict

    tmp = os.path.join(tempfile.gettempdir(), f"_contract_{mode}.json")
    save_log(tmp, log)

    rows, summ, _ = rs.replay_experiment(tmp, tasks, experiment="E1", limit=None)
    assert len(rows) == len(sub) * 6, f"{len(rows)} rows (expected {len(sub)*6})"
    h = rs.headline(rows)
    print(f"  {mode:10s}: tasks={len(log['tasks'])} rows={len(rows)} "
          f"fidelity={summ['fidelity']:.2f} secfail={h['secfail']:.3f} "
          f"legit_allow={h['legit_allow']:.3f}")


if __name__ == "__main__":
    run("selection")
    run("validation")
    print("PRODUCER CONTRACT: PASS ✅")
