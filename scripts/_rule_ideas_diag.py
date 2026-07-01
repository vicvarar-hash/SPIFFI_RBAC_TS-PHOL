"""Diagnose where the deterministic stack over-denies (legit blocked) and under-catches
(illegit allowed) on a validation log, to drive RBAC/ABAC/TRAC rule ideas."""
import os, sys
from collections import Counter, defaultdict
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.loaders.astra_loader import load_astra_dataset

LOG = sys.argv[1] if len(sys.argv) > 1 else "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"


def layers(x):
    return tuple(L for L, d in (("RBAC", x.rbac_deny), ("ABAC", x.abac_deny), ("TSPHOL", x.tsphol_deny)) if d)


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    rows, summ, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=None)
    h = rs.headline(rows)
    print("LOG:", os.path.basename(LOG), "| rows:", len(rows))
    print("secfail=%.3f legit_allow=%.3f deny=%.3f\n" % (h["secfail"], h["legit_allow"], h["deny_rate"]))

    legit = [x for x in rows if x.is_legitimate]
    illeg = [x for x in rows if not x.is_legitimate]

    # ---- OVER-DENIAL: legitimate bundles the stack denies ----
    legit_den = [x for x in legit if (x.rbac_deny or x.abac_deny or x.tsphol_deny)]
    print("=== OVER-DENIAL: %d / %d legitimate rows DENIED (%.1f%%) ===" % (
        len(legit_den), len(legit), 100*len(legit_den)/len(legit)))
    print("  by layer-combo:", dict(Counter(layers(x) for x in legit_den).most_common()))
    print("  ABAC rule among legit-denied:", dict(Counter(x.abac_reason or x.abac_rule for x in legit_den if x.abac_deny).most_common()))
    print("  TSPHOL rule among legit-denied:", dict(Counter(x.tsphol_rule for x in legit_den if x.tsphol_deny).most_common()))
    print("  RBAC-denied legit by domain:", dict(Counter(x.domain for x in legit_den if x.rbac_deny).most_common(8)))
    print("  contains_write among legit-denied:", dict(Counter(x.contains_write for x in legit_den).most_common()))
    print()

    # ---- UNDER-CATCH: illegitimate bundles the stack allows (secfail) ----
    illeg_allow = [x for x in illeg if not (x.rbac_deny or x.abac_deny or x.tsphol_deny)]
    print("=== UNDER-CATCH: %d / %d illegitimate rows ALLOWED (secfail) ===" % (len(illeg_allow), len(illeg)))
    print("  by match_tag:", dict(Counter(x.match_tag for x in illeg_allow).most_common()))
    print("  contains_write:", dict(Counter(x.contains_write for x in illeg_allow).most_common()))
    print("  hard_missing(capability gap):", dict(Counter(x.hard_missing for x in illeg_allow).most_common()))
    print("  domain_mismatch:", dict(Counter(x.domain_mismatch for x in illeg_allow).most_common()))
    print("  multi_domain:", dict(Counter(x.multi_domain for x in illeg_allow).most_common()))
    print("  top domains:", dict(Counter(x.domain for x in illeg_allow).most_common(8)))
    print()

    # split illegit by *why* illegit: wrong/null bundle vs unauthorized persona (correct bundle)
    print("  illegit-allowed breakdown (correct=unauthorized-persona, wrong/null=bad bundle):")
    for tag in ("correct", "wrong", "null"):
        sub = [x for x in illeg_allow if x.match_tag == tag]
        if not sub: continue
        print("    %-7s n=%d | write=%d hard_missing=%d domain_mismatch=%d" % (
            tag, len(sub), sum(x.contains_write for x in sub),
            sum(x.hard_missing for x in sub), sum(x.domain_mismatch for x in sub)))
    print()

    # ---- how much could each signal catch among the currently-allowed illegit ----
    print("=== LEVERAGE: illegit-allowed rows a candidate rule COULD flag ===")
    print("  have hard_missing(cap gap) but allowed:", sum(x.hard_missing for x in illeg_allow))
    print("  have domain_mismatch but allowed:", sum(x.domain_mismatch for x in illeg_allow))
    print("  are writes but allowed:", sum(x.contains_write for x in illeg_allow))
    print("  multi_domain but allowed:", sum(x.multi_domain for x in illeg_allow))


if __name__ == "__main__":
    main()
