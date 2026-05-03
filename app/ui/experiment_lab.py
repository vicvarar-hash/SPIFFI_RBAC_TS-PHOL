"""
Experiment Lab — batch experiment execution, OPA baseline comparison, and access decision matrix explorer.

Three main sections:
1. Experiment Runner — execute E1–E4 configurations and view results
2. OPA Baseline Comparison — replay any saved log through OPA-equivalent evaluation
3. Access Decision Matrix — explore pre-computed ground truth governance decisions
"""

import os
import json
import hashlib
import logging
from datetime import datetime
import streamlit as st
import pandas as pd
from dataclasses import asdict
from typing import List, Dict
from collections import Counter, defaultdict

from app.services.experiment_config import (
    EXPERIMENTS, EXPERIMENT_MAP, EXPERIMENT_GROUPS,
    PERSONAS, LEGITIMATE_PAIRINGS, ExperimentConfig,
)
from app.services.experiment_runner import (
    run_experiment, compute_domain_breakdown, build_llm_cache,
    _task_fingerprint,
    ExperimentMetrics, RunResult,
)
from app.services.opa_comparison import run_opa_comparison

MATRIX_PATH = os.path.join("datasets", "access_decision_matrix.json")
LOG_DIR = os.path.join("datasets", "experiment_logs")

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Experiment log persistence
# ═══════════════════════════════════════════════════════════════════════

