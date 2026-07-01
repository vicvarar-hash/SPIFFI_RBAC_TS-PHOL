"""ABAC firing distribution for the simplified 6-rule set (rules-as-data).

Runs the isolated Python ABAC engine over every (task, persona) pair and tallies
which deny rule fires. Confirms each of the six rules is live (no dead rules) and
shows the layer's deterministic contribution. Python-only (no OPA), so it is fast.
"""
import os, sys
from collections import Counter
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import replay_service as rs
from app.services.experiment_config import PERSONAS
from app.services.normalization import normalize_mcp_name
from app.loaders.astra_loader import load_astra_dataset
from app.loaders.mcp_loader import load_mcp_personas


def main():
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    mcp_personas, _ = load_mcp_personas("mcp_servers")
    rbac_pol, abac_pol, tsphol_pol = rs.baseline_policies()
    engines = rs._engines_from_policies(mcp_personas, rbac_pol, abac_pol, tsphol_pol)

    fired = Counter()
    denials = 0
    evals = 0
    for t in tasks:
        tools, mcps = list(t.candidate_tools), list(t.candidate_mcp)
        dom = normalize_mcp_name(t.groundtruth_mcp[0]) if t.groundtruth_mcp else None
        for pk in PERSONAS:
            res = rs._eval(engines["abac"], pk, tools, mcps, t.task, "validation", task_domain=dom)
            evals += 1
            if res.final_decision in rs.DENY_STATES:
                denials += 1
                ctx = (res.context or {}).get("abac_baseline", {})
                fired[ctx.get("matched_rule", "?")] += 1

    rs._release_engines(engines)
    print("evaluations: %d   ABAC denials: %d (%.1f%%)" % (evals, denials, 100.0 * denials / evals))
    print("\nfiring distribution (matched rule on DENY):")
    for rid, c in fired.most_common():
        print("   %-42s %5d" % (rid, c))
    # confirm liveness of every configured rule
    from app.services.abac_rule_service import ABACRuleService
    configured = [r["id"] for r in ABACRuleService().get_all()]
    dead = [r for r in configured if r not in fired]
    print("\nconfigured rules: %d   live: %d   dead: %s"
          % (len(configured), len(configured) - len(dead), dead or "none"))


if __name__ == "__main__":
    main()
