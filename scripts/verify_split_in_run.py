"""Verify which split partition the evaluated tasks actually came from."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from app.services.split_service import load_or_build_split, _task_fingerprint

# Use the raw JSON directly (the runner sees raw dicts via the cache, but
# match_tag filter and fingerprinting work on either shape).
tasks = json.load(open(r'datasets\astra_03_tools.json', 'r', encoding='utf-8'))
split = load_or_build_split(tasks, ratio=0.7, seed=42)
train_fps = set(split.train_fingerprints)
test_fps = set(split.test_fingerprints)
other_fps = set(split.other_fingerprints)
print(f'Split fingerprints — train={len(train_fps)}, test={len(test_fps)}, other={len(other_fps)}')

# Load run
d = json.load(open(r'datasets\experiment_logs\run_20260527_172305_llm_gpt-4o.json', 'r', encoding='utf-8'))
rows = d['experiments']['E1']['rows']

# Build a {task_idx: task} map by re-running the filter the same way the runner does
# (we don't have fingerprints in rows directly, so reconstruct via dataset position).
# Actually we have selected_tools + domain + groundtruth which lets us match.
# Easier: compute fingerprint from (task_text, mcps) — but we don't have task_text in rows.
# We DO have groundtruth_tools, groundtruth_mcps, domain. Let's match against the dataset.
fp_to_task = {}
for t in tasks:
    fp_to_task[_task_fingerprint(t)] = t

# Dedupe rows by task_idx
seen = {}
for r in rows:
    if r['task_idx'] not in seen:
        seen[r['task_idx']] = r
print(f'unique task_idx in results: {len(seen)}')

# For each result, find matching task by groundtruth_tools+mcps and check partition
from collections import Counter
partition_counter = Counter()
matched = 0
unmatched_samples = []
for r in seen.values():
    # Reconstruct candidate fp by searching tasks with matching groundtruth + domain
    gt = (tuple(sorted(r['groundtruth_tools'])), r['domain'], r['match_tag'])
    found_partition = None
    for fp, t in fp_to_task.items():
        t_gt = sorted(t.get('expected_output', {}).get('tools') or [])
        t_mcps = t.get('input', {}).get('mcp_servers') or []
        t_tag = t.get('match_tag')
        if tuple(t_gt) == gt[0] and t_mcps and t_mcps[0] == gt[1] and t_tag == gt[2]:
            if fp in train_fps:
                found_partition = 'TRAIN'
            elif fp in test_fps:
                found_partition = 'TEST'
            elif fp in other_fps:
                found_partition = 'OTHER'
            else:
                found_partition = 'UNCLASSIFIED'
            break
    partition_counter[found_partition or 'NOT_FOUND'] += 1

print()
print('Partition of evaluated tasks:')
for p, c in partition_counter.most_common():
    print(f'  {p:<15} {c}')
