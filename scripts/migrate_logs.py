"""Migrate every legacy ``experiments[E1..E4]`` log into ``llm_inference_v1``.

Reads ``datasets/experiment_logs/*.json``, converts each real-LLM run (skips pure
simulation logs), and writes the per-task LLM-inference record to
``datasets/llm_inference_logs/``. The Post-Experiment Lab consumes the new files;
no LLM calls are made and the original logs are left untouched.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath("."))

from app.services.llm_inference_log import migrate_experiment_log, save_log

SRC = os.path.join("datasets", "experiment_logs")
DST = os.path.join("datasets", "llm_inference_logs")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(s or "")).strip("-").lower()


def _ra_tag(ra: dict) -> str:
    if not isinstance(ra, dict) or ra.get("strategy") in (None, "none", ""):
        return ""
    k = ra.get("k")
    return f"_ra-{_slug(ra.get('strategy'))}" + (f"-k{k}" if k else "")


def main():
    os.makedirs(DST, exist_ok=True)
    paths = sorted(glob.glob(os.path.join(SRC, "*.json")))
    print(f"{len(paths)} legacy logs in {SRC}\n")
    done, skipped = [], []
    for p in paths:
        name = os.path.basename(p)
        try:
            with open(p, encoding="utf-8") as f:
                old = json.load(f)
        except Exception as e:
            skipped.append((name, f"unreadable: {e}"))
            continue
        if "experiments" not in old:
            skipped.append((name, "no experiments key"))
            continue
        if (old.get("inference_mode") == "simulation"
                or old.get("llm_model") in (None, "simulation")
                or "simulation" in name):
            skipped.append((name, "simulation (no real LLM)"))
            continue

        new = migrate_experiment_log(old, name)
        # source date prefix keeps chronological order + uniqueness
        m = re.search(r"(\d{8})_(\d{6})", name)
        stamp = (m.group(1) + m.group(2)) if m else "00000000000000"
        ra = new.get("retrieval") or {}
        out_name = f"{stamp}_{_slug(new['model'])}_{_slug(new['mode'])}{_ra_tag(ra)}.json"
        save_log(os.path.join(DST, out_name), new)
        n = len(new["tasks"])
        n_valid = sum(1 for t in new["tasks"] if t.get("is_valid") is not None)
        done.append((name, out_name, new["mode"], new["model"], n, n_valid,
                     ra.get("strategy", "none")))

    print(f"MIGRATED {len(done)}:")
    for src, dst, mode, model, n, nv, ra in done:
        print(f"  {model:22s} {mode:10s} ra={ra:10s} tasks={n:4d} verdicts={nv:4d}  -> {dst}")
    print(f"\nSKIPPED {len(skipped)}:")
    for name, why in skipped:
        print(f"  {name}: {why}")


if __name__ == "__main__":
    main()