def _save_experiment_log(all_metrics: List, all_results: Dict,
                         mode: str, inference_mode: str,
                         llm_model: str = None) -> str:
    """Save full experiment results to a timestamped JSON log file.

    Returns the path to the saved log file.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    import re
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_mode = re.sub(r'[^\w\-]', '_', inference_mode)
    model_tag = f"_{re.sub(r'[^\w\-]', '_', llm_model)}" if llm_model else ""
    filename = f"run_{ts}_{safe_mode}{model_tag}.json"
    filepath = os.path.join(LOG_DIR, filename)

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "inference_mode": inference_mode,
        "llm_model": llm_model,
        "evaluation_mode": mode,
        "experiments": {},
    }

    for m in all_metrics:
        exp_name = m.name
        results = all_results.get(exp_name, [])

        # Serialize every row
        rows = []
        for r in results:
            rows.append(asdict(r))

        log_data["experiments"][exp_name] = {
            "metrics": m.to_dict(),
            "config": {
                "description": m.description,
            },
            "total_rows": len(rows),
            "rows": rows,
        }

    # Also store config details from the experiment definitions
    from app.services.experiment_config import EXPERIMENT_MAP
    for exp_name in log_data["experiments"]:
        cfg = EXPERIMENT_MAP.get(exp_name)
        if cfg:
            log_data["experiments"][exp_name]["config"].update({
                "rbac_fn": cfg.rbac_fn,
                "abac_fn": cfg.abac_fn,
                "tsphol_fn": cfg.tsphol_fn,
                "match_tag_filter": cfg.match_tag_filter,
            })

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, default=str)

    logger.info("Experiment log saved to %s", filepath)
    return filepath


# ═══════════════════════════════════════════════════════════════════════
# Cache helpers
# ═══════════════════════════════════════════════════════════════════════

def _regenerate_matrix():
    """Regenerate the Access Decision Matrix from the UI with progress tracking."""
    from scripts.generate_access_matrix import generate_matrix
    with st.spinner("🔄 Regenerating Access Decision Matrix... This may take a few minutes."):
        try:
            result = generate_matrix()
            total = result["metadata"]["total_rows"]
            st.success(f"✅ Matrix regenerated: **{total:,}** rows written to `{MATRIX_PATH}`")
            # Clear the cached version so it reloads
            _load_matrix.clear()
        except Exception as e:
            st.error(f"❌ Matrix generation failed: {e}")

@st.cache_data
def _load_matrix():
    """Load the access decision matrix from disk (cached)."""
    if not os.path.exists(MATRIX_PATH):
        return None
    with open(MATRIX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _current_policy_hashes() -> Dict[str, str]:
    """Compute current policy file hashes for staleness detection."""
    policy_files = ["rbac.yaml", "abac_rules.yaml", "tsphol_rules.yaml",
                    "domain_capability_ontology.json"]
    hashes = {}
    for pf in policy_files:
        path = os.path.join("policies", pf)
        if os.path.exists(path):
            with open(path, "rb") as f:
                hashes[pf] = hashlib.sha256(f.read()).hexdigest()[:12]
    return hashes


# ═══════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════

def render_experiment_lab(tasks, personas):
    st.title("🧪 Experiment Lab")
    st.markdown(
        "Run governance experiments and explore the pre-computed Access Decision Matrix "
        "that maps every *(persona × task)* combination through the full policy pipeline."
    )

    tab_runner, tab_opa, tab_matrix = st.tabs([
        "🚀 Experiment Runner",
        "🆚 OPA Baseline Comparison",
        "📊 Access Decision Matrix",
    ])

    with tab_runner:
        _render_experiment_runner(tasks, personas)

    with tab_opa:
        _render_opa_comparison()

    with tab_matrix:
        _render_matrix_explorer()


# ═══════════════════════════════════════════════════════════════════════
# Tab 1 — Experiment Runner
# ═══════════════════════════════════════════════════════════════════════

def _render_experiment_runner(tasks, personas):
    st.markdown("### Experiment Configurations")
    st.markdown(
        "Each experiment runs all **6 personas** across **all tasks** through the governance pipeline. "
        "E1 is the full baseline; E2–E4 perform **subtractive ablation** — removing one layer at a time "
        "from the top to measure each layer's marginal contribution."
    )

    # ── Experiment cards — 2×2 grid ──
    col_top1, col_top2 = st.columns(2)
    col_bot1, col_bot2 = st.columns(2)
    card_cols = [col_top1, col_top2, col_bot1, col_bot2]

    for col, cfg in zip(card_cols, EXPERIMENTS):
        with col:
            total_evals = len(PERSONAS) * len(tasks)

            # Highlight: full pipeline vs ablation vs control
            active_layers = []
            if cfg.rbac_fn != "open":
                active_layers.append("RBAC")
            if cfg.abac_fn != "open":
                active_layers.append("ABAC")
            if cfg.tsphol_fn != "open":
                active_layers.append("TS-PHOL")

            if len(active_layers) == 3:
                icon = "🛡️"
            elif len(active_layers) == 0:
                icon = "⚪"
            else:
                icon = "🔬"

            st.markdown(f"#### {cfg.name} {icon}")
            st.markdown(cfg.description)

            # Show which layers are active/disabled
            layers = []
            layers.append(f"RBAC: {'`on`' if cfg.rbac_fn != 'open' else '~~off~~'}")
            layers.append(f"ABAC: {'`on`' if cfg.abac_fn != 'open' else '~~off~~'}")
            layers.append(f"TS-PHOL: {'`on`' if cfg.tsphol_fn != 'open' else '~~off~~'}")

            st.caption(
                f"**Tasks:** {len(tasks):,} · **Evals:** {total_evals:,}"
            )
            st.caption(" · ".join(layers))

    st.markdown("---")

    # ── Inference mode selection ──
    st.markdown("### ⚙️ Inference Settings")
    inf_col1, inf_col2 = st.columns([2, 2])
    with inf_col1:
        inference_mode = st.radio(
            "Inference Mode",
            ["🧪 Simulation (Deterministic)", "🤖 Real LLM (API)"],
            horizontal=True,
            help="Simulation uses deterministic passthrough (no API calls). "
                 "Real LLM calls the OpenAI API once per unique task."
        )
        use_real_llm = inference_mode.startswith("🤖")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    llm_model = "gpt-4o"
    if use_real_llm:
        with inf_col2:
            llm_model = st.selectbox(
                "Model",
                ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
                help="Model used for tool selection inference."
            )
        if not api_key:
            st.warning("⚠️ Please provide your OpenAI API key in the **sidebar Settings** to run real LLM experiments.")

    # ── Run controls ──
    col_sel, col_mode, col_btn = st.columns([2, 2, 1])
    with col_sel:
        run_choice = st.selectbox(
            "Select Experiment",
            ["Run All (E1–E4)", "Run E1 (Full Pipeline)", "Run E2–E4 (Ablation)"]
            + [f"{e.name}: {e.description[:60]}" for e in EXPERIMENTS],
        )
    with col_mode:
        mode = st.radio("Mode", ["Selection (LLM-ResM)", "Validation"], horizontal=True)
        mode_str = "selection" if mode.startswith("Selection") else "validation"
    with col_btn:
        st.write("")  # spacing
        run_clicked = st.button("🚀 Run", type="primary", use_container_width=True)

    if run_choice == "Run All (E1–E4)":
        configs_to_run = list(EXPERIMENTS)
    elif run_choice == "Run E1 (Full Pipeline)":
        configs_to_run = [e for e in EXPERIMENTS if e.name == "E1"]
    elif run_choice == "Run E2–E4 (Ablation)":
        configs_to_run = [e for e in EXPERIMENTS if e.name in ("E2", "E3", "E4")]
    else:
        cname = run_choice.split(":")[0].strip()
        configs_to_run = [EXPERIMENT_MAP[cname]]

    # ── Results area ──
    if run_clicked:
        if use_real_llm and not api_key:
            st.error("Please enter your OpenAI API key before running.")
        else:
            _run_and_display(configs_to_run, tasks, personas, mode_str,
                             use_real_llm=use_real_llm, api_key=api_key,
                             llm_model=llm_model)
    elif "experiment_results" in st.session_state:
        _display_results(st.session_state["experiment_results"])
    else:
        st.info("Select a configuration and click **Run** to begin.")


def _run_and_display(configs: List[ExperimentConfig], tasks, personas,
                     mode: str, use_real_llm: bool = False,
                     api_key: str = None, llm_model: str = "gpt-4o"):
    """Execute experiments with progress tracking and display results."""
    all_metrics: List[ExperimentMetrics] = []
    all_results: Dict[str, List[RunResult]] = {}

    progress_bar = st.progress(0, text="Starting experiments...")
    status_text = st.empty()
    llm_cache = None

    # Phase 1: Build LLM cache if using real inference
    if use_real_llm:
        status_text.markdown("**Phase 1/2 — LLM Inference** (one API call per unique task)")

        # Collect all unique tasks across all configs
        all_tasks_for_cache = set()
        for config in configs:
            if config.match_tag_filter:
                for t in tasks:
                    tag = t.get("match_tag", "null") if isinstance(t, dict) else getattr(t, "match_tag", "null")
                    if tag == config.match_tag_filter:
                        all_tasks_for_cache.add(_task_fingerprint(t))
            else:
                for t in tasks:
                    all_tasks_for_cache.add(_task_fingerprint(t))

        unique_count = len(all_tasks_for_cache)
        st.info(f"🤖 Calling {llm_model} for **{unique_count}** unique tasks "
                f"(~{unique_count * 2:.0f}–{unique_count * 3:.0f}s estimated)")

        try:
            def llm_progress(info):
                cur = info["current"]
                tot = info["total"]
                errs = info.get("errors", 0)
                pct = cur / tot if tot > 0 else 0
                err_str = f" · ⚠️ {errs} errors" if errs > 0 else ""
                progress_bar.progress(
                    pct * 0.7,  # LLM phase is 70% of total progress
                    text=f"Phase 1: LLM Inference — {cur}/{tot} tasks{err_str}"
                )

            llm_cache = build_llm_cache(
                tasks, personas, api_key=api_key, model=llm_model,
                progress_callback=llm_progress,
            )

            failed = sum(1 for v in llm_cache.values() if v.get("_failed"))
            status_text.markdown(
                f"✅ **Phase 1 complete** — {len(llm_cache)} tasks cached"
                f"{f', ⚠️ {failed} failures' if failed else ''}"
            )
        except Exception as e:
            st.error(f"❌ LLM cache build failed: {e}")
            return

    # Phase 2: Run governance evaluation
    phase_label = "Phase 2/2" if use_real_llm else ""
    total_configs = len(configs)

    for cfg_idx, config in enumerate(configs):
        phase_text = f"{phase_label} — " if phase_label else ""
        status_text.markdown(f"**{phase_text}Governance Evaluation** — {config.name}: {config.description[:60]}")

        def progress_cb(info):
            if isinstance(info, dict):
                cur = info.get("current", 0)
                tot = info.get("total", 1)
                pct = cur / tot if tot > 0 else 0
            else:
                pct = float(info)
            overall = (cfg_idx + pct) / total_configs
            if use_real_llm:
                overall = 0.7 + overall * 0.3  # 70-100% range
            progress_bar.progress(overall, text=f"{config.name} — {pct:.0%}")

        metrics, results = run_experiment(config, tasks, personas, mode=mode,
                                          progress_callback=progress_cb,
                                          llm_cache=llm_cache)
        all_metrics.append(metrics)
        all_results[config.name] = results

    progress_bar.progress(1.0, text="Complete!")
    inference_label = f"real LLM ({llm_model})" if use_real_llm else "simulation"
    status_text.markdown(f"✅ **Completed {total_configs} experiment(s)** — {mode} mode, {inference_label}")

    # Show LLM failure summary if any
    total_failures = sum(m.llm_failures for m in all_metrics)
    if total_failures > 0:
        st.warning(f"⚠️ {total_failures} evaluations skipped due to LLM failures "
                   f"(excluded from governance metrics)")

    st.session_state["experiment_results"] = {
        "metrics": all_metrics,
        "results": all_results,
        "mode": mode,
        "inference_mode": "llm" if use_real_llm else "simulation",
        "llm_model": llm_model if use_real_llm else None,
    }

    # Persist full log to disk
    try:
        log_path = _save_experiment_log(
            all_metrics, all_results, mode,
            inference_mode="llm" if use_real_llm else "simulation",
            llm_model=llm_model if use_real_llm else None,
        )
        st.success(f"📄 Results log saved to `{log_path}`")
    except Exception as e:
        st.warning(f"⚠️ Could not save log: {e}")

    _display_results(st.session_state["experiment_results"])


def _display_results(data: dict):
    """Render experiment results dashboard."""
    metrics_list: List[ExperimentMetrics] = data["metrics"]
    results_dict: Dict[str, List[RunResult]] = data["results"]
    mode = data.get("mode", "selection")
    inf_mode = data.get("inference_mode", "simulation")
    llm_model = data.get("llm_model")

    if not metrics_list:
        st.warning("No results to display.")
        return

    # ── Inference badge ──
    if inf_mode == "llm":
        st.success(f"🤖 Results from **real LLM inference** ({llm_model})")
    else:
        st.info("🧪 Results from **deterministic simulation** (no API calls)")

    # ── Summary metrics ──
    st.markdown("### 📊 Summary Metrics")
    rows = []
    for m in metrics_list:
        row = {
            "Config": m.name,
            "Total": m.total,
            "F₁": f"{m.f1:.4f}",
            "Precision": f"{m.precision:.4f}",
            "Recall": f"{m.recall:.4f}",
            "SecFail": f"{m.security_failure_rate:.4f}",
            "Tool Acc": f"{m.tool_accuracy:.4f}",
            "Jaccard": f"{m.tool_jaccard_avg:.4f}",
            "ALLOW": m.allow_count,
            "DENY": m.deny_count,
            "TP": m.true_positive,
            "TN": m.true_negative,
            "FP": m.false_positive,
            "FN": m.false_negative,
        }
        if m.llm_failures > 0:
            row["LLM Fail"] = m.llm_failures
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Metric glossary ──
    with st.expander("📖 Metric Glossary", expanded=False):
        st.markdown("""
