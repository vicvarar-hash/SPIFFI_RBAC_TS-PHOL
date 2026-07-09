"""Cross-vendor SELECTION-mode run (full ASTRA set) for a non-OpenAI model.

Tier-3 rebuttal to reviewers: the cross-vendor panel was validation-only. Here each
model *generates* the tool bundle (selection mode); we replay the generated bundles
through the deterministic floor (E1) to test whether the floor's SecFail stays low
when the model, not ASTRA, produces the bundle. Reports E1 SecFail/admission and
tool-selection quality (exact-match / Jaccard on the correct slice).

Usage:
  python scratch/run_crossvendor_selection.py --provider anthropic --model claude-opus-4-8 --tag opus48
  python scratch/run_crossvendor_selection.py --provider google --model gemini-2.5-pro --tag gemini25pro
"""
import os, sys, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ENV = {"anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY",
        "openai": "OPENAI_API_KEY", "azure_foundry": "AZURE_FOUNDRY_API_KEY"}


def load_env():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    for line in open(p, encoding="utf-8"):
        m = line.strip()
        if m and not m.startswith("#") and "=" in m:
            k, v = m.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def _slug(s):
    import re
    return re.sub(r"[^A-Za-z0-9]+", "-", str(s or "")).strip("-").lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=list(_ENV))
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    load_env()
    from app.loaders.astra_loader import load_astra_dataset
    from app.loaders.mcp_loader import load_mcp_personas
    from app.services.llm_inference_producer import produce_inference_log, default_log_path
    from app.services.llm_inference_log import save_log

    api_key = os.environ.get(_ENV[args.provider], "")
    print(f"[{args.provider}/{args.model}] key present: {bool(api_key)}", flush=True)
    if not api_key:
        sys.exit(2)

    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    personas, _ = load_mcp_personas("mcp_servers")
    run_tasks = tasks[: args.limit] if args.limit else tasks
    print(f"tasks={len(run_tasks)} personas={len(personas)} model={args.model} mode=selection", flush=True)

    t0 = time.time(); done = {"n": 0}
    def cb(ev):
        done["n"] += 1
        if done["n"] % 50 == 0:
            dt = time.time() - t0; rate = done["n"]/dt if dt else 0
            eta = (len(run_tasks)-done["n"])/rate if rate else 0
            print(f"  ... {done['n']}/{len(run_tasks)} generated ({rate:.2f}/s, ETA {eta/60:.1f} min)", flush=True)

    log = produce_inference_log(run_tasks, personas, model=args.model, provider=args.provider,
                                api_key=api_key, mode="selection", progress_cb=cb)
    entries = log.get("tasks", [])
    failed = sum(1 for t in entries if t.get("llm_failed"))
    print(f"\nGENERATED entries={len(entries)} failed={failed} in {(time.time()-t0)/60:.1f} min", flush=True)

    if args.limit:
        print("[pilot] not saving.", flush=True)
        print("sample:", json.dumps(entries[:2], separators=(",", ":"))[:400], flush=True)
        return

    path = save_log(default_log_path(log), log)
    print(f"Saved log -> {path}", flush=True)

    # tool-selection quality (correct slice)
    corr = [e for e in entries if e.get("match_tag") == "correct" and not e.get("llm_failed")]
    exact = sum(1 for e in corr if e.get("tool_match")) / len(corr) if corr else 0
    jacc = sum(e.get("tool_jaccard") or 0 for e in corr) / len(corr) if corr else 0

    # replay generated bundles through the deterministic floor (E1)
    from app.services import replay_service as rs
    from app.services import tool_relevance as trel
    trel.RESCUE_RELEVANCE = 4.0
    rows, _, _ = rs.replay_experiment(path, tasks, experiment="E1", limit=None,
                                      policies=rs.baseline_policies())

    def metr(deny):
        tp = fp = tn = fn = 0
        for x in rows:
            legit = x.is_legitimate; allow = not deny(x)
            if not legit and not allow: tp += 1
            elif legit and not allow:   fp += 1
            elif legit and allow:       tn += 1
            else:                       fn += 1
        f1 = 2*tp/(2*tp+fp+fn) if (2*tp+fp+fn) else 0
        sf = fn/(tp+fn) if (tp+fn) else 0
        adm = tn/(tn+fp) if (tn+fp) else 0
        return {"f1": round(f1, 4), "secfail": round(sf, 4), "admit": round(100*adm, 2)}

    det = lambda x: x.rbac_deny or x.abac_deny or x.tsphol_deny
    e1 = metr(det)
    print(f"  E1 (det floor on generated bundles) F1={e1['f1']} SecFail={e1['secfail']} Admit={e1['admit']}%", flush=True)
    print(f"  tool-selection: exact-match={100*exact:.1f}% jaccard={jacc:.3f} (n_correct={len(corr)})", flush=True)
    print(f"  rows={len(rows)}", flush=True)

    summary = {"provider": args.provider, "model": args.model, "mode": "selection", "log_path": path,
               "n_tasks": len(entries), "n_rows": len(rows), "llm_failed": failed,
               "e1": e1, "exact_match": round(100*exact, 2), "jaccard": round(jacc, 4),
               "elapsed_min": round((time.time()-t0)/60, 1)}
    out = os.path.join("scratch", f"xvendor_sel_{args.tag or _slug(args.model)}.json")
    json.dump(summary, open(out, "w"), indent=2)
    print(f"Summary -> {out}", flush=True)


if __name__ == "__main__":
    main()
