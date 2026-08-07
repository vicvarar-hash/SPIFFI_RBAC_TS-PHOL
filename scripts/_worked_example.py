"""Worked-example verifier for the paper's tab:worked (the A->D short-circuit walk).

Runs the FULL PALADIN pipeline (E1: RBAC + ABAC + TRAC) for the incident persona on a
single incident-response task, across several candidate tool bundles, and prints the TRUE
per-stage verdict, denial source, ABAC matched rule, and TRAC decider for each — so the
paper's worked example uses real numbers, not illustrative ones.

Run: python scripts/_worked_example.py
"""
import sys, json
sys.path.insert(0, '.')
from app.services.experiment_runner import build_engine_from_policies
from app.services.experiment_config import EXPERIMENT_MAP, PERSONAS, LEGITIMATE_PAIRINGS
from app.services.normalization import normalize_mcp_name
from app.loaders.mcp_loader import load_mcp_personas
from app.services.task_domain_classifier import domain_scores, topk_domains, infer_task_domain

PERSONA = 'incident_agent'

# The advisor's paraphrased worked-example task (crisp, paper-ready) ...
TAU_ADVISOR = ("Investigate why the checkout service is showing high request latency and a "
               "spike in 5xx error responses over the last hour.")
# ... and the nearest REAL ASTRA rows, for a leak-free cross-check of the domain inference.
ASTRA_IDXS = [455, 723, 210]

mcp_personas, _ = load_mcp_personas('mcp_servers')
engine = build_engine_from_policies(EXPERIMENT_MAP['E1'].get_policies(), mcp_personas)
spiffe = PERSONAS[PERSONA]['spiffe_id']
attrs = PERSONAS[PERSONA]['attributes']

entitled = sorted(LEGITIMATE_PAIRINGS.get(PERSONA, []))

print('='*80)
print('PERSONA:', PERSONA, spiffe)
print('  attributes :', attrs)
print('  RBAC-entitled domains:', entitled)
print('='*80)


def run_bundle(label, tools, mcps, task_text):
    pre = engine.pre_llm_check(spiffe, mcps, tools)
    llm_out = {'_mode': 'validation', 'issue_codes': [], 'is_valid': True,
               'expected_domain': 'uncertain', 'id_source': 'Replay'}
    res = engine.evaluate(pre_llm_result=pre, caller_spiffe_id=spiffe, mcps=mcps, tools=tools,
                          llm_outputs=llm_out, task_text=task_text, mode='validation',
                          mcp_filter='All')
    ctx = res.context
    st = res.evaluation_states
    P = ctx.get('tsphol_predicate_set', {})
    abac = ctx.get('abac_baseline', {}) or {}
    rbac = ctx.get('rbac_evaluation', {}) or {}
    print('\n--- BUNDLE %s : %s' % (label, mcps))
    print('    tools           :', tools)
    print('    states          : identity=%s transport=%s rbac=%s abac=%s tsphol=%s' % (
        st.get('identity'), st.get('transport'), st.get('rbac'), st.get('abac'), st.get('tsphol')))
    print('    FINAL DECISION  : %s   (denial_source=%s)' % (res.final_decision, res.denial_source))
    print('    reason          :', res.reason)
    if st.get('rbac') == 'DENY':
        print('    RBAC matched    :', rbac.get('matched_rule'), '|', rbac.get('reason'))
    if st.get('abac') == 'DENY':
        print('    ABAC matched    :', abac.get('matched_rule'), '|', abac.get('failure_reason'))
    # TRAC diagnostics (only meaningful if we reached TRAC)
    if st.get('rbac') == 'ALLOW' and st.get('abac') == 'ALLOW':
        print('    TRAC expected_domain=%r actual_domain=%r' % (
            P.get('TaskDomainExpected'), P.get('BundleDomainActual')))
        print('    TRAC HardCapabilityMissing=%r missing=%r' % (
            P.get('HardCapabilityMissing'), P.get('MissingHardCapabilities')))
        print('    TRAC BundleIrrelevantToTask=%r  ContainsWrite=%r ContainsDelete=%r' % (
            P.get('BundleIrrelevantToTask'), P.get('ContainsWrite'), P.get('ContainsDelete')))
        print('    TRAC derived    :', ctx.get('tsphol_derived_predicates'))
    return res


# ── domain inference (the BM25 numbers for the paper) ───────────────────────────
def show_domains(task_text, label):
    print('\n[DOMAIN INFERENCE] %s' % label)
    print('  task:', task_text[:100])
    all_sc = domain_scores(task_text)                       # full 8-domain catalog (allowed=None)
    ent_sc = domain_scores(task_text, allowed=entitled)     # restricted to persona's entitled MCPs
    def top(d):
        return sorted(d.items(), key=lambda kv: -kv[1])[:4]
    print('  BM25 over ALL domains     :', top(all_sc))
    print('  BM25 over ENTITLED domains:', top(ent_sc))
    print('  infer_task_domain(all)    :', infer_task_domain(task_text))
    print('  infer_task_domain(entitled):', infer_task_domain(task_text, allowed=entitled))


astra = json.load(open('datasets/astra_03_tools.json', encoding='utf-8'))
tasks = astra['tasks'] if isinstance(astra, dict) and 'tasks' in astra else astra

show_domains(TAU_ADVISOR, 'ADVISOR PARAPHRASE (paper tau)')
for i in ASTRA_IDXS:
    show_domains(tasks[i]['input']['task'], 'ASTRA #%d (gt_mcps=%s)' % (i, tasks[i]['input']['mcp_servers']))

print('\n' + '='*80)
print('FOUR-BUNDLE WALK on tau (advisor paraphrase), incident persona, E1 full pipeline')
print('='*80)

TAU = TAU_ADVISOR
# A: in-domain grafana reads -> expect ALLOW
run_bundle('A', ['find_slow_requests', 'find_error_pattern_logs', 'list_incidents'], ['grafana'], TAU)
# B: adds an unentitled stripe tool -> expect RBAC DENY (stripe not in incident's entitlements)
run_bundle('B', ['find_slow_requests', 'create_refund'], ['grafana', 'stripe'], TAU)
# C candidates: entitled-domain (atlassian) writes/destructive -> which one does prod ABAC deny?
run_bundle('C1_add_comment', ['jira_add_comment'], ['atlassian'], TAU)
run_bundle('C2_delete_issue', ['jira_delete_issue'], ['atlassian'], TAU)
run_bundle('C3_update_issue', ['jira_update_issue'], ['atlassian'], TAU)
# D: entitled, read-only atlassian bundle, irrelevant to a grafana task -> expect TRAC DENY
run_bundle('D', ['jira_search', 'jira_get_issue'], ['atlassian'], TAU)