| Metric | Description |
|---|---|
| **F₁** | Harmonic mean of Precision and Recall — overall governance effectiveness (0–1, higher is better) |
| **Precision** | Of all requests denied, what fraction were truly illegitimate? High precision = few false alarms |
| **Recall** | Of all illegitimate requests, what fraction were caught? High recall = few missed threats |
| **SecFail** | Security Failure Rate — fraction of illegitimate requests that were **not** caught (1 − Recall). Lower is better |
| **Tool Acc** | LLM Tool Selection Accuracy — fraction of tasks where the LLM selected the **exact same** tools as the groundtruth |
| **Jaccard** | Average Jaccard similarity between LLM-selected and groundtruth tool sets (partial credit for overlapping selections) |
| **ALLOW** | Total requests permitted through the governance pipeline |
| **DENY** | Total requests blocked by any governance layer |
| **TP** | True Positive — illegitimate request correctly denied |
| **TN** | True Negative — legitimate request correctly allowed |
| **FP** | False Positive — legitimate request incorrectly denied (over-restriction) |
| **FN** | False Negative — illegitimate request incorrectly allowed (security gap) |
""")

    # ── Denial source ──
    st.markdown("### 🔒 Denial Source Attribution")
    denial_rows = []
    for m in metrics_list:
        denial_rows.append({
            "Config": m.name,
            "RBAC": m.rbac_denials,
            "ABAC": m.abac_denials,
            "TS-PHOL": m.tsphol_denials,
        })
    st.dataframe(pd.DataFrame(denial_rows), use_container_width=True, hide_index=True)

    # ── Detail view ──
    if results_dict:
        st.markdown("### 🔍 Detail View")
        selected_detail = st.selectbox("Configuration", list(results_dict.keys()))
        if selected_detail and selected_detail in results_dict:
            detail_results = results_dict[selected_detail]
            tab_persona, tab_domain, tab_raw = st.tabs(
                ["Per-Persona", "Per-Domain", "Raw Results"]
            )

            with tab_persona:
                persona_groups = {}
                for r in detail_results:
                    persona_groups.setdefault(r.persona, []).append(r)
                prows = []
                for persona, pr in sorted(persona_groups.items()):
                    tp = sum(1 for r in pr if not r.is_legitimate and r.final_decision in ("DENY", "DECEPTION_ROUTED"))
                    tn = sum(1 for r in pr if r.is_legitimate and r.final_decision == "ALLOW")
                    fp = sum(1 for r in pr if r.is_legitimate and r.final_decision in ("DENY", "DECEPTION_ROUTED"))
                    fn = sum(1 for r in pr if not r.is_legitimate and r.final_decision == "ALLOW")
                    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                    f1 = 2 * p * rec / (p + rec) if (p + rec) > 0 else 0.0
                    prows.append({
                        "Persona": PERSONAS.get(persona, {}).get("display_name", persona),
                        "Total": len(pr), "F₁": f"{f1:.4f}",
                        "TP": tp, "TN": tn, "FP": fp, "FN": fn,
                    })
                st.dataframe(pd.DataFrame(prows), use_container_width=True, hide_index=True)

            with tab_domain:
                breakdown = compute_domain_breakdown(detail_results)
                drows = []
                for domain, stats in breakdown.items():
                    drows.append({
                        "Domain": domain, "Total": stats["total"],
                        "F₁": f"{stats['f1']:.4f}",
                        "TP": stats["TP"], "TN": stats["TN"],
                        "FP": stats["FP"], "FN": stats["FN"],
                    })
                st.dataframe(pd.DataFrame(drows), use_container_width=True, hide_index=True)

            with tab_raw:
                raw_rows = [asdict(r) for r in detail_results[:500]]
                st.dataframe(pd.DataFrame(raw_rows), use_container_width=True, hide_index=True)
                st.caption(f"Showing first 500 of {len(detail_results)} results")

    # ── Comparison ──
    if len(metrics_list) >= 2:
        st.markdown("### ⚖️ Experiment Comparison")

        compare_data = []
        for m in metrics_list:
            compare_data.append({
                "Config": m.name,
                "F₁": m.f1,
                "Precision": m.precision,
                "Recall": m.recall,
                "Security Failure Rate": m.security_failure_rate,
                "Tool Accuracy": m.tool_accuracy,
                "Tool Jaccard Avg": m.tool_jaccard_avg,
            })
        df_compare = pd.DataFrame(compare_data).set_index("Config")
        st.bar_chart(df_compare)

        # Ablation delta table — subtractive chain: E4 → E3 → E2 → E1
        metrics_by_name = {m.name: m for m in metrics_list}
        e1 = metrics_by_name.get("E1")
        e4 = metrics_by_name.get("E4")
        ablation_chain = [
            ("E4", "E3", "TS-PHOL added (E4→E3)"),
            ("E3", "E2", "ABAC added (E3→E2)"),
            ("E2", "E1", "RBAC added (E2→E1)"),
        ]
        has_ablation = e1 and e4
        if has_ablation:
            st.markdown("##### 🔬 Subtractive Ablation: Layer-by-Layer Value")
            st.caption(
                "Starting from **E4 (no governance)** and adding layers one at a time. "
                "Each row shows the marginal contribution of adding that layer. "
                "Δ ALLOW < 0 means the layer blocked additional unsafe requests."
            )
            delta_rows = []
            for from_name, to_name, desc in ablation_chain:
                from_m = metrics_by_name.get(from_name)
                to_m = metrics_by_name.get(to_name)
                if not from_m or not to_m:
                    continue
                delta_rows.append({
                    "Layer Added": desc,
                    f"{from_name} ALLOW": from_m.allow_count,
                    f"{to_name} ALLOW": to_m.allow_count,
                    "Δ ALLOW": to_m.allow_count - from_m.allow_count,
                    f"{from_name} SecFail": f"{from_m.security_failure_rate:.4f}",
                    f"{to_name} SecFail": f"{to_m.security_failure_rate:.4f}",
                    "Δ SecFail": f"{to_m.security_failure_rate - from_m.security_failure_rate:+.4f}",
                })
            if delta_rows:
                st.dataframe(pd.DataFrame(delta_rows), use_container_width=True, hide_index=True)

    # ── Export ──
    st.markdown("### 💾 Export")
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        metrics_csv = pd.DataFrame([m.to_dict() for m in metrics_list]).to_csv(index=False)
        st.download_button("Download Metrics CSV", metrics_csv, "experiment_metrics.csv", "text/csv")
    with col_exp2:
        if results_dict:
            all_raw = []
            for cn, rl in results_dict.items():
                all_raw.extend(asdict(r) for r in rl)
            raw_csv = pd.DataFrame(all_raw).to_csv(index=False)
            st.download_button("Download Raw CSV", raw_csv, "experiment_results.csv", "text/csv")

    # ── AI Assessment ──
    st.markdown("### 🧠 AI-Powered Assessment")
    st.caption(
        "Send experiment results and the Access Decision Matrix to an LLM for "
        "a comprehensive analysis — key findings, highlights, and detailed explanations."
    )

    assess_key = os.environ.get("OPENAI_API_KEY", "")
    assess_model = st.selectbox(
        "Assessment Model", ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        key="assess_model",
        help="Recommended: gpt-4o for best analysis quality. Uses the API key from sidebar Settings."
    )

    assess_clicked = st.button("🔬 Generate AI Assessment", type="secondary",
                                use_container_width=True)

    if assess_clicked:
        if not assess_key:
            st.error("Please provide your OpenAI API key in the **sidebar Settings**.")
        else:
            _run_ai_assessment(metrics_list, results_dict, mode, inf_mode,
                               llm_model, assess_key, assess_model)

    # Show cached assessment if available
    if "ai_assessment" in st.session_state and not assess_clicked:
        with st.expander("📝 Last AI Assessment", expanded=True):
            st.markdown(st.session_state["ai_assessment"])


def _build_assessment_prompt(metrics_list: List[ExperimentMetrics],
                              results_dict: Dict[str, List[RunResult]],
                              mode: str, inf_mode: str,
                              llm_model: str) -> str:
    """Build a comprehensive prompt with all experiment data for AI assessment."""

    # Metrics summary
    metrics_text = "## Experiment Metrics\n\n"
    metrics_text += "| Config | Total | F1 | Precision | Recall | SecFail | Tool Acc | Jaccard | ALLOW | DENY | DEC | TP | TN | FP | FN | LLM Fail |\n"
    metrics_text += "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    for m in metrics_list:
        metrics_text += (
            f"| {m.name} | {m.total} | {m.f1:.4f} | {m.precision:.4f} | "
            f"{m.recall:.4f} | {m.security_failure_rate:.4f} | "
            f"{m.tool_accuracy:.4f} | {m.tool_jaccard_avg:.4f} | {m.allow_count} | "
            f"{m.deny_count} | {m.deception_count} | {m.true_positive} | "
            f"{m.true_negative} | {m.false_positive} | {m.false_negative} | "
            f"{m.llm_failures} |\n"
        )

    # Denial attribution
    metrics_text += "\n## Denial Source Attribution\n\n"
    metrics_text += "| Config | RBAC | ABAC | TS-PHOL |\n"
    metrics_text += "|---|---|---|---|\n"
    for m in metrics_list:
        metrics_text += (
            f"| {m.name} | {m.rbac_denials} | {m.abac_denials} | "
            f"{m.tsphol_denials} |\n"
        )

    # Per-persona breakdown for each config
    persona_text = "\n## Per-Persona Breakdown\n\n"
    for config_name, results in results_dict.items():
        persona_groups = {}
        for r in results:
            persona_groups.setdefault(r.persona, []).append(r)
        persona_text += f"\n### {config_name}\n"
        persona_text += "| Persona | Total | ALLOW | DENY | DEC | LLM Fail |\n"
        persona_text += "|---|---|---|---|---|---|\n"
        for persona, pr in sorted(persona_groups.items()):
            allow = sum(1 for r in pr if r.final_decision == "ALLOW")
            deny = sum(1 for r in pr if r.final_decision == "DENY")
            dec = sum(1 for r in pr if r.final_decision == "DECEPTION_ROUTED")
            fail = sum(1 for r in pr if r.llm_failed)
            persona_text += f"| {persona} | {len(pr)} | {allow} | {deny} | {dec} | {fail} |\n"

    # Per-domain breakdown for E1
    domain_text = "\n## Per-Domain Breakdown (E1)\n\n"
    e1_results = results_dict.get("E1", [])
    if e1_results:
        domain_breakdown = compute_domain_breakdown(e1_results)
        domain_text += "| Domain | Total | F1 | TP | TN | FP | FN |\n"
        domain_text += "|---|---|---|---|---|---|---|\n"
        for domain, stats in sorted(domain_breakdown.items()):
            domain_text += (
                f"| {domain} | {stats['total']} | {stats['f1']:.4f} | "
                f"{stats['TP']} | {stats['TN']} | {stats['FP']} | {stats['FN']} |\n"
            )

    # Ablation comparison — subtractive chain
    ablation_text = "\n## Subtractive Ablation Comparison\n\n"
    metrics_by_name = {m.name: m for m in metrics_list}
    e1 = metrics_by_name.get("E1")
    e2 = metrics_by_name.get("E2")
    e3 = metrics_by_name.get("E3")
    e4 = metrics_by_name.get("E4")
    if e1 and e4:
        ablation_text += "| Metric | E4 (None) | E3 (TS-PHOL) | E2 (ABAC+TS-PHOL) | E1 (Full) |\n"
        ablation_text += "|---|---|---|---|---|\n"
        exps = [e4, e3, e2, e1]
        for label, attr in [("ALLOW", "allow_count"), ("DENY", "deny_count"),
                             ("DECEPTION", "deception_count"), ("F1", "f1"),
                             ("Precision", "precision"), ("Recall", "recall"),
                             ("SecFail", "security_failure_rate"),
                             ("Tool Accuracy", "tool_accuracy"),
                             ("Tool Jaccard Avg", "tool_jaccard_avg"),
                             ("RBAC Denials", "rbac_denials"),
                             ("ABAC Denials", "abac_denials"),
                             ("TSPHOL Denials", "tsphol_denials")]:
            vals = []
            for e in exps:
                v = getattr(e, attr) if e else "N/A"
                vals.append(f"{v:.4f}" if isinstance(v, float) else str(v))
            ablation_text += f"| {label} | {' | '.join(vals)} |\n"

        if e3 and e4:
            ablation_text += f"\nTS-PHOL contribution (E4→E3): {e4.allow_count - e3.allow_count} fewer unsafe ALLOWs\n"
        if e2 and e3:
            ablation_text += f"ABAC contribution (E3→E2): {e3.allow_count - e2.allow_count} fewer unsafe ALLOWs\n"
        if e1 and e2:
            ablation_text += f"RBAC contribution (E2→E1): {e2.allow_count - e1.allow_count} fewer unsafe ALLOWs\n"

    # Access Decision Matrix summary
    matrix_text = "\n## Access Decision Matrix Summary\n\n"
    matrix_data = _load_matrix()
    if matrix_data:
        rows = matrix_data.get("rows", [])
        total_rows = len(rows)
        if total_rows > 0:
            decisions = Counter(r.get("final_decision", "UNKNOWN") for r in rows)
            matrix_text += f"Total matrix rows: {total_rows} (personas × tasks)\n\n"
            matrix_text += "| Decision | Count | % |\n|---|---|---|\n"
            for dec, cnt in decisions.most_common():
                matrix_text += f"| {dec} | {cnt} | {cnt/total_rows*100:.1f}% |\n"

            # Per-persona summary from matrix
            persona_decisions = defaultdict(Counter)
            for r in rows:
                persona_decisions[r.get("persona", "?")][r.get("final_decision", "?")] += 1
            matrix_text += "\n### Matrix Per-Persona\n"
            matrix_text += "| Persona | ALLOW | DENY | DECEPTION |\n|---|---|---|---|\n"
            for persona, counts in sorted(persona_decisions.items()):
                matrix_text += (
                    f"| {persona} | {counts.get('ALLOW',0)} | "
                    f"{counts.get('DENY',0)} | {counts.get('DECEPTION_ROUTED',0)} |\n"
                )

            # Denial attribution from matrix
            denial_sources = Counter()
            for r in rows:
                src = r.get("denial_source")
                if src:
                    denial_sources[src] += 1
            if denial_sources:
                matrix_text += "\n### Matrix Denial Attribution\n"
                matrix_text += "| Source | Count |\n|---|---|\n"
                for src, cnt in denial_sources.most_common():
                    matrix_text += f"| {src} | {cnt} |\n"

    # Experiment config context
    config_text = "\n## Experiment Configurations\n\n"
    config_text += "| ID | Task Filter | RBAC | ABAC | TS-PHOL | Purpose |\n"
    config_text += "|---|---|---|---|---|---|\n"
    from app.services.experiment_config import EXPERIMENTS as ALL_EXPS
    for cfg in ALL_EXPS:
        config_text += (
            f"| {cfg.name} | {cfg.match_tag_filter or 'all'} | "
            f"{cfg.rbac_fn} | {cfg.abac_fn} | {cfg.tsphol_fn} | "
            f"{cfg.description[:80]} |\n"
        )

    prompt = f"""You are an expert researcher analyzing experiment results from PALADIN — a layered governance framework for LLM-based agentic tool selection.

