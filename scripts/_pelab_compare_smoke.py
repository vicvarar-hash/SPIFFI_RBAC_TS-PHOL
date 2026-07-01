"""Drive a full Run-comparison in the Post-Experiment Lab (exercises sampling + new UI)."""
import os
import sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

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


if __name__ == "__main__":
    at = AppTest.from_function(page).run(timeout=300)
    assert not at.exception, f"initial render: {at.exception}"
    # Pick a VALIDATION log (so the corrective view renders) + the quick stratified preset.
    val_opt = next(o for o in at.selectbox[0].options if "validation" in o)
    at.selectbox[0].set_value(val_opt).run(timeout=300)
    at.selectbox[1].set_value("~500 (quick · stratified)").run(timeout=300)
    btn = [b for b in at.button if "Run comparison" in b.label]
    assert btn, "Run comparison button not found"
    btn[0].click().run(timeout=600)
    assert not at.exception, f"after Run comparison: {at.exception}"
    # Section headers (st.markdown) + the explainer expander (st.expander label).
    md = " ".join(m.value for m in at.markdown)
    for needle in ("Which rules fired", "Corrective view", "LLM validation accuracy"):
        assert needle in md, f"missing section: {needle}"
    exp_labels = " ".join(getattr(e, "label", "") or "" for e in at.expander)
    assert "How to read these results" in exp_labels, f"explainer expander missing; expanders={exp_labels!r}"
    print(f"FULL COMPARISON RENDER: PASS — validation log {val_opt!r}, headers + explainer present, 0 exceptions")
