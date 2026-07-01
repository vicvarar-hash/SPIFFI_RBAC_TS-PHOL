"""Comprehensive numerical fact-check of paper/main_acm.tex against raw experiment logs."""
import json, pathlib, statistics, random
from collections import Counter, defaultdict

LOGS = pathlib.Path('datasets/experiment_logs')
RUNS = {
    'gpt-3.5-turbo-16k_val': 'run_20260613_141204_llm_gpt-35-turbo-16k_validation.json',
    'gpt-4o_val':            'run_20260613_005419_llm_gpt-4o_validation.json',
    'gpt-5.4_val':           'run_20260612_191843_llm_gpt-5_4_validation.json',
    'gpt-5.4_sel_base':      'run_20260613_105137_llm_gpt-5_4_selection.json',
    'gpt-5.4_sel_+C':        'run_20260613_165151_llm_gpt-5_4_selection_raicl-K_all-train_k10000_+C.json',
}

def load(name):
    return json.load(open(LOGS / RUNS[name], 'r', encoding='utf-8'))

def conf_matrix(rows, positive='illegit'):
    """Convention A: positive=illegitimate, predict=DENY (incl DECEPTION)."""
    tp=fp=tn=fn=0
    for r in rows:
        illegit = not r['is_legitimate']
        deny = r['final_decision'] != 'ALLOW'
        if positive == 'illegit':
            if illegit and deny: tp+=1
            elif (not illegit) and deny: fp+=1
            elif (not illegit) and (not deny): tn+=1
            elif illegit and (not deny): fn+=1
        else:  # Convention B: positive=correct, predict=ALLOW
            correct = r['match_tag'] == 'correct'
            allow = r['final_decision'] == 'ALLOW'
            if correct and allow: tp+=1
            elif (not correct) and allow: fp+=1
            elif (not correct) and (not allow): tn+=1
            elif correct and (not allow): fn+=1
    return tp,fp,tn,fn

def prf(tp,fp,tn,fn):
    n = tp+fp+tn+fn
    p = tp/(tp+fp) if tp+fp else 0
    r = tp/(tp+fn) if tp+fn else 0
    f1 = 2*p*r/(p+r) if p+r else 0
    acc = (tp+tn)/n if n else 0
    secfail = fn/(tp+fn) if tp+fn else 0
    return dict(n=n,tp=tp,fp=fp,tn=tn,fn=fn,p=p,r=r,f1=f1,acc=acc,secfail=secfail)

def fmt(d, keys=('n','p','r','f1','secfail')):
    return ' '.join(f'{k}={d[k]:.4f}' if isinstance(d[k],float) else f'{k}={d[k]}' for k in keys)

print('='*100)
print('TABLE 5 (Convention A, validation, E1 vs E4)')
print('='*100)
print(f'{"Model":<22} {"Exp":<3} {"n":>5} {"TP":>5} {"FP":>5} {"TN":>5} {"FN":>5} {"Prec":>7} {"Recall":>7} {"F1":>7} {"SecFail":>8}')
for m in ['gpt-3.5-turbo-16k_val','gpt-4o_val','gpt-5.4_val']:
    d = load(m)
    for e in ['E1','E4']:
        rows = d['experiments'][e]['rows']
        cm = prf(*conf_matrix(rows,'illegit'))
        print(f'{m:<22} {e:<3} {cm["n"]:>5} {cm["tp"]:>5} {cm["fp"]:>5} {cm["tn"]:>5} {cm["fn"]:>5} '
              f'{cm["p"]:>7.4f} {cm["r"]:>7.4f} {cm["f1"]:>7.4f} {cm["secfail"]:>8.4f}')

print()
print('='*100)
print('TABLE 6 (Convention B, E4 ASTRA replication)')
print('='*100)
print(f'{"Model":<22} {"n":>5} {"Acc":>7} {"Prec":>7} {"Recall":>7} {"F1":>7}')
for m in ['gpt-3.5-turbo-16k_val','gpt-4o_val','gpt-5.4_val']:
    d = load(m)
    rows = d['experiments']['E4']['rows']
    cm = prf(*conf_matrix(rows,'correct'))
    print(f'{m:<22} {cm["n"]:>5} {cm["acc"]:>7.4f} {cm["p"]:>7.4f} {cm["r"]:>7.4f} {cm["f1"]:>7.4f}')

print()
print('='*100)
print('TABLE 7 (gpt-5.4 E4 per-domain allow rates for wrong & null)')
print('='*100)
d = load('gpt-5.4_val')
rows = d['experiments']['E4']['rows']
per = defaultdict(lambda: defaultdict(lambda: dict(n=0,allow=0)))
for r in rows:
    if r['match_tag'] in ('wrong','null'):
        dom = r['domain']
        per[dom][r['match_tag']]['n'] += 1
        if r['final_decision'] == 'ALLOW':
            per[dom][r['match_tag']]['allow'] += 1