PALADIN enforces access control through three composable layers:
1. **RBAC** (Role-Based Access Control): Identity-based tool permissions per persona
2. **ABAC** (Attribute-Based Access Control): Contextual rules (time-of-day, risk level, trust score, clearance)
3. **TS-PHOL** (Typed Security Policy Higher-Order Logic): Formal logic rules for domain alignment, capability coverage, confidence thresholds, and deception routing

The experiments use the ASTRA dataset (Agentic Security Tool Recommendation Assessment) with 6 SPIFFE-authenticated personas.

**Inference mode used:** {inf_mode}{f' ({llm_model})' if llm_model else ''}
**Evaluation mode:** {mode}

---

{config_text}

{metrics_text}

{persona_text}

{domain_text}

{ablation_text}

{matrix_text}

---

Please provide a comprehensive assessment covering:

1. **Executive Summary** — The most important findings in 3-4 sentences.

2. **Ablation Analysis** — What does each layer contribute? Quantify the incremental value with specific numbers. Is the layered approach justified?

3. **Security Analysis** — Where are the remaining gaps? What does the security failure rate tell us? Are there domains or personas with concerning patterns?

4. **Per-Persona Insights** — Which personas have the most/least restrictive governance? Are there any surprising patterns?

5. **Per-Domain Insights** — Which domains see the most denials? Any cross-domain leakage concerns?

