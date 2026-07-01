"""Debug & properly reconstruct paired cohort."""
import json, hashlib

tasks = json.load(open('datasets/astra_03_tools.json','r',encoding='utf-8'))
split = json.load(open('datasets/splits/correct_70_30_seed42_v2.json','r',encoding='utf-8'))
train = set(split['train_fingerprints'])
test  = set(split['test_fingerprints'])
other = set(split['other_fingerprints'])

def fp(t):
    text = t['input']['task']
    mcps = t['input']['mcp_servers'] or []
    tag  = t.get('match_tag') or 'null'
    joined = ",".join(sorted(mcps))
    raw = text + "|" + joined + "|" + tag
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

fps = [fp(t) for t in tasks]
in_train = sum(1 for f in fps if f in train)
in_test  = sum(1 for f in fps if f in test)
in_other = sum(1 for f in fps if f in other)
print(f'tasks: {len(tasks)}  in_train: {in_train}  in_test: {in_test}  in_other: {in_other}')
print(f'expected: 405 train, 174 test, 578 other')
print(f'sample fp:    {fps[0]} (task0 tag={tasks[0]["match_tag"]})')
print(f'sample train: {list(train)[0]}')

# +C cohort = test ∪ other = NOT in train AND in (test ∪ other)
nontrain_fps = test | other
plusC_cohort = [(i,t) for i,t in enumerate(tasks) if fps[i] in nontrain_fps]
print(f'+C cohort (test+other): {len(plusC_cohort)}')

baseline_cohort = list(enumerate(tasks))
baseline_idx_to_fp = {i: fps[i] for i in range(len(tasks))}
plusC_idx_to_fp   = {pidx: fp(t) for pidx,(_,t) in enumerate(plusC_cohort)}

base = json.load(open('datasets/experiment_logs/run_20260613_105137_llm_gpt-5_4_selection.json','r',encoding='utf-8'))
plusC = json.load(open('datasets/experiment_logs/run_20260613_165151_llm_gpt-5_4_selection_raicl-K_all-train_k10000_+C.json','r',encoding='utf-8'))

def index_by_fp(rows, idx_to_fp):
    out = {}
    for r in rows:
        f = idx_to_fp.get(r['task_idx'])
        if f is None: continue
        out[(r['persona'], f)] = r
    return out

def conf(rows):
    tp=fp_=tn=fn=0
    for r in rows:
        illegit = not r['is_legitimate']; deny = r['final_decision']!='ALLOW'
        if illegit and deny: tp+=1
        elif (not illegit) and deny: fp_+=1
        elif (not illegit) and (not deny): tn+=1
        else: fn+=1
    p = tp/(tp+fp_) if tp+fp_ else 0
    rec = tp/(tp+fn) if tp+fn else 0
    f1 = 2*p*rec/(p+rec) if p+rec else 0
    sf = fn/(tp+fn) if tp+fn else 0
    return dict(n=len(rows),tp=tp,fp=fp_,tn=tn,fn=fn,p=p,r=rec,f1=f1,sf=sf)

base_map = index_by_fp(base['experiments']['E1']['rows'], baseline_idx_to_fp)
plusC_map = index_by_fp(plusC['experiments']['E1']['rows'], plusC_idx_to_fp)
common = set(base_map.keys()) & set(plusC_map.keys())
print(f'baseline E1 rows mapped: {len(base_map)}')
print(f'+C E1 rows mapped: {len(plusC_map)}')
print(f'common: {len(common)}')

# Match_tag distribution in common cohort
from collections import Counter
mt_dist = Counter(base_map[k]['match_tag'] for k in common)
print(f'common tag dist: {dict(mt_dist)}')

# CORRECT PAIRED METRICS for E1, E2, E3
print('\nCORRECT PAIRED METRICS (fingerprint join, v2 split):')
print(f'{"Variant":<28} {"Exp":<3} {"n":>5} {"F1":>7} {"P":>7} {"R":>7} {"SF":>7}')
for e in ['E1','E2','E3']:
    b_map = index_by_fp(base['experiments'][e]['rows'], baseline_idx_to_fp)
    c_map = index_by_fp(plusC['experiments'][e]['rows'], plusC_idx_to_fp)
    com = set(b_map.keys()) & set(c_map.keys())
    bp = [b_map[k] for k in com]
    cp = [c_map[k] for k in com]
    bm = conf(bp); cm = conf(cp)
    print(f'{"Baseline (paired)":<28} {e:<3} {bm["n"]:>5} {bm["f1"]:>7.4f} {bm["p"]:>7.4f} {bm["r"]:>7.4f} {bm["sf"]:>7.4f}')
    print(f'{"+C BM25 (paired)":<28} {e:<3} {cm["n"]:>5} {cm["f1"]:>7.4f} {cm["p"]:>7.4f} {cm["r"]:>7.4f} {cm["sf"]:>7.4f}')
    print(f'  delta (+C - base): dF1={cm["f1"]-bm["f1"]:+.4f}  dP={cm["p"]-bm["p"]:+.4f}  dR={cm["r"]-bm["r"]:+.4f}  dSF={cm["sf"]-bm["sf"]:+.4f}')
    print()

# Flip ledger E1
a2d=[]; d2a=[]; nf=0
for k in common:
    b = base_map[k]['final_decision']; c = plusC_map[k]['final_decision']
    tag = base_map[k]['match_tag']
    if b=='ALLOW' and c!='ALLOW': a2d.append(tag)
    elif b!='ALLOW' and c=='ALLOW': d2a.append(tag)
    else: nf += 1
print(f'\nFLIP LEDGER (E1, paired):')
print(f'  ALLOW->DENY: {len(a2d)}  correct={a2d.count("correct")}  wrong={a2d.count("wrong")}  null={a2d.count("null")}')
print(f'  DENY->ALLOW: {len(d2a)}  correct={d2a.count("correct")}  wrong={d2a.count("wrong")}  null={d2a.count("null")}')
print(f'  no flip:     {nf}  ({100*nf/len(common):.1f}%)')

# Tool quality on correct slice
print()
correct_common = [k for k in common if base_map[k]['match_tag']=='correct']
print(f'Tool quality, paired correct slice n={len(correct_common)}')
b_exact = sum(1 for k in correct_common if base_map[k].get('tool_match'))
c_exact = sum(1 for k in correct_common if plusC_map[k].get('tool_match'))
b_j = sum(base_map[k].get('tool_jaccard',0) for k in correct_common) / len(correct_common)
c_j = sum(plusC_map[k].get('tool_jaccard',0) for k in correct_common) / len(correct_common)
print(f'  baseline: exact={b_exact} ({100*b_exact/len(correct_common):.1f}%) jaccard={b_j:.4f}')
print(f'  +C BM25:  exact={c_exact} ({100*c_exact/len(correct_common):.1f}%) jaccard={c_j:.4f}')
