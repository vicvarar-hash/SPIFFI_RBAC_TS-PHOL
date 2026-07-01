"""Post-Experiment Lab — Baseline vs Modified comparison over cached logs.

Re-runs the deterministic stack (RBAC / ABAC / TRAC) over the bundles recorded
in an experiment log — *no new LLM inference* — and shows two pictures side by side:

* **Baseline** — the original production policies (what the log recorded).
* **Modified** — after you edit RBAC / ABAC / TRAC rules below.

For each picture you see headline metrics and which rules fired per layer, and you
can drill into any single transaction to see how and why each layer was triggered.
"""

import streamlit as st
import pandas as pd
import yaml
import json
import os
import glob
import datetime

from app.services import replay_service as rs
from app.services.tsphol_rule_service import TSPHOLRuleService
from app.services.experiment_config import rbac_open, abac_open, tsphol_open, PERSONAS

RBAC_PATH = "policies/rbac.yaml"
ABAC_PATH = "policies/abac_rules.yaml"
ROW_OPTS = {"~500 (quick · stratified)": 500, "~2,000 (stratified)": 2000, "All rows": None}


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _collect_tsphol_rules() -> list:
    """Rebuild the TRAC rule list from the structured editor's session state."""
    out = []
    for r in TSPHOLRuleService().get_all():
        if str(r.get("then", "")).upper() != "DENY":
            out.append(r)
            continue
        name = r.get("rule_name")
        if not st.session_state.get(f"on_{name}", True):
            continue  # disabled
        new_r = {k: (v[:] if isinstance(v, list) else v) for k, v in r.items()}
        new_r["if"] = [dict(c) for c in r.get("if", [])]
        for c in new_r["if"]:
            if "lt" in c:
                key = f"lt_{name}"
                if key in st.session_state:
                    c["lt"] = float(st.session_state[key])
        out.append(new_r)
    return out


def _tsphol_editor():
    st.caption("Enable/disable each rule and edit its `lt` threshold. (Identity, transport "
               "and ALLOW rules are not shown.)")
    for r in TSPHOLRuleService().get_all():
        if str(r.get("then", "")).upper() != "DENY":
            continue
        name = r.get("rule_name")
        lt_cond = next((c for c in r.get("if", []) if "lt" in c), None)
        cols = st.columns([3, 2])
        cols[0].checkbox(name, value=st.session_state.get(f"on_{name}", True), key=f"on_{name}")
        if lt_cond is not None:
            cols[1].number_input(f"{lt_cond.get('predicate')} <", 0.0, 1.0,
                                 float(st.session_state.get(f"lt_{name}", lt_cond["lt"])),
                                 0.05, key=f"lt_{name}")


def _row_lookup(log_path: str, experiment: str) -> dict:
    """Per (persona, task_idx) context from the log rows, plus the E4 LLM verdict.

    Note: the row's own ``groundtruth_tools`` field actually stores the *candidate*
    (``input.tools``), so the real ground truth is taken from the dataset, not here.
    """
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    out = {}
    # New ``llm_inference_v1`` format: per-task LLM output (persona-independent). Fan it
    # out across every persona so the (persona, task) lookup is uniform with the old path.
    if log.get("schema") == "llm_inference_v1":
        for t in log.get("tasks", []):
            ti = t.get("task_idx")
            info = {
                "selected_tools": t.get("selected_tools") or [],
                "selected_mcps": t.get("selected_mcps") or [],
                "issue_codes": t.get("issue_codes"),
                "is_valid": t.get("is_valid"),
                "tool_match": t.get("tool_match"),
                "tool_jaccard": t.get("tool_jaccard"),
                "match_tag": t.get("match_tag"),
                "is_legitimate": None,  # persona-dependent; recomputed in the replay rows
                "llm_e4_decision": None,  # verdict is stored directly in is_valid
            }
            for persona in PERSONAS:
                out[(persona, ti)] = dict(info)
        return out
    for r in log["experiments"][experiment]["rows"]:
        out[(r.get("persona"), r.get("task_idx"))] = {
            "selected_tools": r.get("selected_tools") or [],
            "selected_mcps": r.get("selected_mcps") or [],
            "issue_codes": r.get("issue_codes"),
            "is_valid": r.get("is_valid"),
            "tool_match": r.get("tool_match"),
            "tool_jaccard": r.get("tool_jaccard"),
            "match_tag": r.get("match_tag"),
            "is_legitimate": r.get("is_legitimate"),
            "llm_e4_decision": None,
        }
    # E4 = LLM-only verdict: its decision IS the LLM's valid/invalid call. Use it to
    # recover the verdict for older validation logs that didn't persist is_valid.
    if log.get("evaluation_mode") == "validation" and "E4" in log["experiments"]:
        for r in log["experiments"]["E4"]["rows"]:
            key = (r.get("persona"), r.get("task_idx"))
            if key in out:
                out[key]["llm_e4_decision"] = r.get("final_decision")
    return out


def _replay(log_path, tasks, experiment, limit, policies, label, domain_source="inferred"):
    prog = st.progress(0.0, text=f"Replaying {label}…")
    rows, summary, _bc = rs.replay_experiment(
        log_path, tasks, experiment=experiment, limit=limit, policies=policies,
        domain_source=domain_source,
        progress_cb=lambda c, t: prog.progress(min(c / t, 1.0), text=f"Replaying {label}… {c}/{t}"))
    prog.empty()
    return rows, summary


def _metrics_block(title, h):
    st.markdown(f"#### {title}")
    a, b, c = st.columns(3)
    a.metric("SecFail", f"{h['secfail']*100:.1f}%",
             help="Security-failure rate: the fraction of **illegitimate** requests the stack "
                  "lets through (allows). illegit-allowed ÷ total-illegit. **Lower is better.**")
    b.metric("Legit-allow", f"{h['legit_allow']*100:.1f}%",
             help="The fraction of **legitimate** requests the stack allows through. "
                  "legit-allowed ÷ total-legit. **Higher is better.**")
    c.metric("Deny rate", f"{h['deny_rate']*100:.1f}%",
             help="The fraction of **all** requests denied by any layer (RBAC ∨ ABAC ∨ TRAC). "
                  "total-denied ÷ total-rows.")
    st.caption(f"Independent deny — RBAC {h['rbac_deny_rate']*100:.0f}% · "
               f"ABAC {h['abac_deny_rate']*100:.0f}% · TRAC {h['tsphol_deny_rate']*100:.0f}%")


def _authz_block(title, m):
    """Authorization-conditioned headline: TRAC scored only on authz-allowed traffic."""
    st.markdown(f"#### {title}")
    st.caption(f"Authorized (SPIFFE · mTLS · RBAC · ABAC allow): "
               f"**{m['authorized']}/{m['n']}** ({m['authorized_rate']*100:.0f}%) — "
               f"TRAC is scored on this traffic only.")
    a, b, c = st.columns(3)
    a.metric("Legit-allow", f"{m['legit_allow']*100:.1f}%",
             help="Of **authorized + correct-bundle** requests, the fraction the stack allows. "
                  "RBAC/ABAC already allowed them, so only TRAC can lower this. "
                  f"**Higher is better** — 100% means TRAC never blocks legitimate work. (n={m['legit_n']})")
    b.metric("SecFail · wrong-domain", f"{m['secfail']*100:.1f}%",
             help="Of **authorized + wrong-DOMAIN** requests (capability misuse RBAC/ABAC can't "
                  "see), the fraction the stack still allows — TRAC's deterministic scope. "
                  f"**Lower is better** — 0% means TRAC catches all. (n={m['wrong_domain_n']})")
    c.metric("TRAC over-deny", f"{m['trac_overdeny']*100:.1f}%",
             help="Legitimate authorized work TRAC wrongly blocked — the true availability cost.")
    st.caption(f"Semantic floor — same-domain wrong-tool: **{m['same_domain_n']}** "
               f"(deterministically uncatchable — the LLM's job). Of the {m['same_write_n']} "
               f"write-bearing ones, the `action_coherence` advisory flags "
               f"**{m['advisory_recovered']}** (non-blocking).")


def _trac_contrib_block(label, f):
    """TRAC acts two distinct ways: ENFORCE (revokes — changes the decision) and
    ADVISE (non-blocking warnings). Shown separately so the two never get conflated."""
    if label:
        st.markdown(f"##### {label}")
    warn_d = f.get("trac_warn_on_denied", 0)
    warn_a = f.get("trac_warn_on_allowed", 0)
    adv_total = f.get("trac_advisory_total", warn_d + warn_a)
    c1, c2, c3, c4 = st.columns(4)
    enforced_label = ("TRAC corrected the LLM" if f.get("mode") == "validation" else "Revoked (enforced)")
    c1.metric(enforced_label, f["trac_changed_on_approved"],
              help="Upstream-approved bundles TRAC flipped allow → deny via capability_coverage "
                   "(wrong-domain). In validation mode these are bundles the LLM itself had marked "
                   "valid (is_valid=true) — TRAC catching the model's false-approvals. These CHANGE "
                   "the outcome.")
    c2.metric("Revocation success", f"{f['trac_revoke_success'] * 100:.0f}%",
              help=f"Of those {f['trac_changed_on_approved']} revocations, "
                   f"{f['trac_revoke_correct']} correct catches, {f['trac_revoke_wrong']} false blocks.")
    c3.metric("Advisory warnings", adv_total,
              help="Non-blocking write_safety / action_coherence flags — a SEPARATE mechanism that "
                   "does NOT change the decision (this is why it differs from the revocations).")
    c4.metric("Redundant catches", f.get("trac_redundant", 0),
              help="Bundles TRAC would also deny, but an upstream layer (RBAC/ABAC, or the LLM gate "
                   "in validation mode) already denied them — defense-in-depth overlap, not unique "
                   "TRAC value (this is why the firing table's standalone TRAC count is higher).")
    denom = f.get("after_llm", f["after_abac"])
    upstream = ("upstream-approved (RBAC ∧ ABAC ∧ LLM)" if f.get("mode") == "validation"
                else "upstream-approved")
    st.caption(
        f"**Enforce** (changes decision): revoked **{f['trac_changed_on_approved']}** of "
        f"{denom} {upstream} → {f['trac_revoke_correct']} correct, "
        f"{f['trac_revoke_wrong']} false.   ·   **Advise** (no change): "
        f"**{adv_total}** warnings = {warn_d} on denied + {warn_a} on allowed.")


