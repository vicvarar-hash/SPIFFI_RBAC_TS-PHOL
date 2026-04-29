"""
Experiment Lab — batch experiment execution UI.

Allows users to select experiment configurations, choose selection or
validation mode, run batch evaluations, and view results with metrics,
breakdowns, and comparisons.
"""

import streamlit as st
import pandas as pd
import json
from dataclasses import asdict
from typing import List, Dict

from app.services.experiment_config import (
    EXPERIMENTS, EXPERIMENT_MAP, EXPERIMENT_GROUPS,
    PERSONAS, LEGITIMATE_PAIRINGS, ExperimentConfig,
)
from app.services.experiment_runner import (
    run_experiment, compute_domain_breakdown,
    ExperimentMetrics, RunResult,
)


def render_experiment_lab(tasks, personas):
    st.title("🧪 Experiment Lab")
    st.markdown(
        "Run batch experiments across all personas and tasks using different "
        "security configurations. Results are deterministic (simulated LLM, no API key required)."
    )

    # ── Sidebar-like config area ──
    col_cfg, col_results = st.columns([1, 3])

    with col_cfg:
        st.subheader("Configuration")

        # Group selector
        group_options = ["All Groups"] + [f"Group {g}: {d[:40]}" for g, d in EXPERIMENT_GROUPS.items()]
        selected_group_display = st.selectbox("Experiment Group", group_options)

        if selected_group_display == "All Groups":
            available_configs = EXPERIMENTS
        else:
            group_letter = selected_group_display.split(":")[0].replace("Group ", "").strip()
            available_configs = [e for e in EXPERIMENTS if e.group == group_letter]

        # Config selector
        config_options = ["Run All"] + [f"{e.name}: {e.description}" for e in available_configs]
        selected_config_display = st.selectbox("Configuration", config_options)

        if selected_config_display == "Run All":
            configs_to_run = available_configs
        else:
            config_name = selected_config_display.split(":")[0].strip()
            configs_to_run = [EXPERIMENT_MAP[config_name]]

        # Mode selector
        mode = st.radio("Experiment Mode", ["Selection (LLM-ResM)", "Validation"], horizontal=True)
        mode_str = "selection" if mode.startswith("Selection") else "validation"

        st.markdown("---")

        # Show config details
        if len(configs_to_run) == 1:
            cfg = configs_to_run[0]
            st.markdown(f"**{cfg.name}**: {cfg.description}")
            policies = cfg.get_policies()
            with st.expander("Policy Settings", expanded=False):
                st.markdown(f"- **Pre-LLM bypass**: {cfg.bypass_pre_llm}")
                st.markdown(f"- **Registry**: {cfg.registry_fn}")
                st.markdown(f"- **Allowlist**: {cfg.allowlist_fn}")
                st.markdown(f"- **RBAC**: {cfg.rbac_fn}")
                st.markdown(f"- **ABAC**: {cfg.abac_fn} ({len(policies['abac'].get('rules', []))} rules)")
                st.markdown(f"- **TS-PHOL**: {cfg.tsphol_fn} ({len(policies['tsphol'].get('rules', []))} rules)")
        else:
            st.info(f"Will run **{len(configs_to_run)}** configurations")

        # Task/persona counts
        active_personas = [k for k in PERSONAS if k != "security_engine"]
        total_evals = len(active_personas) * len(tasks) * len(configs_to_run)
        st.metric("Total Evaluations", f"{total_evals:,}")
        st.caption(f"{len(active_personas)} personas × {len(tasks):,} tasks × {len(configs_to_run)} configs")

        # Run button
        run_clicked = st.button("🚀 Run Experiment", type="primary", use_container_width=True)

    with col_results:
        st.subheader("Results")

        if run_clicked:
            _run_and_display(configs_to_run, tasks, personas, mode_str)
        elif "experiment_results" in st.session_state:
            _display_results(st.session_state["experiment_results"])
        else:
            st.info("Select a configuration and click **Run Experiment** to begin.")
            _show_experiment_overview()


