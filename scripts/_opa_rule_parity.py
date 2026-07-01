"""Parity: real `opa eval` of tsphol.rego (TRAC) vs the Python engine, per unique bundle.

Replays a sample to get, per bundle, the Python decision (tsphol_deny) + advisory and the
predicate set; feeds the predicates to real OPA; checks the decisions and advisories agree.
"""
import json, os, subprocess, sys, tempfile
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.loaders.astra_loader import load_astra_dataset

OPA = os.path.join(os.environ.get("TEMP", "."), "opa.exe")
LOG = "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"
KEYS = ("HardCapabilityMissing", "ContainsDelete", "ContainsReadBeforeWrite",
        "ReadIntentMutatingBundle", "BundleToolsIrrelevant")
INPUT = os.path.join(tempfile.gettempdir(), f"_opa_trac_{os.getpid()}.json")


def opa_trac(preds):
    with open(INPUT, "w", encoding="utf-8") as f:
        json.dump({"predicates": preds}, f)
    r = subprocess.run([OPA, "eval", "-d", "policies/trac_rules.yaml",
                        "-d", "policies/rego/tsphol.rego", "-i", INPUT,
                        "-f", "json", "data.paladin.tsphol"], capture_output=True, text=True)
    val = json.loads(r.stdout)["result"][0]["expressions"][0]["value"]
    return val.get("decision", "ALLOW"), set(val.get("advisories", []) or [])


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    rows, _, bundle_cache = rs.replay_experiment(LOG, tasks, experiment="E1", limit=600)
    ADVISORY_RULES = {"write_safety", "action_coherence"}
    py = {}
    for x in rows:
        py.setdefault(x.sig, (x.tsphol_deny, set(x.tsphol_advisory_rules or []) & ADVISORY_RULES))

    n = dec_mm = adv_mm = 0
    examples = []
    for ckey, preds in bundle_cache.items():
        inp = {k: bool(preds.get(k)) for k in KEYS}
        d, adv = opa_trac(inp)
        py_deny, py_adv = py.get(ckey, (None, set()))
        opa_deny = (d == "DENY")
        opa_adv = adv & ADVISORY_RULES
        n += 1
        if opa_deny != py_deny:
            dec_mm += 1
            if len(examples) < 5:
                examples.append(("DEC", ckey[:30], inp, d, py_deny))
        if opa_adv != py_adv:
            adv_mm += 1
            if len(examples) < 5:
                examples.append(("ADV", ckey[:30], inp, sorted(opa_adv), sorted(py_adv)))
    if os.path.exists(INPUT):
        os.remove(INPUT)
    print("unique bundles tested: %d" % n)
    print("decision mismatches (OPA vs Python): %d" % dec_mm)
    print("advisory mismatches: %d" % adv_mm)
    for tag, k, inp, d, pyd in examples:
        print("  ", tag, k, inp, "opa=", d, "py=", pyd)
    print("\nTRAC OPA PARITY:", "PASS" if (dec_mm == 0 and adv_mm == 0) else "FAIL")


if __name__ == "__main__":
    main()
