"""Policy-independent label + operating-point frontier (deterministic, no API).

Reviewers A & B (SACMAT R5), remaining accept conditions:
  (3) a label defined *independently of any policy artifact*, and
  (4) a recommended *deployable* operating point on the SecFail/false-block frontier.

Both are computable offline from the frozen canonical rows (val gpt-4o; the deterministic floor is
model-invariant). No replay, no API.

LABELS
  coupled      : the paper's Convention A -- is_legitimate = (match_tag==correct AND
                 persona in LEGITIMATE_PAIRINGS). The persona-domain allow-list also sources RBAC.
  independent  : is_legitimate = (match_tag==correct) ONLY -- ASTRA's tag, authored by no policy.
                 Illegitimate = wrong OR null. Fully decoupled from every policy artifact.

Reporting SecFail / F1 / false-block for each single layer, RBAC+ABAC, and FULL under both labels,
plus the order-independent drop-one marginals, so we can see whether RBAC's marginal is a label
artefact and where a deployable operating point sits.
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


def metr(rows, legit_fn, deny_fn):
    tp = fp = tn = fn = 0
    for x in rows:
        legit = legit_fn(x)
        allow = not deny_fn(x)
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    fb = fp / (fp + tn) if (fp + tn) else 0.0
    return f1, sf, fb


LABELS = {
    "coupled (Conv A)":        lambda x: x["is_legitimate"],
    "independent (match_tag)": lambda x: x["match_tag"] == "correct",
}
R = lambda x: x["rbac_deny"]
A = lambda x: x["abac_deny"]
T = lambda x: x["tsphol_deny"]
CONFIGS = {
    "RBAC only":      lambda x: R(x),
    "ABAC only":      lambda x: A(x),
    "TRAC only":      lambda x: T(x),
    "RBAC+ABAC":      lambda x: R(x) or A(x),
    "FULL (R+A+T)":   lambda x: R(x) or A(x) or T(x),
}
DROPONE = {
    "RBAC": (lambda x: A(x) or T(x)),
    "ABAC": (lambda x: R(x) or T(x)),
    "TRAC": (lambda x: R(x) or A(x)),
}


def main():
    rows = json.load(open(ROWS, encoding="utf-8"))
    n_legit = {k: sum(1 for x in rows if f(x)) for k, f in LABELS.items()}
    out = {}
    for lname, lf in LABELS.items():
        print(f"\n=== Label: {lname}  (legit rows={n_legit[lname]}/{len(rows)}) ===")
        print(f"  {'config':14} {'F1':>6} {'SecFail':>8} {'false-block':>12}")
        cfg = {}
        for cname, df in CONFIGS.items():
            f1, sf, fb = metr(rows, lf, df)
            cfg[cname] = dict(f1=round(f1, 4), secfail=round(sf, 4), false_block=round(fb, 4))
            print(f"  {cname:14} {f1:>6.3f} {sf:>8.4f} {fb:>12.4f}")
        full = metr(rows, lf, CONFIGS["FULL (R+A+T)"])
        print("  drop-one marginals (delta SecFail, pp; negative = layer lowers SecFail):")
        marg = {}
        for layer, wf in DROPONE.items():
            _, sf_w, _ = metr(rows, lf, wf)
            d = full[1] - sf_w
            marg[layer] = round(100 * d, 2)
            print(f"    {layer}: {100*d:+.2f}")
        out[lname] = {"n_legit": n_legit[lname], "configs": cfg, "dropone_pp": marg}

    json.dump(out, open(os.path.join("scratch", "policy_independent_label.json"), "w"), indent=2)
    print("\nSaved -> scratch/policy_independent_label.json")


if __name__ == "__main__":
    main()
