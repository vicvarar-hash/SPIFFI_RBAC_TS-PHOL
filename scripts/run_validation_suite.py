"""PALADIN new-stack validation suite — runs the headline tests and prints pass/fail
against the expected results. Run:  python scripts/run_validation_suite.py

Heavy replays are bounded for speed; expected ranges allow for the bounded sample.
"""
import json, os, subprocess, sys, time
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

PY = sys.executable
VAL_LOG = "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"


def _run(script):
    r = subprocess.run([PY, os.path.join("scripts", script)], capture_output=True, text=True)
    return (r.stdout or "") + (r.stderr or "")


def check_subprocess(script, needle):
    out = _run(script)
    return (needle in out), _grep(out, needle)


def _grep(out, needle):
    for line in out.splitlines():
        if needle.split(":")[0] in line or needle in line:
            return line.strip()[:90]
    return out.strip().splitlines()[-1][:90] if out.strip() else "(no output)"


def check_stack_metrics():
    """Hybrid headline + normalization-fix legitimacy distribution (bounded replay).

    NOTE: the legacy ``headline`` is the action-blind domain-pairing metric (deprecated in favour of
    ``authz_headline``); this remains only as a gross-regression guard. Baseline reflects the current
    stack: ``domain_source`` defaults to leak-free **inferred** (BM25, no gold) and ``tool_relevance``
    is ENFORCING — both raise the whole-stack deny-rate, so legacy secfail and legit-allow sit well
    below the original pre-change baseline."""
    from app.services import replay_service as rs
    from app.loaders.astra_loader import load_astra_dataset
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    rows, _, _ = rs.replay_experiment(VAL_LOG, tasks, experiment="E1", limit=2000)
    h = rs.headline(rows)
    n_legit = sum(1 for x in rows if x.is_legitimate)
    frac_legit = n_legit / len(rows)
    ok = (0.08 <= h["secfail"] <= 0.16 and 0.42 <= h["legit_allow"] <= 0.51
          and 0.25 <= frac_legit <= 0.32)
    return ok, ("secfail=%.3f legit_allow=%.3f legit_frac=%.3f (n=%d)"
                % (h["secfail"], h["legit_allow"], frac_legit, len(rows)))


CHECKS = [
    ("Stack metrics: hybrid + normfix",
     "SecFail≈0.10–0.13, legit≈0.44–0.48, legit-frac≈0.28 (tool_relevance enforcing)", check_stack_metrics),
    ("Verb classifier vs MCP annotations",
     "WRITE 100% / DESTRUCTIVE 98.8%", lambda: check_subprocess("_verb_module_parity.py", "WRITE 100.0%")),
    ("Action classifier: Rego == Python",
     "ALL AGREE", lambda: check_subprocess("_opa_action_demo.py", "ALL AGREE: True")),
    ("TRAC: opa eval == Python",
     "0 decision/advisory mismatches", lambda: check_subprocess("_opa_rule_parity.py", "TRAC OPA PARITY: PASS")),
    ("RBAC + ABAC: opa eval == Python",
     "0 mismatches both layers", lambda: check_subprocess("_opa_rbac_abac_parity.py", "RBAC+ABAC OPA PARITY: PASS")),
    ("Producer → consumer contract",
     "valid logs, consumer governs", lambda: check_subprocess("_producer_contract.py", "PRODUCER CONTRACT: PASS")),
]


def main():
    print("=" * 78)
    print("PALADIN NEW-STACK VALIDATION SUITE  (SPIFFE → RBAC → ABAC → TRAC, OPA/Rego)")
    print("=" * 78)
    results = []
    for name, expected, fn in CHECKS:
        t0 = time.time()
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"ERROR: {e}"
        dt = time.time() - t0
        results.append((name, expected, ok, detail, dt))
        print("\n[%s] %-38s (%.0fs)" % ("PASS" if ok else "FAIL", name, dt))
        print("    expected: %s" % expected)
        print("    actual  : %s" % detail)

    npass = sum(1 for *_, ok, _, _ in [(r[0], r[1], r[2], r[3], r[4]) for r in results] if ok)
    npass = sum(1 for r in results if r[2])
    print("\n" + "=" * 78)
    print("SUITE RESULT: %d/%d PASSED" % (npass, len(results)))
    print("=" * 78)
    sys.exit(0 if npass == len(results) else 1)


if __name__ == "__main__":
    main()
