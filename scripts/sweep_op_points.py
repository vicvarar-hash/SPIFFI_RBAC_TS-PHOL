"""Operating-point characterisation: compute SecFail vs legitimate-allow at
several log-derivable operating points across the experiment_logs runs.

This is a substitute for a full TRAC threshold-grid sweep (which would
require re-invoking the decision engine on the cached LLM outputs). Each
operating point is one of:
  OP1  E1 strict      (full stack, DECEPTION_ROUTED counted as DENY)
  OP2  E1 lenient     (full stack, DECEPTION_ROUTED counted as ALLOW)
  OP3  E2             (drop RBAC)
  OP4  E3             (drop RBAC + ABAC)
  OP5  E3 lenient     (drop RBAC + ABAC, deception=ALLOW)
  OP6  E4             (LLM verdict alone)

Reads only the released raw experiment logs; runs no LLM calls.
"""
import json
import pathlib

LOGS = pathlib.Path('datasets/experiment_logs')
RUNS = [
    ('gpt-3.5-turbo-16k', 'run_20260613_141204_llm_gpt-35-turbo-16k_validation.json'),
    ('gpt-4o',            'run_20260613_005419_llm_gpt-4o_validation.json'),
    ('gpt-5.4',           'run_20260612_191843_llm_gpt-5_4_validation.json'),
    ('gemini-2.5-pro',    'run_20260612_160439_llm_gemini-2_5-pro_validation.json'),
]


def metrics(rows, allow_set):
    tp = fp = tn = fn = 0
    legit_all = legit_n = 0
    failed = 0
    for r in rows:
        if r.get('llm_failed'):
            failed += 1
        legit = r['is_legitimate']
        if legit:
            legit_n += 1
        allow = r['final_decision'] in allow_set
        if legit and allow:
            legit_all += 1
        if not legit and not allow:
            tp += 1
        elif legit and not allow:
            fp += 1
        elif legit and allow:
            tn += 1
        elif not legit and allow:
            fn += 1
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r_ = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r_ / (p + r_) if (p + r_) else 0.0
    sf = fn / (tp + fn) if (tp + fn) else 0.0
    la = 100.0 * legit_all / legit_n if legit_n else 0.0
    return dict(n=len(rows), f1=f1, secfail=sf, legit_allow_pct=la, failed=failed)


OPS = [
    ('OP1 full stack (strict)',  'E1', {'ALLOW'}),
    ('OP2 full stack (lenient)', 'E1', {'ALLOW', 'DECEPTION_ROUTED'}),
    ('OP3 -RBAC',                'E2', {'ALLOW'}),
    ('OP4 -RBAC -ABAC',          'E3', {'ALLOW'}),
    ('OP5 -RBAC -ABAC (lenient)','E3', {'ALLOW', 'DECEPTION_ROUTED'}),
    ('OP6 LLM only',             'E4', {'ALLOW'}),
]


def main():
    for model, fn in RUNS:
        path = LOGS / fn
        if not path.exists():
            print(f'[skip] {model}: missing {fn}')
            continue
        d = json.load(open(path, 'r', encoding='utf-8'))
        print(f'=== {model}  ({fn})')
        print(f'{"label":40s} {"F1":>6} {"SecFail":>8} {"legit-allow":>12}')
        for label, exp, allow_set in OPS:
            if exp not in d['experiments']:
                continue
            rows = d['experiments'][exp]['rows']
            m = metrics(rows, allow_set)
            print(f'{label:40s} {m["f1"]:>6.3f} {m["secfail"]:>8.4f} {m["legit_allow_pct"]:>11.1f}%')
        print()


if __name__ == '__main__':
    main()