def _run_and_display(configs: List[ExperimentConfig], tasks, personas,
                     mode: str):
    """Execute experiments with progress tracking and display results."""
    all_metrics: List[ExperimentMetrics] = []
    all_results: Dict[str, List[RunResult]] = {}

    progress_bar = st.progress(0, text="Starting experiments...")
    status_text = st.empty()

    total_configs = len(configs)
    for cfg_idx, config in enumerate(configs):
        status_text.text(f"Running {config.name}: {config.description}...")

        def progress_cb(pct):
            overall = (cfg_idx + pct) / total_configs
            progress_bar.progress(overall, text=f"{config.name} — {pct:.0%}")

        metrics, results = run_experiment(config, tasks, personas, mode=mode,
                                          progress_callback=progress_cb)
        all_metrics.append(metrics)
        all_results[config.name] = results

    progress_bar.progress(1.0, text="Complete!")
    status_text.text(f"✅ Completed {total_configs} experiment(s) in {mode} mode")

    # Store in session state
    st.session_state["experiment_results"] = {
        "metrics": all_metrics,
        "results": all_results,
        "mode": mode,
    }

    _display_results(st.session_state["experiment_results"])


def _display_results(data: dict):
    """Render experiment results dashboard."""
    metrics_list: List[ExperimentMetrics] = data["metrics"]
    results_dict: Dict[str, List[RunResult]] = data["results"]
    mode = data.get("mode", "selection")

    if not metrics_list:
        st.warning("No results to display.")
        return

    # ── Summary metrics table ──
    st.markdown("### 📊 Summary Metrics")
    rows = []
    for m in metrics_list:
        rows.append({
            "Config": m.name,
            "Description": m.description[:45],
            "Total": m.total,
            "F₁": f"{m.f1:.4f}",
            "Precision": f"{m.precision:.4f}",
            "Recall": f"{m.recall:.4f}",
            "SecFail": f"{m.security_failure_rate:.4f}",
            "ALLOW": m.allow_count,
            "DENY": m.deny_count,
            "TP": m.true_positive,
            "TN": m.true_negative,
            "FP": m.false_positive,
            "FN": m.false_negative,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Denial source breakdown ──
    if len(metrics_list) > 0:
        st.markdown("### 🔒 Denial Source Attribution")
        denial_rows = []
        for m in metrics_list:
            denial_rows.append({
                "Config": m.name,
                "Identity": m.identity_denials,
                "Transport": m.transport_denials,
                "RBAC": m.rbac_denials,
                "ABAC": m.abac_denials,
                "TS-PHOL": m.tsphol_denials,
                "Other": m.other_denials,
            })
        df_denial = pd.DataFrame(denial_rows)
        st.dataframe(df_denial, use_container_width=True, hide_index=True)

    # ── Per-config detail view ──
    if len(results_dict) > 0:
        st.markdown("### 🔍 Detail View")
        selected_detail = st.selectbox(
            "Select configuration for detailed breakdown",
            list(results_dict.keys()),
        )

        if selected_detail and selected_detail in results_dict:
            detail_results = results_dict[selected_detail]

            tab_domain, tab_persona, tab_raw = st.tabs(
                ["Per-Domain Breakdown", "Per-Persona Breakdown", "Raw Results"]
            )

            with tab_domain:
                breakdown = compute_domain_breakdown(detail_results)
                domain_rows = []
                for domain, stats in breakdown.items():
                    domain_rows.append({
                        "Domain": domain,
                        "Total": stats["total"],
                        "TP": stats["TP"],
                        "TN": stats["TN"],
                        "FP": stats["FP"],
                        "FN": stats["FN"],
                        "F₁": f"{stats['f1']:.4f}",
                        "Precision": f"{stats['precision']:.4f}",
                        "Recall": f"{stats['recall']:.4f}",
                    })
                st.dataframe(pd.DataFrame(domain_rows), use_container_width=True, hide_index=True)

            with tab_persona:
                persona_groups = {}
                for r in detail_results:
                    persona_groups.setdefault(r.persona, []).append(r)

                persona_rows = []
                for persona, p_results in sorted(persona_groups.items()):
                    tp = sum(1 for r in p_results if not r.is_legitimate and r.final_decision in ("DENY", "DECEPTION_ROUTED"))
                    tn = sum(1 for r in p_results if r.is_legitimate and r.final_decision == "ALLOW")
                    fp = sum(1 for r in p_results if r.is_legitimate and r.final_decision in ("DENY", "DECEPTION_ROUTED"))
                    fn = sum(1 for r in p_results if not r.is_legitimate and r.final_decision == "ALLOW")
                    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                    f1 = 2 * p * rec / (p + rec) if (p + rec) > 0 else 0.0
                    persona_rows.append({
                        "Persona": PERSONAS.get(persona, {}).get("display_name", persona),
                        "Total": len(p_results),
                        "F₁": f"{f1:.4f}",
                        "Precision": f"{p:.4f}",
                        "Recall": f"{rec:.4f}",
                        "TP": tp, "TN": tn, "FP": fp, "FN": fn,
                    })
                st.dataframe(pd.DataFrame(persona_rows), use_container_width=True, hide_index=True)

            with tab_raw:
                raw_rows = [asdict(r) for r in detail_results[:500]]
                df_raw = pd.DataFrame(raw_rows)
                st.dataframe(df_raw, use_container_width=True, hide_index=True)
                st.caption(f"Showing first 500 of {len(detail_results)} results")

    # ── Comparison view ──
    if len(metrics_list) >= 2:
        st.markdown("### ⚖️ Configuration Comparison")
        compare_options = [m.name for m in metrics_list]
        selected_compare = st.multiselect("Select configs to compare", compare_options,
                                           default=compare_options[:min(4, len(compare_options))])

        if len(selected_compare) >= 2:
            compare_data = []
            for m in metrics_list:
                if m.name in selected_compare:
                    compare_data.append({
                        "Config": m.name,
                        "F₁": m.f1,
                        "Precision": m.precision,
                        "Recall": m.recall,
                        "SecFail": m.security_failure_rate,
                    })
            df_compare = pd.DataFrame(compare_data).set_index("Config")
            st.bar_chart(df_compare)

    # ── CSV export ──
    st.markdown("### 💾 Export")
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        metrics_csv = pd.DataFrame([m.to_dict() for m in metrics_list]).to_csv(index=False)
        st.download_button("Download Metrics CSV", metrics_csv, "experiment_metrics.csv", "text/csv")
    with col_exp2:
        if results_dict:
            all_raw = []
            for config_name, results in results_dict.items():
                all_raw.extend(asdict(r) for r in results)
            raw_csv = pd.DataFrame(all_raw).to_csv(index=False)
            st.download_button("Download Raw Results CSV", raw_csv, "experiment_results.csv", "text/csv")


def _show_experiment_overview():
    """Show overview of available experiment groups."""
    st.markdown("### Available Experiment Groups")

    for group, desc in EXPERIMENT_GROUPS.items():
        configs = [e for e in EXPERIMENTS if e.group == group]
        with st.expander(f"**Group {group}**: {desc}", expanded=False):
            for cfg in configs:
                st.markdown(f"- **{cfg.name}**: {cfg.description}")
                details = []
                if cfg.bypass_pre_llm:
                    details.append("bypass pre-LLM")
                if cfg.rbac_fn != "production":
                    details.append(f"RBAC={cfg.rbac_fn}")
                if cfg.abac_fn != "production":
                    details.append(f"ABAC={cfg.abac_fn}")
                if cfg.tsphol_fn != "production":
                    details.append(f"TS-PHOL={cfg.tsphol_fn}")
                if details:
                    st.caption("  " + " · ".join(details))
