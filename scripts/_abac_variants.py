"""Prototype + measure ABAC tuning variants (shipped policies untouched).

Replays baseline vs candidate ABAC variants over the dataset and reports headline
metrics, corrective (catch/rescue), and per-row legit-recovered / illegit-newly-allowed
deltas vs baseline — so we can decide before changing any policy file.
"""
import copy
import json
import os
import sys
from collections import Counter

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services.experiment_config import PERSONAS
from app.loaders.astra_loader import load_astra_dataset

LOG = "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 2000


def _edit(abac, rule_id, mutate):
    a = copy.deepcopy(abac)
    for r in a["rules"]:
        if r.get("id") == rule_id:
            mutate(r)
    return a


def v_pci_writes(abac):
    """PCI isolation applies to WRITES only (non-Finance may READ PCI/Stripe data)."""
    return _edit(abac, "abac_pci_isolation", lambda r: r["match_attributes"].append(
        {"attribute": "contains_write", "op": "==", "source": "action", "value": True}))


def v_clear_l2(abac):
    """High-risk WRITE clearance: allow L2 (deny only L1) instead of requiring L3."""
    def m(r):
        for c in r["match_attributes"]:
            if c["attribute"] == "attributes.clearance_level":
                c["op"], c["value"] = "==", "L1"
    return _edit(abac, "abac_clearance_write_high_risk", m)


def _lookup(log_path):
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    out = {}
    for t in log.get("tasks", []):
        for p in PERSONAS:
            out[(p, t.get("task_idx"))] = t.get("is_valid")
    return out


def _verdict(lookup, x):
    return lookup.get((x.persona, x.task_idx))


def _metrics(rows, lookup):
    h = rs.headline(rows)
    legit = [x for x in rows if x.is_legitimate]
    illeg = [x for x in rows if not x.is_legitimate]
    catch = catch_den = resc = resc_den = 0
    for x in illeg:
        v = _verdict(lookup, x)
        if v is True:
            catch_den += 1
            if x.rbac_deny or x.abac_deny or x.tsphol_deny:
                catch += 1
    for x in legit:
        v = _verdict(lookup, x)
        if v is False:
            resc_den += 1
            if not (x.rbac_deny or x.abac_deny or x.tsphol_deny):
                resc += 1
    return {"secfail": h["secfail"], "legit_allow": h["legit_allow"], "deny": h["deny_rate"],
            "catch": catch, "catch_den": catch_den, "resc": resc, "resc_den": resc_den}


def _denied(x):
    return x.rbac_deny or x.abac_deny or x.tsphol_deny


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    lookup = _lookup(LOG)
    rbac, abac, tsphol = rs.baseline_policies()

    variants = {
        "baseline": (rbac, abac, tsphol),
        "V1 PCI=writes": (rbac, v_pci_writes(abac), tsphol),
        "V2 clearance>=L2": (rbac, v_clear_l2(abac), tsphol),
        "V1+V2": (rbac, v_clear_l2(v_pci_writes(abac)), tsphol),
    }

    print(f"LOG={os.path.basename(LOG)}  limit={LIMIT}\n")
    base_rows = None
    base_key = {}
    for name, pol in variants.items():
        rows, _, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=LIMIT, policies=pol)
        m = _metrics(rows, lookup)
        key = {(x.persona, x.task_idx): (x.is_legitimate, _denied(x)) for x in rows}
        if name == "baseline":
            base_rows, base_key = rows, key
            recov = newleak = 0
        else:
            recov = sum(1 for k, (leg, den) in key.items()
                        if leg and not den and base_key.get(k, (0, 1))[1])      # legit: was denied, now allowed
            newleak = sum(1 for k, (leg, den) in key.items()
                          if (not leg) and not den and base_key.get(k, (0, 0))[1])  # illeg: was denied, now allowed
        print("%-18s secfail=%.3f legit_allow=%.3f deny=%.3f | catch=%d/%d resc=%d/%d"
              % (name, m["secfail"], m["legit_allow"], m["deny"],
                 m["catch"], m["catch_den"], m["resc"], m["resc_den"]),
              "" if name == "baseline" else "| legit_recovered=%d illeg_newly_allowed=%d" % (recov, newleak))


if __name__ == "__main__":
    main()
