"""Regenerate the gpt-4o canonical row dumps with the tool-name normalization fix, then re-run the
structural-rule (action_coherence) analysis off the fresh rows. structural_rules.py reads
scratch/canonical_rows/val_gpt-4o_r4.json (offline), so that dump must be regenerated post-fix.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.loaders.astra_loader import load_astra_dataset
from app.services import replay_service as rs
from app.services import tool_relevance as trel

LL = os.path.join("datasets", "llm_inference_logs")
OUTDIR = os.path.join("scratch", "canonical_rows")
LOG = "20260613005419_gpt-4o_validation.json"
FIELDS = ("persona", "task_idx", "domain", "match_tag", "is_legitimate",
          "rbac_deny", "abac_deny", "tsphol_deny", "tsphol_rule", "llm_valid",
          "contains_write", "hard_missing", "tsphol_advisory_rules")
tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
trel.THRESHOLD = 1.0

for rescue in (4.0, 0.0):
    trel.RESCUE_RELEVANCE = rescue
    rows, _, _ = rs.replay_experiment(os.path.join(LL, LOG), tasks, experiment="E1",
                                      limit=None, policies=rs.baseline_policies())
    out = [{f: getattr(x, f, None) for f in FIELDS} for x in rows]
    path = os.path.join(OUTDIR, f"val_gpt-4o_r{int(rescue)}.json")
    json.dump(out, open(path, "w"), separators=(",", ":"))
    print(f"regenerated {path}  (n={len(out)}, rescue={rescue})", flush=True)

print("\n--- re-running structural_rules on fresh rows ---", flush=True)
import runpy
runpy.run_path(os.path.join("scratch", "structural_rules.py"), run_name="__main__")
