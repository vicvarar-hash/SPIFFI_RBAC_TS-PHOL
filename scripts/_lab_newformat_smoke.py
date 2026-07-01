"""Smoke test: the Post-Experiment Lab consumes ``llm_inference_v1`` logs end-to-end.

Exercises the new-format code paths directly (list_run_logs ordering, _row_lookup,
a small replay, headline + corrective), then a render-only AppTest of the page.
"""
import os
import sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))


def _functional():
    from app.services import replay_service as rs
    from app.loaders.astra_loader import load_astra_dataset
    from app.ui.post_experiment_lab import _row_lookup, _corrective

    logs = rs.list_run_logs()
    new = [l for l in logs if l.get("schema") == "llm_inference_v1"]
    assert new, "no llm_inference_v1 logs listed"
    assert logs[0].get("schema") == "llm_inference_v1", "new-format logs should list first"
    val = next(l for l in new if l["mode"] == "validation")
    print(f"listed {len(new)} new-format logs; using {val['name']} ({val['model']}, {val['mode']})")

    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    rows, summ, _ = rs.replay_experiment(val["path"], tasks, experiment="E1", limit=120)
    h = rs.headline(rows)
    print(f"replay rows={len(rows)} fidelity={summ['fidelity']:.3f} "
          f"secfail={h['secfail']:.3f} legit_allow={h['legit_allow']:.3f}")
    assert len(rows) == 120 and summ["fidelity"] == 1.0  # nothing logged to diverge from

    lookup = _row_lookup(val["path"], "E1")
    assert lookup, "empty lookup"
    sample = rows[0]
    info = lookup.get((sample.persona, sample.task_idx))
    assert info is not None and "is_valid" in info, "lookup missing per-row info"
    c = _corrective(rows, lookup)
    print(f"corrective verdicts={c['has_verdict']} "
          f"catches={c['illeg']['vd']}/{c['illeg']['vd']+c['illeg']['va']} "
          f"rescues={c['legit']['ia']}/{c['legit']['ia']+c['legit']['id']}")
    assert c["has_verdict"] > 0, "validation log should yield LLM verdicts"

    # Selection: verdict must be absent (no valid/invalid in selection mode).
    seln = next((l for l in new if l["mode"] == "selection"), None)
    if seln:
        srows, _, _ = rs.replay_experiment(seln["path"], tasks, experiment="E1", limit=120)
        slk = _row_lookup(seln["path"], "E1")
        sc = _corrective(srows, slk)
        print(f"selection corrective verdicts={sc['has_verdict']} (expected 0)")
        assert sc["has_verdict"] == 0, "selection logs must not produce phantom verdicts"
    print("FUNCTIONAL: PASS")


def _render():
    from streamlit.testing.v1 import AppTest

    def page():
        import os
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        from app.ui.post_experiment_lab import render_post_experiment_lab
        from app.loaders.astra_loader import load_astra_dataset
        from app.loaders.mcp_loader import load_mcp_personas
        tasks = load_astra_dataset("datasets/astra_03_tools.json")
        personas, _ = load_mcp_personas("mcp_servers")
        render_post_experiment_lab(tasks, personas)

    at = AppTest.from_function(page).run(timeout=120)
    assert not at.exception, f"render raised: {at.exception}"
    print(f"RENDER: PASS ({len(at.selectbox)} selectboxes, {len(at.button)} buttons)")


if __name__ == "__main__":
    _functional()
    _render()
    print("\nALL SMOKE PASSED ✅")
