"""Provider-general cross-vendor validation run (full ASTRA set, no subset).

Generalizes scratch/run_claude_validation.py to any backend (anthropic / google /
openai / azure_foundry). Runs the LLM validator ONCE per task over the full ASTRA
corpus, saves an llm_inference_v1 log, then replays it through the current agnostic
engine to report E1 (deterministic floor, model-independent), E4 (LLM-only), and
FULL (floor + the model's own verdict gate) — scored identically to the paper.

A compact JSON summary is written to scratch/xvendor_<tag>.json for table assembly.

Usage:
  python scratch/run_crossvendor_validation.py --provider anthropic --model claude-opus-4-8
  python scratch/run_crossvendor_validation.py --provider google    --model gemini-2.5-pro
  python scratch/run_crossvendor_validation.py --provider anthropic --model claude-sonnet-4-6 --limit 5   # pilot
"""
import os
import sys
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ENV_BY_PROVIDER = {
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "azure_foundry": "AZURE_FOUNDRY_API_KEY",
}


def load_env():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            m = line.strip()
            if not m or m.startswith("#") or "=" not in m:
                continue
            k, v = m.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _slug(s):
    import re
    return re.sub(r"[^A-Za-z0-9]+", "-", str(s or "")).strip("-").lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True,
                    choices=["anthropic", "google", "openai", "azure_foundry"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int, default=None,
                    help="Pilot: infer only this many tasks, no save/replay.")
    ap.add_argument("--tag", default=None,
                    help="Summary file tag; defaults to slug(model).")
    args = ap.parse_args()

    load_env()
    from app.loaders.astra_loader import load_astra_dataset
    from app.loaders.mcp_loader import load_mcp_personas
    from app.services.llm_inference_producer import produce_inference_log, default_log_path
    from app.services.llm_inference_log import save_log

    env_var = _ENV_BY_PROVIDER[args.provider]
    api_key = os.environ.get(env_var, "")
    print(f"[{args.provider}/{args.model}] {env_var} present: {bool(api_key)} (len={len(api_key)})", flush=True)
    if not api_key:
        print(f"ERROR: {env_var} not set", flush=True)
        sys.exit(2)

    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    personas, _ = load_mcp_personas("mcp_servers")
    print(f"tasks={len(tasks)} personas={len(personas)} model={args.model}", flush=True)

    run_tasks = tasks[: args.limit] if args.limit else tasks
    t0 = time.time()
    done = {"n": 0}

    def cb(ev):
        done["n"] += 1
        if done["n"] % 50 == 0:
            dt = time.time() - t0
            rate = done["n"] / dt if dt else 0
            eta = (len(run_tasks) - done["n"]) / rate if rate else 0
            print(f"  ... {done['n']}/{len(run_tasks)} inferred "
                  f"({rate:.2f}/s, ETA {eta/60:.1f} min)", flush=True)

    print(f"Producing validation log over {len(run_tasks)} tasks ...", flush=True)
    log = produce_inference_log(
        run_tasks, personas,
        model=args.model, provider=args.provider, api_key=api_key,
        mode="validation", progress_cb=cb,
    )
    entries = log.get("tasks", [])
    failed = sum(1 for t in entries if t.get("llm_failed"))
    vt = sum(1 for t in entries if t.get("is_valid") is True)
    vf = sum(1 for t in entries if t.get("is_valid") is False)
    print(f"\nINFERRED entries={len(entries)} failed={failed} "
          f"is_valid True={vt} False={vf} in {(time.time()-t0)/60:.1f} min", flush=True)

    if args.limit:
        print("\n[pilot] not saving / not replaying. Re-run without --limit for the full run.", flush=True)
        print("sample:", json.dumps(entries[:3], separators=(",", ":"))[:500], flush=True)
        return

    path = save_log(default_log_path(log), log)
    print(f"\nSaved log -> {path}", flush=True)

    # Replay through the agnostic engine — identical settings to the paper headline.
    from app.services import replay_service as rs
    from app.services import tool_relevance as trel
    trel.RESCUE_RELEVANCE = 4.0
    rows, _, _ = rs.replay_experiment(path, tasks, experiment="E1",
                                      limit=None, policies=rs.baseline_policies())

    def metr(deny):
        tp = fp = tn = fn = 0
        for x in rows:
            legit = x.is_legitimate
            allow = not deny(x)
            if not legit and not allow:
                tp += 1
            elif legit and not allow:
                fp += 1
            elif legit and allow:
                tn += 1
            else:
                fn += 1
        f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0
        sf = fn / (tp + fn) if (tp + fn) else 0
        adm = tn / (tn + fp) if (tn + fp) else 0
        return {"f1": round(f1, 4), "secfail": round(sf, 4), "admit": round(100 * adm, 2),
                "tp": tp, "fp": fp, "tn": tn, "fn": fn}

    det = lambda x: x.rbac_deny or x.abac_deny or x.tsphol_deny
    e4 = lambda x: x.llm_valid is False
    full = lambda x: det(x) or (x.llm_valid is False)
    res = {"E1": metr(det), "E4": metr(e4), "FULL": metr(full)}
    for name in ("E1", "E4", "FULL"):
        m = res[name]
        print(f"  {name:5s} F1={m['f1']:.3f} SecFail={m['secfail']:.3f} Admit={m['admit']:.1f}%", flush=True)
    print(f"\nrows={len(rows)}", flush=True)

    tag = args.tag or _slug(args.model)
    summary = {
        "provider": args.provider, "model": args.model, "log_path": path,
        "n_tasks": len(entries), "n_rows": len(rows), "llm_failed": failed,
        "e1": res["E1"], "e4": res["E4"], "full": res["FULL"],
        "elapsed_min": round((time.time() - t0) / 60, 1),
    }
    out = os.path.join("scratch", f"xvendor_{tag}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary -> {out}", flush=True)


if __name__ == "__main__":
    main()