6. **Deception Routing Analysis** — When and why does the system route to deception instead of hard-deny? Is this behavior appropriate?

7. **Comparison: Simulation vs Real LLM** — If this was a real LLM run, what changed compared to simulation expectations? If simulation, what would we expect to change with a real LLM?

8. **Key Highlights for a Research Paper** — What are the most compelling data points and narratives for publication?

9. **Recommendations** — Specific actionable improvements to the governance framework.

10. **Limitations & Caveats** — What should readers be cautious about when interpreting these results?

Format your response in well-structured Markdown with clear headers and bullet points. Use specific numbers from the data — do not generalize.
"""
    return prompt


def _run_ai_assessment(metrics_list, results_dict, mode, inf_mode,
                        llm_model, api_key, assess_model):
    """Call the LLM with full experiment context and display the assessment."""
    from app.services.llm_provider import LLMProvider

    with st.spinner("🧠 Generating comprehensive assessment... (this may take 30-60 seconds)"):
        prompt = _build_assessment_prompt(
            metrics_list, results_dict, mode, inf_mode, llm_model
        )

        try:
            llm = LLMProvider(api_key=api_key, model=assess_model)
            if not llm.is_configured():
                st.error("LLM not configured — check API key.")
                return

            # Use a non-JSON response format for the assessment
            response = llm.client.chat.completions.create(
                model=assess_model,
                messages=[
                    {"role": "system", "content": "You are an expert AI security researcher providing detailed experiment analysis. Respond in well-formatted Markdown."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096,
            )
            assessment = response.choices[0].message.content

            st.session_state["ai_assessment"] = assessment

            with st.expander("📝 AI Assessment", expanded=True):
                st.markdown(assessment)

            # Download button for the assessment
            st.download_button(
                "📥 Download Assessment (Markdown)",
                assessment,
                "paladin_assessment.md",
                "text/markdown",
            )

        except Exception as e:
            st.error(f"Assessment failed: {e}")


# ═══════════════════════════════════════════════════════════════════════
# OPA Baseline Comparison
# ═══════════════════════════════════════════════════════════════════════

def _render_opa_comparison():
    """Render the OPA baseline comparison tab — standalone, works on any saved log."""
    st.markdown("### 🆚 OPA Baseline Comparison")
    st.markdown(
        "Compare PALADIN's layered governance against **OPA (Open Policy Agent)** — "
        "the industry-standard flat policy engine. Select any saved experiment log below; "
        "no new experiment run required."
    )

    with st.expander("ℹ️ What is this?", expanded=False):
        st.markdown("""
This compares PALADIN's **layered governance** against **OPA (Open Policy Agent)** — the industry standard flat policy engine.

The same RBAC, ABAC, and TS-PHOL rules are translated to OPA-equivalent semantics and evaluated against the same inputs:

| Mode | Description |
|---|---|
| **OPA-Flat** | All rules evaluated simultaneously, any deny wins. No layering, no short-circuit. |
| **OPA-Layered** | Sequential RBAC → ABAC → TS-PHOL with short-circuit, but **binary ALLOW/DENY only**. |
| **PALADIN** | Layered short-circuit + **DECEPTION_ROUTED** third outcome (OPA cannot express this). |