def _funnel_chart(f):
    """Horizontal defense-in-depth funnel: transactions remaining after each layer.
    SPIFFE/mTLS (and the LLM in selection mode) are pass-through; RBAC/ABAC/TRAC (and the LLM
    self-validation gate in validation mode) actually filter — colored distinctly so it's honest
    about which layers reduce the set."""
    import altair as alt
    mode = f.get("mode")
    after_llm = f.get("after_llm", f["after_abac"])
    llm_reject = f.get("llm_reject", 0)
    # True pipeline order: SPIFFE → mTLS → RBAC → ABAC → (LLM gate, validation only) → TRAC.
    rows = [
        {"stage": "Total requests", "remaining": f["total"], "label": f"{f['total']}", "kind": "total"},
        {"stage": "after SPIFFE", "remaining": f["total"],
         "label": f"{f['total']}   (identity — pass-through)", "kind": "pass"},
        {"stage": "after mTLS", "remaining": f["total"],
         "label": f"{f['total']}   (transport — pass-through)", "kind": "pass"},
        {"stage": "after RBAC", "remaining": f["after_rbac"],
         "label": f"{f['after_rbac']}   (−{f['rbac_deny']} identity/tool)", "kind": "gate"},
        {"stage": "after ABAC", "remaining": f["after_abac"],
         "label": f"{f['after_abac']}   (−{f['abac_deny']} attributes)", "kind": "gate"},
    ]
    # The LLM is a real self-validation GATE in validation mode; in selection mode it only
    # proposes the bundle (no gate), so the LLM stage is omitted from the funnel.
    if mode == "validation":
        rows.append({"stage": "after LLM gate", "remaining": after_llm,
                     "label": f"{after_llm}   (−{llm_reject} LLM rejected · is_valid=false)",
                     "kind": "gate"})
    rows.append({"stage": "✅ Approved (TRAC passed)", "remaining": f["approved"],
                 "label": f"{f['approved']}   (−{f['trac_deny']} task-relational)", "kind": "approved"})
    order = [r["stage"] for r in rows]
    data = pd.DataFrame(rows)
    enc = alt.Chart(data).encode(
        y=alt.Y("stage:N", sort=order, title=None,
                axis=alt.Axis(labelLimit=240, labelFontSize=12)),
        x=alt.X("remaining:Q", title="transactions remaining",
                scale=alt.Scale(domain=[0, max(f["total"], 1)])),
    )
    bars = enc.mark_bar(height=22).encode(
        color=alt.Color("kind:N", legend=None, scale=alt.Scale(
            domain=["total", "pass", "gate", "approved"],
            range=["#4C78A8", "#C9D6E5", "#4C78A8", "#54A24B"])))
    text = enc.mark_text(align="left", dx=5, fontSize=11, color="#1f2933").encode(text="label:N")
    return (bars + text).properties(height=240)


def _outcome_top(f, az):
    """Top-line outcome + honest quality for one policy set."""
    n = f["total"] or 1
    c1, c2, c3 = st.columns(3)
    appr_help = ("Transactions the full pipeline allowed end-to-end. In validation mode this is "
                 "RBAC ∧ ABAC ∧ LLM-validates ∧ TRAC (the LLM rejects is_valid=false bundles before "
                 "TRAC); in selection mode it is RBAC ∧ ABAC ∧ TRAC (the LLM only proposes the bundle)."
                 if f.get("mode") == "validation"
                 else "Transactions the full stack (RBAC ∧ ABAC ∧ TRAC) allowed.")
    c1.metric("Approved end-to-end", f"{f['approved']} / {f['total']}",
              f"{f['approved'] / n * 100:.0f}%", help=appr_help)
    c2.metric("Legitimate work allowed", f"{az['legit_allow'] * 100:.0f}%",
              help="Of authorized + correct-bundle requests, the fraction allowed. 100% means the "
                   "stack never blocks legitimate authorized work.")
    c3.metric("Security failures (TRAC scope)", f"{az['secfail'] * 100:.0f}%",
              help="Of authorized wrong-DOMAIN requests, the fraction that slipped through. 0% means "
                   "TRAC caught all the cross-domain capability misuse RBAC/ABAC cannot see.")


def _layer_roles(f):
    """One line per layer: what it's for + how many it uniquely removed."""
    n = f["total"] or 1
    mode = f.get("mode")
    adv_total = f.get("trac_advisory_total",
                      f.get("trac_warn_on_denied", 0) + f.get("trac_warn_on_allowed", 0))
    if mode == "validation":
        llm_line = (f"- **LLM** *(self-validation gate)* — *did the model judge the bundle acceptable?* "
                    f"→ **rejected {f.get('llm_reject', 0)}** (`is_valid=false`) before TRAC sees them\n")
        trac_verb = "**corrected** the LLM on"
    else:
        llm_line = ("- **LLM** *(tool selection)* — *the model proposes the bundle* → never abstains "
                    "(**pass-through**; it is the requester TRAC governs, not a gate)\n")
        trac_verb = "revoked"
    st.markdown(
        f"- **SPIFFE · mTLS** — cryptographic identity & mutual-TLS transport *(trust root; pass-through)*\n"
        f"- **RBAC** — *may this identity use these tools?* → denied **{f['rbac_deny']}** "
        f"({f['rbac_deny'] / n * 100:.0f}% of total)\n"
        f"- **ABAC** — *do the attributes (clearance · department · trust) permit it?* → denied "
        f"**{f['abac_deny']}** more\n"
        f"{llm_line}"
        f"- **TRAC** — *does the bundle match the task's domain & action?* → {trac_verb} "
        f"**{f['trac_deny']}** *(enforced)* + **{adv_total}** advisory warnings *(non-blocking)*"
    )


# Plain-language reason for each TRAC predicate that can deny or advise.
_ADVISORY_WHY = {
    "write_safety": "destructive op without a verifying read",
    "action_coherence": "read-intent task selected destructive tools",
    "tool_relevance": "selected tools are lexically irrelevant to the task",
    "capability_coverage": "bundle operates outside the task's domain",
}


def _task_snippet(tasks, ti, n=70):
    t = tasks[ti] if (ti is not None and ti < len(tasks)) else None
    if t is None:
        return ""
    txt = (t["input"]["task"] if isinstance(t, dict) else getattr(t, "task", "")) or ""
    return txt[:n]


def _denied_by_layer(x):
    if x.rbac_deny:
        return f"RBAC · {x.rbac_rule or 'deny'}"
    if x.abac_deny:
        return f"ABAC · {x.abac_rule or 'deny'}"
    return "—"


def _rev_from_funnel(fn):
    """Build a minimal revocation-audit dict from a saved funnel (for saves made before
    ``revocation_audit`` was persisted — the verdict breakdown is unavailable, counts aren't)."""
    if not fn:
        return {}
    return {
        "n_revoked": fn.get("trac_changed_on_approved", 0),
        "n_correct": fn.get("trac_revoke_correct", 0),
        "n_wrong": fn.get("trac_revoke_wrong", 0),
        "success": fn.get("trac_revoke_success", 1.0),
        "by_verdict": {}, "by_rule": {},
    }


def _revocation_audit_block(label, rev):
    """One policy set's ENFORCE detail: metrics + what the revoked bundles actually were.
    Mirrors the advisory block on the ADVISE side."""
    st.markdown(f"##### {label}")
    n = rev.get("n_revoked", 0)
    mode = rev.get("mode")
    m1, m2, m3 = st.columns(3)
    if mode == "validation":
        m1.metric("TRAC corrected the LLM", n,
                  help="Bundles RBAC ∧ ABAC AND the LLM-judge (is_valid=true) had APPROVED that TRAC "
                       "then flipped to DENY via `capability_coverage` — the model's false-approvals "
                       "TRAC caught. This is TRAC's **enforced** correction of the LLM.")
        m2.metric("Correct catches", rev.get("n_correct", 0),
                  help="Of those corrections, how many were RIGHT — the bundle the LLM validated was "
                       "genuinely wrong-domain (match ≠ correct). TRAC's true value over the LLM judge.")
        m3.metric("False blocks", rev.get("n_wrong", 0),
                  help="Of those corrections, how many were WRONG — TRAC overruled a bundle that was "
                       "actually correct (match = correct) and the LLM had rightly approved. The cost.")
    else:
        m1.metric("Revoked (allow→deny)", n,
                  help="The LLM's tool selections RBAC ∧ ABAC had ALLOWED that TRAC then flipped to DENY "
                       "via `capability_coverage` (the bundle operates outside the task's domain). This is "
                       "TRAC's **enforced** contribution — it changes the final decision.")
        m2.metric("Correct catches", rev.get("n_correct", 0),
                  help="Of those revocations, how many were RIGHT — the bundle was genuinely wrong-domain "
                       "(match ≠ correct). These are TRAC's true value: misuse RBAC/ABAC can't see.")
        m3.metric("False blocks", rev.get("n_wrong", 0),
                  help="Of those revocations, how many were WRONG — TRAC denied a bundle that was actually "
                       "correct (match = correct). This is the cost of enforcement; 0 means none lost.")
    succ_word = ("correction success" if mode == "validation" else "revocation success")
    st.caption(f"{succ_word.capitalize()} **{rev.get('success', 1.0) * 100:.0f}%** — correct catches ÷ "
               "revoked (a *correct catch* = the bundle was genuinely wrong-domain; a *false block* = a "
               "correct bundle TRAC wrongly denied).")
    if mode == "validation" and rev.get("n_llm_rejected_redundant"):
        st.caption(f"_(Plus **{rev['n_llm_rejected_redundant']}** bundles the LLM had already rejected "
                   "that TRAC would also deny — defense-in-depth agreement, not unique corrections.)_")
    bv = rev.get("by_verdict") or {}
    if bv:
        st.dataframe(pd.DataFrame([
            {"bundle was (match)": k, "revoked": v,
             "verdict": "✅ correct catch" if k != "correct" else "⚠️ false block"}
            for k, v in bv.items()]), hide_index=True, use_container_width=True)
    elif n:
        st.caption("_(verdict breakdown unavailable for this saved run — re-run to capture it)_")
    else:
        st.caption("— no revocations —")


