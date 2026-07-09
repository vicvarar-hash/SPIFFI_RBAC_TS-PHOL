"""Enforcing marginal of TRAC's non-lexical structural rules (deterministic, no API).

A common critique is that TRAC's enforcing surface reduces to two BM25 predicates
(capability_coverage, tool_relevance). But TRAC also carries two *structural, non-lexical*
task-relational predicates that are currently ADVISORY:
  * write_safety     -- a destructive op without a preceding verifying read (read/write ORDER).
  * action_coherence -- a read-intent task that selected mutating tools (action SEMANTICS).
Neither is BM25/lexical. This measures what they buy if made ENFORCING, from the frozen canonical
rows (val gpt-4o; the deterministic floor is model-invariant). Their per-row firings are recorded in
``tsphol_advisory_rules``.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROWS = os.path.join("scratch", "canonical_rows", "val_gpt-4o_r4.json")


def e1_deny(x):
    return bool(x["rbac_deny"] or x["abac_deny"] or x["tsphol_deny"])


def fires(x, rule):
    return rule in (x.get("tsphol_advisory_rules") or [])


def metrics(rows, deny_fn):
    tp = fp = tn = fn = 0
    for x in rows:
        legit = x["is_legitimate"]
        allow = not deny_fn(x)
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    fb = fp / (fp + tn) if (fp + tn) else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    return dict(f1=round(f1, 4), secfail=round(sf, 4), false_block=round(fb, 4))


def added_denial_quality(rows, rule):
    """Among E1-admitted rows, precision of the structural rule's *new* denials."""
    admitted = [x for x in rows if not e1_deny(x)]
    fired = [x for x in admitted if fires(x, rule)]
    catch = sum(1 for x in fired if not x["is_legitimate"])   # true violations newly caught
    block = sum(1 for x in fired if x["is_legitimate"])       # legitimate newly blocked
    illeg = sum(1 for x in admitted if not x["is_legitimate"])
    base = illeg / len(admitted) if admitted else 0.0
    prec = catch / len(fired) if fired else 0.0
    return dict(fired=len(fired), catch=catch, block=block,
                precision=round(prec, 3), approved_base_rate=round(base, 3))


def main():
    rows = json.load(open(ROWS, encoding="utf-8"))
    AC = lambda x: fires(x, "action_coherence")
    WS = lambda x: fires(x, "write_safety")

    configs = {
        "E1 (baseline: 2 enforcing BM25 rules)": e1_deny,
        "E1 + action_coherence (structural)":    lambda x: e1_deny(x) or AC(x),
        "E1 + write_safety (structural)":        lambda x: e1_deny(x) or WS(x),
        "E1 + both structural enforcing":        lambda x: e1_deny(x) or AC(x) or WS(x),
    }
    out = {"configs": {}, "added_denial_quality": {}}
    base = metrics(rows, e1_deny)
    print(f"{'config':42} {'F1':>6} {'SecFail':>8} {'false-block':>12}")
    for name, fn in configs.items():
        m = metrics(rows, fn)
        out["configs"][name] = m
        d_sf = 100 * (m["secfail"] - base["secfail"])
        d_fb = 100 * (m["false_block"] - base["false_block"])
        tail = "" if name.startswith("E1 (") else f"   (dSecFail {d_sf:+.2f}pp, dFB {d_fb:+.2f}pp)"
        print(f"{name:42} {m['f1']:>6.3f} {m['secfail']:>8.4f} {m['false_block']:>12.4f}{tail}")

    print("\nQuality of each structural rule's NEW denials on the E1-admitted set "
          "(precision vs a random denier = approved base rate):")
    for rule in ("action_coherence", "write_safety"):
        q = added_denial_quality(rows, rule)
        out["added_denial_quality"][rule] = q
        print(f"  {rule:16}: fires {q['fired']:>3}  catch {q['catch']:>3}  block {q['block']:>3}  "
              f"precision {q['precision']:.3f}  (approved base rate {q['approved_base_rate']:.3f})")

    json.dump(out, open(os.path.join("scratch", "structural_rules.json"), "w"), indent=2)
    print("\nSaved -> scratch/structural_rules.json")


if __name__ == "__main__":
    main()
