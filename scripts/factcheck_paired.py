"""Reconstruct true paired cohort via fingerprint join."""
import json, hashlib

def fp(t):
    text = t['input']['task']
    mcps = t['input']['mcp_servers'] or []
    tag = t.get('match_tag') or 'null'
    raw = f'{text}|{",".join(sorted(mcps))}|{tag}'
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

tasks = json.load(open('datasets/astra_03_tools.json','r',encoding='utf-8'))
split = json.load(open('datasets/splits/correct_70_30_seed42.json','r',encoding='utf-8'))
train = set(split['train_fingerprints'])

baseline_cohort = list(enumerate(tasks))
plusC_cohort = [(i,t) for i,t in enumerate(tasks) if fp(t) not in train]
print(f'baseline cohort: {len(baseline_cohort)}')
print(f'+C cohort:       {len(plusC_cohort)}')

baseline_idx_to_fp = {i: fp(t) for i,t in baseline_cohort}
plusC_idx_to_fp = {pidx: fp(t) for pidx,(_,t) in enumerate(plusC_cohort)}

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

print()
print('PAIRED via fingerprint reconstruction:')
print(f'{"Variant":<28} {"Exp":<3} {"n":>5} {"F1":>7} {"P":>7} {"R":>7} {"SF":>7}')
for e in ['E1','E2','E3']:
    base_map = index_by_fp(base['experiments'][e]['rows'], baseline_idx_to_fp)
    plusC_map = index_by_fp(plusC['experiments'][e]['rows'], plusC_idx_to_fp)
    common = set(base_map.keys()) & set(plusC_map.keys())
    base_paired = [base_map[k] for k in common]
    plusC_paired = [plusC_map[k] for k in common]
    bm = conf(base_paired); cm = conf(plusC_paired)
    print(f'{"Baseline (paired)":<28} {e:<3} {bm["n"]:>5} {bm["f1"]:>7.4f} {bm["p"]:>7.4f} {bm["r"]:>7.4f} {bm["sf"]:>7.4f}')
    print(f'{"+C BM25 (paired)":<28} {e:<3} {cm["n"]:>5} {cm["f1"]:>7.4f} {cm["p"]:>7.4f} {cm["r"]:>7.4f} {cm["sf"]:>7.4f}')
    print(f'  delta (+C - baseline): dF1={cm["f1"]-bm["f1"]:+.4f}  dP={cm["p"]-bm["p"]:+.4f}  dR={cm["r"]-bm["r"]:+.4f}  dSF={cm["sf"]-bm["sf"]:+.4f}')
    print()

# Flip ledger E1
base_map = index_by_fp(base['experiments']['E1']['rows'], baseline_idx_to_fp)
plusC_map = index_by_fp(plusC['experiments']['E1']['rows'], plusC_idx_to_fp)
common = set(base_map.keys()) & set(plusC_map.keys())
print(f'Common paired rows: {len(common)}')
a2d=[]; d2a=[]; nf=0
for k in common:
    b = base_map[k]['final_decision']; c = plusC_map[k]['final_decision']
    tag = base_map[k]['match_tag']
    if b=='ALLOW' and c!='ALLOW': a2d.append(tag)
    elif b!='ALLOW' and c=='ALLOW': d2a.append(tag)
    else: nf += 1
print(f'ALLOW->DENY: {len(a2d)}  (correct={a2d.count("correct")}, wrong={a2d.count("wrong")}, null={a2d.count("null")})')
print(f'DENY->ALLOW: {len(d2a)}  (correct={d2a.count("correct")}, wrong={d2a.count("wrong")}, null={d2a.count("null")})')
print(f'no flip:     {nf}  ({100*nf/len(common):.1f}%)')
print(f'Net A->D: {len(a2d)-len(d2a)}')

# Tool quality paired (correct slice only)
print()
print('Tool quality on correct slice (paired):')
correct_common = [k for k in common if base_map[k]['match_tag']=='correct']
print(f'  paired correct rows: {len(correct_common)}')
b_exact = sum(1 for k in correct_common if base_map[k].get('tool_match'))
c_exact = sum(1 for k in correct_common if plusC_map[k].get('tool_match'))
b_jacc = sum(base_map[k].get('tool_jaccard',0) for k in correct_common) / len(correct_common)
c_jacc = sum(plusC_map[k].get('tool_jaccard',0) for k in correct_common) / len(correct_common)
print(f'  baseline exact={b_exact} ({100*b_exact/len(correct_common):.1f}%) jaccard={b_jacc:.4f}')
print(f'  +C BM25  exact={c_exact} ({100*c_exact/len(correct_common):.1f}%) jaccard={c_jacc:.4f}')
