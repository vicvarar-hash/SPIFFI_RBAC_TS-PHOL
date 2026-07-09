"""Full-factorial layer ablation (deterministic, from canonical rows; no API).

Motivation: E1->E2->E3 successive deltas are order-dependent and don't isolate TRAC's marginal
on top of conventional access control. Here we score ALL non-empty layer subsets from the released
per-row decisions (validation; deterministic => model-independent), including the key missing cell
RBAC+ABAC (no TRAC), and report the marginal value of each layer added last.
"""
import os, json

rows = json.load(open(os.path.join("scratch", "canonical_rows", "val_gpt-4o_r4.json"), encoding="utf-8"))


def metr(deny):
    tp = fp = tn = fn = 0
    for x in rows:
        legit = x["is_legitimate"]; allow = not deny(x)
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    f1 = 2*tp/(2*tp+fp+fn) if (2*tp+fp+fn) else 0
    sf = fn/(tp+fn) if (tp+fn) else 0
    adm = tn/(tn+fp) if (tn+fp) else 0
    return f1, sf, 100*adm


R = lambda x: x["rbac_deny"]
A = lambda x: x["abac_deny"]
T = lambda x: x["tsphol_deny"]

configs = [
    ("(none)",        lambda x: False),
    ("RBAC",          lambda x: R(x)),
    ("ABAC",          lambda x: A(x)),
    ("TRAC",          lambda x: T(x)),
    ("RBAC+ABAC",     lambda x: R(x) or A(x)),
    ("RBAC+TRAC",     lambda x: R(x) or T(x)),
    ("ABAC+TRAC",     lambda x: A(x) or T(x)),
    ("RBAC+ABAC+TRAC",lambda x: R(x) or A(x) or T(x)),
]

print(f"n={len(rows)}")
print(f"{'config':16} {'F1':>6} {'SecFail':>8} {'Admit':>7}")
res = {}
for name, d in configs:
    f1, sf, adm = metr(d)
    res[name] = (f1, sf, adm)
    print(f"{name:16} {f1:>6.3f} {sf:>8.4f} {adm:>6.1f}%")

print("\n=== Marginal value of adding each layer LAST to the full stack (drop-one) ===")
full = res["RBAC+ABAC+TRAC"]
for layer, without in [("RBAC", "ABAC+TRAC"), ("ABAC", "RBAC+TRAC"), ("TRAC", "RBAC+ABAC")]:
    w = res[without]
    dsf = full[1] - w[1]   # SecFail(full) - SecFail(without)  (negative = layer lowers SecFail)
    dadm = full[2] - w[2]
    print(f"  drop {layer:5}: SecFail {w[1]:.4f} -> {full[1]:.4f} (Δ={dsf:+.4f}), "
          f"Admit {w[2]:.1f}% -> {full[2]:.1f}% (Δ={dadm:+.1f}pp)")

json.dump({k: {"f1": round(v[0],4), "secfail": round(v[1],4), "admit": round(v[2],2)} for k,v in res.items()},
          open(os.path.join("scratch", "factorial_ablation.json"), "w"), indent=2)
print("\nSaved -> scratch/factorial_ablation.json")
