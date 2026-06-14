"""
Smoke tests for the in-context RA-ICL learning feature.

Verifies:
1. Split is deterministic, stratified by MCP, and persists/reloads cleanly.
2. ExemplarRetriever returns K in-domain exemplars, never includes the
   query task itself, and is reproducible across calls.
3. PredictionService and ValidationService inject exemplars into their
   prompts (verified via a recording mock LLM).
4. build_llm_cache plumbs the retriever through and tags entries with
   `_raicl_k`.
5. run_experiment honors `task_filter_fingerprints` to restrict
   evaluation to the test split.

Run from repo root:
    python scripts\test_ra_icl.py
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.services.split_service import (
    build_split, load_or_build_split, TaskSplit, _task_fingerprint as fp_fn,
)
from app.services.exemplar_retriever import ExemplarRetriever


def load_astra():
    path = os.path.join(ROOT, "datasets", "astra_03_tools.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────
# 1. Split tests
# ─────────────────────────────────────────────────────────────────────────

def test_split_deterministic_and_stratified():
    tasks = load_astra()
    s1 = build_split(tasks, ratio=0.7, seed=42)
    s2 = build_split(tasks, ratio=0.7, seed=42)
    assert s1.train_fingerprints == s2.train_fingerprints, "Split is not deterministic"
    assert s1.test_fingerprints == s2.test_fingerprints, "Split is not deterministic"

    # No overlap between train and test
    assert set(s1.train_fingerprints).isdisjoint(set(s1.test_fingerprints)), \
        "Train and test fingerprints overlap"

    # Each correct MCP bucket got at least 1 test task (where pool > 1)
    for mcp, cnt in s1.per_mcp_counts.items():
        assert cnt["train"] + cnt["test"] == cnt["total"], f"{mcp} counts don't sum"
        if cnt["total"] > 1:
            assert cnt["test"] >= 1, f"{mcp} has 0 test tasks"
            assert cnt["train"] >= 1, f"{mcp} has 0 train tasks"

    # Ratio is approximately right
    total_correct = sum(c["total"] for c in s1.per_mcp_counts.values())
    train_share = len(s1.train_fingerprints) / total_correct
    assert 0.65 < train_share < 0.75, f"Train share {train_share:.2f} not near 0.70"

    print(f"  ✓ deterministic + stratified · {len(s1.train_fingerprints)} train / "
          f"{len(s1.test_fingerprints)} test / {len(s1.other_fingerprints)} other")


def test_split_persist_and_reload():
    tasks = load_astra()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "split.json")
        s1 = load_or_build_split(tasks, path=path, ratio=0.7, seed=42)
        assert os.path.exists(path), "Split file was not persisted"

        # Reloading must give the same split without rebuilding
        s2 = load_or_build_split(tasks, path=path, ratio=0.7, seed=42)
        assert s1.train_fingerprints == s2.train_fingerprints
        assert s1.test_fingerprints == s2.test_fingerprints
    print("  ✓ persists to disk and reloads identically")


def test_split_classify():
    tasks = load_astra()
    s = build_split(tasks, ratio=0.7, seed=42)
    train_tasks = s.filter_train(tasks)
    test_tasks = s.filter_test(tasks)
    other_tasks = s.filter_other(tasks)
    # Use unique fingerprint counts since the dataset can contain duplicate tasks
    train_unique = {fp_fn(t) for t in train_tasks}
    test_unique = {fp_fn(t) for t in test_tasks}
    other_unique = {fp_fn(t) for t in other_tasks}
    assert train_unique == set(s.train_fingerprints), \
        f"train fp mismatch: filter={len(train_unique)} vs split={len(s.train_fingerprints)}"
    assert test_unique == set(s.test_fingerprints)
    assert other_unique == set(s.other_fingerprints)
    assert all(s.classify(t) == "train" for t in train_tasks[:5])
    assert all(s.classify(t) == "test" for t in test_tasks[:5])
    print(f"  ✓ classify/filter consistent · {len(train_unique)} train / {len(test_unique)} test / {len(other_unique)} other")


# ─────────────────────────────────────────────────────────────────────────
# 2. Retriever tests
# ─────────────────────────────────────────────────────────────────────────

def test_retriever_in_domain_and_excludes_self():
    tasks = load_astra()
    s = build_split(tasks, ratio=0.7, seed=42)
    train_tasks = s.filter_train(tasks)
    test_tasks = s.filter_test(tasks)

    retriever = ExemplarRetriever(train_tasks, k=3, strategy="random_in_domain", seed=42)

    for test_task in test_tasks[:10]:
        exs = retriever.get(test_task)
        assert len(exs) == 3, f"Expected 3 exemplars, got {len(exs)}"
        # Self-exclusion (should never apply since splits are disjoint, but
        # the defensive check should still hold)
        test_text = test_task["input"]["task"]
        for e in exs:
            assert e["task"] != test_text, "Retriever returned the query task!"
        # In-domain (primary MCP match)
        query_mcp = test_task["input"]["mcp_servers"][0]
        in_domain = sum(1 for e in exs if e["mcp"] == query_mcp)
        assert in_domain == 3, f"Expected all in-domain, got {in_domain}/3 for {query_mcp}"

    # Determinism — same retriever, same task → same exemplars
    t = test_tasks[0]
    a = retriever.get(t)
    b = retriever.get(t)
    assert [e["task"] for e in a] == [e["task"] for e in b], "Retriever not deterministic"
    print(f"  ✓ in-domain · self-excluding · deterministic")


def test_retriever_k_zero():
    tasks = load_astra()
    s = build_split(tasks, ratio=0.7, seed=42)
    retriever = ExemplarRetriever(s.filter_train(tasks), k=0)
    assert retriever.get(s.filter_test(tasks)[0]) == []
    print("  ✓ k=0 returns empty list")


def test_retriever_no_pad_returns_in_domain_only():
    """With pad_cross_domain=False and huge k, should return all & only in-domain train tasks."""
    tasks = load_astra()
    s = build_split(tasks, ratio=0.7, seed=42)
    train_tasks = s.filter_train(tasks)
    test_tasks = s.filter_test(tasks)
    retriever = ExemplarRetriever(train_tasks, k=10_000, strategy="random_in_domain",
                                  seed=42, pad_cross_domain=False)
    # Pick a test task and count its in-domain train pool size
    t = test_tasks[0]
    query_mcp = t["input"]["mcp_servers"][0]
    in_domain_pool = [tr for tr in train_tasks
                      if tr.get("input", {}).get("mcp_servers", [None])[0] == query_mcp]
    exs = retriever.get(t)
    # All returned exemplars must be in-domain
    assert all(e["mcp"] == query_mcp for e in exs), "no-pad leaked cross-domain"
    # Length should match in-domain pool (minus any self-matches, which shouldn't occur)
    assert len(exs) == len(in_domain_pool), \
        f"expected {len(in_domain_pool)} in-domain, got {len(exs)}"
    # And with pad_cross_domain=True + huge k, should return more (full train pool)
    retriever_pad = ExemplarRetriever(train_tasks, k=10_000, strategy="random_in_domain",
                                       seed=42, pad_cross_domain=True)
    exs_pad = retriever_pad.get(t)
    assert len(exs_pad) > len(exs), "pad mode should return more exemplars"
    print(f"  ✓ no-pad: {len(exs)} in-domain only · pad: {len(exs_pad)} total")


def test_retriever_random_any_uniform_pool():
    """random_any strategy should ignore in-domain filter; K caps the size."""
    tasks = load_astra()
    s = build_split(tasks, ratio=0.7, seed=42)
    train_tasks = s.filter_train(tasks)
    test_tasks = s.filter_test(tasks)
    t = test_tasks[0]
    query_mcp = t["input"]["mcp_servers"][0]

    # K smaller than pool: cap respected, multiple MCPs present.
    retriever = ExemplarRetriever(train_tasks, k=50, strategy="random_any",
                                  seed=42, pad_cross_domain=True)
    exs = retriever.get(t)
    assert len(exs) == 50, f"expected K=50 exemplars, got {len(exs)}"
    mcps = {e["mcp"] for e in exs}
    assert len(mcps) > 1, "random_any should produce multi-MCP exemplars"
    # Most exemplars should NOT be query_mcp (probabilistic; assert <90% to
    # rule out accidental in-domain bias).
    pct_same = sum(1 for e in exs if e["mcp"] == query_mcp) / len(exs)
    assert pct_same < 0.9, f"random_any unexpectedly skewed to query mcp: {pct_same:.0%}"

    # Huge K: returns full pool (excluding self).
    retriever_all = ExemplarRetriever(train_tasks, k=10_000, strategy="random_any",
                                      seed=42, pad_cross_domain=True)
    exs_all = retriever_all.get(t)
    assert len(exs_all) == len(train_tasks), \
        f"all-train should return {len(train_tasks)} exemplars, got {len(exs_all)}"
    print(f"  ✓ random_any K=50: {len(exs)} exemplars across {len(mcps)} MCPs, "
          f"{pct_same:.0%} same as query · all-train: {len(exs_all)}")


def test_raicl_widget_resolver():
    """Widget option strings should resolve to expected RAICLChoice values."""
    from app.ui.raicl_widget import _resolve

    # Selection-mode percentage options use random_any
    c = _resolve("25% train")
    assert c.strategy == "random_any"
    assert c.resolve_k(400) == 100
    c = _resolve("50% train")
    assert c.resolve_k(405) == 202, f"got {c.resolve_k(405)}"
    c = _resolve("75% train")
    assert c.resolve_k(405) == 304, f"got {c.resolve_k(405)}"
    c = _resolve("All train")
    assert c.strategy == "random_any"
    # Validation-mode literal-K options use random_in_domain
    c = _resolve("3")
    assert c.strategy == "random_in_domain" and c.resolve_k(999) == 3
    c = _resolve("All in-domain")
    assert c.strategy == "random_in_domain" and c.pad_cross_domain is False
    print("  ✓ widget resolver maps all option strings correctly")


# ─────────────────────────────────────────────────────────────────────────
# 3. Prompt injection tests (no real LLM)
# ─────────────────────────────────────────────────────────────────────────

class RecordingLLM:
    """Mock LLMProvider that records prompts and returns fixed JSON."""

    def __init__(self, response: str):
        self.response = response
        self.system_prompts = []
        self.user_prompts = []

    def is_configured(self):
        return True

    def query(self, system_prompt: str, user_prompt: str):
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        return self.response


def test_prediction_service_injects_exemplars():
    from app.services.prediction_service import PredictionService
    from app.loaders.mcp_loader import load_mcp_personas
    from app.models.astra import AstraTask

    personas, _errs = load_mcp_personas(os.path.join(ROOT, "mcp_servers"))
    fake_response = json.dumps({
        "is_valid": True, "justification": "ok",
        "selections": [
            {"tool": "search-wikipedia", "mcp": "wikipedia-mcp"},
            {"tool": "get-article", "mcp": "wikipedia-mcp"},
            {"tool": "get-summary", "mcp": "wikipedia-mcp"},
        ],
        "mission_metrics": {"capability_coverage": 1.0, "task_alignment": 0.9},
        "issue_metadata": {"codes": [], "details": []},
    })
    llm = RecordingLLM(fake_response)
    svc = PredictionService(llm, personas)

    task = AstraTask(
        task="Find articles about the moon landing",
        candidate_tools=["search-wikipedia"],
        candidate_mcp=["wikipedia-mcp"],
        groundtruth_tools=["search-wikipedia", "get-article", "get-summary"],
        groundtruth_mcp=["wikipedia-mcp"],
        match_tag="correct",
    )
    exemplars = [
        {"task": "Look up info on Albert Einstein", "mcp": "wikipedia-mcp",
         "tools": ["search-wikipedia", "get-article", "get-summary"]},
        {"task": "Get article about Python language", "mcp": "wikipedia-mcp",
         "tools": ["search-wikipedia", "get-article", "get-related-topics"]},
    ]

    # No exemplars → no examples block
    svc.run_selection(task)
    assert "RETRIEVED EXAMPLES" not in llm.user_prompts[-1]

    # With exemplars → examples block present
    svc.run_selection(task, exemplars=exemplars)
    last = llm.user_prompts[-1]
    assert "RETRIEVED EXAMPLES" in last
    assert "Albert Einstein" in last
    assert "Python language" in last
    assert "[END EXAMPLES]" in last
    # The model's instructions should still be present
    assert "User Task" in last
    print("  ✓ PredictionService prompt contains EXAMPLES block when exemplars passed")


def test_validation_service_injects_exemplars():
    from app.services.validation_service import ValidationService
    from app.loaders.mcp_loader import load_mcp_personas
    from app.models.astra import AstraTask

    personas, _errs = load_mcp_personas(os.path.join(ROOT, "mcp_servers"))
    fake_response = json.dumps({
        "is_valid": True, "justification": "ok",
        "selections": [], "mission_metrics": {"capability_coverage": 1.0, "task_alignment": 0.9},
        "issue_metadata": {"codes": [], "details": []},
        "domain_context": {"expected": "wikipedia-mcp", "actual": "wikipedia-mcp"},
    })
    llm = RecordingLLM(fake_response)
    svc = ValidationService(llm, personas)

    task = AstraTask(
        task="Find articles about the moon landing",
        candidate_tools=["search-wikipedia", "get-article", "get-summary"],
        candidate_mcp=["wikipedia-mcp"],
        groundtruth_tools=["search-wikipedia", "get-article", "get-summary"],
        groundtruth_mcp=["wikipedia-mcp"],
        match_tag="correct",
    )
    exemplars = [
        {"task": "Look up info on Marie Curie", "mcp": "wikipedia-mcp",
         "tools": ["search-wikipedia", "get-article", "get-summary"]},
    ]

    svc.run_validation(task)
    assert "RETRIEVED EXAMPLES" not in llm.user_prompts[-1]

    svc.run_validation(task, exemplars=exemplars)
    last = llm.user_prompts[-1]
    assert "RETRIEVED EXAMPLES" in last
    assert "Marie Curie" in last
    assert "is_valid=true" in last
    print("  ✓ ValidationService prompt contains EXAMPLES block when exemplars passed")


# ─────────────────────────────────────────────────────────────────────────
# 4. build_llm_cache plumbing
# ─────────────────────────────────────────────────────────────────────────

def test_build_llm_cache_uses_retriever(monkeypatch=None):
    """Patch the LLM provider so we can observe prompts and `_raicl_k`."""
    from app.services import experiment_runner
    from app.loaders.mcp_loader import load_mcp_personas

    personas, _errs = load_mcp_personas(os.path.join(ROOT, "mcp_servers"))
    tasks = load_astra()
    s = build_split(tasks, ratio=0.7, seed=42)
    train_tasks = s.filter_train(tasks)
    # Just take 3 test tasks to keep it fast
    test_tasks = s.filter_test(tasks)[:3]

    retriever = ExemplarRetriever(train_tasks, k=2, strategy="random_in_domain", seed=42)

    # Monkeypatch the LLMProvider import inside build_llm_cache to use a stub.
    import app.services.llm_provider as llm_mod

    class StubLLM:
        def __init__(self, *a, **kw): self.model = kw.get("model", "stub")
        def is_configured(self): return True
        def query(self, sp, up):
            # Branch on whether this is selection or validation
            if "Meta-Level" in sp:
                return json.dumps({"is_valid": True, "justification": "ok",
                                    "selections": [], "mission_metrics": {},
                                    "issue_metadata": {}, "domain_context": {}})
            return json.dumps({
                "is_valid": True, "justification": "ok",
                "selections": [{"tool": "x", "mcp": "y"}] * 3,
                "mission_metrics": {}, "issue_metadata": {}
            })

    original = llm_mod.LLMProvider
    llm_mod.LLMProvider = StubLLM
    try:
        cache = experiment_runner.build_llm_cache(
            test_tasks, personas, api_key="stub", model="stub",
            mode="selection", retriever=retriever, max_retries=0,
        )
    finally:
        llm_mod.LLMProvider = original

    assert len(cache) == 3
    for entry in cache.values():
        assert entry.get("_raicl_k") == 2, f"Expected _raicl_k=2, got {entry.get('_raicl_k')}"
        assert entry.get("_mode") == "selection"
    print(f"  ✓ build_llm_cache passes retriever + tags entries with _raicl_k")


# ─────────────────────────────────────────────────────────────────────────
# 5. run_experiment task_filter_fingerprints
# ─────────────────────────────────────────────────────────────────────────

def test_run_experiment_filter():
    from app.services import experiment_runner
    from app.services.experiment_config import EXPERIMENT_MAP
    from app.loaders.mcp_loader import load_mcp_personas

    personas, _errs = load_mcp_personas(os.path.join(ROOT, "mcp_servers"))
    tasks = load_astra()
    s = build_split(tasks, ratio=0.7, seed=42)
    # Pick 2 test tasks
    test_fps = set(s.test_fingerprints[:2])

    config = EXPERIMENT_MAP["E1"]
    metrics, results = experiment_runner.run_experiment(
        config, tasks, personas, mode="selection",
        llm_cache=None,  # simulation mode
        task_filter_fingerprints=test_fps,
    )
    # Filter is fingerprint-based; the dataset may contain multiple rows per fingerprint.
    # Verify the filter sharply restricts evaluation (vs the unfiltered 6 × len(tasks)).
    n_matching_tasks = sum(1 for t in tasks if fp_fn(t) in test_fps)
    expected = 6 * n_matching_tasks
    assert len(results) == expected, f"Expected {expected} results, got {len(results)}"
    assert len(results) < 6 * len(tasks), "Filter did not restrict evaluation"
    print(f"  ✓ run_experiment filter restricted to {len(test_fps)} fps → "
          f"{n_matching_tasks} tasks × 6 personas = {len(results)} evaluations")


# ─────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────

TESTS = [
    ("Split: deterministic + stratified", test_split_deterministic_and_stratified),
    ("Split: persist + reload",            test_split_persist_and_reload),
    ("Split: classify + filter",           test_split_classify),
    ("Retriever: in-domain, dedup",        test_retriever_in_domain_and_excludes_self),
    ("Retriever: k=0",                     test_retriever_k_zero),
    ("Retriever: no-pad in-domain only",   test_retriever_no_pad_returns_in_domain_only),
    ("Retriever: random_any uniform",      test_retriever_random_any_uniform_pool),
    ("Widget: option resolver",            test_raicl_widget_resolver),
    ("Prompt: PredictionService inject",   test_prediction_service_injects_exemplars),
    ("Prompt: ValidationService inject",   test_validation_service_injects_exemplars),
    ("Runner: build_llm_cache retriever",  test_build_llm_cache_uses_retriever),
    ("Runner: run_experiment filter",      test_run_experiment_filter),
]


def main():
    failed = 0
    for name, fn in TESTS:
        print(f"[{name}]")
        try:
            fn()
        except AssertionError as e:
            print(f"  ✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print()
    if failed:
        print(f"❌ {failed}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"✅ All {len(TESTS)} tests passed")


if __name__ == "__main__":
    main()
