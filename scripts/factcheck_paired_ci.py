"""Paired-cohort bootstrap CIs for Table 11 (RA-ICL paired comparison)."""
import json, hashlib, random, numpy as np
from collections import defaultdict

SPLIT='datasets/splits/correct_70_30_seed42_v2.json'
TOOLS='datasets/astra_03_tools.json'
BASE='datasets/experiment_logs/run_20260613_105137_llm_gpt-5_4_selection.json'
PC  ='datasets/experiment_logs/run_20260613_165151_llm_gpt-5_4_selection_raicl-K_all-train_k10000_+C.json'

tasks=json.load(open(TOOLS,encoding='utf-8'))
split=json.load(open(SPLIT,encoding='utf-8'))
train_fp=set(split['train_fingerprints'])

def fp(t):
    text=t['input']['task']
    mcps=sorted(t['input']['mcp_servers'])
    tag=t.get('match_tag') or 'null'
    raw=f"{text}|{','.join(mcps)}|{tag}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

task_fp=[fp(t) for t in tasks]
base=json.load(open(BASE,encoding='utf-8'))
pc=json.load(open(PC,encoding='utf-8'))

pc_task_indices=[i for i,t in enumerate(tasks) if task_fp[i] not in train_fp]

def group(rows, idx_map):
    g=defaultdict(list)
    for r in rows:
        ti=r['task_idx']; orig_i=idx_map[ti]; f=task_fp[orig_i]
        g[(f, r['persona'])].append(r)
    return g

results={}
for exp in ['E1','E2','E3']:
    base_g=group(base['experiments'][exp]['rows'], list(range(len(tasks))))
    pc_g=group(pc['experiments'][exp]['rows'], pc_task_indices)
    common=set(base_g)&set(pc_g)
    items=[(k[0], base_g[k][0], pc_g[k][0]) for k in common]
    pairs_only=[(br,pr) for (_,br,pr) in items]

    def metrics(rows, which):
        tp=fp_=fn=tn=0
        for br,pr in rows:
            r = br if which=='b' else pr
            pred_deny=(r['final_decision']=='DENY')
            actual_pos=not r['is_legitimate']
            if pred_deny and actual_pos: tp+=1
            elif pred_deny: fp_+=1
            elif actual_pos: fn+=1
            else: tn+=1
        P=tp/(tp+fp_) if tp+fp_>0 else 0
        R=tp/(tp+fn) if tp+fn>0 else 0
        F1=2*P*R/(P+R) if P+R>0 else 0
        SF=fn/(fn+tp) if fn+tp>0 else 0
        return F1,P,R,SF

    by_task=defaultdict(list)
    for f,br,pr in items:
        by_task[f].append((br,pr))
    tasks_list=list(by_task.keys())

    fb_full,pb_full,rb_full,sb_full=metrics(pairs_only, 'b')
    fp_full,pp_full,rp_full,sp_full=metrics(pairs_only, 'p')

    rng=random.Random(42); B=1000
    dF1=[]; dP=[]; dR=[]; dSF=[]
    for _ in range(B):
        samp=[]
        for _ in tasks_list:
            samp.extend(by_task[rng.choice(tasks_list)])
        fb,pb,rb,sb=metrics(samp,'b')
        fp1,pp,rp,sp=metrics(samp,'p')
        dF1.append(fp1-fb); dP.append(pp-pb); dR.append(rp-rb); dSF.append(sp-sb)

    print(f'\n=== {exp}  n_pairs={len(items)}  unique_tasks={len(tasks_list)} ===')
    print(f'Baseline: F1={fb_full:.4f} P={pb_full:.4f} R={rb_full:.4f} SF={sb_full:.4f}')
    print(f'+C BM25:  F1={fp_full:.4f} P={pp_full:.4f} R={rp_full:.4f} SF={sp_full:.4f}')
    for name,v in [('dF1',dF1),('dP',dP),('dR',dR),('dSF',dSF)]:
        lo,hi=np.percentile(v,[2.5,97.5])
        print(f'  {name}: point={np.mean(v):+.4f}  95% CI=[{lo:+.4f}, {hi:+.4f}]')
