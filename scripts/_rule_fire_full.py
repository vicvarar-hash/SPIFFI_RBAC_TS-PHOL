import sys, json
sys.path.insert(0, '.')
from collections import Counter, defaultdict
from app.services.experiment_runner import build_engine_from_policies
from app.services.experiment_config import EXPERIMENT_MAP
from app.services.normalization import normalize_mcp_name
from app.loaders.mcp_loader import load_mcp_personas

astra = json.load(open('datasets/astra_03_tools.json', encoding='utf-8'))
tasks = astra['tasks'] if isinstance(astra, dict) and 'tasks' in astra else astra
N = len(tasks)

mcp_personas, _ = load_mcp_personas('mcp_servers')
engine = build_engine_from_policies(EXPERIMENT_MAP['E3'].get_policies(), mcp_personas)

# A neutral persona spiffe is fine: RBAC/ABAC are OPEN in E3, and TRAC facts
# are persona-independent in validation (bundle = ASTRA candidate).
SPIFFE = 'spiffe://demo.local/service/security'

def decider_rule(trace):
    """Return the rule that produced the DENY (first-firing), or None if allow."""
    denier = None
    for t in trace:
        if t.get('triggered') and str(t.get('action', '')).upper() == 'DENY':
            denier = t.get('rule')
            break
    return denier

# Replay each unique task once (decision is persona/model-independent in E3 validation)
per_task = {}   # task_idx -> (tsphol_state, decider_rule, match_tag)
rule_counter = Counter()
state_counter = Counter()
for i, task in enumerate(tasks):
    gt_tools = task['input']['tools']; gt_mcps = task['input']['mcp_servers']
    task_text = task['input']['task']; match_tag = task.get('match_tag', 'null')
    mcp_filter = gt_mcps[0] if gt_mcps else 'All'
    llm_out = {'_mode': 'validation', 'issue_codes': [], 'is_valid': True,
               'expected_domain': normalize_mcp_name(gt_mcps[0]) if gt_mcps else 'uncertain',
               'id_source': 'Replay'}
    pre_llm = engine.pre_llm_check(SPIFFE, gt_mcps, gt_tools)
    res = engine.evaluate(pre_llm_result=pre_llm, caller_spiffe_id=SPIFFE, mcps=gt_mcps, tools=gt_tools,
                          llm_outputs=llm_out, task_text=task_text, mode='validation', mcp_filter=mcp_filter)
    tsphol_state = res.evaluation_states.get('tsphol', 'N/A')
    rule = decider_rule(res.context.get('tsphol_logic_trace', []))
    per_task[i] = (tsphol_state, rule, match_tag)
    state_counter[tsphol_state] += 1
    rule_counter[rule if rule else '(ALLOW / no deny rule)'] += 1

print('=== Replay over %d unique tasks (E3, TRAC only, validation) ===' % N)
print('tsphol_state:', dict(state_counter))
deny_total = sum(v for k, v in rule_counter.items() if k != '(ALLOW / no deny rule)')
print('\nPer-rule firing (the deciding DENY rule):')
print(f"{'rule':40} {'count':>6} {'% of all':>9} {'% of denies':>12}")
for rule, c in rule_counter.most_common():
    pct_all = 100*c/N
    pct_den = 100*c/deny_total if (rule != '(ALLOW / no deny rule)' and deny_total) else 0
    print(f"{rule:40} {c:6d} {pct_all:8.1f}% {pct_den:11.1f}%")

# Validate reconstructed tsphol_state against each model's logged E3 rows
logs = {
 'gpt-3.5-turbo-16k': 'datasets/experiment_logs/run_20260613_141204_llm_gpt-35-turbo-16k_validation.json',
 'gpt-4o':           'datasets/experiment_logs/run_20260613_005419_llm_gpt-4o_validation.json',
 'gpt-5.4':          'datasets/experiment_logs/run_20260612_191843_llm_gpt-5_4_validation.json',
 'gemini-2.5-pro':   'datasets/experiment_logs/run_20260612_160439_llm_gemini-2_5-pro_validation.json',
}
print('\n=== Allow/deny + decider rule by match_tag (replay) ===')
by_tag = defaultdict(Counter)
allow_by_tag = defaultdict(lambda: [0, 0])  # tag -> [allow, total]
for i, (state, rule, tag) in per_task.items():
    allow_by_tag[tag][1] += 1
    if state == 'ALLOW':
        allow_by_tag[tag][0] += 1
    by_tag[tag][rule if rule else '(ALLOW)'] += 1
for tag in ('correct', 'wrong', 'null'):
    a, t = allow_by_tag[tag]
    print(f"  {tag:8} n={t:4d}  allow={a:3d} ({100*a/t:.1f}%)  deciders={dict(by_tag[tag])}")

def norm_state(s):
    return 'DENY' if s in ('DENY', 'DECEPTION_ROUTED') else ('ALLOW' if s == 'ALLOW' else s)
for m, p in logs.items():
    d = json.load(open(p, encoding='utf-8'))
    rows = d['experiments']['E3']['rows']
    match = tot = mism_tag = 0
    for r in rows:
        ti = r.get('task_idx')
        if ti is None or ti not in per_task:
            continue
        recon_state, _, recon_tag = per_task[ti]
        if recon_tag != r.get('match_tag'):
            mism_tag += 1
        tot += 1
        if norm_state(recon_state) == norm_state(r.get('tsphol_state')):
            match += 1
    print(f"  {m:20} rows={tot:5d}  state-match={100*match/tot:5.1f}%  (task_idx/tag mismatches={mism_tag})")
