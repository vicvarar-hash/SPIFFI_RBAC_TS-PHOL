import json
import sys
from collections import Counter

def analyze_run(filepath):
    with open(filepath) as f:
        data = json.load(f)

    rows = data['experiments']['E1']['rows']
    total_rows = len(rows)
    personas = set(r['persona'] for r in rows)
    
    # Deduplicate: same LLM call reused across personas
    task_results = {}
    for r in rows:
        idx = r['task_idx']
        if idx not in task_results:
            task_results[idx] = r

    total = len(task_results)

    # Count exact tool matches
    exact_0 = exact_1 = exact_2 = exact_3 = 0
    for idx, r in task_results.items():
        selected = r['selected_tools']
        gt = list(r['groundtruth_tools'])
        matches = 0
        gt_remaining = list(gt)
        for tool in selected:
            if tool in gt_remaining:
                matches += 1
                gt_remaining.remove(tool)
        if matches == 0:
            exact_0 += 1
        elif matches == 1:
            exact_1 += 1
        elif matches == 2:
            exact_2 += 1
        elif matches >= 3:
            exact_3 += 1

    jaccards = [r['tool_jaccard'] for r in task_results.values()]
    avg_jaccard = sum(jaccards) / len(jaccards)
    
    mcp_correct = sum(1 for r in task_results.values()
                      if set(r['selected_mcps']) == set(r['groundtruth_mcps']))
    
    confs = [r['confidence'] for r in task_results.values() if r['confidence']]
    avg_conf = sum(confs) / len(confs) if confs else 0

    tool_matches = sum(1 for r in task_results.values() if r['tool_match'])

    # By category
    by_tag = {}
    for tag in ['correct', 'wrong', 'null']:
        subset = {k: v for k, v in task_results.items() if v['match_tag'] == tag}
        n = len(subset)
        if n == 0:
            continue
        tm = sum(1 for v in subset.values() if v['tool_match'])
        avg_j = sum(v['tool_jaccard'] for v in subset.values()) / n
        by_tag[tag] = {'n': n, 'exact_match': tm, 'jaccard': avg_j}

    return {
        'total_rows': total_rows,
        'unique_tasks': total,
        'personas': len(personas),
        'exact_3': exact_3, 'exact_2': exact_2, 'exact_1': exact_1, 'exact_0': exact_0,
        'avg_jaccard': avg_jaccard,
        'mcp_correct': mcp_correct,
        'mcp_pct': mcp_correct / total * 100,
        'avg_confidence': avg_conf,
        'tool_match_pct': tool_matches / total * 100,
        'by_tag': by_tag,
    }


# Compare two runs
run_old = 'datasets/experiment_logs/run_20260502_151424_llm_gpt-4o.json'
run_new = 'datasets/experiment_logs/run_20260505_123954_llm_gpt-4o.json'

print("Analyzing previous run (May 2)...")
old = analyze_run(run_old)
print("Analyzing new run (May 5)...")
new = analyze_run(run_new)

print()
print("=" * 70)
print("COMPARISON: May 2 vs May 5 (GPT-4o Selection Mode)")
print("=" * 70)
print()

def delta(new_v, old_v, fmt=".1f"):
    d = new_v - old_v
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:{fmt}}"

t = old['unique_tasks']
print(f"{'Metric':<25} {'May 2':>10} {'May 5':>10} {'Delta':>10}")
print("-" * 58)
print(f"{'3/3 (perfect)':<25} {old['exact_3']:>10} {new['exact_3']:>10} {delta(new['exact_3'], old['exact_3'], 'd'):>10}")
print(f"{'2/3 partial':<25} {old['exact_2']:>10} {new['exact_2']:>10} {delta(new['exact_2'], old['exact_2'], 'd'):>10}")
print(f"{'1/3 partial':<25} {old['exact_1']:>10} {new['exact_1']:>10} {delta(new['exact_1'], old['exact_1'], 'd'):>10}")
print(f"{'0/3 none':<25} {old['exact_0']:>10} {new['exact_0']:>10} {delta(new['exact_0'], old['exact_0'], 'd'):>10}")
print()

al1_old = old['exact_1'] + old['exact_2'] + old['exact_3']
al1_new = new['exact_1'] + new['exact_2'] + new['exact_3']
al2_old = old['exact_2'] + old['exact_3']
al2_new = new['exact_2'] + new['exact_3']

print(f"{'At least 1 correct':<25} {al1_old/t*100:>9.1f}% {al1_new/t*100:>9.1f}% {delta(al1_new/t*100, al1_old/t*100):>9}%")
print(f"{'At least 2 correct':<25} {al2_old/t*100:>9.1f}% {al2_new/t*100:>9.1f}% {delta(al2_new/t*100, al2_old/t*100):>9}%")
print(f"{'All 3 correct':<25} {old['exact_3']/t*100:>9.1f}% {new['exact_3']/t*100:>9.1f}% {delta(new['exact_3']/t*100, old['exact_3']/t*100):>9}%")
print()
print(f"{'MCP domain match':<25} {old['mcp_pct']:>9.1f}% {new['mcp_pct']:>9.1f}% {delta(new['mcp_pct'], old['mcp_pct']):>9}%")
print(f"{'Avg Jaccard':<25} {old['avg_jaccard']:>9.3f}  {new['avg_jaccard']:>9.3f}  {delta(new['avg_jaccard'], old['avg_jaccard'], '.3f'):>9}")
print(f"{'Avg Confidence':<25} {old['avg_confidence']:>9.3f}  {new['avg_confidence']:>9.3f}  {delta(new['avg_confidence'], old['avg_confidence'], '.3f'):>9}")
print()

print("BY CATEGORY:")
print(f"{'Category':<10} {'Metric':<18} {'May 2':>10} {'May 5':>10} {'Delta':>10}")
print("-" * 60)
for tag in ['correct', 'wrong', 'null']:
    o = old['by_tag'].get(tag, {})
    n = new['by_tag'].get(tag, {})
    on = o.get('n', 0)
    nn = n.get('n', 0)
    otm = o.get('exact_match', 0)
    ntm = n.get('exact_match', 0)
    oj = o.get('jaccard', 0)
    nj = n.get('jaccard', 0)
    print(f"{tag:<10} {'exact_match':<18} {otm:>10} {ntm:>10} {delta(ntm, otm, 'd'):>10}")
    print(f"{'':10} {'avg_jaccard':<18} {oj:>10.3f} {nj:>10.3f} {delta(nj, oj, '.3f'):>10}")

