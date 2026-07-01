import sys, json
sys.path.insert(0, '.')
from app.services.experiment_runner import build_engine_from_policies
from app.services.experiment_config import EXPERIMENT_MAP, PERSONAS
from app.services.normalization import normalize_mcp_name
from app.loaders.mcp_loader import load_mcp_personas
from app.services.tsphol_interpreter import TSPHOLInterpreter

TASK_IDX = 243
PERSONA = 'incident_agent'

astra = json.load(open('datasets/astra_03_tools.json', encoding='utf-8'))
tasks = astra['tasks'] if isinstance(astra, dict) and 'tasks' in astra else astra
task = tasks[TASK_IDX]

mcp_personas, _ = load_mcp_personas('mcp_servers')
engine = build_engine_from_policies(EXPERIMENT_MAP['E3'].get_policies(), mcp_personas)

spiffe = PERSONAS[PERSONA]['spiffe_id']
gt_tools = task['input']['tools']; gt_mcps = task['input']['mcp_servers']
task_text = task['input']['task']; match_tag = task.get('match_tag')
mcp_filter = gt_mcps[0] if gt_mcps else 'All'
llm_out = {'_mode': 'validation', 'issue_codes': [], 'is_valid': True,
           'expected_domain': normalize_mcp_name(gt_mcps[0]) if gt_mcps else 'uncertain', 'id_source': 'Replay'}

pre = engine.pre_llm_check(spiffe, gt_mcps, gt_tools)
res = engine.evaluate(pre_llm_result=pre, caller_spiffe_id=spiffe, mcps=gt_mcps, tools=gt_tools,
                      llm_outputs=llm_out, task_text=task_text, mode='validation', mcp_filter=mcp_filter)
ctx = res.context
P = ctx.get('tsphol_predicate_set', {})

print('='*78)
print('STEP 0 — RAW INPUTS')
print('='*78)
print('Persona     :', PERSONA, '(', spiffe, ')')
print('match_tag   :', match_tag)
print('Task text   :', task_text)
print('Candidate MCPs :', gt_mcps)
print('Candidate tools:', gt_tools)

print('\n' + '='*78)
print('STEP 1 — FACT EXTRACTION (how predicates are computed)')
print('='*78)
ac = ctx.get('alignment_components', {})
print('Domain inference : expected=%r  actual=%r  -> match=%s (score %.1f)' % (
    P.get('TaskDomainExpected'), P.get('BundleDomainActual'),
    P.get('TaskDomainExpected') == P.get('BundleDomainActual'), ac.get('domain_score', 0)))
print('Capability ontology:')
print('   required caps (from task intent):', sorted(ctx.get('all_required_capabilities', [])))
print('   has caps (expanded from tools)  :', sorted(ctx.get('all_has_capabilities', [])))
print('   missing (required - has)        :', sorted(set(ctx.get('all_required_capabilities', [])) - set(ctx.get('all_has_capabilities', []))))
print('   CapabilityCoverageScore         : %.3f   (cap alignment component %.3f)' % (
    P.get('CapabilityCoverageScore', -1), ac.get('capability_score', 0)))
print('   HardCapabilityMissing           :', P.get('HardCapabilityMissing'), '->', P.get('MissingHardCapabilities'))
print('Semantic score   : %.3f' % ac.get('semantic_score', 0))
print('ALIGNMENT  = 0.4*%.2f(domain) + 0.4*%.2f(cap) + 0.2*%.2f(sem) = %.3f' % (
    ac.get('domain_score', 0), ac.get('capability_score', 0), ac.get('semantic_score', 0),
    P.get('TaskAlignmentScore', 0)))
print('Tool aggregates  : Write=%s Read=%s ReadBeforeWrite=%s Delete=%s MultiDomain=%s Risk=%s' % (
    P.get('ContainsWrite'), P.get('ContainsRead'), P.get('ContainsReadBeforeWrite'),
    P.get('ContainsDelete'), P.get('MultiDomain'), P.get('HighestRiskLevel')))

print('\n' + '='*78)
print('STEP 2 — PREDICATE SET handed to the interpreter (key facts)')
print('='*78)
keys = ['TaskDomainExpected','BundleDomainActual','TaskBundleDomainMismatch','AlignmentEvaluated',
        'TaskAlignmentScore','SelectionToleranceActive','CapabilityCoverageScore','HardCapabilityMissing',
        'ContainsWrite','ContainsRead','ContainsReadBeforeWrite','ContainsDelete','MultiDomain',
        'HighestRiskLevel','CriticalValidationFailure','BundleIrrelevantToTask']
for k in keys:
    print('   %-28s = %r' % (k, P.get(k)))

print('\n' + '='*78)
print('STEP 3 — RULE EXECUTION (priority order; first DENY short-circuits)')
print('='*78)
interp = TSPHOLInterpreter()
rules = sorted(engine.tsphol_svc.get_all(), key=lambda r: r.get('priority', 0), reverse=True)
short_circuited = False
decider = None
for r in rules:
    name = r.get('rule_name'); action = r.get('then', 'ALLOW'); pri = r.get('priority', 0)
    triggered, reason = interp.evaluate_conditions(r.get('if', []), dict(P), set())
    if short_circuited:
        status = 'SKIPPED (short-circuited)'
    elif triggered and action.upper() == 'DENY':
        status = '>>> FIRES -> DENY (DECIDER) <<<'; short_circuited = True; decider = name
    elif triggered and action.upper() == 'ALLOW':
        status = 'matched (ALLOW tag, no stop)'
    else:
        status = 'not triggered'
    print('  [p%3d] %-34s %-5s | %s' % (pri, name, action, status))
    if triggered and not short_circuited or (triggered and decider == name):
        print('         reason: %s' % reason)

print('\n' + '='*78)
print('STEP 4 — FINAL DECISION')
print('='*78)
print('Decider rule    :', decider)
print('tsphol_state    :', res.evaluation_states.get('tsphol'))
print('final_decision  :', res.final_decision, '(DECEPTION_ROUTED = a DENY routed to a honeypot)')
print('derived facts   :', ctx.get('tsphol_derived_predicates'))
print('engine summary  :', ctx.get('tsphol_summary'))