print(f'{"Domain":<15} {"wrong n":>8} {"wrong %":>9} {"null n":>8} {"null %":>9}')
for dom in sorted(per.keys()):
    w = per[dom]['wrong']; nu = per[dom]['null']
    wp = 100*w['allow']/w['n'] if w['n'] else 0
    np_ = 100*nu['allow']/nu['n'] if nu['n'] else 0
    print(f'{dom:<15} {w["n"]:>8} {wp:>8.1f}% {nu["n"]:>8} {np_:>8.1f}%')

print()
print('='*100)
print('TABLE 8 (per-layer Δ in validation: E1 vs E2 vs E3 vs E4)')
print('='*100)
print(f'{"Model":<22} {"Exp":<3} {"F1":>7} {"SecFail":>8}')
for m in ['gpt-3.5-turbo-16k_val','gpt-4o_val','gpt-5.4_val']:
    d = load(m)
    cells = {}
    for e in ['E1','E2','E3','E4']:
        rows = d['experiments'][e]['rows']
        cm = prf(*conf_matrix(rows,'illegit'))
        cells[e] = cm
        print(f'{m:<22} {e:<3} {cm["f1"]:>7.4f} {cm["secfail"]:>8.4f}')
    dRBAC_f1 = cells['E1']['f1'] - cells['E2']['f1']
    dABAC_f1 = cells['E2']['f1'] - cells['E3']['f1']
    dTS_f1   = cells['E3']['f1'] - cells['E4']['f1']
    dRBAC_sf = cells['E2']['secfail'] - cells['E1']['secfail']
    dABAC_sf = cells['E3']['secfail'] - cells['E2']['secfail']
    dTS_sf   = cells['E4']['secfail'] - cells['E3']['secfail']
    print(f'  Δ vs paper: dRBAC F1={dRBAC_f1:+.4f} SF={dRBAC_sf:+.4f} | dABAC F1={dABAC_f1:+.4f} SF={dABAC_sf:+.4f} | dTSPHOL F1={dTS_f1:+.4f} SF={dTS_sf:+.4f}')
    if dRBAC_sf>0: ratio = dTS_sf/dRBAC_sf
    else: ratio = float('inf')
    print(f'  |dTS|/|dRBAC| ratio = {abs(dTS_sf)/abs(dRBAC_sf) if dRBAC_sf else "inf":.1f}x')

print()
print('='*100)
print('TABLE 9 (per-domain dominance, gpt-4o, validation E1 vs E2 vs E3 F1)')
print('='*100)
d = load('gpt-4o_val')
print(f'{"Domain":<15} {"n":>5} {"F1(E1)":>7} {"F1(E2)":>7} {"F1(E3)":>7} {"dRBAC":>7} {"dABAC":>7}')
domains = set(r['domain'] for r in d['experiments']['E1']['rows'])
for dom in sorted(domains):
    f1s = {}
    for e in ['E1','E2','E3']:
        rows = [r for r in d['experiments'][e]['rows'] if r['domain']==dom]
        cm = prf(*conf_matrix(rows,'illegit'))
        f1s[e] = cm['f1']
        n = cm['n']
    print(f'{dom:<15} {n:>5} {f1s["E1"]:>7.4f} {f1s["E2"]:>7.4f} {f1s["E3"]:>7.4f} '
          f'{f1s["E1"]-f1s["E2"]:>+7.4f} {f1s["E2"]-f1s["E3"]:>+7.4f}')

print()
print('='*100)
print('TABLE 10 (denial attribution E1 by first-firing layer)')
print('='*100)
for m in ['gpt-3.5-turbo-16k_val','gpt-4o_val','gpt-5.4_val']:
    d = load(m)
    rows = d['experiments']['E1']['rows']
    deny = [r for r in rows if r['final_decision'] != 'ALLOW']
    cnt = Counter(r['denial_source'] for r in deny)
    tot = len(deny)
    print(f'{m:<22} total denies={tot}  ', end='')
    for src in ['rbac','abac','tsphol','identity','transport']:
        c = sum(v for k,v in cnt.items() if k and src in k.lower())
        if c:
            print(f'{src}={c}({100*c/tot:.1f}%) ', end='')
    print()
    print(f'   raw denial_source values: {dict(cnt)}')

print()
print('='*100)
print('§8.7 read/write asymmetry (gpt-4o E1)')
print('='*100)
d = load('gpt-4o_val')
rows = d['experiments']['E1']['rows']
for has_w in [True, False]:
    sub = [r for r in rows if r.get('has_write')==has_w]
    cm = prf(*conf_matrix(sub,'illegit'))
    label = 'write-bearing' if has_w else 'read-only'
    print(f'  {label:<14} n={cm["n"]:>5} F1={cm["f1"]:.4f} SecFail={cm["secfail"]:.4f}')

