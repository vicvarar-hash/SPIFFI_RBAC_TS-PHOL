"""Compute clean TEST-only metrics, excluding train-leaked rows."""
import json, sys
from pathlib import Path
from collections import defaultdict, Counter
sys.path.insert(0, str(Path.cwd()))

from app.services.split_service import load_or_build_split, _task_fingerprint

tasks = json.load(open(r'datasets\astra_03_tools.json', 'r', encoding='utf-8'))
split = load_or_build_split(tasks, ratio=0.7, seed=42)
train_fps = set(split.train_fingerprints)
test_fps = set(split.test_fingerprints)
other_fps = set(split.other_fingerprints)

# Reconstruct: which raw tasks the runner actually evaluated (filter = test|other)
filter_set = test_fps | other_fps
filtered_tasks = [t for t in tasks if _task_fingerprint(t) in filter_set]
print(f'runner saw {len(filtered_tasks)} raw tasks')

# Map runner's task_idx -> raw task (runner uses enumerate order)
idx_to_task = {i: t for i, t in enumerate(filtered_tasks)}

# Load run + dedupe
d = json.load(open(r'datasets\experiment_logs\run_20260527_172305_llm_gpt-4o.json', 'r', encoding='utf-8'))
rows = d['experiments']['E1']['rows']
seen = {}
for r in rows:
    if r['task_idx'] not in seen:
        seen[r['task_idx']] = r

# Tag each row by its TRUE partition based on (fp, match_tag)
def true_partition(t):
    fp = _task_fingerprint(t)
    tag = t.get('match_tag') or 'null'
    if tag == 'correct':
        if fp in train_fps: return 'TRAIN-correct (LEAKED)'
        if fp in test_fps:  return 'TEST-correct (clean)'
        return 'correct-unclassified'
    # wrong/null
    return f'OTHER-{tag}'

bucket = defaultdict(list)
for idx, r in seen.items():
    t = idx_to_task.get(idx)
    if t is None:
        bucket['NO-MATCH'].append(r)
        continue
    bucket[true_partition(t)].append(r)

def overlap(r):
    return len(set(r['selected_tools']) & set(r['groundtruth_tools']))

print()
print(f"{'partition':<28} {'N':>4} {'exact%':>7} {'≥2/3%':>7} {'≥1/3%':>7} {'sameMCP%':>9} {'avgJacc':>8}")
print('-' * 78)
for part in sorted(bucket.keys()):
    items = bucket[part]
    n = len(items)
    if n == 0: continue
    exact = sum(1 for r in items if r['tool_match'])
    ge2 = sum(1 for r in items if overlap(r) >= 2)
    ge1 = sum(1 for r in items if overlap(r) >= 1)
    same_mcp = sum(1 for r in items
                   if r['selected_mcps'] and r['groundtruth_mcps']
                   and r['selected_mcps'][0] == r['groundtruth_mcps'][0])
    avg_j = sum(r['tool_jaccard'] for r in items) / n
    print(f'{part:<28} {n:>4} {100*exact/n:>6.1f}% {100*ge2/n:>6.1f}% {100*ge1/n:>6.1f}% {100*same_mcp/n:>8.1f}% {avg_j:>8.3f}')

# Per-MCP for clean TEST only
print()
print('=== Clean TEST cohort — per MCP ===')
test_items = bucket.get('TEST-correct (clean)', [])
by_mcp = defaultdict(list)
for r in test_items:
    by_mcp[r['domain']].append(r)
print(f"{'mcp':<18} {'N':>4} {'exact%':>7} {'≥2/3%':>7} {'≥1/3%':>7} {'sameMCP%':>9}")
for mcp, items in sorted(by_mcp.items(), key=lambda x: -len(x[1])):
    n = len(items)
    exact = sum(1 for r in items if r['tool_match'])
    ge2 = sum(1 for r in items if overlap(r) >= 2)
    ge1 = sum(1 for r in items if overlap(r) >= 1)
    same_mcp = sum(1 for r in items if r['selected_mcps'] and r['groundtruth_mcps'] and r['selected_mcps'][0] == r['groundtruth_mcps'][0])
    print(f'{mcp:<18} {n:>4} {100*exact/n:>6.1f}% {100*ge2/n:>6.1f}% {100*ge1/n:>6.1f}% {100*same_mcp/n:>8.1f}%')
