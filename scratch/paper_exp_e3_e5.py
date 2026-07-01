"""Paper experiments E3 (corroborated-coverage generalization) + E5 (cross-model selection security).

Both RE-RUN the deterministic engine over the cached LLM-inference logs (no LLM calls), using the
paper's operating-point accounting (sweep_op_points.metrics): a row is ALLOW unless denied by the
active pipeline; SecFail = illegitimate-allowed / illegitimate; legit-allow = legit-allowed / legit.

E3: 4 validation models x {rescue 0, 4.0} at OP1 (full validation pipeline: RBAC ∧ ABAC ∧ LLM-valid
    ∧ TRAC). Shows the corroborated-coverage Pareto win generalizes across models.
E5: 4 selection models, full deterministic stack (RBAC ∧ ABAC ∧ TRAC; no LLM gate in selection).
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services import tool_relevance as trel

LL = os.path.join("datasets", "llm_inference_logs")
VAL = [
    ("gpt-4o",            "20260613005419_gpt-4o_validation.json"),
    ("gpt-5.4",           "20260612191843_gpt-5-4_validation.json"),
    ("gemini-2.5-pro",    "20260612160439_gemini-2-5-pro_validation.json"),
    ("gpt-3.5-turbo-16k", "20260613141204_gpt-35-turbo-16k_validation.json"),
]
SEL = [
    ("gpt-4o",          "20260529112541_gpt-4o_selection.json"),
    ("gpt-3.5-turbo",   "20260505161002_gpt-3-5-turbo_selection.json"),
    ("claude-opus-4-8", "20260612103402_claude-opus-4-8_selection.json"),
    ("gpt-5.4",         "20260613105137_gpt-5-4_selection.json"),
]


def op_metrics(rows, deny_fn):
    tp = fp = tn = fn = 0
    legit_all = legit_n = 0
    for x in rows:
        legit = x.is_legitimate
        allow = not deny_fn(x)
        if legit:
            legit_n += 1
            if allow:
                legit_all += 1
        if not legit and not allow:
            tp += 1
        elif legit and not allow:
            fp += 1
        elif legit and allow:
            tn += 1
        else:
            fn += 1
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    la = 100.0 * legit_all / legit_n if legit_n else 0.0
    return dict(n=len(rows), f1=round(f1, 3), secfail=round(sf, 4), legit_allow=round(la, 1))


def val_deny(x):
    return x.rbac_deny or x.abac_deny or (x.llm_valid is False) or x.tsphol_deny


def det_deny(x):
    # deterministic stack only (no LLM gate) — TRAC's direct effect is visible here
    return x.rbac_deny or x.abac_deny or x.tsphol_deny


def trac_unique(rows):
    """TRAC-unique over-deny (legit) and catches (illeg): RBAC&ABAC allow, TRAC decides."""
    od = sum(1 for x in rows if x.is_legitimate and x.tsphol_deny and not (x.rbac_deny or x.abac_deny))
    ca = sum(1 for x in rows if (not x.is_legitimate) and x.tsphol_deny and not (x.rbac_deny or x.abac_deny))
    return od, ca


def sel_deny(x):
    return x.rbac_deny or x.abac_deny or x.tsphol_deny


def main():
    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    out = {"E3_validation_corroborated_coverage": [], "E5_selection_security": []}

    print("=== E3: corroborated-coverage generalization ===", flush=True)
    print("(det = deterministic stack RBAC.ABAC.TRAC; full = + LLM gate; "
          "TRAC-unique over-deny/catch = RBAC&ABAC allow, TRAC decides)", flush=True)
    print(f'{"model":18s} {"rescue":>6} | {"det_SecF":>8} {"det_adm":>8} | {"full_SecF":>9} {"full_adm":>8} | {"TRACoverdeny":>12} {"TRACcatch":>9}', flush=True)
    for model, fn in VAL:
        path = os.path.join(LL, fn)
        for rescue in (0.0, 4.0):
            trel.RESCUE_RELEVANCE = rescue
            rows, _, _ = rs.replay_experiment(path, tasks, experiment="E1", limit=None,
                                              policies=rs.baseline_policies())
            md = op_metrics(rows, det_deny)
            mf = op_metrics(rows, val_deny)
            od, ca = trac_unique(rows)
            rec = dict(model=model, rescue=rescue,
                       det_secfail=md["secfail"], det_admission=md["legit_allow"], det_f1=md["f1"],
                       full_secfail=mf["secfail"], full_admission=mf["legit_allow"], full_f1=mf["f1"],
                       trac_overdeny=od, trac_catch=ca, n=md["n"])
            out["E3_validation_corroborated_coverage"].append(rec)
            print(f'{model:18s} {rescue:>6} | {md["secfail"]:>8.4f} {md["legit_allow"]:>7.1f}% | '
                  f'{mf["secfail"]:>9.4f} {mf["legit_allow"]:>7.1f}% | {od:>12} {ca:>9}', flush=True)
        json.dump(out, open(os.path.join("scratch", "paper_exp_e3_e5.json"), "w"), indent=2)

    print("\n=== E5: cross-model selection security (full deterministic stack, rescue=4.0) ===", flush=True)
    trel.RESCUE_RELEVANCE = 4.0
    print(f'{"model":18s} {"F1":>6} {"SecFail":>8} {"legit-allow":>12}', flush=True)
    for model, fn in SEL:
        path = os.path.join(LL, fn)
        rows, _, _ = rs.replay_experiment(path, tasks, experiment="E1", limit=None,
                                          policies=rs.baseline_policies())
        m = op_metrics(rows, sel_deny)
        m.update(model=model)
        out["E5_selection_security"].append(m)
        print(f'{model:18s} {m["f1"]:>6.3f} {m["secfail"]:>8.4f} {m["legit_allow"]:>11.1f}%', flush=True)
        json.dump(out, open(os.path.join("scratch", "paper_exp_e3_e5.json"), "w"), indent=2)

    print("\nSaved -> scratch/paper_exp_e3_e5.json", flush=True)


if __name__ == "__main__":
    main()
