"""RA-ICL paired-cohort join for Table `raicl_security` (deterministic, no API).

The quick diagnostic in ``canonical_tables.py`` keyed the RA-ICL
pairing by ``task_idx`` alone, collapsing the six personas, and the paper's claimed content
fingerprint join had no released script. This is that script.

The baseline (``none``) covers 1,157 tasks x 6 personas = 6,942 rows; the retrieval variants hold out
the 405 training-pool tasks, leaving 752 tasks x 6 personas = 4,512 rows. We join the common cohort
on the stable ``(task_idx, persona)`` row identity -- ASTRA contains duplicate task *texts*, so a
content hash of (task text, MCPs, match_tag) is NOT one-to-one; the (task, persona) index is. We
verify the mapping is one-to-one and recompute the E1-gated SecFail / F1 on the paired 4,512-row
cohort. Numbers reproduce Table `raicl_security` to the reported precision.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROWS = os.path.join("scratch", "canonical_rows")


def load(f):
    return json.load(open(os.path.join(ROWS, f + ".json"), encoding="utf-8"))


def row_key(r):
    """Stable (task, persona) row identity -- the one-to-one join key."""
    return (r["task_idx"], r["persona"])


def e1_deny(r):
    return bool(r["rbac_deny"] or r["abac_deny"] or r["tsphol_deny"])


def metr(rows):
    tp = fp = tn = fn = 0
    for r in rows:
        legit = r["is_legitimate"]
        allow = not e1_deny(r)
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    return f1, sf


def index_by_key(rows, label):
    out = {}
    for r in rows:
        k = row_key(r)
        if k in out:
            raise SystemExit(f"[{label}] duplicate row identity {k}")
        out[k] = r
    return out


def main():
    none = index_by_key(load("sel_gpt-5.4_none"), "none")
    bm25 = index_by_key(load("sel_gpt-5.4_bm25"), "bm25")
    rnd = index_by_key(load("sel_gpt-5.4_random"), "random")
    print(f"one-to-one (task, persona) rows: none={len(none)} bm25={len(bm25)} random={len(rnd)}")

    cohort = set(bm25) & set(rnd) & set(none)
    print(f"common paired cohort: {len(cohort)} rows")

    variants = [("No retrieval (paired)", none), ("+ random RA-ICL", rnd), ("+ BM25 RA-ICL", bm25)]
    res = {}
    print(f"\n{'variant':22} {'n':>5} {'F1':>7} {'SecFail':>8}")
    for name, idx in variants:
        rows = [idx[k] for k in cohort]
        f1, sf = metr(rows)
        res[name] = (f1, sf)
        print(f"{name:22} {len(rows):>5} {f1:>7.3f} {sf:>8.4f}")

    sfn = res["No retrieval (paired)"][1]
    sfb = res["+ BM25 RA-ICL"][1]
    sfr = res["+ random RA-ICL"][1]
    print(f"\ndSecFail  BM25-none = {sfb - sfn:+.4f}   random-none = {sfr - sfn:+.4f}")

    json.dump({k: {"f1": round(v[0], 4), "secfail": round(v[1], 4)} for k, v in res.items()},
              open(os.path.join("scratch", "raicl_join.json"), "w"), indent=2)
    print("\nSaved -> scratch/raicl_join.json")


if __name__ == "__main__":
    main()