def _revocation_rows(rows, tasks, limit=None):
    """List-of-dicts for the revoked drill-down (upstream-approved txns TRAC then DENIED), plus the
    total. Used live AND persisted to the saved run so the 'see why' survives a reload.

    By default returns **every** revoked transaction (both verdicts), ordered correct-catches first then
    false-blocks. If a ``limit`` is given and exceeded, the sample is **stratified** across both verdicts
    — the ASTRA dataset is ordered correct-candidates first, so a naive prefix would be all false-blocks
    and hide every correct catch."""
    revoked = [x for x in rows
               if not (x.rbac_deny or x.abac_deny)
               and (getattr(x, "llm_valid", None) is not False) and x.tsphol_deny]
    total = len(revoked)
    catches = [x for x in revoked if x.match_tag != "correct"]      # correct catches (bundle was wrong)
    false_blocks = [x for x in revoked if x.match_tag == "correct"]  # false blocks (bundle was correct)
    if limit and total > limit:
        n_catch = round(limit * len(catches) / total) if catches else 0
        n_catch = min(n_catch, len(catches))
        n_false = min(limit - n_catch, len(false_blocks))
        picked = catches[:n_catch] + false_blocks[:n_false]
    else:
        picked = catches + false_blocks
    sample = [{
        "persona": x.persona,
        "task_idx": x.task_idx,
        "task": _task_snippet(tasks, x.task_idx),
        "match": x.match_tag,
        "TRAC rule": x.tsphol_rule or "—",
        "why": _ADVISORY_WHY.get(x.tsphol_rule, x.tsphol_reason or "—"),
        "verdict": "✅ correct catch" if x.match_tag != "correct" else "⚠️ false block",
    } for x in picked]
    return sample, total


def _revocation_table(sample, total, label="", mode=None):
    """Render the 'See why' expander from a list of dicts (works live AND from a persisted saved
    sample). Heading is mode-aware: selection → TRAC *rejected* the LLM's selections; validation →
    TRAC *corrected* the LLM's approvals; unknown/legacy → the generic wording."""
    if not total:
        return
    suffix = f" — {label}" if label else ""
    if mode == "selection":
        head = (f"🔍 See why — TRAC rejected {total} of the LLM's tool selection(s) "
                f"that RBAC/ABAC had approved{suffix}")
    elif mode == "validation":
        head = (f"🔍 See why — TRAC corrected the LLM on {total} bundle(s) "
                f"RBAC/ABAC and the LLM had approved{suffix}")
    else:
        head = f"🔍 See why — TRAC revoked {total} transaction(s) RBAC/ABAC had approved{suffix}"
    with st.expander(head):
        if sample:
            st.dataframe(pd.DataFrame(sample), hide_index=True, use_container_width=True)
        if total > len(sample):
            n_catch = sum(1 for r in sample if r.get("verdict", "").startswith("✅"))
            st.caption(f"Showing a **stratified** sample of {len(sample)} of {total} "
                       f"({n_catch} correct catches · {len(sample) - n_catch} false blocks) — "
                       "proportional to the full verdict mix (click a column header to sort).")
        if mode == "validation":
            st.caption("The LLM-judge had marked these bundles **valid**; TRAC flipped them to DENY. "
                       "`correct catch` = the bundle was genuinely wrong (TRAC corrected the model); "
                       "`false block` = a correct bundle TRAC wrongly blocked (the cost).")
        else:
            st.caption("RBAC/ABAC ALLOWED these; TRAC flipped them to DENY. `correct catch` = the bundle "
                       "was genuinely wrong (wrong-domain / wrong-tool); `false block` = a correct bundle "
                       "TRAC wrongly blocked (the cost of leak-free inference).")


def _revocation_drilldown(rows, tasks, mode=None):
    """Live path: build the revoked sample from rows and render the expander."""
    if mode is None:
        mode = "validation" if any(getattr(x, "llm_valid", None) is not None for x in rows) else "selection"
    sample, total = _revocation_rows(rows, tasks)
    _revocation_table(sample, total, mode=mode)


_FIRE_LABEL = {"rbac": "RBAC", "abac": "ABAC", "tsphol": "TRAC"}
_FIRING_CAPTION = (
    "Per-layer **attribution**, each layer evaluated **independently** — one transaction can trip "
    "several layers, so these counts **overlap and sum to more than the denied-row total**. This is "
    "*not* the funnel: e.g. TRAC's standalone count here also includes bundles RBAC/ABAC already "
    "blocked, whereas the funnel above counts only TRAC's **unique** revocations."
)


