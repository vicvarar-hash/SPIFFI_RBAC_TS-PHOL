"""Cross-distribution generalisation: does the floor's single fixed operating point hold across
ASTRA's distinct MCP domains (each a different tool catalog / lexical distribution)? Deterministic,
no LLM calls; reads the post-fix canonical rows. Reported in the Discussion (generalisability).
"""
import json
import collections
import statistics as st

ROWS = "scratch/canonical_rows/val_gpt-4o_r4.json"
rows = json.load(open(ROWS, encoding="utf-8"))

by = collections.defaultdict(list)
for x in rows:
    by[(x.get("domain") or "").strip()].append(x)


def floor_metrics(rs):
    tp = fp = tn = fn = 0
    for x in rs:
        deny = x["rbac_deny"] or x["abac_deny"] or x["tsphol_deny"]
        if not x["is_legitimate"] and deny:      tp += 1
        elif x["is_legitimate"] and deny:        fp += 1
        elif x["is_legitimate"] and not deny:    tn += 1
        else:                                    fn += 1
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    fb = fp / (fp + tn) if (fp + tn) else 0.0
    return dict(n=len(rs), secfail=round(sf, 3), f1=round(f1, 3), false_block=round(fb, 3))


res = {d: floor_metrics(rs) for d, rs in by.items() if d}
print(f"{'domain':16}{'n':>6}{'SecFail':>9}{'F1':>7}{'FB':>7}")
for d in sorted(res, key=lambda k: -res[k]['n']):
    m = res[d]
    print(f"{d:16}{m['n']:>6}{m['secfail']:>9.3f}{m['f1']:>7.3f}{m['false_block']:>7.3f}")

sfs = [m['secfail'] for m in res.values()]
f1s = [m['f1'] for m in res.values()]
print(f"\nAcross {len(res)} domains (8 distinct tool catalogs):")
print(f"  F1:      mean={st.mean(f1s):.3f}  sd={st.pstdev(f1s):.3f}  range=[{min(f1s):.3f},{max(f1s):.3f}]")
print(f"  SecFail: mean={st.mean(sfs):.3f}  sd={st.pstdev(sfs):.3f}  range=[{min(sfs):.3f},{max(sfs):.3f}]")
json.dump({"per_domain": res,
           "f1_sd": round(st.pstdev(f1s), 3), "secfail_sd": round(st.pstdev(sfs), 3)},
          open("scratch/cross_domain_generalization.json", "w"), indent=2)
print("\nsaved -> scratch/cross_domain_generalization.json")
