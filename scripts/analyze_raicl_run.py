"""Per-cohort breakdown of the RA-ICL all-in-domain experiment."""
import json
from collections import defaultdict

PATH = r'datasets\experiment_logs\run_20260527_172305_llm_gpt-4o.json'

d = json.load(open(PATH, 'r', encoding='utf-8'))
rows = d['experiments']['E1']['rows']  # tool selection is identical across E1-E4

# Dedupe by task_idx (selection is per-task, replicated across personas)
seen = {}
for r in rows:
    if r['task_idx'] not in seen:
        seen[r['task_idx']] = r
print(f'unique tasks: {len(seen)}')

by_tag = defaultdict(list)
for r in seen.values():
    by_tag[r['match_tag'] or 'null'].append(r)

def overlap(r):
    return len(set(r['selected_tools']) & set(r['groundtruth_tools']))

hdr = f"{'tag':<10} {'N':>5} {'exact%':>7} {'>=2/3%':>7} {'>=1/3%':>7} {'sameMCP%':>9} {'avgJacc':>8}"
print()
print(hdr)
print('-' * len(hdr))
for tag, items in sorted(by_tag.items()):
    n = len(items)
    exact = sum(1 for r in items if r['tool_match'])
    ge2 = sum(1 for r in items if overlap(r) >= 2)
    ge1 = sum(1 for r in items if overlap(r) >= 1)
    same_mcp = sum(1 for r in items
                   if r['selected_mcps'] and r['groundtruth_mcps']
                   and r['selected_mcps'][0] == r['groundtruth_mcps'][0])
    avg_j = sum(r['tool_jaccard'] for r in items) / n if n else 0
    print(f'{tag:<10} {n:>5} {100*exact/n:>6.1f}% {100*ge2/n:>6.1f}% {100*ge1/n:>6.1f}% {100*same_mcp/n:>8.1f}% {avg_j:>8.3f}')

# Per-MCP breakdown for the test cohort (the apples-to-apples comparison vs baseline)
print()
print('=== TEST cohort only (correct-tagged, 30% holdout) — per MCP ===')
test_items = by_tag.get('correct', [])
by_mcp = defaultdict(list)
for r in test_items:
    by_mcp[r['domain']].append(r)
print(f"{'mcp':<18} {'N':>4} {'exact%':>7} {'>=2/3%':>7} {'sameMCP%':>9} {'avgJacc':>8}")
print('-' * 60)
for mcp, items in sorted(by_mcp.items(), key=lambda x: -len(x[1])):
    n = len(items)
    exact = sum(1 for r in items if r['tool_match'])
    ge2 = sum(1 for r in items if overlap(r) >= 2)
    same_mcp = sum(1 for r in items
                   if r['selected_mcps'] and r['groundtruth_mcps']
                   and r['selected_mcps'][0] == r['groundtruth_mcps'][0])
    avg_j = sum(r['tool_jaccard'] for r in items) / n if n else 0
    print(f'{mcp:<18} {n:>4} {100*exact/n:>6.1f}% {100*ge2/n:>6.1f}% {100*same_mcp/n:>8.1f}% {avg_j:>8.3f}')
