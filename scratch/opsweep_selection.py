"""Post-fix recompute for (a) the operating-sweep deterministic frontier points (model-invariant:
TRAC-only -> +ABAC -> +RBAC, on domain-level admission = 1-false-block) and (b) the selection-mode
E1 floor cited at the experimental-design paragraph. Uses the fixed relevance module.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services import tool_relevance as trel

trel.RESCUE_RELEVANCE = 4.0
trel.THRESHOLD = 1.0
LL = os.path.join("datasets", "llm_inference_logs")
tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))


def point(rows, deny):
    legit = [x for x in rows if x.is_legitimate]
    illeg = [x for x in rows if not x.is_legitimate]
    la = sum(1 for x in legit if not deny(x)) / len(legit) if legit else 0.0  # admission
    sf = sum(1 for x in illeg if not deny(x)) / len(illeg) if illeg else 0.0  # SecFail
    return round(100 * la, 1), round(sf, 3)


def full_metrics(rows, deny):
    tp = fp = tn = fn = 0
    for x in rows:
        d = deny(x)
        if not x.is_legitimate and d:   tp += 1
        elif x.is_legitimate and d:     fp += 1
        elif x.is_legitimate and not d: tn += 1
        else:                           fn += 1
    return dict(f1=round(2 * tp / (2 * tp + fp + fn), 3) if (2 * tp + fp + fn) else 0.0,
                secfail=round(fn / (tp + fn), 3) if (tp + fn) else 0.0,
                false_block=round(100 * fp / (fp + tn), 1) if (fp + tn) else 0.0)


# (a) deterministic frontier (gpt-4o val, model-invariant)
rows, _, _ = rs.replay_experiment(os.path.join(LL, "20260613005419_gpt-4o_validation.json"),
                                  tasks, experiment="E1", limit=None, policies=rs.baseline_policies())
trac = point(rows, lambda x: x.tsphol_deny)
tabac = point(rows, lambda x: x.tsphol_deny or x.abac_deny)
full_floor = point(rows, lambda x: x.tsphol_deny or x.abac_deny or x.rbac_deny)
print("=== operating-sweep deterministic frontier (domain-level admission %, SecFail) ===")
print(f"  TRAC-only : {trac}")
print(f"  +ABAC     : {tabac}")
print(f"  +RBAC (E1): {full_floor}")

# (b) selection-mode E1 floor (gpt-5.4 selection)
rows_sel, _, _ = rs.replay_experiment(os.path.join(LL, "20260613105137_gpt-5-4_selection.json"),
                                      tasks, experiment="E1", limit=None, policies=rs.baseline_policies())
m = full_metrics(rows_sel, lambda x: x.tsphol_deny or x.abac_deny or x.rbac_deny)
print("\n=== selection-mode E1 floor (gpt-5.4) FIXED ===")
print(f"  F1={m['f1']}  SecFail={m['secfail']}  domain-false-block={m['false_block']}%  (n={len(rows_sel)})")

json.dump({"frontier": {"trac": trac, "trac_abac": tabac, "full_floor": full_floor},
           "selection_floor": m},
          open(os.path.join("scratch", "opsweep_selection_fixed.json"), "w"), indent=2)
print("\nsaved -> scratch/opsweep_selection_fixed.json")
