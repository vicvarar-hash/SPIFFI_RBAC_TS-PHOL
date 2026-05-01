"""
Generate the Access Decision Ground Truth Matrix.

For each (persona x task) combination, runs the full policy pipeline
deterministically and records the expected decision at each governance layer.

Output: datasets/access_decision_matrix.json
"""

import os
import sys
import json
import hashlib
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.experiment_config import (
    PERSONAS, LEGITIMATE_PAIRINGS, simulate_llm_output, ExperimentConfig,
)
from app.services.experiment_runner import build_engine_from_policies, cleanup_engine, WRITE_KEYWORDS
from app.services.normalization import normalize_mcp_name


def generate_matrix():
    """Generate the full access decision matrix."""

    dataset_path = os.path.join("datasets", "astra_03_tools.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    production_config = ExperimentConfig(
        name="matrix_gen", group="X", description="Matrix generation"
    )
    policies = production_config.get_policies()

    # Load MCP personas for the engine
    from app.loaders.mcp_loader import load_mcp_personas
    personas_list, _ = load_mcp_personas("mcp_servers")

    engine = build_engine_from_policies(policies, personas_list)

    persona_keys = sorted(PERSONAS.keys())
    matrix = []
    stats = defaultdict(int)

    total = len(persona_keys) * len(tasks)
    print(f"Generating matrix: {len(persona_keys)} personas x {len(tasks)} tasks = {total} rows")

    for p_idx, persona_key in enumerate(persona_keys):
        persona = PERSONAS[persona_key]
        spiffe_id = persona["spiffe_id"]
        print(f"\n[{p_idx+1}/{len(persona_keys)}] Processing {persona_key}...")

        for task_idx, task in enumerate(tasks):
            if task_idx % 200 == 0:
                print(f"  Task {task_idx}/{len(tasks)}...")

            tools = task["input"]["tools"]
            mcps = task["input"]["mcp_servers"]
            task_text = task["input"]["task"]
            match_tag = task.get("match_tag", "null")
            task_domain = normalize_mcp_name(mcps[0]) if mcps else "unknown"

            domain_authorized = task_domain in LEGITIMATE_PAIRINGS.get(persona_key, set())

            llm_out = simulate_llm_output(task, mode="selection", seed_extra=persona_key)
            confidence = llm_out["confidence"]
            mcp_filter = mcps[0] if mcps else "All"

            pre_llm = engine.pre_llm_check(spiffe_id, mcps, tools)

            result = engine.evaluate(
                pre_llm_result=pre_llm,
                caller_spiffe_id=spiffe_id,
                mcps=mcps,
                tools=tools,
                confidence=confidence,
                llm_outputs=llm_out,
                task_text=task_text,
                mode="selection",
                mcp_filter=mcp_filter,
            )

            states = result.evaluation_states or {}
            ctx = result.context or {}

            # Per-tool RBAC decisions
            rbac_trace = ctx.get("rbac_evaluation", {}).get("rbac_trace", [])
            tool_decisions = []
            for t_info in rbac_trace:
                tool_decisions.append({
                    "tool": t_info.get("tool", ""),
                    "mcp": t_info.get("mcp", ""),
                    "rbac": t_info.get("decision", "N/A"),
                    "rbac_rule": t_info.get("policy", ""),
                })

            # ABAC details
            abac_info = ctx.get("abac_baseline", {})
            abac_matched_rule = abac_info.get("matched_rule", "")

            # TS-PHOL details
            tsphol_summary = ctx.get("tsphol_summary", {})
            tsphol_triggered = tsphol_summary.get("triggered_rules", 0)

            # Capability coverage
            required_caps = ctx.get("task_required_capabilities", [])
            has_caps = ctx.get("has_capabilities", [])
            missing_caps = ctx.get("missing_capabilities", [])

            # All deny layers (not just first)
            deny_layers = []
            for layer in ["identity", "transport", "rbac", "abac", "tsphol"]:
                if states.get(layer) == "DENY":
                    deny_layers.append(layer)

            has_write = any(kw in t for t in tools for kw in WRITE_KEYWORDS)

            row = {
                "persona": persona_key,
                "task_idx": task_idx,
                "task_domain": task_domain,
                "match_tag": match_tag,
                "domain_authorized": domain_authorized,
                "has_write": has_write,
                "confidence": round(confidence, 4),
                # Layer decisions
                "expected_identity": states.get("identity", "N/A"),
                "expected_transport": states.get("transport", "N/A"),
                "expected_rbac": states.get("rbac", "N/A"),
                "expected_abac": states.get("abac", "N/A"),
                "expected_tsphol": states.get("tsphol", "N/A"),
                "expected_final": result.final_decision,
                # Deny attribution
                "first_deny_layer": result.denial_source,
                "all_deny_layers": deny_layers,
                # Per-tool RBAC
                "tool_decisions": tool_decisions,
                # ABAC detail
                "abac_matched_rule": abac_matched_rule,
                # TS-PHOL detail
                "tsphol_triggered_rules": tsphol_triggered,
                "tsphol_status": tsphol_summary.get("final_status", "N/A"),
                # Capability coverage
                "required_capabilities": required_caps,
                "has_capabilities": has_caps,
                "missing_capabilities": missing_caps,
                "capability_coverage": round(
                    len([c for c in required_caps if c in has_caps]) / len(required_caps), 4
                ) if required_caps else 1.0,
            }

            matrix.append(row)

            stats["total"] += 1
            stats[f"final_{result.final_decision}"] += 1
            if deny_layers:
                stats[f"deny_by_{deny_layers[0]}"] += 1
            stats[f"tag_{match_tag}"] += 1
            if domain_authorized:
                stats["domain_authorized"] += 1

    cleanup_engine(engine)

    # Policy version hash for reproducibility
    policy_files = ["rbac.yaml", "abac_rules.yaml", "tsphol_rules.yaml",
                    "domain_capability_ontology.json"]
    policy_hashes = {}
    for pf in policy_files:
        path = os.path.join("policies", pf)
        if os.path.exists(path):
            with open(path, "rb") as f:
                policy_hashes[pf] = hashlib.sha256(f.read()).hexdigest()[:12]

    output = {
        "metadata": {
            "personas": len(persona_keys),
            "tasks": len(tasks),
            "total_rows": len(matrix),
            "policy_versions": policy_hashes,
            "dataset": "astra_03_tools.json",
        },
        "summary": dict(stats),
        "matrix": matrix,
    }

    output_path = os.path.join("datasets", "access_decision_matrix.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Matrix generated: {output_path}")
    print(f"Total rows: {len(matrix)}")
    print(f"\nSummary:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    return output


if __name__ == "__main__":
    generate_matrix()
