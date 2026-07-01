"""Downstream stack impact of the verb-lexicon fusion (name-only vs name+description).

Replays the same log twice — fusion OFF (monkeypatched to a no-op) then ON — and reports
SecFail / legit-allow / ABAC write-gate firing / write_safety advisory counts.
"""
import json, os, sys
from collections import Counter
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services import verb_action_classifier as vac
from app.loaders.astra_loader import load_astra_dataset

LOG = "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"
_REAL = vac.classify_action


def run(label):
    rows, _, _ = rs.replay_experiment(LOG, load_astra_dataset("datasets/astra_03_tools.json"),
                                      experiment="E1", limit=None)
    h = rs.headline(rows)
    fire = rs.layer_firing_summary(rows)
    adv = sum(1 for x in rows if x.tsphol_advisory and x.tsphol_advisory_rule == "write_safety")
    abac = fire.get("abac", {})
    write_gates = {k: v for k, v in abac.items() if "write" in k or "trust" in k or "pci" in k or "clearance" in k}
    print("\n== %s ==" % label)
    print("  secfail=%.3f legit_allow=%.3f deny=%.3f | abac_deny_rate=%.3f"
          % (h["secfail"], h["legit_allow"], h["deny_rate"], h["abac_deny_rate"]))
    print("  ABAC write/attr-gate firing: %s" % {k: v for k, v in sorted(write_gates.items())})
    print("  write_safety advisories: %d" % adv)
    return h, sum(write_gates.values()), adv


def main():
    # OFF — emulate name-only classification (verb fusion returns nothing to escalate)
    vac.classify_action = lambda n, d: (False, False, "")
    h0, g0, a0 = run("FUSION OFF (name only)")
    # ON — real verb-lexicon fusion
    vac.classify_action = _REAL
    h1, g1, a1 = run("FUSION ON (name + description)")

    print("\n=== DELTA (ON - OFF) ===")
    print("  secfail      %+.3f" % (h1["secfail"] - h0["secfail"]))
    print("  legit_allow  %+.3f" % (h1["legit_allow"] - h0["legit_allow"]))
    print("  deny_rate    %+.3f" % (h1["deny_rate"] - h0["deny_rate"]))
    print("  ABAC write-gate firings %+d" % (g1 - g0))
    print("  write_safety advisories %+d" % (a1 - a0))


if __name__ == "__main__":
    main()
