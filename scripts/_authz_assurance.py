"""Authorization x Assurance model for TRAC.

Authorization plane = RBAC OR ABAC (the access gate). Assurance plane = TRAC,
run on EVERY decision. Builds the 2x2, characterises the 'authorized-but-flagged'
alert cell, splits write_safety into bulk vs scoped destructive, and compares three
composition policies:
  (1) authz only            (TRAC fully advisory)
  (2) authz + TRAC all   (current full stack)
  (3) hybrid: capability_coverage ENFORCES, write_safety ADVISES
"""
import json, os, sys
from collections import Counter
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services.experiment_config import PERSONAS
from app.loaders.astra_loader import load_astra_dataset

LOG = "datasets/llm_inference_logs/20260612191843_gpt-5-4_validation.json"
BULK = ("delete-many", "deletemany", "drop", "rename-collection", "truncate",
        "delete-all", "purge", "remove-many", "update-many")


def is_bulk(tools):
    return any(any(b in str(t).lower() for b in BULK) for t in tools)


def secfail_legit(rows, deny_fn):
    illeg = [x for x in rows if not x.is_legitimate]
    legit = [x for x in rows if x.is_legitimate]
    sf = sum(1 for x in illeg if not deny_fn(x)) / len(illeg) if illeg else 0
    la = sum(1 for x in legit if not deny_fn(x)) / len(legit) if legit else 0
    return sf, la


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    with open(LOG, encoding="utf-8") as f:
        verdict = {(p, t["task_idx"]): t.get("is_valid")
                   for t in json.load(f)["tasks"] for p in PERSONAS}
    rows, _, _ = rs.replay_experiment(LOG, tasks, experiment="E1", limit=None)
    n = len(rows)
    for x in rows:
        x._authz = x.rbac_deny or x.abac_deny
        x._cc = x.tsphol_deny and x.tsphol_rule == "capability_coverage"
        x._ws = x.tsphol_deny and x.tsphol_rule == "write_safety"
        x._bulk = is_bulk(getattr(tasks[x.task_idx], "candidate_tools", []) or [])

    # ---- 2x2 authorization x assurance ----
    print("LOG=%s rows=%d\n" % (os.path.basename(LOG), n))
    print("=== AUTHORIZATION x ASSURANCE 2x2 ===")
    cells = {}
    for az in (False, True):       # authz deny?
        for fl in (False, True):   # assurance flag?
            sub = [x for x in rows if x._authz == az and x.tsphol_deny == fl]
            cells[(az, fl)] = sub
    lab = {(False, False): "authz ALLOW · assurance CLEAN",
           (False, True): "authz ALLOW · assurance CONCERN  <-- the alerts",
           (True, False): "authz DENY  · assurance clean",
           (True, True): "authz DENY  · assurance concern (defense-in-depth)"}
    for k in [(False, False), (False, True), (True, False), (True, True)]:
        sub = cells[k]
        leg = sum(1 for x in sub if x.is_legitimate)
        print("  %-46s %5d  (legit=%d illeg=%d)" % (lab[k], len(sub), leg, len(sub) - leg))

    # ---- the alert cell (authorized + concern) ----
    alerts = cells[(False, True)]
    print("\n=== ALERT CELL: authorized-but-flagged (%d) ===" % len(alerts))
    for rule in ("capability_coverage", "write_safety"):
        sub = [x for x in alerts if x.tsphol_rule == rule]
        leg = sum(1 for x in sub if x.is_legitimate)
        llm_ok = sum(1 for x in sub if verdict.get((x.persona, x.task_idx)) is True)
        print("  %-20s n=%-4d legit=%-3d illeg=%-3d  (LLM had ACCEPTED %d)" % (rule, len(sub), leg, len(sub) - leg, llm_ok))
    ws = [x for x in alerts if x._ws]
    print("  write_safety split: bulk=%d (legit=%d) · scoped=%d (legit=%d)"
          % (sum(x._bulk for x in ws), sum(x._bulk and x.is_legitimate for x in ws),
             sum(not x._bulk for x in ws), sum((not x._bulk) and x.is_legitimate for x in ws)))

    # ---- capability_coverage enforce-safety (legit cost across ALL rows) ----
    cc_all = [x for x in rows if x._cc]
    print("\ncapability_coverage fires on %d rows total; legit among them = %d (enforce cost)"
          % (len(cc_all), sum(1 for x in cc_all if x.is_legitimate)))

    # ---- composition policies ----
    print("\n=== COMPOSITION POLICIES (validation, model-invariant deny) ===")
    comps = {
        "1 authz only (TRAC advisory)": lambda x: x._authz,
        "2 authz + TRAC all (current)": lambda x: x._authz or x.tsphol_deny,
        "3 hybrid: cap_cov ENFORCE, write_safety ADVISE": lambda x: x._authz or x._cc,
    }
    print("  %-48s %8s %8s %8s" % ("policy", "secfail", "legitOK", "denyrate"))
    for name, fn in comps.items():
        sf, la = secfail_legit(rows, fn)
        dr = sum(1 for x in rows if fn(x)) / n
        print("  %-48s %7.3f %8.3f %8.3f" % (name, sf, la, dr))

    print("\nNote: write_safety as ADVISE still raises %d alerts (incl. bulk-destructive like task 900) "
          "for human/LLM review or escalation — it just no longer hard-blocks legit scoped deletes."
          % sum(1 for x in rows if x._ws))


if __name__ == "__main__":
    main()
