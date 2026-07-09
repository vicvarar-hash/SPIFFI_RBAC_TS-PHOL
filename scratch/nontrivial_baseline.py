"""Non-trivial baselines for TRAC (deterministic, no API).

Comparing the stack only to "LLM alone" is a weak baseline. Is TRAC's
drop-one marginal the *task-relational axis*, or would ANY extra denial mechanism at a matched
operating point do as well? Two baselines answer this on the model-invariant validation floor
(gpt-4o log; the deterministic floor is identical across models):

  (1) VOLUME-MATCHED RANDOM DENIER. On the RBAC AND ABAC-approved set (the only place TRAC acts),
      compare TRAC's denials to a random denier that denies the SAME number of bundles. If TRAC's
      denial *precision* (true catches / denials) beats the base rate (what random achieves), TRAC's
      denials are informative, not volume. We report the expected random outcome analytically.

  (2) ORACLE-DOMAIN capability_coverage. Re-run the identical TRAC rules with the task domain set
      from the gold MCP (``domain_source="gold"``) instead of leak-free BM25. This is the optimistic
      ceiling: if oracle-domain TRAC has a far lower false-block at comparable SecFail, the ~56%
      false-block is an artefact of imperfect BM25 inference, not of the task-relational axis itself.
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
VAL_LOG = "20260613005419_gpt-4o_validation.json"


def floor_metrics(rows):
    tp = fp = tn = fn = 0
    for x in rows:
        legit = x.is_legitimate
        allow = not (x.rbac_deny or x.abac_deny or x.tsphol_deny)
        if not legit and not allow: tp += 1
        elif legit and not allow:   fp += 1
        elif legit and allow:       tn += 1
        else:                       fn += 1
    return dict(secfail=fn / (tp + fn) if (tp + fn) else 0.0,
                false_block=fp / (fp + tn) if (fp + tn) else 0.0,
                f1=2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)


def approved_analysis(rows):
    """TRAC vs a volume-matched random denier on the RBAC & ABAC-approved set."""
    A = [x for x in rows if not x.rbac_deny and not x.abac_deny]
    I = [x for x in A if not x.is_legitimate]   # illegitimate reaching TRAC
    L = [x for x in A if x.is_legitimate]        # legitimate reaching TRAC
    denied = [x for x in A if x.tsphol_deny]
    M = len(denied)
    catch = sum(1 for x in denied if not x.is_legitimate)
    block = sum(1 for x in denied if x.is_legitimate)
    base_rate = len(I) / len(A) if A else 0.0            # random denier precision
    trac_prec = catch / M if M else 0.0
    # SecFail among approved-illegit (fraction of true violations that escape the last layer):
    sf_trac = (len(I) - catch) / len(I) if I else 0.0
    # Volume-matched random denier: deny M random approved -> expected catch = M*base_rate.
    exp_catch_rand = M * base_rate
    sf_rand = (len(I) - exp_catch_rand) / len(I) if I else 0.0
    fb_trac = block / len(L) if L else 0.0
    fb_rand = (M * (1 - base_rate)) / len(L) if L else 0.0
    return dict(approved=len(A), illeg=len(I), legit=len(L), trac_denials=M,
                base_rate=round(base_rate, 4), trac_precision=round(trac_prec, 4),
                lift=round(trac_prec / base_rate, 2) if base_rate else None,
                catch=catch, block=block, exp_catch_random=round(exp_catch_rand, 1),
                secfail_trac_on_approved=round(sf_trac, 4),
                secfail_random_on_approved=round(sf_rand, 4),
                falseblock_trac_on_approved=round(fb_trac, 4),
                falseblock_random_on_approved=round(fb_rand, 4))


def replay(domain_source):
    trel.RESCUE_RELEVANCE = 4.0
    trel.THRESHOLD = 1.0
    rows, _, _ = rs.replay_experiment(os.path.join(LL, VAL_LOG), tasks, experiment="E1",
                                      limit=None, policies=rs.baseline_policies(),
                                      domain_source=domain_source)
    return rows


if __name__ == "__main__":
    tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))

    print("=== (1) TRAC vs volume-matched random denier (shipped leak-free BM25) ===")
    rows_inf = replay("inferred")
    fm_inf = floor_metrics(rows_inf)
    aa = approved_analysis(rows_inf)
    print(f"  Full floor (BM25):  SecFail={fm_inf['secfail']:.4f}  false-block={fm_inf['false_block']:.4f}")
    print(f"  Approved set: n={aa['approved']} (illegit={aa['illeg']}, legit={aa['legit']})")
    print(f"  TRAC denials={aa['trac_denials']}  catch={aa['catch']}  block={aa['block'] if 'block' in aa else '-'}")
    print(f"  TRAC precision={aa['trac_precision']}  base rate (random)={aa['base_rate']}  LIFT={aa['lift']}x")
    print(f"  At matched denial volume: TRAC catches {aa['catch']} vs random ~{aa['exp_catch_random']}")
    print(f"  SecFail on approved-illegit:  TRAC={aa['secfail_trac_on_approved']}  random={aa['secfail_random_on_approved']}")
    print(f"  False-block on approved-legit: TRAC={aa['falseblock_trac_on_approved']}  random={aa['falseblock_random_on_approved']}")

    print("\n=== (2) Oracle-domain capability_coverage (optimistic ceiling; gold domain) ===")
    rows_gold = replay("gold")
    fm_gold = floor_metrics(rows_gold)
    print(f"  Oracle-domain floor: SecFail={fm_gold['secfail']:.4f}  false-block={fm_gold['false_block']:.4f}  F1={fm_gold['f1']:.3f}")
    print(f"  (vs leak-free BM25:  SecFail={fm_inf['secfail']:.4f}  false-block={fm_inf['false_block']:.4f}  F1={fm_inf['f1']:.3f})")

    json.dump({"bm25_floor": fm_inf, "oracle_floor": fm_gold, "approved_analysis": aa},
              open(os.path.join("scratch", "nontrivial_baseline.json"), "w"), indent=2)
    print("\nSaved -> scratch/nontrivial_baseline.json")
