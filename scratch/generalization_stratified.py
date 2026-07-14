"""Within-corpus generalisation: does the fixed floor operating point hold across strata?
Deterministic, no LLM calls; reads canonical rows. Reports, per stratum:
  - E1 floor (model-independent): SecFail, F1, false-block over ADMISSIBLE (correct AND authorised),
  - E4 (LLM-alone) SecFail for each OpenAI model, to check the floor bounds every model in each stratum.
Strata available directly from the rows: domain, match_tag class (wrong/null), persona.
"""
import json, collections
import statistics as st

VAL = {
    "gpt-3.5": "scratch/canonical_rows/val_gpt-3.5-turbo-16k_r4.json",
    "gpt-4o":  "scratch/canonical_rows/val_gpt-4o_r4.json",
    "gpt-5.4": "scratch/canonical_rows/val_gpt-5.4_r4.json",
}
rows_by_model = {m: json.load(open(p, encoding="utf-8")) for m, p in VAL.items()}
ref = rows_by_model["gpt-4o"]  # E1 is model-independent; use gpt-4o dump for the floor.


def e1(x):  return x["rbac_deny"] or x["abac_deny"] or x["tsphol_deny"]
def e4(x):  return x["llm_valid"] is False


def secfail(rs, deny):
    tp = fn = 0
    for x in rs:
        if not x["is_legitimate"]:
            if deny(x): tp += 1
            else:       fn += 1
    return fn / (tp + fn) if (tp + fn) else 0.0


def floor_stats(rs):
    tp = fp = tn = fn = 0
    for x in rs:
        d = e1(x)
        if not x["is_legitimate"] and d:   tp += 1
        elif x["is_legitimate"] and d:     fp += 1
        elif x["is_legitimate"] and not d: tn += 1
        else:                              fn += 1
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    # false-block over ADMISSIBLE = legit AND not rbac AND not abac; denied by TRAC.
    adm = [x for x in rs if x["is_legitimate"] and not x["rbac_deny"] and not x["abac_deny"]]
    ob = sum(1 for x in adm if x["tsphol_deny"])
    fb_adm = ob / len(adm) if adm else 0.0
    return dict(n=len(rs), secfail=sf, f1=f1, fb_adm=fb_adm, adm_n=len(adm))


def report(name, key_fn):
    print("=" * 78)
    print(f"STRATIFY BY {name}")
    print(f"{'stratum':16}{'n':>6}{'E1_SF':>7}{'E1_F1':>7}{'FB_adm':>7} | "
          f"{'E4 SecFail (LLM alone)':>28}  floor<all?")
    groups = collections.defaultdict(list)
    for x in ref:
        groups[key_fn(x)].append(x)
    out = {}
    worst_ok = True
    for g in sorted(groups, key=lambda k: -len(groups[k])):
        if g in (None, ""):
            continue
        fs = floor_stats(groups[g])
        # per-model E4 SecFail on the same stratum (rows aligned by index across dumps)
        idx = [i for i, x in enumerate(ref) if key_fn(x) == g]
        e4sf = {}
        for m, rs in rows_by_model.items():
            sub = [rs[i] for i in idx]
            e4sf[m] = secfail(sub, e4)
        bounds = all(fs["secfail"] <= v + 1e-9 for v in e4sf.values())
        worst_ok = worst_ok and bounds
        out[g] = dict(fs, e4=e4sf, floor_bounds_all=bounds)
        e4str = " ".join(f"{m}={v:.2f}" for m, v in e4sf.items())
        print(f"{str(g):16}{fs['n']:>6}{fs['secfail']:>7.3f}{fs['f1']:>7.3f}{fs['fb_adm']:>7.3f} | "
              f"{e4str:>28}  {'YES' if bounds else 'NO'}")
    print(f"  -> floor SecFail <= every model's E4 SecFail in ALL {len(out)} strata: {worst_ok}")
    return out


dom = report("DOMAIN (8 tool catalogs)", lambda x: (x.get("domain") or "").strip())
tag = report("MATCH_TAG CLASS (negative type)", lambda x: x.get("match_tag"))
per = report("PERSONA", lambda x: x.get("persona"))

json.dump({"by_domain": dom, "by_match_tag": tag, "by_persona": per},
          open("scratch/generalization_stratified.json", "w"), indent=2, default=float)
print("\nsaved -> scratch/generalization_stratified.json")

# Summary spread of the model-independent floor across domains
fb = [v["fb_adm"] for v in dom.values()]
sf = [v["secfail"] for v in dom.values()]
f1 = [v["f1"] for v in dom.values()]
print(f"\nAcross {len(dom)} domains (fixed thresholds): "
      f"F1 {min(f1):.3f}-{max(f1):.3f} (sd {st.pstdev(f1):.3f}); "
      f"SecFail {min(sf):.3f}-{max(sf):.3f}; FB_adm {min(fb):.3f}-{max(fb):.3f}")