**Key architectural gaps in OPA:**
- ❌ No deception routing (tri-state enforcement)
- ❌ No native per-layer ablation
- ❌ No typed predicate system with priority ordering
- ⚠️ Flat evaluation sees all denial sources simultaneously (no short-circuit attribution)
""")

    # Find saved log files to compare against
    log_dir = os.path.join("datasets", "experiment_logs")
    if not os.path.isdir(log_dir):
        st.info("No experiment logs found. Run an experiment first.")
        return

    log_files = sorted(
        [f for f in os.listdir(log_dir) if f.endswith(".json")],
        reverse=True,
    )
    if not log_files:
        st.info("No experiment logs found. Run an experiment first.")
        return

    col_log, col_exp, col_btn = st.columns([3, 1, 1])
    with col_log:
        selected_log = st.selectbox(
            "Experiment Log", log_files,
            key="opa_log_select",
            help="Select a saved experiment log to compare against OPA."
        )
    with col_exp:
        exp_choice = st.selectbox("Experiment", ["E1", "E2", "E3", "E4"], key="opa_exp_select")
    with col_btn:
        st.write("")
        opa_clicked = st.button("🚀 Run OPA Comparison", type="primary",
                                 use_container_width=True, key="opa_run_btn")

    if opa_clicked:
        log_path = os.path.join(log_dir, selected_log)
        progress = st.progress(0, text="Running OPA comparison...")

        def opa_progress(info):
            pct = info["current"] / info["total"] if info["total"] else 0
            progress.progress(pct, text=f"OPA evaluation: {info['current']}/{info['total']}")

        try:
            metrics, details = run_opa_comparison(
                log_path, experiment=exp_choice, progress_callback=opa_progress,
            )
            progress.progress(1.0, text="Complete!")
            st.session_state["opa_comparison"] = {"metrics": metrics, "details": details, "exp": exp_choice}
        except Exception as e:
            st.error(f"OPA comparison failed: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

    if "opa_comparison" not in st.session_state:
        return

    comp = st.session_state["opa_comparison"]
    m = comp["metrics"]
    exp_label = comp["exp"]

    st.success(f"✅ OPA comparison complete — **{m.total:,}** evaluations ({exp_label})")

    # ── Side-by-side metrics ──
    st.markdown("#### 📊 PALADIN vs OPA — Head-to-Head")
    comparison_rows = [
        {
            "Engine": f"PALADIN ({exp_label})",
            "F₁": f"{m.paladin_f1:.4f}",
            "SecFail": f"{m.paladin_secfail:.4f}",
            "ALLOW": m.paladin_allow,
            "DENY": m.paladin_deny,
            "DECEPTION": m.paladin_deception,
            "TP": m.paladin_tp,
            "TN": m.paladin_tn,
            "FP": m.paladin_fp,
            "FN": m.paladin_fn,
        },
        {
            "Engine": "OPA-Flat",
            "F₁": f"{m.opa_flat_f1:.4f}",
            "SecFail": f"{m.opa_flat_secfail:.4f}",
            "ALLOW": m.opa_flat_allow,
            "DENY": m.opa_flat_deny,
            "DECEPTION": "N/A ❌",
            "TP": m.opa_flat_tp,
            "TN": m.opa_flat_tn,
            "FP": m.opa_flat_fp,
            "FN": m.opa_flat_fn,
        },
        {
            "Engine": "OPA-Layered",
            "F₁": f"{m.opa_layered_f1:.4f}",
            "SecFail": f"{m.opa_layered_secfail:.4f}",
            "ALLOW": m.opa_layered_allow,
            "DENY": m.opa_layered_deny,
            "DECEPTION": "N/A ❌",
            "TP": m.opa_layered_tp,
            "TN": m.opa_layered_tn,
            "FP": m.opa_layered_fp,
            "FN": m.opa_layered_fn,
        },
    ]
    st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)

    # ── Agreement analysis ──
    st.markdown("#### 🤝 Decision Agreement")
    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        st.metric("OPA-Flat Agreement", f"{m.agreement_rate_flat:.1%}",
                   help="Fraction of rows where PALADIN and OPA-Flat made the same ALLOW/DENY decision")
    with col_a2:
        st.metric("OPA-Layered Agreement", f"{m.agreement_rate_layered:.1%}",
                   help="Fraction of rows where PALADIN and OPA-Layered agree")
    with col_a3:
        st.metric("Deception Gap", f"{m.deception_gap:,}",
                   help="Rows where PALADIN deception-routed (OPA cannot express this)")

    if m.paladin_only_deny > 0 or m.opa_only_deny > 0:
        st.markdown("##### Disagreement Breakdown")
        dis_col1, dis_col2 = st.columns(2)
        with dis_col1:
            st.metric("PALADIN denies, OPA-Flat allows", m.paladin_only_deny,
                       help="Cases where PALADIN's layered engine catches threats OPA misses")
        with dis_col2:
            st.metric("OPA-Flat denies, PALADIN allows", m.opa_only_deny,
                       help="Cases where OPA-Flat is stricter (sees all denial sources)")

    # ── OPA-Flat denial source visibility ──
    if m.opa_flat_deny > 0:
        st.markdown("#### 🔍 OPA-Flat Denial Source Visibility")
        st.caption(
            "In flat mode, OPA sees ALL denial sources simultaneously — "
            "unlike PALADIN which short-circuits at the first denying layer."
        )
        flat_src_rows = [{
            "RBAC Denials": m.opa_flat_rbac_denials,
            "ABAC Denials": m.opa_flat_abac_denials,
            "TS-PHOL Denials": m.opa_flat_tsphol_denials,
            "Total Denied Rows": m.opa_flat_deny,
        }]
        st.dataframe(pd.DataFrame(flat_src_rows), use_container_width=True, hide_index=True)

    # ── Deception routing callout ──
    if m.deception_gap > 0:
        st.markdown("#### 🔀 Deception Routing Gap")
        st.warning(f"""
**{m.deception_gap:,} evaluations** were deception-routed by PALADIN (sandboxed to honeypot).

OPA can only express binary ALLOW/DENY — it cannot:
- Contain threats via deception without alerting the attacker
- Distinguish "hard deny" from "observe and contain"
- Provide the intelligence-gathering advantage of honeypot routing

