"""Measure the impact of normalizing LEGITIMATE_PAIRINGS keys (ground-truth fix).

The legitimacy label compares normalize_mcp_name(candidate) against LEGITIMATE_PAIRINGS,
whose keys are hyphenated (hummingbot-mcp/wikipedia-mcp/paper-search) — so those domains
never match. This re-labels is_legitimate with normalized keys and reports the metric
shift. No stack DECISION changes — only the legit/illeg ground truth.
"""
import json
import os
import sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services.experiment_config import PERSONAS, LEGITIMATE_PAIRINGS
from app.services.normalization import normalize_mcp_name
from app.loaders.astra_loader import load_astra_dataset

LOG = "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 2000


def _lookup():
    with open(LOG, encoding="utf-8") as f:
        log = json.load(f)
    return {(p, t.get("task_idx")): t.get("is_valid")
            for t in log.get("tasks", []) for p in PERSONAS}


def _metrics(rows, lookup):
    h = rs.headline(rows)
    catch = catch_den = resc = resc_den = 0
    for x in rows:
        v = lookup.get((x.persona, x.task_idx))
        den = x.rbac_deny or x.abac_deny or x.tsphol_deny
        if not x.is_legitimate and v is True:
            catch_den += 1; catch += den
        if x.is_legitimate and v is False:
            resc_den += 1; resc += (not den)
    n_leg = sum(1 for x in rows if x.is_legitimate)
    return dict(secfail=h["secfail"], legit_allow=h["legit_allow"], deny=h["deny_rate"],
               n_legit=n_leg, catch=catch, catch_den=catch_den, resc=resc, resc_den=resc_den)


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    lookup = _lookup()

    # one replay produces the decisions; is_legitimate is recomputed in _normalize_rows
    # from rs.LEGITIMATE_PAIRINGS, so patch it and replay again for the fixed labels.
    print(f"LOG={os.path.basename(LOG)} limit={LIMIT}\n")

    rows_base, _, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=LIMIT)
    m0 = _metrics(rows_base, lookup)

    orig = rs.LEGITIMATE_PAIRINGS
    rs.LEGITIMATE_PAIRINGS = {p: {normalize_mcp_name(d) for d in doms}
                             for p, doms in orig.items()}
    try:
        rows_fix, _, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=LIMIT)
    finally:
        rs.LEGITIMATE_PAIRINGS = orig
    m1 = _metrics(rows_fix, lookup)

    def line(tag, m):
        print("%-22s secfail=%.3f legit_allow=%.3f deny=%.3f | legit_rows=%d catch=%d/%d resc=%d/%d"
              % (tag, m["secfail"], m["legit_allow"], m["deny"], m["n_legit"],
                 m["catch"], m["catch_den"], m["resc"], m["resc_den"]))
    line("current (hyphen keys)", m0)
    line("FIXED (normalized)", m1)
    print("\nΔ  secfail %+.3f | legit_allow %+.3f | legit_rows %+d | catch_den %+d"
          % (m1["secfail"]-m0["secfail"], m1["legit_allow"]-m0["legit_allow"],
             m1["n_legit"]-m0["n_legit"], m1["catch_den"]-m0["catch_den"]))


if __name__ == "__main__":
    main()