print()
print('='*100)
print('TABLE 11 (RA-ICL paired comparison, gpt-5.4 selection)')
print('='*100)
base = load('gpt-5.4_sel_base')
plusC = load('gpt-5.4_sel_+C')
# Build key set for paired comparison: (group/persona/match_tag/groundtruth_tools-tuple)
def keyof(r):
    gt = tuple(sorted(r['groundtruth_tools'] or []))
    return (r['persona'], r['match_tag'], gt)

for label, src in [('Baseline (all)', base), ('+C BM25', plusC)]:
    for e in ['E1','E2','E3']:
        rows = src['experiments'][e]['rows']
        cm = prf(*conf_matrix(rows,'illegit'))
        print(f'{label:<18} {e} n={cm["n"]:>5} F1={cm["f1"]:.4f} P={cm["p"]:.4f} R={cm["r"]:.4f} SF={cm["secfail"]:.4f}')

# Paired: intersect base with +C task keys
plusC_keys = set(keyof(r) for r in plusC['experiments']['E1']['rows'])
print(f'\n+C unique keys: {len(plusC_keys)}')
for e in ['E1','E2','E3']:
    base_paired = [r for r in base['experiments'][e]['rows'] if keyof(r) in plusC_keys]
    cm = prf(*conf_matrix(base_paired,'illegit'))
    print(f'Baseline (restricted to +C cohort) {e} n={cm["n"]} F1={cm["f1"]:.4f} P={cm["p"]:.4f} R={cm["r"]:.4f} SF={cm["secfail"]:.4f}')

print()
print('='*100)
print('TABLE 12 (tool-selection quality, correct slice)')
print('='*100)
for label, src in [('Baseline', base), ('+C BM25', plusC)]:
    rows = src['experiments']['E1']['rows']
    correct = [r for r in rows if r['match_tag']=='correct']
    n = len(correct)
    exact = sum(1 for r in correct if r.get('tool_match'))
    jacc = [r.get('tool_jaccard',0) for r in correct]
    print(f'{label:<10} n_correct={n} exact={exact} ({100*exact/n:.1f}%) jaccard_avg={sum(jacc)/n:.4f}')

print()
print('='*100)
print('Flip ledger (paired baseline vs +C, common cohort, E1)')
print('='*100)
base_E1 = {keyof(r): r for r in base['experiments']['E1']['rows'] if keyof(r) in plusC_keys}
plusC_E1 = {keyof(r): r for r in plusC['experiments']['E1']['rows']}
common_keys = set(base_E1.keys()) & set(plusC_E1.keys())
print(f'Common paired rows: {len(common_keys)}')
flips_A2D = []; flips_D2A = []; noflip = 0
for k in common_keys:
    b = base_E1[k]['final_decision']
    c = plusC_E1[k]['final_decision']
    tag = base_E1[k]['match_tag']
    if b=='ALLOW' and c!='ALLOW': flips_A2D.append(tag)
    elif b!='ALLOW' and c=='ALLOW': flips_D2A.append(tag)
    else: noflip += 1
print(f'ALLOW→DENY: {len(flips_A2D)}  (correct={flips_A2D.count("correct")}, wrong={flips_A2D.count("wrong")}, null={flips_A2D.count("null")})')
print(f'DENY→ALLOW: {len(flips_D2A)}  (correct={flips_D2A.count("correct")}, wrong={flips_D2A.count("wrong")}, null={flips_D2A.count("null")})')
print(f'no flip: {noflip} ({100*noflip/len(common_keys):.1f}%)')

print()
print('='*100)
print('§8.1 Legitimate-allow rate (E1)')
print('='*100)
for m in ['gpt-3.5-turbo-16k_val','gpt-4o_val','gpt-5.4_val']:
    d = load(m)
    rows = d['experiments']['E1']['rows']
    legit = [r for r in rows if r['is_legitimate']]
    legit_allowed = [r for r in legit if r['final_decision']=='ALLOW']
    print(f'{m:<22} n_legit={len(legit)} allowed={len(legit_allowed)} ({100*len(legit_allowed)/len(legit):.2f}%)')

print()
print('='*100)
print('Deception precision (validation)')
print('='*100)
for m in ['gpt-3.5-turbo-16k_val','gpt-4o_val','gpt-5.4_val']:
    d = load(m)
    print(f'\n{m}')
    for e in ['E1','E2','E3']:
        rows = d['experiments'][e]['rows']
        routed = [r for r in rows if r['final_decision']=='DECEPTION_ROUTED']
        if not routed: continue
        illegit = sum(1 for r in routed if not r['is_legitimate'])
        print(f'  {e} routed={len(routed)} illegit={illegit} precision={illegit/len(routed):.3f}')
