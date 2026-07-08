"""Point 2, canonical: advisory->enforcing counterfactual on the paper's own gpt-4o rows.
Reads scratch/canonical_rows/val_gpt-4o_r4.json (E1 is model-independent), so the baseline
matches the paper headline (SecFail 0.107 / Admit 43.9%). No replay, no API.
"""
import os, json
rows = json.load(open(os.path.join("scratch", "canonical_rows", "val_gpt-4o_r4.json"), encoding="utf-8"))

def metr(deny):
    tp=fp=tn=fn=0
    for x in rows:
        legit=x["is_legitimate"]; allow=not deny(x)
        if not legit and not allow: tp+=1
        elif legit and not allow:   fp+=1
        elif legit and allow:       tn+=1
        else:                       fn+=1
    f1=2*tp/(2*tp+fp+fn) if (2*tp+fp+fn) else 0
    sf=fn/(tp+fn) if (tp+fn) else 0
    adm=tn/(tn+fp) if (tn+fp) else 0
    return f1, sf, 100*adm

det = lambda x: x["rbac_deny"] or x["abac_deny"] or x["tsphol_deny"]
adv = lambda x, n: n in (x.get("tsphol_advisory_rules") or [])
ws  = lambda x: det(x) or adv(x,"write_safety")
ac  = lambda x: det(x) or adv(x,"action_coherence")
both= lambda x: det(x) or adv(x,"write_safety") or adv(x,"action_coherence")

def delta(cf):
    nc = sum(1 for x in rows if (not x["is_legitimate"]) and cf(x) and not det(x))
    nb = sum(1 for x in rows if x["is_legitimate"] and cf(x) and not det(x))
    return nc, nb

print(f"n={len(rows)}")
print(f"{'config':32} {'F1':>6} {'SecFail':>8} {'Admit%':>8}  {'+catch':>7} {'+block':>7}")
for name, fn in [("E1 baseline (both advisory)", det),
                 ("+ write_safety ENFORCING", ws),
                 ("+ action_coherence ENFORCING", ac),
                 ("+ BOTH ENFORCING", both)]:
    f1, sf, adm = metr(fn)
    nc, nb = (0,0) if fn is det else delta(fn)
    print(f"{name:32} {f1:6.3f} {sf:8.4f} {adm:8.1f}  {nc:7d} {nb:7d}")

print(f"\nadvisory firings: write_safety={sum(1 for x in rows if adv(x,'write_safety'))} rows, "
      f"action_coherence={sum(1 for x in rows if adv(x,'action_coherence'))} rows")
