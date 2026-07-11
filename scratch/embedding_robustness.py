"""Does a SEMANTIC (embedding) instantiation of TRAC's enforcing predicates resist the task-text
padding attack that collapses the lexical BM25 instantiation to 0%? Fully local (model2vec static
embeddings; no API, no keys). We mirror scratch/adversarial_robustness.py exactly, swapping only the
predicate backend, and report catch rate on the 578 wrong/null bundles: original vs. padded, BM25 vs.
embedding. Honest either way.
"""
import os
import sys
import json
import glob
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
from numpy.linalg import norm
from model2vec import StaticModel

from app.services.task_domain_classifier import resolve_required_domain
from app.services import tool_relevance as trel
from app.services.normalization import normalize_mcp_name

trel.RESCUE_RELEVANCE = 4.0
THRESH = trel.THRESHOLD

MODEL = StaticModel.from_pretrained("scratch/m2v_model")


def emb(texts):
    v = MODEL.encode(list(texts))
    return v / (norm(v, axis=1, keepdims=True) + 1e-9)


# --- build catalog: tool text + per-domain document ---
TOOLTEXT, DOMAIN_DOC = {}, {}
for p in sorted(glob.glob(os.path.join("mcp_servers", "*.json"))):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    dom = normalize_mcp_name(os.path.splitext(os.path.basename(p))[0])
    parts = []
    for t in d.get("tools", []):
        nm = t.get("name")
        if nm:
            txt = (nm + " " + (t.get("description") or "")).strip()
            TOOLTEXT[nm] = txt
            parts.append(txt)
    if parts:
        DOMAIN_DOC[dom] = " ".join(parts)

DOMAINS = list(DOMAIN_DOC)
DOM_VECS = emb([DOMAIN_DOC[d] for d in DOMAINS])           # (D, dim)
_AMBIG = 0.98  # runner-up within 98% of top cosine -> uncertain (embedding cosines are compressed)


def emb_infer_domain(task_text):
    tv = emb([task_text])[0]
    sims = DOM_VECS @ tv
    order = np.argsort(-sims)
    if len(order) >= 2 and sims[order[1]] >= _AMBIG * sims[order[0]]:
        return "uncertain"
    return DOMAINS[order[0]]


def emb_tool_relevance(tools, task_text):
    texts = [TOOLTEXT[t] for t in tools if t in TOOLTEXT]
    if not texts:
        return None
    tv = emb([task_text])[0]
    tvecs = emb(texts)
    return float(np.mean(tvecs @ tv))


# --- predicate deny functions (BM25 baseline vs embedding) ---
def bm25_denies(task_text, tools, bundle_domains):
    bd = {normalize_mcp_name(x) for x in bundle_domains if x}
    req = resolve_required_domain(task_text, list(bd), None)
    hard_missing = (req != "uncertain") and (req not in bd)
    rel = trel.bundle_tool_relevance(tools, task_text)
    rescued = (rel is not None and rel >= trel.RESCUE_RELEVANCE)
    return (hard_missing and not rescued) or (rel is not None and rel < THRESH), \
           (hard_missing and not rescued)


def emb_denies(task_text, tools, bundle_domains, rel_thresh):
    bd = {normalize_mcp_name(x) for x in bundle_domains if x}
    req = emb_infer_domain(task_text)
    hard_missing = (req != "uncertain") and (req not in bd)
    rel = emb_tool_relevance(tools, task_text)
    toolrel_deny = (rel is not None and rel < rel_thresh)
    return (hard_missing or toolrel_deny), hard_missing


def adv_text(orig, tools):
    return (orig + " " + " ".join(TOOLTEXT.get(t, t) for t in tools)).strip()


astra = json.load(open("datasets/astra_03_tools.json", encoding="utf-8"))
tasks = astra["tasks"] if isinstance(astra, dict) and "tasks" in astra else astra
neg = [t for t in tasks if t.get("match_tag") in ("wrong", "null")]

# calibrate embedding tool-relevance threshold to match BM25's normal tool_relevance catch on these
rels = [emb_tool_relevance(t["input"]["tools"], t["input"]["task"]) for t in neg]
rels = [r for r in rels if r is not None]
bm25_toolrel_catch = sum(1 for t in neg
                         if (lambda r: r is not None and r < THRESH)(
                             trel.bundle_tool_relevance(t["input"]["tools"], t["input"]["task"]))) / len(neg)
# pick emb threshold so its normal tool_relevance catch ~ BM25's
rel_thresh = float(np.quantile(rels, bm25_toolrel_catch)) if rels else 0.0
print(f"BM25 tool_relevance normal catch = {100*bm25_toolrel_catch:.1f}%  -> emb rel_thresh={rel_thresh:.3f}")


def run(deny_fn, label, **kw):
    st = collections.defaultdict(lambda: {"n": 0, "do": 0, "da": 0, "cap_o": 0, "cap_a": 0})
    for t in neg:
        tag = t.get("match_tag"); tools = t["input"]["tools"]; doms = t["input"]["mcp_servers"]
        text = t["input"]["task"]; s = st[tag]; s["n"] += 1
        d_o, cap_o = deny_fn(text, tools, doms, **kw)
        d_a, cap_a = deny_fn(adv_text(text, tools), tools, doms, **kw)
        s["do"] += d_o; s["da"] += d_a; s["cap_o"] += cap_o; s["cap_a"] += cap_a
    n = sum(s["n"] for s in st.values()); do = sum(s["do"] for s in st.values())
    da = sum(s["da"] for s in st.values()); co = sum(s["cap_o"] for s in st.values())
    ca = sum(s["cap_a"] for s in st.values())
    print(f"\n[{label}]  n={n}")
    print(f"  TRAC catch (capcov OR toolrel):  original {100*do/n:5.1f}%  ->  padded {100*da/n:5.1f}%")
    print(f"  capability_coverage alone (domain): original {100*co/n:5.1f}%  ->  padded {100*ca/n:5.1f}%")
    return {"n": n, "catch_orig": round(100*do/n, 1), "catch_padded": round(100*da/n, 1),
            "capcov_orig": round(100*co/n, 1), "capcov_padded": round(100*ca/n, 1)}


print("=== Padding-attack robustness: BM25 (lexical) vs embedding (semantic) instantiation ===")
r_bm = run(bm25_denies, "BM25 (shipped lexical instantiation)")
r_em = run(lambda tx, tl, dm, rel_thresh: emb_denies(tx, tl, dm, rel_thresh), "Embedding (model2vec semantic instantiation)", rel_thresh=rel_thresh)
json.dump({"bm25": r_bm, "embedding": r_em, "rel_thresh": rel_thresh},
          open("scratch/embedding_robustness.json", "w"), indent=2)
print("\nsaved -> scratch/embedding_robustness.json")
