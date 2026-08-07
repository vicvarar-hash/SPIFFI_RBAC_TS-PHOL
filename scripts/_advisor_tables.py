"""Advisor-requested result views, computed from the CANONICAL leak-free row dumps
(scratch/canonical_rows/*.json) using the exact metric/deny definitions of
scratch/canonical_tables.py. Reproduces the paper anchors, then derives:

  (A) per-persona deterministic floor (validation E1)
  (B) LLM-alone precision & recall (validation E4, per model)
  (C) whole-flow FULL, both modes (validation FULL per model; selection det-stack)
  (A') per-persona FULL (validation), for optional per-persona whole-flow view

All numbers are offline from committed row dumps; no engine re-run, no LLM calls.
"""
import json, os

D = os.path.join("scratch", "canonical_rows")


def load(name):
    return json.load(open(os.path.join(D, name), encoding="utf-8"))


# --- canonical deny functions (verbatim from scratch/canonical_tables.py) ---
d_e1   = lambda x: x["rbac_deny"] or x["abac_deny"] or x["tsphol_deny"]
d_e4   = lambda x: x["llm_valid"] is False
d_full = lambda x: x["rbac_deny"] or x["abac_deny"] or (x["llm_valid"] is False) or x["tsphol_deny"]


def confusion(rows, deny):
    tp = fp = tn = fn = 0
    for x in rows:
        legit = x["is_legitimate"]
        allow = not deny(x)
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    return tp, fp, tn, fn


def metr(rows, deny):
    tp, fp, tn, fn = confusion(rows, deny)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec  = tp / (tp + fn) if (tp + fn) else 0.0
    f1   = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    sf   = fn / (tp + fn) if (tp + fn) else 0.0
    adm  = tn / (tn + fp) if (tn + fp) else 0.0
    return dict(n=len(rows), n_illeg=tp + fn, P=prec, R=rec, F1=f1, SecFail=sf, admit=100 * adm)


def row(label, m):
    return (f'  {label:<22} n={m["n"]:>5} illeg={m["n_illeg"]:>5} '
            f'P={m["P"]:.3f} R={m["R"]:.3f} F1={m["F1"]:.3f} SecFail={m["SecFail"]:.4f} admit={m["admit"]:.1f}%')


PERS = {  # canonical persona id -> paper display name (Table tab:personas)
    "devops_agent": "DevOps", "incident_agent": "Incident", "finance_agent": "Finance",
    "research_agent": "Research", "automation_gateway": "Gateway", "security_engine": "Security",
}
PORDER = ["devops_agent", "incident_agent", "finance_agent", "research_agent",
          "automation_gateway", "security_engine"]

print("=" * 96)
print("(A) PER-PERSONA DETERMINISTIC FLOOR  (validation E1, val_gpt-4o_r4; aggregate must be 0.848/0.1029)")
print("=" * 96)
val = load("val_gpt-4o_r4.json")
byp = {p: [r for r in val if r["persona"] == p] for p in PORDER}
for p in PORDER:
    print(row(PERS[p], metr(byp[p], d_e1)))
print(row("ALL (aggregate check)", metr(val, d_e1)))

print()
print("=" * 96)
print("(A') PER-PERSONA FULL (validation E1+LLM gate, val_gpt-4o_r4)")
print("=" * 96)
for p in PORDER:
    print(row(PERS[p], metr(byp[p], d_full)))
print(row("ALL", metr(val, d_full)))

print()
print("=" * 96)
print("(B) LLM ALONE (E4) PRECISION & RECALL  (validation, per model)")
print("=" * 96)
for m in ["gpt-3.5-turbo-16k", "gpt-4o", "gpt-5.4", "gemini-2.5-pro"]:
    print(row(m, metr(load(f"val_{m}_r4.json"), d_e4)))

print()
print("=" * 96)
print("(C) WHOLE FLOW, BOTH MODES")
print("=" * 96)
print("Validation -- deterministic floor (E1) then FULL (floor+gate), per model:")
print(row("FLOOR E1 (any model)", metr(load("val_gpt-4o_r4.json"), d_e1)))
for m in ["gpt-3.5-turbo-16k", "gpt-4o", "gpt-5.4", "gemini-2.5-pro"]:
    print(row(f"FULL {m}", metr(load(f"val_{m}_r4.json"), d_full)))
print("Selection -- det stack on LLM-generated bundles (no LLM gate; FULL==E1):")
for f in ["sel_gpt-3.5-turbo_none.json", "sel_gpt-4o_none.json", "sel_gpt-5.4_none.json",
          "sel_gpt-5.4_random.json", "sel_gpt-5.4_bm25.json", "sel_claude-opus-4-8_none.json"]:
    try:
        print(row(f[4:-5], metr(load(f), d_e1)))
    except FileNotFoundError:
        print(f"  (missing {f})")
