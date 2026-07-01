"""Regenerate the rebuilt paper's Appendix D tables from scratch/canonical_rows/ (agnostic engine, rescue=4.0)."""
import os, json, random
random.seed(7)
D = os.path.join("scratch", "canonical_rows")
def load(n): return json.load(open(os.path.join(D, n), encoding="utf-8"))

# deny predicates (E4 model-dependent; E1-E3 deterministic)
e1 = lambda x: x["rbac_deny"] or x["abac_deny"] or x["tsphol_deny"]
e2 = lambda x: x["abac_deny"] or x["tsphol_deny"]
e3 = lambda x: x["tsphol_deny"]
e4 = lambda x: x["llm_valid"] is False
noTRAC = lambda x: x["rbac_deny"] or x["abac_deny"]

def conf(rows, deny):
    tp=fp=tn=fn=0
    for x in rows:
        legit=x["is_legitimate"]; allow=not deny(x)
        if not legit and not allow: tp+=1
        elif legit and not allow:   fp+=1
        elif legit and allow:       tn+=1
        else:                       fn+=1
    return tp,fp,tn,fn

def metr(rows, deny):
    tp,fp,tn,fn=conf(rows,deny)
    p=tp/(tp+fp) if tp+fp else 0
    r=tp/(tp+fn) if tp+fn else 0
    f1=2*tp/(2*tp+fp+fn) if (2*tp+fp+fn) else 0
    sf=fn/(tp+fn) if tp+fn else 0
    alw=sum(1 for x in rows if not deny(x)); dny=len(rows)-alw
    return dict(ALW=alw,DENY=dny,TP=tp,FP=fp,FN=fn,TN=tn,P=p,R=r,F1=f1,SF=sf)

VAL={"gpt-3.5-turbo-16k":"val_gpt-3.5-turbo-16k_r4.json","gpt-4o":"val_gpt-4o_r4.json","gpt-5.4":"val_gpt-5.4_r4.json"}

print("="*70); print("TABLE 1: validation_full confusion (E1-E4, 3 models)")
for m,fn_ in VAL.items():
    rows=load(fn_)
    for lbl,d in [("E1",e1),("E2",e2),("E3",e3),("E4",e4)]:
        x=metr(rows,d)
        print(f" {m:18s} & {lbl} & {x['ALW']:5d} & {x['DENY']:5d} & {x['TP']:5d} & {x['FP']:5d} & {x['FN']:5d} & {x['TN']:5d} & {x['P']:.3f} & {x['R']:.3f} & {x['F1']:.3f} \\\\")

# sanity: are E1-E3 identical across models?
r0=load(VAL["gpt-4o"]); r1=load(VAL["gpt-5.4"])
det_same=all(e1(a)==e1(b) and e2(a)==e2(b) and e3(a)==e3(b) for a,b in zip(r0,r1))
print(f"  [sanity] det E1-E3 identical gpt-4o vs gpt-5.4: {det_same}")

print("="*70); print("TABLE 2: selection_full confusion (gpt-5.4 baseline + bm25, E1-E3)")
for cond,fn_ in [("Baseline","sel_gpt-5.4_none.json"),("+C BM25","sel_gpt-5.4_bm25.json")]:
    rows=load(fn_); nleg=sum(1 for x in rows if x["is_legitimate"])
    print(f"  -- {cond}: n={len(rows)} legit={nleg} illeg={len(rows)-nleg}")
    for lbl,d in [("E1",e1),("E2",e2),("E3",e3)]:
        x=metr(rows,d)
        print(f" {cond:14s} & {lbl} & {x['ALW']:5d} & {x['DENY']:5d} & {x['TP']:5d} & {x['FP']:5d} & {x['FN']:5d} & {x['TN']:5d} & {x['P']:.3f} & {x['R']:.3f} & {x['F1']:.3f} \\\\")

print("="*70); print("TABLE 3: attribution_full (first-firing, validation E1)")
for m,fn_ in VAL.items():
    rows=load(fn_)
    tot=rb=ab=tr=0
    for x in rows:
        if not e1(x): continue
        tot+=1
        if x["rbac_deny"]: rb+=1
        elif x["abac_deny"]: ab+=1
        else: tr+=1
    print(f" {m:18s} & {tot} & {100*rb/tot:.1f} & {100*ab/tot:.1f} & {100*tr/tot:.1f} \\\\")

print("="*70); print("TABLE 4: per_persona_fp (validation E1, gpt-4o)")
rows=load(VAL["gpt-4o"])
from collections import defaultdict
agg=defaultdict(lambda:[0,0])
for x in rows:
    if not x["is_legitimate"]: continue
    a=agg[x["persona"]]; a[0]+=1
    if not e1(x): a[1]+=1
tot_l=tot_a=0
for p in ["devops_agent","incident_agent","finance_agent","research_agent","automation_gateway","security_engine"]:
    nl,al=agg[p]; dn=nl-al; tot_l+=nl; tot_a+=al
    pn=p.replace("_","\\_")
    print(f" {pn:20s} & {nl} & {al} & {dn} & ${dn/nl:.3f}$ \\\\")
print(f" TOTAL & {tot_l} & {tot_a} & {tot_l-tot_a} & ${(tot_l-tot_a)/tot_l:.3f}$ \\\\  (admit={100*tot_a/tot_l:.1f}%)")

print("="*70); print("TABLE 5: bootstrap_summary (task-level B=1000)")
def boot(rows, fn_metric, B=1000):
    by=defaultdict(list)
    for x in rows: by[x["task_idx"]].append(x)
    tasks=list(by.keys()); vals=[]
    for _ in range(B):
        samp=[]
        for _ in range(len(tasks)): samp.extend(by[random.choice(tasks)])
        vals.append(fn_metric(samp))
    vals.sort(); lo=vals[int(0.025*B)]; hi=vals[int(0.975*B)]
    return lo,hi
for m,fn_ in VAL.items():
    rows=load(fn_)
    pf1=metr(rows,e1)["F1"]; psf=metr(rows,e1)["SF"]
    lo1,hi1=boot(rows, lambda s: metr(s,e1)["F1"])
    los,his=boot(rows, lambda s: metr(s,e1)["SF"])
    print(f" {m:18s} E1 & $F_1$   & ${pf1:.3f}$ & $[{lo1:.3f}, {hi1:.3f}]$ \\\\")
    print(f" {m:18s} E1 & SecFail & ${psf:.3f}$ & $[{los:.3f}, {his:.3f}]$ \\\\")
# det marginals (model-independent) on gpt-4o dump
rows=load(VAL["gpt-4o"])
def dsf(s,da,db): return metr(s,da)["SF"]-metr(s,db)["SF"]
dR=dsf(rows,e2,e1); dA=dsf(rows,e3,e2); dT=dsf(rows,noTRAC,e1)
loR,hiR=boot(rows, lambda s: dsf(s,e2,e1)); loA,hiA=boot(rows, lambda s: dsf(s,e3,e2)); loT,hiT=boot(rows, lambda s: dsf(s,noTRAC,e1))
print(f" det $\\Delta$RBAC & SecFail & ${dR:+.3f}$ & $[{loR:+.3f}, {hiR:+.3f}]$ \\\\")
print(f" det $\\Delta$ABAC & SecFail & ${dA:+.3f}$ & $[{loA:+.3f}, {hiA:+.3f}]$ \\\\")
print(f" det $\\Delta$TRAC & SecFail & ${dT:+.3f}$ & $[{loT:+.3f}, {hiT:+.3f}]$ \\\\")