This represents a **fundamental architectural capability gap** in flat policy engines.
""")

    # ── Architectural comparison ──
    st.markdown("#### 📐 Architectural Comparison")
    arch_rows = [
        {"Capability": "Layered short-circuit evaluation", "PALADIN": "✅", "OPA": "❌ (flat)"},
        {"Capability": "Deception routing (tri-state)", "PALADIN": "✅", "OPA": "❌"},
        {"Capability": "Per-layer ablation testing", "PALADIN": "✅ (native)", "OPA": "❌ (requires rewrite)"},
        {"Capability": "Per-layer denial attribution", "PALADIN": "✅", "OPA": "⚠️ (flat: all sources visible)"},
        {"Capability": "Typed predicate system", "PALADIN": "✅ (TS-PHOL)", "OPA": "❌"},
        {"Capability": "Priority-ordered rule evaluation", "PALADIN": "✅", "OPA": "⚠️ (manual else chains)"},
        {"Capability": "Industry adoption", "PALADIN": "Research", "OPA": "✅ (CNCF graduated)"},
        {"Capability": "Policy language", "PALADIN": "YAML + Python", "OPA": "Rego"},
    ]
    st.dataframe(pd.DataFrame(arch_rows), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════
# Tab 2 — Access Decision Matrix Explorer
# ═══════════════════════════════════════════════════════════════════════

def _render_matrix_explorer():
    # ── Regeneration button ──
    regen_col1, regen_col2 = st.columns([3, 1])
    with regen_col1:
        st.markdown("### 📊 Access Decision Matrix")
    with regen_col2:
        regen_clicked = st.button("🔄 Regenerate Matrix", type="secondary",
                                   help="Re-run all persona × task evaluations through the full governance pipeline.",
                                   use_container_width=True)

    if regen_clicked:
        _regenerate_matrix()
        st.rerun()

    data = _load_matrix()
    if data is None:
        st.warning(
            "Access Decision Matrix not found. Click **🔄 Regenerate Matrix** above "
            "or run `python scripts/generate_access_matrix.py`."
        )
        return

    metadata = data["metadata"]
    summary = data["summary"]
    matrix = data["matrix"]

    # ── Staleness check ──
    stored_hashes = metadata.get("policy_versions", {})
    current_hashes = _current_policy_hashes()
    is_stale = stored_hashes != current_hashes
    if is_stale:
        st.warning(
            "⚠️ **Stale Matrix** — Policy files have changed since this matrix was generated. "
            "Click **🔄 Regenerate Matrix** above to update.",
            icon="⚠️",
        )

    # ── Header info ──
    st.markdown("### Selection-Mode Production Baseline")
    st.caption(
        "This matrix was generated by running every *(persona × task)* combination through "
        "the full governance pipeline with production policies in **selection mode**. "
        "It serves as the ground truth for validating experiment results."
    )

    # ── KPI row ──
    total = summary["total"]
    allow = summary.get("final_ALLOW", 0)
    deny = summary.get("final_DENY", 0)
    deception = summary.get("final_DECEPTION_ROUTED", 0)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Rows", f"{total:,}")
    k2.metric("ALLOW", f"{allow:,}", f"{allow*100/total:.1f}%")
    k3.metric("DENY", f"{deny:,}", f"{deny*100/total:.1f}%")
    k4.metric("DECEPTION", f"{deception:,}", f"{deception*100/total:.1f}%")
    k5.metric("Personas × Tasks", f"{metadata['personas']} × {metadata['tasks']:,}")

    st.markdown("---")

    # ── Sub-tabs for different views ──
    sub_waterfall, sub_heatmap, sub_persona, sub_browse = st.tabs([
        "🔽 Governance Waterfall",
        "🗺️ Persona × Layer Heatmap",
        "👤 Per-Persona Deep Dive",
        "🔍 Browse & Filter",
    ])

    # ── Governance Waterfall ──
    with sub_waterfall:
        _render_waterfall(matrix)

    # ── Persona × Layer Heatmap ──
    with sub_heatmap:
        _render_heatmap(matrix)

    # ── Per-Persona Deep Dive ──
    with sub_persona:
        _render_persona_dive(matrix)

    # ── Browse & Filter ──
    with sub_browse:
        _render_browse(matrix)

    # ── Policy Fingerprints ──
    st.markdown("---")
    with st.expander("📋 Policy Fingerprints", expanded=False):
        st.caption(
            "Partial SHA-256 hashes of the policy files used to generate this matrix. "
            "If current hashes differ, the matrix is stale."
        )
        fp_rows = []
        for pf, h in stored_hashes.items():
            curr = current_hashes.get(pf, "—")
            match = "✅" if h == curr else "❌"
            fp_rows.append({"File": pf, "Matrix Hash": h, "Current Hash": curr, "Match": match})
        st.dataframe(pd.DataFrame(fp_rows), use_container_width=True, hide_index=True)
        st.caption(f"Dataset: `{metadata.get('dataset', 'N/A')}`")


def _render_waterfall(matrix: list):
    """Governance layer waterfall showing how tasks flow through each gate."""
    st.markdown("#### Governance Layer Waterfall")
    st.caption(
        "Shows how evaluations flow through each governance layer. "
        "Tasks are blocked at the first DENY and do not reach subsequent layers."
    )

    # ── Optional persona filter ──
    persona_filter = st.selectbox(
        "Filter by Persona",
        ["All Personas"] + [PERSONAS[k]["display_name"] for k in sorted(PERSONAS)],
        key="waterfall_persona",
    )

    if persona_filter != "All Personas":
        pkey = next(k for k, v in PERSONAS.items() if v["display_name"] == persona_filter)
        rows = [r for r in matrix if r["persona"] == pkey]
    else:
        rows = matrix

    total = len(rows)
    layers = [
        ("RBAC", "expected_rbac"),
        ("ABAC", "expected_abac"),
        ("TS-PHOL", "expected_tsphol"),
    ]

    waterfall_data = []
    surviving = total
    for layer_name, key in layers:
        passed = sum(1 for r in rows if r[key] == "ALLOW")
        blocked = sum(1 for r in rows if r[key] == "DENY")
        not_eval = sum(1 for r in rows if r[key] == "NOT_EVALUATED")
        waterfall_data.append({
            "Layer": layer_name,
            "Passed ✅": passed,
            "Blocked Here 🛑": blocked,
            "Not Evaluated ⏭️": not_eval,
        })
        surviving -= blocked

    st.dataframe(pd.DataFrame(waterfall_data), use_container_width=True, hide_index=True)

    # Funnel bar chart
    funnel_data = []
    remaining = total
    funnel_data.append({"Stage": "Entered", "Count": remaining})
    for layer_name, key in layers:
        blocked = sum(1 for r in rows if r[key] == "DENY")
        remaining -= blocked
        funnel_data.append({"Stage": f"After {layer_name}", "Count": remaining})
    df_funnel = pd.DataFrame(funnel_data).set_index("Stage")
    st.bar_chart(df_funnel)

    # Denial source attribution (first_deny_layer)
    st.markdown("##### First Deny Layer Attribution")
    deny_counter = Counter(r["first_deny_layer"] for r in rows if r["first_deny_layer"])
    if deny_counter:
        dc_rows = [{"Layer": k, "Count": v, "% of Total": f"{v*100/total:.1f}%"}
                   for k, v in deny_counter.most_common()]
        st.dataframe(pd.DataFrame(dc_rows), use_container_width=True, hide_index=True)

    # Defense-in-depth (all_deny_layers)
    st.markdown("##### Defense-in-Depth (All Layers That Would Deny)")
    all_deny = Counter()
    for r in rows:
        for dl in r.get("all_deny_layers", []):
            all_deny[dl] += 1
    if all_deny:
        ad_rows = [{"Layer": k, "Would Deny": v} for k, v in all_deny.most_common()]
        st.dataframe(pd.DataFrame(ad_rows), use_container_width=True, hide_index=True)
        st.caption(
            "Even if a task is blocked early (e.g., by RBAC), later layers may have also "
            "denied it. This shows the total defense-in-depth coverage."
        )


def _render_heatmap(matrix: list):
    """Persona × governance layer heatmap."""
    st.markdown("#### Persona × Governance Outcome")
    st.caption(
        "Each cell shows `Passed / Blocked / Not Evaluated` for that persona at each layer."
    )

    layers = [
        ("RBAC", "expected_rbac"),
        ("ABAC", "expected_abac"),
        ("TS-PHOL", "expected_tsphol"),
        ("Final", "expected_final"),
    ]

    heatmap_rows = []
    for pkey in sorted(PERSONAS):
        pdata = PERSONAS[pkey]
        prows = [r for r in matrix if r["persona"] == pkey]
        total = len(prows)
        row = {"Persona": pdata["display_name"]}
        for lname, lkey in layers:
            if lname == "Final":
                allow = sum(1 for r in prows if r[lkey] == "ALLOW")
                deny = sum(1 for r in prows if r[lkey] == "DENY")
                dec = sum(1 for r in prows if r[lkey] == "DECEPTION_ROUTED")
                row[lname] = f"✅{allow} 🛑{deny} 🪤{dec}"
            else:
                passed = sum(1 for r in prows if r[lkey] == "ALLOW")
                blocked = sum(1 for r in prows if r[lkey] == "DENY")
                not_eval = sum(1 for r in prows if r[lkey] == "NOT_EVALUATED")
                row[lname] = f"✅{passed} 🛑{blocked} ⏭️{not_eval}"
        heatmap_rows.append(row)

    st.dataframe(pd.DataFrame(heatmap_rows), use_container_width=True, hide_index=True)

    # Numeric summary for bar chart
    st.markdown("##### Final Decision Distribution by Persona")
    bar_rows = []
    for pkey in sorted(PERSONAS):
        prows = [r for r in matrix if r["persona"] == pkey]
        bar_rows.append({
            "Persona": PERSONAS[pkey]["display_name"],
            "ALLOW": sum(1 for r in prows if r["expected_final"] == "ALLOW"),
            "DENY": sum(1 for r in prows if r["expected_final"] == "DENY"),
            "DECEPTION": sum(1 for r in prows if r["expected_final"] == "DECEPTION_ROUTED"),
        })
    df_bar = pd.DataFrame(bar_rows).set_index("Persona")
    st.bar_chart(df_bar)


def _render_persona_dive(matrix: list):
    """Deep dive into a single persona's governance outcomes."""
    st.markdown("#### Per-Persona Deep Dive")

    persona_sel = st.selectbox(
        "Select Persona",
        [PERSONAS[k]["display_name"] for k in sorted(PERSONAS)],
        key="persona_dive_sel",
    )
    pkey = next(k for k, v in PERSONAS.items() if v["display_name"] == persona_sel)
    prows = [r for r in matrix if r["persona"] == pkey]
    total = len(prows)

    # Domain breakdown
    st.markdown("##### Domain Breakdown")
    domain_groups = defaultdict(list)
    for r in prows:
        domain_groups[r["task_domain"]].append(r)

    domain_rows = []
    for domain in sorted(domain_groups):
        dr = domain_groups[domain]
        allow = sum(1 for r in dr if r["expected_final"] == "ALLOW")
        deny = sum(1 for r in dr if r["expected_final"] == "DENY")
        dec = sum(1 for r in dr if r["expected_final"] == "DECEPTION_ROUTED")
        authorized = domain in LEGITIMATE_PAIRINGS.get(pkey, set())
        domain_rows.append({
            "Domain": domain,
            "Authorized": "✅" if authorized else "❌",
            "Tasks": len(dr),
            "ALLOW": allow,
            "DENY": deny,
            "DECEPTION": dec,
            "Allow Rate": f"{allow*100/len(dr):.0f}%" if dr else "—",
        })
    st.dataframe(pd.DataFrame(domain_rows), use_container_width=True, hide_index=True)

    # RBAC-pass / ABAC-fail zone
    abac_only = [r for r in prows if r["expected_rbac"] == "ALLOW" and r["expected_abac"] == "DENY"]
    if abac_only:
        st.markdown("##### RBAC-Pass / ABAC-Fail Zone")
        st.caption(f"{len(abac_only)} tasks passed RBAC but were blocked by ABAC.")
        abac_domains = Counter(r["task_domain"] for r in abac_only)
        abac_rules = Counter(r["abac_matched_rule"] for r in abac_only)
        c1, c2 = st.columns(2)
        with c1:
            st.write("**By Domain:**")
            st.dataframe(
                pd.DataFrame([{"Domain": k, "Count": v} for k, v in abac_domains.most_common()]),
                use_container_width=True, hide_index=True,
            )
        with c2:
            st.write("**By ABAC Rule:**")
            st.dataframe(
                pd.DataFrame([{"Rule": k, "Count": v} for k, v in abac_rules.most_common()]),
                use_container_width=True, hide_index=True,
            )

    # TS-PHOL-only catches
    tsphol_only = [r for r in prows
                   if r["expected_rbac"] == "ALLOW" and r["expected_abac"] == "ALLOW"
                   and r.get("tsphol_status", "ALLOW") != "ALLOW"]
    if tsphol_only:
        st.markdown("##### TS-PHOL Additional Catches")
        st.caption(f"{len(tsphol_only)} tasks passed RBAC+ABAC but were caught by TS-PHOL rules.")

    # Capability coverage summary
    st.markdown("##### Capability Coverage")
    cov_values = [r["capability_coverage"] for r in prows if r["expected_final"] == "ALLOW"]
    if cov_values:
        avg_cov = sum(cov_values) / len(cov_values)
        full_cov = sum(1 for v in cov_values if v >= 1.0)
        st.caption(
            f"Among {len(cov_values)} ALLOW decisions: "
            f"avg coverage = **{avg_cov:.1%}**, full coverage = **{full_cov}** "
            f"({full_cov*100/len(cov_values):.0f}%)"
        )

    # Match tag breakdown
    st.markdown("##### By Match Tag")
    tag_rows = []
    for tag in ["correct", "wrong", "null"]:
        tr = [r for r in prows if r["match_tag"] == tag]
        if tr:
            allow = sum(1 for r in tr if r["expected_final"] == "ALLOW")
            tag_rows.append({
                "Tag": tag,
                "Tasks": len(tr),
                "ALLOW": allow,
                "DENY": len(tr) - allow,
                "Allow Rate": f"{allow*100/len(tr):.0f}%",
            })
    st.dataframe(pd.DataFrame(tag_rows), use_container_width=True, hide_index=True)


