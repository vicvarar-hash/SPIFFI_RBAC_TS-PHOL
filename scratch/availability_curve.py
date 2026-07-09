"""Security/availability trade-off curve (deterministic, no API).

Motivation: the paper folds availability into F1 and never reports a separate
false-block rate; the headline floor (SecFail 0.107) is reached at a ~56% false-block rate. We report
(i) the false-block rate as a first-class number, per model, and (ii) the SecFail<->false-block
trade-off curve as the operating point moves.

We sweep the enforcing ``tool_relevance`` BM25 threshold (``PALADIN_TOOLREL_THRESHOLD``, default 1.0)
— the primary security/availability dial — replaying the deterministic floor at each setting. The
floor is model-invariant in validation mode (the candidate bundle is fixed; the model only judges),
so one validation log traces the frontier. We also report the per-model false-block at the shipped
operating point from the frozen canonical rows.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services import tool_relevance as trel
from app.services.experiment_config import abac_production, tsphol_production, rbac_production

LL = os.path.join("datasets", "llm_inference_logs")
ROWS_DIR = os.path.join("scratch", "canonical_rows")
VAL_LOG = "20260613005419_gpt-4o_validation.json"
THRESHOLDS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]

VAL_MODELS = ["gpt-4o", "gpt-5.4", "gemini-2.5-pro", "gpt-3.5-turbo-16k"]


def floor_metrics(rows):
    """SecFail, false-block, F1 for the deterministic floor (rbac OR abac OR tsphol)."""
    tp = fp = tn = fn = 0
    for x in rows:
        legit = x.is_legitimate
        allow = not (x.rbac_deny or x.abac_deny or x.tsphol_deny)
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    fb = fp / (fp + tn) if (fp + tn) else 0.0
    la = tn / (tn + fp) if (tn + fp) else 0.0
    return dict(f1=f1, secfail=sf, false_block=fb, legit_allow=la, tp=tp, fp=fp, tn=tn, fn=fn)


def floor_metrics_json(rows):
    tp = fp = tn = fn = 0
    for x in rows:
        legit = x["is_legitimate"]
        allow = not (x["rbac_deny"] or x["abac_deny"] or x["tsphol_deny"])
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    fb = fp / (fp + tn) if (fp + tn) else 0.0
    return dict(f1=f1, secfail=sf, false_block=fb)


def main():
    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))

    # (i) Per-model false-block at the shipped operating point (threshold=1.0, rescue=4.0),
    #     from the frozen canonical rows.
    print("=== Per-model deterministic floor @ shipped operating point (from canonical rows) ===")
    per_model = {}
    for m in VAL_MODELS:
        p = os.path.join(ROWS_DIR, f"val_{m}_r4.json")
        if not os.path.exists(p):
            continue
        rws = json.load(open(p, encoding="utf-8"))
        mm = floor_metrics_json(rws)
        per_model[m] = {k: round(v, 4) for k, v in mm.items()}
        print(f"  {m:18s} F1={mm['f1']:.3f}  SecFail={mm['secfail']:.4f}  "
              f"false-block={mm['false_block']:.3f}  (legit-allow={1-mm['false_block']:.3f})")

    # (ii) Trade-off curve: sweep the enforcing tool_relevance threshold.
    print("\n=== SecFail <-> false-block frontier (sweep tool_relevance threshold; gpt-4o val) ===")
    print(f"{'threshold':>9} {'F1':>6} {'SecFail':>8} {'false-block':>12} {'legit-allow':>12}")
    curve = []
    for thr in THRESHOLDS:
        trel.THRESHOLD = thr
        trel.RESCUE_RELEVANCE = 4.0
        rows, _, _ = rs.replay_experiment(os.path.join(LL, VAL_LOG), tasks, experiment="E1",
                                          limit=None,
                                          policies=(rbac_production(), abac_production(), tsphol_production()))
        mm = floor_metrics(rows)
        curve.append({"threshold": thr, "f1": round(mm["f1"], 4), "secfail": round(mm["secfail"], 4),
                      "false_block": round(mm["false_block"], 4), "legit_allow": round(mm["legit_allow"], 4)})
        print(f"{thr:>9.1f} {mm['f1']:>6.3f} {mm['secfail']:>8.4f} "
              f"{mm['false_block']:>12.3f} {mm['legit_allow']:>12.3f}")

    json.dump({"per_model_floor": per_model, "tradeoff_curve": curve},
              open(os.path.join("scratch", "availability_curve.json"), "w"), indent=2)
    print("\nSaved -> scratch/availability_curve.json")


if __name__ == "__main__":
    main()