def _firing_block(fire):
    for layer in ("rbac", "abac", "tsphol"):
        d = fire.get(layer, {})
        st.markdown(f"**{_FIRE_LABEL.get(layer, layer.upper())}** — {sum(d.values())} standalone denials")
        if d:
            st.dataframe(pd.DataFrame(list(d.items()), columns=["rule", "fired"]),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("— no denials —")


def _selection_accuracy(rows, lookup, tasks):
    """Distribution of how many ground-truth tools the LLM selected (per unique task)."""
    from collections import Counter
    dist = Counter()
    jac = []
    seen = set()
    for x in rows:
        if x.task_idx in seen:
            continue
        seen.add(x.task_idx)
        info = lookup.get((x.persona, x.task_idx), {})
        sel = set(info.get("selected_tools", []))
        t = tasks[x.task_idx]
        gt = set(getattr(t, "groundtruth_tools", []) or [])
        if not gt:
            continue
        dist[len(sel & gt)] += 1
        jac.append(len(sel & gt) / len(sel | gt) if (sel | gt) else 1.0)
    total = sum(dist.values())
    return dist, total, (sum(jac) / len(jac) if jac else 0.0)


def _validation_accuracy(rows, lookup):
    """LLM validate-verdict accuracy vs ground truth (match_tag), per unique task.

    Verdict from stored is_valid, else recovered from the E4 LLM-only decision.
    correct -> should be valid; wrong/null -> should be invalid.
    """
    from collections import defaultdict
    tab = defaultdict(lambda: {"n": 0, "valid": 0, "invalid": 0})
    seen = set()
    for x in rows:
        if x.task_idx in seen:
            continue
        seen.add(x.task_idx)
        info = lookup.get((x.persona, x.task_idx), {})
        isv, e4 = info.get("is_valid"), info.get("llm_e4_decision")
        if isv is not None:
            llm_valid = bool(isv)
        elif e4 is not None:
            llm_valid = e4 not in ("DENY", "DECEPTION_ROUTED")
        else:
            continue
        tag = info.get("match_tag") or "unknown"
        tab[tag]["n"] += 1
        tab[tag]["valid" if llm_valid else "invalid"] += 1
    return tab


def _llm_verdict(info):
    """LLM valid/invalid verdict for a validation row, or None if unavailable."""
    isv, e4 = info.get("is_valid"), info.get("llm_e4_decision")
    if isv is not None:
        return bool(isv)
    if e4 is not None:
        return e4 not in ("DENY", "DECEPTION_ROUTED")
    return None


def _corrective(rows, lookup):
    """Catch/rescue scoreboard: LLM-as-validator verdict × stack decision, per legitimacy.

    Keys per bucket: va/vd/ia/id = LLM (v)alid/(i)nvalid × stack (a)llow/(d)eny.
    catches = illeg['vd'] (illegit the LLM would allow, stack denies);
    rescues = legit['ia']  (legit the LLM would reject, stack allows).
    """
    out = {"legit": {"va": 0, "vd": 0, "ia": 0, "id": 0},
           "illeg": {"va": 0, "vd": 0, "ia": 0, "id": 0}, "has_verdict": 0}
    for x in rows:
        v = _llm_verdict(lookup.get((x.persona, x.task_idx), {}))
        if v is None:
            continue
        out["has_verdict"] += 1
        stack_deny = x.rbac_deny or x.abac_deny or x.tsphol_deny
        b = out["legit"] if x.is_legitimate else out["illeg"]
        b[("v" if v else "i") + ("d" if stack_deny else "a")] += 1
    return out


def _corrective_block(label, sc):
    st.markdown(f"##### {label}")
    catches, catch_den = sc["illeg"]["vd"], sc["illeg"]["vd"] + sc["illeg"]["va"]
    rescues, resc_den = sc["legit"]["ia"], sc["legit"]["ia"] + sc["legit"]["id"]
    m1, m2 = st.columns(2)
    m1.metric("Catches", f"{catches}/{catch_den}",
              help="Illegitimate bundles the LLM would ALLOW that the stack DENIES.")
    m2.metric("Rescues", f"{rescues}/{resc_den}",
              help="Legitimate bundles the LLM would REJECT that the stack ALLOWS.")
    with st.expander("2×2 detail"):
        for title, q in (("Illegitimate requests", sc["illeg"]), ("Legitimate requests", sc["legit"])):
            st.caption(title)
            st.dataframe(pd.DataFrame([
                {"LLM verdict": "valid", "stack ALLOW": q["va"], "stack DENY": q["vd"]},
                {"LLM verdict": "invalid", "stack ALLOW": q["ia"], "stack DENY": q["id"]},
            ]), hide_index=True, use_container_width=True)


def _tsphol_facts(L, domain_source="inferred"):
    """Human-readable *why* behind the agnostic TRAC decision — the facts, not just
    which rule fired: whether the bundle operates in the task's domain, the destructive-
    write-safety signal, and the action-coherence advisory. Also discloses where the
    'required domain' comes from, so the decision is auditable end-to-end."""
    p = L.get("predicates", {}) or {}
    req = sorted(p.get("RequiredCapabilities") or [])
    has = sorted(p.get("HasCapabilities") or [])
    miss = sorted(p.get("MissingHardCapabilities") or [])
    cd, cr = p.get("ContainsDelete"), p.get("ContainsRead")
    crbw = p.get("ContainsReadBeforeWrite")
    rim = p.get("ReadIntentMutatingBundle")
    bti = p.get("BundleToolsIrrelevant")
    st.markdown(
        "**① capability_coverage** *(enforced — changes the decision)* — does the bundle operate in the "
        "task's domain?\n\n"
        f"- **Task's domain (required):** `{', '.join(req) if req else '— (domain uncertain)'}`\n"
        f"- **Bundle provides:** `{', '.join(has) if has else '— (empty)'}`  "
        "·  *per tool = its MCP + read/write; a write also grants the read*\n"
        f"- **Missing:** `{', '.join(miss) if miss else 'none'}`  →  "
        + ("🔴 **DENY — wrong domain / empty**" if miss else "🟢 in-domain")
    )
    if domain_source == "inferred":
        st.caption(
            "ℹ️ **Where does the required domain come from?** It is **inferred from the task text alone** "
            "by a deterministic **BM25** lexical match against the public MCP tool catalog (the leak-free "
            "`d_inf` variant) — **no ground truth** "
            "is read. The candidate bundle, `match_tag` and `is_legitimate` play no part."
        )
    else:
        st.caption(
            "ℹ️ **Where does the required domain come from?** It is the **operator-declared workflow scope** "
            "— which MCP/domain the agent is authorised to act in for this task — *not* anything read from "
            "the candidate bundle. No live operator exists at benchmark time, so the harness substitutes the "
            "task's **gold MCP** as that scope (disclosed as `dₑₓₚ`, paper §8.2). The candidate's `match_tag` "
            "and `is_legitimate` are **scoring labels only** and never enter any layer's decision."
        )
    fired_ws = bool(cd) and not bool(crbw)
    st.markdown(
        "**② write_safety** *(advisory — warns, never denies)* — a destructive op (delete/drop) with no "
        "verifying read?\n\n"
        f"- ContainsDelete=`{cd}` · ContainsRead=`{cr}` · read-present(ReadBeforeWrite)=`{crbw}`  →  "
        + ("⚠️ **WARN — blind destructive write**" if fired_ws else "🟢 safe (no warning)")
    )
    st.markdown(
        "**③ action_coherence** *(advisory — warns, never denies)* — does a read-only-sounding task select "
        "destructive tools?\n\n"
        f"- ReadIntentMutatingBundle=`{rim}`  →  "
        + ("⚠️ **WARN — read-intent task, destructive bundle**" if rim else "🟢 coherent (no warning)")
    )
    st.markdown(
        "**④ tool_relevance** *(enforced — changes the decision)* — are the selected tools relevant to the "
        "task? *(BM25 of each tool's catalog description vs the task — the tool-level analogue of ①; it "
        "catches the wrong-domain / wrong-tool bundles the BM25 domain check misses)*\n\n"
        f"- BundleToolsIrrelevant=`{bti}`  →  "
        + ("🔴 **DENY — selected tools are irrelevant to the task**" if bti else "🟢 relevant")
    )
    st.caption(
        "**① capability_coverage** and **④ tool_relevance** can change ALLOW/DENY (**enforced**, complementary: "
        "domain-match + tool-match). **②③ are advisory** — they raise a deterministic warning but never block. "
        "The raw trace below lists only rules that **triggered a verdict**; rules evaluated-but-passed (e.g. "
        "write_safety when safe) are shown above with 🟢 and are intentionally *not* repeated below — so a "
        "single-rule trace does **not** mean the others were skipped."
    )
    if L.get("trace"):
        with st.expander("Rule firing trace (raw) — triggered rules only"):
            st.json(L["trace"])


def _trace_card(trace, domain_source="inferred"):
    labels = {"rbac": "RBAC", "abac": "ABAC", "tsphol": "TRAC"}
    deciding = trace.get("deciding_layer")
    for layer in ("rbac", "abac", "tsphol"):
        L = trace["layers"][layer]
        mark = "🔴" if L["denied"] else "🟢"
        crown = "  ⬅ **deciding layer**" if layer == deciding else ""
        st.markdown(f"{mark} **{labels[layer]}** — {L['decision']}"
                    + (f" · rule `{L['rule']}`" if L["rule"] else "") + crown)
        if L.get("reason"):
            st.caption(L["reason"])
        if layer == "tsphol":
            _tsphol_facts(L, domain_source)
        elif L["denied"] and L.get("trace"):
            with st.expander(f"{labels[layer]} reasoning detail"):
                st.json(L["trace"])


def _render_transaction_trace(persona, task_idx, lookup, tasks, mode, base_policies, mod_policies,
                              domain_source="inferred"):
    """Per-transaction deterministic trace — **identical in the live run view and the load-a-run
    view**. Re-evaluates the 3 isolated engines on demand for the baseline and modified policy sets."""
    info = lookup.get((persona, task_idx), {})
    tools = info.get("selected_tools", [])
    mcps = info.get("selected_mcps", [])
    codes = info.get("issue_codes")
    task = tasks[task_idx]
    # Real ground truth comes from the dataset (the log row's groundtruth_tools field
    # actually holds the candidate, not the correct bundle).
    if isinstance(task, dict):
        task_text = task["input"]["task"]
        gt_tools = task.get("groundtruth", {}).get("tools", [])
        gt_mcps = task.get("groundtruth", {}).get("mcp_servers", [])
    else:
        task_text = getattr(task, "task", "")
        gt_tools = list(getattr(task, "groundtruth_tools", []) or [])
        gt_mcps = list(getattr(task, "groundtruth_mcp", []) or [])

    st.caption(f"**Task:** {task_text}")
    st.markdown(f"**match_tag:** `{info.get('match_tag')}` · "
                f"**legitimate:** `{info.get('is_legitimate')}`")
    st.caption(
        "🔎 **How to read the trace:** layers run SPIFFE → mTLS → RBAC → ABAC → TRAC, **first-deny-wins**. "
        "RBAC/ABAC decide from (persona, bundle, attributes) only; **TRAC** additionally checks the bundle "
        "against the task's required domain (the source is shown below). "
        "The candidate's `match_tag` / `is_legitimate` are **scoring labels only** and never enter any "
        "layer's decision — so the stack is not 'graded against the answer'."
    )
    if domain_source == "inferred":
        from app.services.task_domain_classifier import infer_task_domain
        td = infer_task_domain(task_text)
        st.caption(f"🔬 TRAC domain source: **task-inferred (d_inf, leak-free)** → required domain = `{td}` "
                   "*(from task text only — no ground truth)*")
    else:
        td = gt_mcps[0] if gt_mcps else (mcps[0] if mcps else None)
        st.caption(f"TRAC domain source: **gold MCP (dₑₓₚ)** → required domain = `{td}` "
                   "*(operator-scope proxy — see §8.2)*")
    _llm_context_block(mode, info, tools, mcps, gt_tools, gt_mcps)
    with st.spinner("Tracing both policy sets…"):
        base_tr = rs.transaction_trace(persona, task_idx, tools, mcps, task_text, mode,
                                       base_policies, issue_codes=codes, task_domain=td)
        mod_tr = rs.transaction_trace(persona, task_idx, tools, mcps, task_text, mode,
                                      mod_policies, issue_codes=codes, task_domain=td)
    st.markdown("#### Deterministic stack trace")
    tl, tr_ = st.columns(2)
    with tl:
        st.markdown("##### 🅰 Baseline trace")
        _trace_card(base_tr, domain_source)
    with tr_:
        st.markdown("##### 🅱 Modified trace")
        _trace_card(mod_tr, domain_source)


def _fmt_bundle(tools, mcps):
    if not tools:
        return "_(none)_"
    dom = f"  ·  MCP: {', '.join(sorted(set(mcps)))}" if mcps else ""
    return f"`{', '.join(tools)}`{dom}"


def _llm_context_block(mode, info, tools, mcps, gt_tools, gt_mcps):
    """Mode-specific LLM I/O vs ground truth, to make the transaction legible."""
    st.markdown("#### LLM input/output vs ground truth")
    c1, c2 = st.columns(2)
    if mode == "selection":
        with c1:
            st.markdown("**🤖 LLM selected** (governed bundle)")
            st.markdown(_fmt_bundle(tools, mcps))
        with c2:
            st.markdown("**🎯 Ground truth** (correct bundle)")
            st.markdown(_fmt_bundle(gt_tools, gt_mcps))
        tm, tj = info.get("tool_match"), info.get("tool_jaccard")
        bits = []
        if tm is not None:
            bits.append(f"exact-match: {'✅' if tm else '❌'}")
        if tj is not None:
            bits.append(f"Jaccard: {tj:.2f}")
        if bits:
            st.caption(" · ".join(bits))
    else:  # validation
        with c1:
            st.markdown("**🤖 LLM validated** (candidate bundle)")
            st.markdown(_fmt_bundle(tools, mcps))
            is_valid = info.get("is_valid")
            codes = info.get("issue_codes")
            e4 = info.get("llm_e4_decision")
            if is_valid is not None or codes:
                verdict = "✅ valid" if is_valid else "❌ invalid"
                st.markdown(f"LLM verdict: **{verdict}**")
                if codes:
                    st.markdown("issue codes: " + ", ".join(f"`{c}`" for c in codes))
            elif e4 is not None:
                verdict = "❌ invalid" if e4 in ("DENY", "DECEPTION_ROUTED") else "✅ valid"
                st.markdown(f"LLM verdict: **{verdict}**")
                st.caption("Recovered from the E4 (LLM-only) run — its decision *is* the LLM's "
                           "valid/invalid verdict. Detailed `issue_codes` weren't persisted in "
                           "this older log; re-run to capture them.")
            else:
                st.caption("LLM verdict not stored in this log and no E4 run to recover it from.")
        with c2:
            st.markdown("**🎯 Ground truth** (correct bundle)")
            st.markdown(_fmt_bundle(gt_tools, gt_mcps))
            st.caption(f"This candidate is tagged `{info.get('match_tag')}` "
                       "(correct = matches ground truth; wrong/null = does not).")


PELAB_RUNS_DIR = os.path.join("datasets", "post_experiment_runs")


def _save_run_log(sel, experiment, limit, base_rows, mod_rows, mod_policies,
                  lookup, tasks, mode, disable, domain_source="inferred") -> str:
    """Persist one comparison run — aggregate metrics + policy edits + a sample of
    decisions that changed — to ``datasets/post_experiment_runs/`` so runs can be
    reviewed and discussed later (no per-row dump; everything here is recomputable)."""
    os.makedirs(PELAB_RUNS_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    def _block(rows):
        c = _corrective(rows, lookup)
        aud = rs.advisory_audit(rows)
        rev_sample, rev_total = _revocation_rows(rows, tasks, limit=2000)
        return {
            "headline": rs.headline(rows),
            "authz": rs.authz_headline(rows),
            "funnel": rs.stack_funnel(rows),
            "advisory": {
                "on_denied": aud["on_denied"], "on_allowed": aud["on_allowed"],
                "n_denied_rows": aud["n_denied_rows"], "n_allowed_rows": aud["n_allowed_rows"],
            },
            "revocation": rs.revocation_audit(rows),
            "revocation_sample": {"count": rev_total, "sample": rev_sample},
            "layer_firing": rs.layer_firing_summary(rows),
            "corrective": {
                "catches": c["illeg"]["vd"], "catch_den": c["illeg"]["vd"] + c["illeg"]["va"],
                "rescues": c["legit"]["ia"], "resc_den": c["legit"]["ia"] + c["legit"]["id"],
                "has_verdict": c["has_verdict"],
                "buckets": {"legit": c["legit"], "illeg": c["illeg"]},
            },
        }

    base, mod = _block(base_rows), _block(mod_rows)
    changed = [r for r in rs.compare(base_rows, mod_rows) if r["decision_changed"]]
    if mode == "selection":
        dist, total, mean_jac = _selection_accuracy(base_rows, lookup, tasks)
        acc = {"selection": {"distribution": {str(k): v for k, v in dict(dist).items()},
                             "total_tasks": total, "mean_jaccard": round(mean_jac, 4)}}
    else:
        acc = {"validation": {k: dict(v) for k, v in _validation_accuracy(base_rows, lookup).items()}}

    _, _, tsphol_mod = mod_policies
    # Only persist TRAC-related transactions (TRAC revoked OR advised, in either policy set) — keeps
    # the saved run small and the explorer's filters meaningful (the user navigates by task id).
    trac_keys = {(x.persona, x.task_idx) for x in base_rows if x.tsphol_deny or x.tsphol_advisory_rules}
    trac_keys |= {(x.persona, x.task_idx) for x in mod_rows if x.tsphol_deny or x.tsphol_advisory_rules}
    rec = {
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "log": {"name": sel["name"], "model": sel.get("model"), "mode": mode,
                "experiment": experiment, "limit": limit, "rows": len(base_rows)},
        "domain_source": domain_source,
        "modified_policies": {
            "disable": dict(disable),
            "tsphol_rules": [r.get("rule_name") for r in (tsphol_mod.get("rules") or [])],
        },
        "baseline": base,
        "modified": mod,
        "delta": {
            "secfail": round(mod["headline"]["secfail"] - base["headline"]["secfail"], 4),
            "legit_allow": round(mod["headline"]["legit_allow"] - base["headline"]["legit_allow"], 4),
            "deny_rate": round(mod["headline"]["deny_rate"] - base["headline"]["deny_rate"], 4),
        },
        "policy_drift_vs_log": len(rs.logged_divergence_keys(base_rows)),
        "accuracy": acc,
        "changed_decisions": {"count": len(changed), "sample": changed[:50]},
        # TRAC-related per-transaction inputs + the modified policy set, so the load-a-run view can
        # re-trace any TRAC transaction (revoked / advised) — identical to the live tracer.
        "trace_lookup": [{"persona": k[0], "task_idx": k[1], **v}
                         for k, v in lookup.items() if k in trac_keys],
        "policies_modified": list(mod_policies),
    }
    path = os.path.join(PELAB_RUNS_DIR, f"pelab_{ts}_{mode}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, default=str)
    return path


# ── Saved-run viewer ─────────────────────────────────────────────────────
def _list_saved_runs():
    """Saved post-experiment runs, newest first (filenames are timestamp-prefixed)."""
    return sorted(glob.glob(os.path.join(PELAB_RUNS_DIR, "pelab_*.json")), reverse=True)


def _backfill_funnel(fn, adv, firing):
    """Saves made before the advisory/redundant funnel fields existed lack trac_advisory_total,
    trac_warn_on_allowed and trac_redundant. Recover them from the saved advisory audit and
    layer-firing so the TRAC panel reconciles with the Assurance-advisories section."""
    if not fn:
        return fn
    fn = dict(fn)
    adv, firing = adv or {}, firing or {}
    if "trac_warn_on_allowed" not in fn:
        fn["trac_warn_on_allowed"] = adv.get("n_allowed_rows", 0)
    if "trac_warn_on_denied" not in fn:
        fn["trac_warn_on_denied"] = adv.get("n_denied_rows", 0)
    if "trac_advisory_total" not in fn:
        fn["trac_advisory_total"] = fn.get("trac_warn_on_denied", 0) + fn.get("trac_warn_on_allowed", 0)
    if "trac_redundant" not in fn:
        tsphol_fire = firing.get("tsphol") or firing.get("TRAC") or firing.get("TSPHOL") or {}
        tsphol_n = sum(tsphol_fire.values()) if isinstance(tsphol_fire, dict) else tsphol_fire
        fn["trac_redundant"] = max(tsphol_n - fn.get("trac_deny", 0), 0)
    return fn


def _render_saved_record(rec, path, tasks=None):
    """Render a saved comparison (aggregate metrics only — no per-row replay)."""
    lg = rec.get("log", {})
    st.caption(f"💾 `{os.path.basename(path)}` · saved {rec.get('saved_at', '?')}")
    st.markdown(
        f"**Source log:** `{lg.get('name')}` · **model** `{lg.get('model')}` · "
        f"**mode** `{lg.get('mode')}` · **experiment** `{lg.get('experiment')}` · "
        f"**rows** {lg.get('rows', 0):,} · **limit** `{lg.get('limit')}`")
    disable = (rec.get("modified_policies", {}) or {}).get("disable", {}) or {}
    dis_str = ", ".join(k.upper() for k, v in disable.items() if v) or "none"
    st.markdown(f"**Modified policy set —** disabled layers: `{dis_str}` · "
                f"policy drift vs log: `{rec.get('policy_drift_vs_log', 0)}`")
    _dsrc = rec.get("domain_source", "inferred")
    st.markdown(f"**TRAC domain source —** "
                + ("`task-inferred · d_inf` 🔬 *(leak-free — required domain from task text only, no "
                   "ground truth)*" if _dsrc == "inferred"
                   else "`gold MCP · dₑₓₚ` *(operator-scope proxy from the gold MCP — paper §8.2)*"))

    base, mod = rec.get("baseline", {}) or {}, rec.get("modified", {}) or {}

    # ── How the stack governed this run (new saves) ──
    base_az, mod_az = base.get("authz"), mod.get("authz")
    base_fn = _backfill_funnel(base.get("funnel"), base.get("advisory"), base.get("layer_firing"))
    mod_fn = _backfill_funnel(mod.get("funnel"), mod.get("advisory"), mod.get("layer_firing"))
    if base_az and base_fn:
        st.markdown("## How the stack governed this run")
        _outcome_top(base_fn, base_az)
        st.altair_chart(_funnel_chart(base_fn), use_container_width=True)
        _layer_roles(base_fn)
        st.markdown("#### TRAC — the deterministic differentiator")
        _trac_contrib_block("", base_fn)
        st.caption(f"Semantic floor — **{base_az.get('same_domain_n', 0)}** same-domain wrong-tool "
                   f"bundles (the LLM's job); `action_coherence` flags "
                   f"**{base_az.get('advisory_recovered', 0)}** of {base_az.get('same_write_n', 0)} writes.")
        if mod_fn and mod_az:
            with st.expander("🅱 Modified policy set — comparison", expanded=False):
                _outcome_top(mod_fn, mod_az)
                st.altair_chart(_funnel_chart(mod_fn), use_container_width=True)
                _trac_contrib_block("", mod_fn)
    else:
        st.info("This run was saved before the authorization-conditioned metrics existed — "
                "showing the whole-stack view only. Re-run it to capture the new metrics.")

    # ── Revocation audit summary (ENFORCE detail — mirror of advisories) ──
    base_rev = base.get("revocation") or _rev_from_funnel(base_fn)
    mod_rev = mod.get("revocation") or _rev_from_funnel(mod_fn)
    if base_rev.get("n_revoked") or mod_rev.get("n_revoked"):
        st.markdown("### 🛑 Revocation audit — TRAC *changed* the decision (allow→deny)")
        st.caption("The ENFORCE side of TRAC: upstream-approved (RBAC ∧ ABAC) bundles that "
                   "`capability_coverage` revoked because they operate outside the task's domain.")
        rv1, rv2 = st.columns(2)
        with rv1:
            _revocation_audit_block("🅰 Baseline", base_rev)
        with rv2:
            _revocation_audit_block("🅱 Modified", mod_rev)
        # 'See why' drill-down — rendered from the sample saved with the run (survives reload).
        base_rs = base.get("revocation_sample") or {}
        mod_rs = mod.get("revocation_sample") or {}
        if base_rs.get("sample"):
            _revocation_table(base_rs["sample"], base_rs.get("count", len(base_rs["sample"])),
                              "baseline", mode=base_rev.get("mode"))
        if mod_rs.get("sample"):
            _revocation_table(mod_rs["sample"], mod_rs.get("count", len(mod_rs["sample"])),
                              "modified", mode=mod_rev.get("mode"))
        if not base_rs and base_rev.get("n_revoked"):
            st.caption("_(per-transaction drill-down wasn't saved with this older run — re-run to capture it.)_")

    # ── Advisory audit summary (new saves) ──
    base_adv = base.get("advisory") or {}
    if base_adv:
        st.markdown("### Assurance advisories")
        st.caption("Two deterministic, agnostic predicates flag transactions without changing ALLOW/DENY "
                   "(the enforcing `capability_coverage` + `tool_relevance` denials are in the Revocation "
                   "audit): **`write_safety`** (destructive-without-verify), **`action_coherence`** "
                   "(read-intent task with destructive tools).")
        a1, a2 = st.columns(2)
        a1.metric("Warnings on already-denied", base_adv.get("n_denied_rows", 0),
                  help="Advisory alerts on transactions RBAC/ABAC/TRAC already DENIED — a deterministic "
                       "warning on the intent recorded for the audit trail. Non-blocking: does NOT change "
                       "the (deny) outcome.")
        a2.metric("Alerts on allowed", base_adv.get("n_allowed_rows", 0),
                  help="Advisory alerts on transactions the stack ALLOWED — a live flag on something that "
                       "passed (e.g. a destructive write). Non-blocking: does NOT change the (allow) "
                       "outcome; surfaced for the operator to review.")
        rules = sorted(set(base_adv.get("on_denied", {})) | set(base_adv.get("on_allowed", {})))
        if rules:
            st.dataframe(pd.DataFrame([
                {"advisory rule": r, "on denied": base_adv.get("on_denied", {}).get(r, 0),
                 "on allowed": base_adv.get("on_allowed", {}).get(r, 0)} for r in rules]),
                hide_index=True, use_container_width=True)

    # ── Whole-stack (legacy) — only for old saves that lack the funnel ──
    if not base_fn:
        with st.expander("Whole-stack vs ground-truth (legacy view)", expanded=True):
            lw, rw = st.columns(2)
            with lw:
                _metrics_block("🅰 Baseline", base.get("headline", {}))
            with rw:
                _metrics_block("🅱 Modified", mod.get("headline", {}))
                d = rec.get("delta", {}) or {}
                st.caption(f"Δ vs baseline — SecFail {d.get('secfail', 0)*100:+.1f} pp · "
                           f"Legit-allow {d.get('legit_allow', 0)*100:+.1f} pp · "
                           f"Deny {d.get('deny_rate', 0)*100:+.1f} pp")

    # ── Layer firing ──
    st.markdown("### Which rules fired (per layer)")
    st.caption(_FIRING_CAPTION)
    fl, fr = st.columns(2)
    with fl:
        st.markdown("##### 🅰 Baseline")
        _firing_block(base.get("layer_firing", {}))
    with fr:
        st.markdown("##### 🅱 Modified")
        _firing_block(mod.get("layer_firing", {}))

    # Accuracy (selection or validation)
    acc = rec.get("accuracy", {}) or {}
    if "selection" in acc:
        s = acc["selection"]
        dist, total = s.get("distribution", {}) or {}, s.get("total_tasks", 0)
        st.markdown("### LLM tool-selection accuracy")
        adf = pd.DataFrame([
            {"ground-truth tools selected": f"{k} of 3" + (" (exact)" if k == 3 else ""),
             "tasks": dist.get(str(k), 0),
             "%": round(100 * dist.get(str(k), 0) / total, 1) if total else 0.0}
            for k in (3, 2, 1, 0)])
        st.dataframe(adf, hide_index=True, use_container_width=True)
        if total:
            st.caption(f"Exact-match: {100*dist.get('3', 0)/total:.1f}% · "
                       f"mean Jaccard: {s.get('mean_jaccard', 0):.2f} · {total:,} tasks.")
    elif "validation" in acc:
        tab = acc["validation"] or {}
        st.markdown("### LLM validation accuracy")
        order = ["correct", "wrong", "null"]
        rows_out, tot_n, tot_ok = [], 0, 0
        for tag in [t for t in order if t in tab] + [t for t in tab if t not in order]:
            dd = tab[tag]
            should_valid = (tag == "correct")
            ok = dd.get("valid", 0) if should_valid else dd.get("invalid", 0)
            n = dd.get("n", 0)
            tot_n += n
            tot_ok += ok
            rows_out.append({"match_tag": tag, "tasks": n, "LLM→valid": dd.get("valid", 0),
                             "LLM→invalid": dd.get("invalid", 0),
                             "should be": "valid" if should_valid else "invalid",
                             "LLM accuracy": f"{(ok/n*100) if n else 0:.1f}%"})
        if rows_out:
            st.dataframe(pd.DataFrame(rows_out), hide_index=True, use_container_width=True)
            if tot_n:
                st.caption(f"Overall LLM validation accuracy: {100*tot_ok/tot_n:.1f}% "
                           f"over {tot_n:,} tasks.")

    # Changed-decision sample
    cd = rec.get("changed_decisions", {}) or {}
    sample = cd.get("sample", []) or []
    st.markdown("### Changed decisions")
    st.caption(f"{cd.get('count', 0):,} decisions changed under the modified policy "
               f"(showing {len(sample)} sampled rows saved with this run).")
    if sample:
        cols = ["persona", "task_idx", "domain", "match_tag", "is_legitimate",
                "base_decision", "base_layer", "base_rule",
                "mod_decision", "mod_layer", "mod_rule"]
        sdf = pd.DataFrame(sample)
        st.dataframe(sdf[[c for c in cols if c in sdf.columns]],
                     hide_index=True, use_container_width=True, height=300)

    # ── Transaction explorer — re-trace ANY saved transaction (identical to the live view) ──
    tl_raw = rec.get("trace_lookup")
    pm = rec.get("policies_modified")
    base = os.path.basename(path)
    if tl_raw and pm and tasks is not None:
        st.markdown("## Transaction explorer")
        st.caption("Only **TRAC-related** transactions are saved here (TRAC revoked or advised them). "
                   "**Type a task_id** (copy one from the audit / revocation tables above) to trace it.")
        if st.checkbox("🔎 Load the per-transaction trace drill-down (re-evaluates on demand)",
                       value=False, key=f"saved_expl_{base}"):
            lookup = {(d["persona"], int(d["task_idx"])):
                      {k: v for k, v in d.items() if k not in ("persona", "task_idx")} for d in tl_raw}
            mode = (rec.get("log") or {}).get("mode", "validation")
            valid_tids = sorted({t for (_p, t) in lookup})
            st.caption(f"{len(valid_tids):,} TRAC-impacted task_ids saved (range {valid_tids[0]}–{valid_tids[-1]}).")
            c1, c2 = st.columns([1, 2])
            tid = int(c1.number_input("Trace task_id", min_value=int(valid_tids[0]),
                                      max_value=int(valid_tids[-1]), value=int(valid_tids[0]), step=1,
                                      key=f"se_tid_{base}"))
            personas_for_task = sorted({p for (p, t) in lookup if t == tid})
            if personas_for_task:
                persona = (c2.selectbox("persona (RBAC/ABAC view)", personas_for_task, key=f"se_pp_{base}")
                           if len(personas_for_task) > 1 else personas_for_task[0])
                if len(personas_for_task) == 1:
                    c2.caption(f"persona: **{persona}** (only one for this task)")
                _render_transaction_trace(persona, tid, lookup, tasks, mode,
                                          rs.baseline_policies(), tuple(pm),
                                          rec.get("domain_source", "inferred"))
            else:
                st.warning(f"task_id **{tid}** isn't a TRAC-impacted transaction in this saved run — "
                           "pick a task_id that appears in the Revocation / Assurance tables above.")
    elif tasks is not None:
        st.caption("ℹ️ This run was saved before per-transaction traces were persisted — "
                   "re-run and save to enable the transaction explorer here.")


def _render_saved_run_viewer(tasks):
    st.markdown(
        "Load a previously-saved post-experiment comparison and review its results — "
        "aggregate metrics, the policy edits used, and a sample of the decisions that "
        "changed. **No re-run, no LLM calls.**")
    paths = _list_saved_runs()
    if not paths:
        st.info("No saved runs yet. Run a comparison in **▶ Run a new comparison** — each "
                "run is auto-saved to `datasets/post_experiment_runs/`.")
        return

    def _label(p):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            lg = d.get("log", {}) or {}
            return (f"{os.path.basename(p)}  ·  {lg.get('model')}  ·  {lg.get('mode')}  ·  "
                    f"{d.get('saved_at', '')}")
        except Exception:
            return os.path.basename(p)

    labels = [_label(p) for p in paths]
    chosen = st.selectbox("Saved run", labels)
    path = paths[labels.index(chosen)]
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except Exception as e:
        st.error(f"Could not read saved run `{os.path.basename(path)}`: {e}")
        return
    _render_saved_record(rec, path, tasks)


def render_post_experiment_lab(tasks, personas):
    st.title("📊 Post-Experiment Lab")
    st.markdown(
        "Re-run the deterministic stack (RBAC · ABAC · TRAC) over the bundles already "
        "recorded in a log — **no new LLM inference** — and compare the **baseline** "
        "(original policies) with a **modified** policy set you edit below.")

    mode_choice = st.radio("Mode", ["▶ Run a new comparison", "📂 Load a saved run"],
                           horizontal=True, label_visibility="collapsed")
    if mode_choice.startswith("📂"):
        _render_saved_run_viewer(tasks)
        return

    logs = rs.list_run_logs()
    if not logs:
        st.warning("No logs found. Produce one in the **🧪 Experiment LLM Lab**, or add a "
                   "legacy log under `datasets/experiment_logs/`.")
        return
    labels = [f"{l['name']}  ·  {l['model']}  ·  {l['mode']}" for l in logs]
    c1, c2 = st.columns([4, 1])
    chosen = c1.selectbox("Experiment log", labels)
    sel = logs[labels.index(chosen)]
    # Always use the full-stack experiment (E1) as the row source: the lab reconstructs
    # the full stack from the bundle, so E1 is the only meaningful fidelity baseline.
    experiment = "E1" if "E1" in sel["experiments"] else sel["experiments"][0]
    rows_label = c2.selectbox("Rows", list(ROW_OPTS.keys()), index=1)
    limit = ROW_OPTS[rows_label]
    if limit:
        st.caption(
            f"ℹ️ The **{rows_label}** preset takes a **stratified sample** — whole tasks "
            "(all 6 personas), balanced across `correct` / `wrong` / `null` in the same "
            "proportion as the dataset (≈50 / 40 / 10%). It is **not** the first N rows, so "
            "quick runs include bundle-level attacks (wrong/null), not just authorised-domain "
            "tasks. Pick **All rows** for the complete picture.")
    # ── Policy editor ────────────────────────────────────────────────────
    with st.expander("⚙️ Edit policies — RBAC · ABAC · TRAC", expanded=False):
        st.caption("Fully disable a whole layer for the **modified** run (its edits are then "
                   "ignored), or edit individual rules in the tabs below.")
        dc1, dc2, dc3 = st.columns(3)
        dis_rbac = dc1.checkbox("🚫 Disable RBAC entirely", key="dis_rbac")
        dis_abac = dc2.checkbox("🚫 Disable ABAC entirely", key="dis_abac")
        dis_tsphol = dc3.checkbox("🚫 Disable TRAC entirely", key="dis_tsphol")
        t_rbac, t_abac, t_ts = st.tabs(["RBAC", "ABAC", "TRAC"])
        with t_rbac:
            if dis_rbac:
                st.info("RBAC is disabled for the modified run — these edits are ignored.")
            st.caption("Full RBAC policy (YAML) — edit roles, MCP/tools, allow/deny rules.")
            st.text_area("rbac", value=st.session_state.get("pel_rbac", _read_text(RBAC_PATH)),
                         height=320, key="pel_rbac", label_visibility="collapsed")
        with t_abac:
            if dis_abac:
                st.info("ABAC is disabled for the modified run — these edits are ignored.")
            st.caption("Full ABAC rules (YAML) — edit `match_attributes`, operators and values.")
            st.text_area("abac", value=st.session_state.get("pel_abac", _read_text(ABAC_PATH)),
                         height=320, key="pel_abac", label_visibility="collapsed")
        with t_ts:
            if dis_tsphol:
                st.info("TRAC is disabled for the modified run — these edits are ignored.")
            _tsphol_editor()
        rcol1, rcol2 = st.columns(2)
        if rcol1.button("↺ Reset policies to original"):
            for k in ("pel_rbac", "pel_abac", "dis_rbac", "dis_abac", "dis_tsphol"):
                st.session_state.pop(k, None)
            for r in TSPHOLRuleService().get_all():
                st.session_state.pop(f"on_{r.get('rule_name')}", None)
                st.session_state.pop(f"lt_{r.get('rule_name')}", None)
            st.rerun()

    # ── TRAC domain source: always leak-free task-inferred (the gold/oracle path is gone) ──
    domain_source = "inferred"
    st.caption("🔬 **`capability_coverage` learns the task's required domain leak-free** — via standard "
               "**BM25** lexical retrieval over the public MCP tool catalog (task text only, **zero ground "
               "truth**; no gold-MCP / oracle shortcut). It is exact on ~64% of tasks and abstains on the "
               "ambiguous rest, so the deterministic domain check stays honest about its limits.")

    # ── The single action button ─────────────────────────────────────────
    if st.button("▶ Run comparison", type="primary"):
        try:
            if st.session_state.get("dis_rbac"):
                rbac_mod = rbac_open()
            else:
                rbac_mod = yaml.safe_load(st.session_state.get("pel_rbac") or "") or {"policies": []}
            if st.session_state.get("dis_abac"):
                abac_mod = abac_open()
            else:
                abac_mod = yaml.safe_load(st.session_state.get("pel_abac") or "") or {"rules": []}
        except yaml.YAMLError as e:
            st.error(f"Policy YAML parse error: {e}")
            return
        tsphol_mod = tsphol_open() if st.session_state.get("dis_tsphol") else {"rules": _collect_tsphol_rules()}
        mod_policies = (rbac_mod, abac_mod, tsphol_mod)

        base_key = (sel["path"], experiment, limit, domain_source)
        if st.session_state.get("pel_base_key") != base_key:
            base_rows, base_summ = _replay(sel["path"], tasks, experiment, limit,
                                           rs.baseline_policies(), "baseline", domain_source)
            st.session_state["pel_base_rows"] = base_rows
            st.session_state["pel_base_summ"] = base_summ
            st.session_state["pel_base_key"] = base_key
        mod_rows, mod_summ = _replay(sel["path"], tasks, experiment, limit, mod_policies,
                                     "modified", domain_source)
        st.session_state["pel_mod_rows"] = mod_rows
        st.session_state["pel_mod_summ"] = mod_summ
        st.session_state["pel_mod_policies"] = mod_policies
        st.session_state["pel_lookup"] = _row_lookup(sel["path"], experiment)
        st.session_state["pel_mode"] = sel["mode"]
        st.session_state["pel_domain_source"] = domain_source
        # Persist this run's results so it can be reviewed/discussed later.
        try:
            disable = {"rbac": bool(st.session_state.get("dis_rbac")),
                       "abac": bool(st.session_state.get("dis_abac")),
                       "tsphol": bool(st.session_state.get("dis_tsphol"))}
            saved = _save_run_log(sel, experiment, limit, base_rows, mod_rows, mod_policies,
                                  st.session_state["pel_lookup"], tasks, sel["mode"], disable,
                                  domain_source)
            st.session_state["pel_last_saved"] = saved
        except Exception as e:  # never let logging break the run
            st.session_state["pel_last_saved"] = None
            st.warning(f"Run completed, but saving the run log failed: {e}")

    base_rows = st.session_state.get("pel_base_rows")
    mod_rows = st.session_state.get("pel_mod_rows")
    if not base_rows or not mod_rows:
        st.info("Edit policies if you like, then click **Run comparison**.")
        return

    # ── Deterministic re-evaluation (no unreproducible rows) ─────────────
    # TRAC is purely deterministic over the cached bundle, so every row is
    # reproducible. Decisions that differ from the ORIGINAL logged run reflect
    # intended policy drift (the active stack differs from the one that generated
    # this log) — they are kept, not excluded.
    st.markdown("## Comparison")
    drift = rs.logged_divergence_keys(base_rows)
    n_now = len(base_rows)
    note = (f"Deterministic re-evaluation over {n_now:,} cached bundles · mode "
            f"{st.session_state['pel_base_summ']['mode']}")
    if drift:
        note += (f" · {len(drift)} decision(s) differ from the original logged run "
                 "— policy drift (active stack ≠ the stack that generated this log), "
                 "not a replay gap")
    else:
        note += " · reproduces the original logged run exactly"
    st.caption(note)
    if st.session_state.get("pel_last_saved"):
        st.caption(f"💾 Run saved to `{st.session_state['pel_last_saved']}` "
                   "(aggregate metrics + policy edits + changed-decision sample).")

    with st.expander("ℹ️ How to read these results"):
        st.markdown(
            "**Rows are `task × persona`.** Every task is judged by all 6 personas, so one "
            "task becomes 6 rows.\n\n"
            "**`legitimate` ≠ `correct`.** `match_tag = correct` is a *per-task* label — the "
            "**bundle** matches ground truth. `legitimate` is *per-row*: the bundle is "
            "`correct` **and** the persona is **authorised** for that domain. So an "
            "*illegitimate* row is often a perfectly correct bundle requested by an "
            "**unauthorised persona** — an access-control violation the LLM can't see "
            "(it only judges the bundle). This is why one `correct` task yields both "
            "legitimate and illegitimate rows.\n\n"
            "**SecFail vs Legit-allow** are computed over **different populations** "
            "(illegitimate vs legitimate rows), so they are independent and need not sum to 1.\n\n"
            "**Rule firings overlap.** RBAC / ABAC / TRAC are evaluated independently, so a "
            "single row can be denied by several layers at once. The per-layer firing counts "
            "therefore **sum to more than the number of denied rows** — they are attribution, "
            "not a partition.")

    base_h, mod_h = rs.headline(base_rows), rs.headline(mod_rows)
    base_az, mod_az = rs.authz_headline(base_rows), rs.authz_headline(mod_rows)
    base_fn, mod_fn = rs.stack_funnel(base_rows), rs.stack_funnel(mod_rows)
    base_fire, mod_fire = rs.layer_firing_summary(base_rows), rs.layer_firing_summary(mod_rows)

    # ── How the stack governed this run (baseline = current policies) ────
    st.markdown("## How the stack governed this run")
    st.caption("Defense-in-depth: each layer removes a class of bad requests; what survives is approved. "
               "The security comes from the **stack**, not the model.")
    _outcome_top(base_fn, base_az)
    st.altair_chart(_funnel_chart(base_fn), use_container_width=True)
    _layer_roles(base_fn)

    st.markdown("#### TRAC — the deterministic differentiator")
    st.caption("Beyond authorization, TRAC **warns** on the intent of already-denied requests and "
               "**revokes** wrong-domain bundles RBAC/ABAC let through — and we score how correct those "
               "revocations were.")
    _trac_contrib_block("", base_fn)
    st.caption(f"Semantic floor — **{base_az['same_domain_n']}** same-domain wrong-tool bundles are "
               f"deterministically uncatchable (the LLM's job); the `action_coherence` advisory flags "
               f"**{base_az['advisory_recovered']}** of the {base_az['same_write_n']} write-bearing ones.")
    _revocation_drilldown(base_rows, tasks)

    # ── Modified policy set — comparison (secondary) ─────────────────────
    with st.expander("🅱 Modified policy set — comparison", expanded=False):
        _outcome_top(mod_fn, mod_az)
        st.altair_chart(_funnel_chart(mod_fn), use_container_width=True)
        d_la = (mod_az["legit_allow"] - base_az["legit_allow"]) * 100
        d_sf = (mod_az["secfail"] - base_az["secfail"]) * 100
        st.caption(f"Δ vs baseline — Legit-allow {d_la:+.1f} pp · SecFail(wrong-domain) {d_sf:+.1f} pp · "
                   f"Approved {mod_fn['approved'] - base_fn['approved']:+d}")
        _trac_contrib_block("", mod_fn)

    # ── Details on demand (keeps the page fast & scrollable) ─────────────
    lookup = st.session_state["pel_lookup"]
    mode = st.session_state["pel_mode"]
    st.markdown("---")
    st.caption("Detail tables load on demand — toggle what you need (keeps the page fast).")
    dc1, dc2, dc3 = st.columns(3)
    show_fire = dc1.checkbox("Rule firings (attribution)", key="pel_show_fire")
    show_adv = dc2.checkbox("TRAC detail (revoke + advise)", key="pel_show_adv")
    show_llm = dc3.checkbox("LLM accuracy", key="pel_show_llm")

    if show_fire:
        st.markdown("##### Which rules fired (per layer)")
        st.caption(_FIRING_CAPTION)
        fl, fr = st.columns(2)
        with fl:
            st.markdown("###### 🅰 Baseline")
            _firing_block(base_fire)
        with fr:
            st.markdown("###### 🅱 Modified")
            _firing_block(mod_fire)

    # ── Revocation audit (ENFORCE: TRAC changed the decision) ──
    if show_adv:
        st.markdown("### 🛑 Revocation audit — TRAC *changed* the decision (allow→deny)")
        st.caption("The ENFORCE side of TRAC: upstream-approved (RBAC ∧ ABAC) bundles that "
                   "`capability_coverage` revoked for operating outside the task's domain — scored as "
                   "correct catches vs false blocks. (The per-transaction list is in the primary view above.)")
        rv1, rv2 = st.columns(2)
        with rv1:
            _revocation_audit_block("🅰 Baseline", rs.revocation_audit(base_rows))
        with rv2:
            _revocation_audit_block("🅱 Modified", rs.revocation_audit(mod_rows))

    # ── Assurance advisories (TRAC alerts that don't change the decision) ───
    base_aud, mod_aud = rs.advisory_audit(base_rows), rs.advisory_audit(mod_rows)
    if show_adv and any(a["n_denied_rows"] or a["n_allowed_rows"] for a in (base_aud, mod_aud)):
        st.markdown("### ⚠️ Assurance advisories — TRAC flagged, *not* blocked")
        st.caption("Two deterministic, agnostic predicates assess **every** transaction and raise an alert "
                   "without changing ALLOW/DENY (the *enforcing* `capability_coverage` + `tool_relevance` "
                   "denials appear in the **Revocation audit**, not here). On an **already-denied** "
                   "transaction the alert is a *warning on the intent* for the audit trail; on an "
                   "**allowed** one it is a live flag to review. **`write_safety`** = destructive-without-"
                   "verify.  **`action_coherence`** = read-intent task that selected destructive tools.")
        ac1, ac2 = st.columns(2)
        for col, label, aud in ((ac1, "🅰 Baseline", base_aud), (ac2, "🅱 Modified", mod_aud)):
            with col:
                st.markdown(f"##### {label}")
                m1, m2 = st.columns(2)
                m1.metric("On already-denied (warning on intent)", aud["n_denied_rows"],
                          help="Advisory alerts on transactions RBAC/ABAC/TRAC already DENIED — a "
                               "deterministic warning on the intent recorded for the audit trail. "
                               "Non-blocking: does NOT change the (deny) outcome.")
                m2.metric("On allowed (live alert)", aud["n_allowed_rows"],
                          help="Advisory alerts on transactions the stack ALLOWED — a live flag on "
                               "something that passed (e.g. a destructive write). Non-blocking: does NOT "
                               "change the (allow) outcome; surfaced for the operator to review.")
                allrules = sorted(set(aud["on_denied"]) | set(aud["on_allowed"]))
                if allrules:
                    st.dataframe(pd.DataFrame([
                        {"advisory rule": r, "on denied": aud["on_denied"].get(r, 0),
                         "on allowed": aud["on_allowed"].get(r, 0)} for r in allrules]),
                        hide_index=True, use_container_width=True)
                else:
                    st.caption("— no advisories —")

        # ── See why: drill-down on the already-denied alerts (baseline) ──
        if base_aud["denied_alerts"]:
            with st.expander(f"🔍 See why — {base_aud['n_denied_rows']} TRAC alert(s) on "
                             f"already-denied transactions (baseline)"):
                tbl = []
                for x in base_aud["denied_alerts"][:200]:
                    alerts = [r for r in (x.tsphol_advisory_rules or []) if r]
                    tbl.append({
                        "persona": x.persona,
                        "task_idx": x.task_idx,
                        "task": _task_snippet(tasks, x.task_idx),
                        "match": x.match_tag,
                        "denied by": _denied_by_layer(x),
                        "TRAC alert": ", ".join(alerts),
                        "why": "; ".join(_ADVISORY_WHY.get(r, r) for r in alerts),
                    })
                st.dataframe(pd.DataFrame(tbl), hide_index=True, use_container_width=True)
                if base_aud["n_denied_rows"] > 200:
                    st.caption(f"Showing first 200 of {base_aud['n_denied_rows']}.")
                st.caption("Blocked by RBAC/ABAC regardless — the TRAC alert is a deterministic warning on "
                           "the intent (defense-in-depth / audit), it does not change the outcome.")

    # ── LLM accuracy (policy-independent; characterises the model) ────────
    if show_llm and mode == "selection":
        st.markdown("### LLM tool-selection accuracy")
        st.caption("How many of the 3 ground-truth tools the LLM selected, per unique task "
                   "(the selection is policy-independent).")
        dist, total, mean_jac = _selection_accuracy(base_rows, lookup, tasks)
        adf = pd.DataFrame([
            {"ground-truth tools selected": f"{k} of 3" + (" (exact)" if k == 3 else ""),
             "tasks": dist.get(k, 0),
             "%": round(100 * dist.get(k, 0) / total, 1) if total else 0.0}
            for k in (3, 2, 1, 0)])
        st.dataframe(adf, hide_index=True, use_container_width=True)
        st.caption(f"Exact-match: {100*dist.get(3,0)/total:.1f}% · mean Jaccard: {mean_jac:.2f} "
                   f"· {total:,} tasks.")
    elif show_llm:  # validation
        st.markdown("### LLM validation accuracy")
        tab = _validation_accuracy(base_rows, lookup)
        if not tab:
            st.caption("No LLM verdict available in this log (no stored `is_valid` and no E4 run).")
        else:
            st.caption("Did the LLM judge each candidate correctly? Counts are **unique tasks** "
                       "(not task×persona rows — that's why this total is smaller than the "
                       "legitimate/illegitimate row counts above). `correct` should be **valid**; "
                       "`wrong`/`null` should be **invalid**. Verdict from stored `is_valid`, "
                       "else recovered from the E4 LLM-only run.")
            order = ["correct", "wrong", "null"]
            rows_out, tot_n, tot_ok = [], 0, 0
            for tag in [t for t in order if t in tab] + [t for t in tab if t not in order]:
                d = tab[tag]
                should_valid = (tag == "correct")
                ok = d["valid"] if should_valid else d["invalid"]
                acc = ok / d["n"] if d["n"] else 0.0
                tot_n += d["n"]; tot_ok += ok
                rows_out.append({"match_tag": tag, "tasks": d["n"],
                                 "LLM→valid": d["valid"], "LLM→invalid": d["invalid"],
                                 "should be": "valid" if should_valid else "invalid",
                                 "LLM accuracy": f"{acc*100:.1f}%"})
            st.dataframe(pd.DataFrame(rows_out), hide_index=True, use_container_width=True)
            st.caption(f"Overall LLM validation accuracy: {100*tot_ok/tot_n:.1f}% over {tot_n:,} tasks.")

    # ── Transaction explorer ─────────────────────────────────────────────
    # Gated off by default: building the per-row diff over every cached bundle
    # (task×persona — up to ~7k rows) and rendering the grid + picker is what made
    # the page heavy and unscrollable. The headline metrics above stay fast; the
    # user opts in to the heavy explorer only when they need it.
    st.markdown("## Transaction explorer")
    if not st.checkbox("🔎 Load the per-transaction diff table & trace drill-down "
                       "(heavy for large logs)", value=False, key="pel_show_explorer"):
        st.caption("Hidden by default so the headline metrics above stay fast and scrollable. "
                   "Tick to load the per-row diff and trace explorer.")
        return
    cmp_rows = rs.compare(base_rows, mod_rows)
    df = pd.DataFrame(cmp_rows)
    fc1, fc2, fc3 = st.columns([1, 1, 1])
    tags = fc1.multiselect("match_tag", sorted(df["match_tag"].unique()),
                           default=sorted(df["match_tag"].unique()))
    pers = fc2.multiselect("persona", sorted(df["persona"].unique()),
                           default=sorted(df["persona"].unique()))
    only_changed = fc3.checkbox("Only rows whose decision changed", value=False)
    view = df[df["match_tag"].isin(tags) & df["persona"].isin(pers)]
    if only_changed:
        view = view[view["decision_changed"]]
    st.caption(f"{len(view):,} of {len(df):,} transactions  ·  "
               f"{int(df['decision_changed'].sum()):,} changed decision under the modified policy.")
    show_cols = ["persona", "task_idx", "match_tag", "base_decision", "base_layer", "base_rule",
                 "mod_decision", "mod_layer", "mod_rule", "decision_changed"]
    st.dataframe(view[show_cols], hide_index=True, use_container_width=True, height=300)

    # Drill-down
    if len(view):
        st.markdown("### Transaction detail")
        st.caption("**Type a task_id** to trace it (copy one from the tables above). Persona defaults to the "
                   "first match — switch it to vary the RBAC/ABAC view (TRAC's own reasoning is "
                   "persona-independent).")
        all_tids = sorted(int(t) for t in view["task_idx"].unique())
        c1, c2 = st.columns([1, 2])
        tid = int(c1.number_input("Trace task_id", min_value=all_tids[0], max_value=all_tids[-1],
                                  value=all_tids[0], step=1))
        personas_for_task = sorted(view[view["task_idx"] == tid]["persona"].unique())
        if personas_for_task:
            persona = (c2.selectbox("persona (RBAC/ABAC view)", personas_for_task)
                       if len(personas_for_task) > 1 else personas_for_task[0])
            if len(personas_for_task) == 1:
                c2.caption(f"persona: **{persona}** (only one for this task)")
            _render_transaction_trace(
                persona, tid, st.session_state["pel_lookup"], tasks, st.session_state["pel_mode"],
                rs.baseline_policies(), st.session_state["pel_mod_policies"],
                st.session_state.get("pel_domain_source", "inferred"))
        else:
            st.warning(f"task_id **{tid}** isn't in the current filtered view — clear the **match_tag · "
                       "persona · Only changed** filters above, or pick a task_id from the tables.")
