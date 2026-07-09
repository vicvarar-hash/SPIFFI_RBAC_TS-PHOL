"""Cross-vendor validation run with a non-OpenAI model.

Produces a Claude validation llm-inference log (LLM judges the ASTRA candidate bundle),
then replays it through the current agnostic engine to report E1 (det, model-independent),
E4 (Claude LLM-only), and FULL (det + Claude verdict gate).

Usage:
  python scratch/run_claude_validation.py --limit 20            # pilot: infer only, no save
  python scratch/run_claude_validation.py --model claude-sonnet-4-6   # full run, save + replay
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_env():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            m = line.strip()
            if not m or m.startswith("#") or "=" not in m:
                continue
            k, v = m.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    load_env()
    from app.loaders.astra_loader import load_astra_dataset
    from app.loaders.mcp_loader import load_mcp_personas
    from app.services.llm_inference_producer import produce_inference_log, default_log_path
    from app.services.llm_inference_log import save_log

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    print(f"ANTHROPIC key present: {bool(api_key)} (len={len(api_key)})", flush=True)

    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
    personas, _ = load_mcp_personas("mcp_servers")
    print(f"tasks={len(tasks)} personas={len(personas)} model={args.model}", flush=True)

    run_tasks = tasks[: args.limit] if args.limit else tasks
    done = {"n": 0}

    def cb(ev):
        done["n"] += 1
        if done["n"] % 25 == 0:
            print(f"  ... {done['n']} tasks inferred", flush=True)

    print(f"Producing validation log over {len(run_tasks)} tasks ...", flush=True)
    log = produce_inference_log(
        run_tasks, personas,
        model=args.model, provider="anthropic", api_key=api_key,
        mode="validation", progress_cb=cb,
    )
    entries = log.get("tasks", [])
    failed = sum(1 for t in entries if t.get("llm_failed"))
    valid_true = sum(1 for t in entries if t.get("is_valid") is True)
    valid_false = sum(1 for t in entries if t.get("is_valid") is False)
    print(f"\nINFERRED entries={len(entries)} failed={failed} "
          f"is_valid True={valid_true} False={valid_false}", flush=True)
    print("sample:", json.dumps(entries[:3], separators=(",", ":"))[:400], flush=True)

    if args.limit:
        print("\n[pilot] not saving / not replaying. Re-run without --limit for the full run.", flush=True)
        return

    path = save_log(default_log_path(log), log)
    print(f"\nSaved log -> {path}", flush=True)

    # Replay through the agnostic engine
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
            if not legit and not allow: tp += 1
            elif legit and not allow:   fp += 1
            elif legit and allow:       tn += 1
            else:                       fn += 1
        f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0
        sf = fn / (tp + fn) if (tp + fn) else 0
        adm = tn / (tn + fp) if (tn + fp) else 0
        return f1, sf, 100 * adm
    det = lambda x: x.rbac_deny or x.abac_deny or x.tsphol_deny
    e4 = lambda x: x.llm_valid is False
    full = lambda x: det(x) or (x.llm_valid is False)
    for name, d in [("E1 (det, model-indep)", det), ("E4 (Claude LLM-only)", e4), ("FULL (det+gate)", full)]:
        f1, sf, adm = metr(d)
        print(f"  {name:24s} F1={f1:.3f} SecFail={sf:.3f} Admit={adm:.1f}%", flush=True)
    print(f"\nrows={len(rows)}", flush=True)


if __name__ == "__main__":
    main()