def _render_browse(matrix: list):
    """Filterable data browser for the matrix."""
    st.markdown("#### Browse & Filter")

    # ── Filters ──
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        f_persona = st.selectbox("Persona", ["All"] + sorted(PERSONAS.keys()), key="browse_persona")
    with fc2:
        all_domains = sorted(set(r["task_domain"] for r in matrix))
        f_domain = st.selectbox("Domain", ["All"] + all_domains, key="browse_domain")
    with fc3:
        f_tag = st.selectbox("Match Tag", ["All", "correct", "wrong", "null"], key="browse_tag")
    with fc4:
        f_decision = st.selectbox("Final Decision", ["All", "ALLOW", "DENY", "DECEPTION_ROUTED"],
                                  key="browse_decision")

    filtered = matrix
    if f_persona != "All":
        filtered = [r for r in filtered if r["persona"] == f_persona]
    if f_domain != "All":
        filtered = [r for r in filtered if r["task_domain"] == f_domain]
    if f_tag != "All":
        filtered = [r for r in filtered if r["match_tag"] == f_tag]
    if f_decision != "All":
        filtered = [r for r in filtered if r["expected_final"] == f_decision]

    st.caption(f"Showing **{len(filtered):,}** of {len(matrix):,} rows")

    # Summary of filtered set
    if filtered:
        fc_allow = sum(1 for r in filtered if r["expected_final"] == "ALLOW")
        fc_deny = sum(1 for r in filtered if r["expected_final"] == "DENY")
        fc_dec = sum(1 for r in filtered if r["expected_final"] == "DECEPTION_ROUTED")
        m1, m2, m3 = st.columns(3)
        m1.metric("ALLOW", fc_allow)
        m2.metric("DENY", fc_deny)
        m3.metric("DECEPTION", fc_dec)

    # Data table (compact view)
    display_rows = []
    for r in filtered[:500]:
        display_rows.append({
            "Persona": r["persona"],
            "Task": r["task_idx"],
            "Domain": r["task_domain"],
            "Tag": r["match_tag"],
            "Write?": "✍️" if r["has_write"] else "",
            "RBAC": r["expected_rbac"],
            "ABAC": r["expected_abac"],
            "TS-PHOL": r["expected_tsphol"],
            "Final": r["expected_final"],
            "Deny Layer": r["first_deny_layer"] or "—",
            "Cap Coverage": f"{r['capability_coverage']:.0%}",
        })

    if display_rows:
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
        if len(filtered) > 500:
            st.caption(f"Showing first 500 of {len(filtered):,} rows")

    # Row detail expander
    if filtered:
        st.markdown("##### Row Detail Inspector")
        row_idx = st.number_input(
            "Select row index to inspect", min_value=0,
            max_value=min(499, len(filtered) - 1), value=0, key="browse_row_idx",
        )
        selected_row = filtered[row_idx]

        with st.expander(
            f"Row {row_idx}: {selected_row['persona']} × task {selected_row['task_idx']} "
            f"→ {selected_row['expected_final']}",
            expanded=True,
        ):
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Per-Tool RBAC Decisions:**")
                if selected_row.get("tool_decisions"):
                    td_rows = []
                    for td in selected_row["tool_decisions"]:
                        td_rows.append({
                            "Tool": td["tool"],
                            "MCP": td["mcp"],
                            "RBAC": td["rbac"],
                            "Rule": td["rbac_rule"],
                        })
                    st.dataframe(pd.DataFrame(td_rows), use_container_width=True, hide_index=True)

            with c2:
                st.write("**Capabilities:**")
                st.write(f"Required: `{selected_row.get('required_capabilities', [])}`")
                st.write(f"Has: `{selected_row.get('has_capabilities', [])}`")
                missing = selected_row.get("missing_capabilities", [])
                if missing:
                    st.write(f"Missing: `{missing}`")
                st.write(f"Coverage: **{selected_row['capability_coverage']:.0%}**")

            st.write("**All Deny Layers:**", selected_row.get("all_deny_layers", []))
            if selected_row.get("abac_matched_rule"):
                st.write(f"**ABAC Rule:** `{selected_row['abac_matched_rule']}`")
            if selected_row.get("tsphol_triggered_rules", 0) > 0:
                st.write(f"**TS-PHOL Triggered:** {selected_row['tsphol_triggered_rules']} rule(s)")
