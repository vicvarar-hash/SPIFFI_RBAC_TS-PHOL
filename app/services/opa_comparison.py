"""
OPA Baseline Comparison — replays experiment log rows through OPA-equivalent engine.

Reads a saved experiment log, reconstructs the input context for each row
using the same static config (personas, MCP attributes, policy files),
evaluates via OPA-Flat and OPA-Layered modes, and computes comparison metrics.
"""

import os
import json
import yaml
import hashlib
import logging
from typing import Dict, Any, List, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

from app.services.opa_engine import OPAEngine, _tool_has_action, _WRITE_KW, _DELETE_KW, _READ_KW
from app.services.experiment_config import PERSONAS
from app.services.normalization import normalize_mcp_name
from app.services.policy_loader import PolicyLoader

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# MCP attributes (static — loaded once)
# ═══════════════════════════════════════════════════════════════════════

def _load_mcp_attributes() -> Dict[str, Dict[str, str]]:
    path = os.path.join("policies", "mcp_attributes.yaml")
    data = PolicyLoader.load_yaml(path)
    return data.get("mcp_attributes", {})


# ═══════════════════════════════════════════════════════════════════════
# Input reconstruction from log rows
# ═══════════════════════════════════════════════════════════════════════

def _reconstruct_input(row: dict, mcp_attrs: dict, mode: str) -> Dict[str, Any]:
    """
    Reconstruct the full OPA input context from an experiment log row.

    RBAC input: spiffe_id + mcps + tools (directly from log).
    ABAC input: subject attrs from PERSONAS config + resource attrs from MCP.
    TS-PHOL input: derived predicates from tool names + confidence + domain.
    """
    persona_key = row["persona"]
    persona = PERSONAS[persona_key]
    spiffe_id = persona["spiffe_id"]
    attrs = persona.get("attributes", {})

    tools = row.get("selected_tools", [])
    mcps = row.get("selected_mcps", [])
    confidence = row.get("confidence", 0.5)
    domain = row.get("domain", "unknown")

    # ── Tool classification (lightweight — from tool names) ──
    contains_write = any(_tool_has_action(t, _WRITE_KW) for t in tools)
    contains_read = any(_tool_has_action(t, _READ_KW) for t in tools)
    contains_delete = any(_tool_has_action(t, _DELETE_KW) for t in tools)
    write_tool_count = sum(1 for t in tools if _tool_has_action(t, _WRITE_KW))

    # Destructive writes: delete/drop/cancel/refund
    contains_destructive = contains_delete
    # Privileged writes: create/update on high-value resources
    contains_privileged = any(
        _tool_has_action(t, {"create", "update", "execute", "finalize"})
        for t in tools
    )

    # ── Resource attributes ──
    primary_mcp = normalize_mcp_name(mcps[0]) if mcps else "unknown"
    resource = mcp_attrs.get(primary_mcp, {
        "risk_level": "medium", "compliance_tier": "General",
        "data_sensitivity": "Internal", "trust_boundary": "Internal",
    })
    resource["domain"] = primary_mcp

    # Highest risk across all MCPs
    unique_mcps = set(normalize_mcp_name(m) for m in mcps)
    highest_risk = "low"
    for m in unique_mcps:
        r = mcp_attrs.get(m, {}).get("risk_level", "low")
        if r == "high":
            highest_risk = "high"
        elif r == "medium" and highest_risk == "low":
            highest_risk = "medium"

    multi_domain = len(unique_mcps) > 1

    # ── Temporal (deterministic hash — same as decision_engine) ──
    task_text_approx = f"task_{row.get('task_idx', 0)}_{domain}"
    hour_seed = int(hashlib.sha256(
        (task_text_approx[:80] + spiffe_id).encode()
    ).hexdigest()[:4], 16) % 24
    after_hours = hour_seed < 6 or hour_seed >= 20

    # ── Domain alignment (simplified) ──
    actual_domain = list(unique_mcps)[0] if len(unique_mcps) == 1 else "multi_domain"
    expected_domain = domain
    domain_mismatch = (expected_domain != actual_domain) and (expected_domain != "uncertain")

    # Alignment score approximation (domain match + basic capability)
    domain_score = 1.0 if not domain_mismatch else 0.0
    # Simplified capability score — full ontology would require heavy reconstruction
    cap_score = 0.5
    alignment_score = 0.4 * domain_score + 0.4 * cap_score + 0.2 * 0.5

    # ── ABAC attribute context ──
    abac_attrs = {
        "subject": {
            "role": persona_key,
            "attributes": attrs,
            "department": attrs.get("department", "Public"),
            "clearance_level": attrs.get("clearance_level", "L1"),
            "trust_score": attrs.get("trust_score", 0.5),
        },
        "resource": resource,
        "action": {
            "tools": tools,
            "tool_count": len(tools),
            "contains_write": contains_write,
            "contains_destructive_write": contains_destructive,
            "contains_privileged_write": contains_privileged,
            "multi_domain": multi_domain,
            "write_tool_count": write_tool_count,
        },
        "environment": {
            "confidence": confidence,
            "after_hours": after_hours,
            "simulated_hour": hour_seed,
        },
    }

    # ── TS-PHOL predicates ──
    predicates = {
        "ContainsWrite": contains_write,
        "ContainsRead": contains_read,
        "ContainsDelete": contains_delete,
        "ConfidenceValue": confidence,
        "HighestRiskLevel": highest_risk,
        "MultiDomain": multi_domain,
        "TaskBundleDomainMismatch": domain_mismatch,
        "SelectionToleranceActive": (mode == "selection"),
        "CriticalValidationFailure": False,  # Not available from log
        "HardCapabilityMissing": False,  # Requires ontology — approximated as False
        "AlignmentEvaluated": (expected_domain != "uncertain"),
        "TaskAlignmentScore": alignment_score,
    }

    return {
        "spiffe_id": spiffe_id,
        "mcps": [normalize_mcp_name(m) for m in mcps],
        "tools": tools,
        "confidence": confidence,
        "mode": mode,
        "abac_attrs": abac_attrs,
        "predicates": predicates,
    }


# ═══════════════════════════════════════════════════════════════════════
# Comparison metrics
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ComparisonMetrics:
    total: int = 0
    paladin_allow: int = 0
    paladin_deny: int = 0
    paladin_deception: int = 0
    opa_flat_allow: int = 0
    opa_flat_deny: int = 0
    opa_layered_allow: int = 0
    opa_layered_deny: int = 0
    agreement_flat: int = 0
    agreement_layered: int = 0
    # Where they disagree
    paladin_only_deny: int = 0  # PALADIN denies, OPA-Flat allows
    opa_only_deny: int = 0      # OPA-Flat denies, PALADIN allows
    deception_gap: int = 0      # PALADIN deception-routed (OPA can only DENY)
    # Standard metrics for OPA modes
    opa_flat_tp: int = 0
    opa_flat_tn: int = 0
    opa_flat_fp: int = 0
    opa_flat_fn: int = 0
    opa_layered_tp: int = 0
    opa_layered_tn: int = 0
    opa_layered_fp: int = 0
    opa_layered_fn: int = 0
    # PALADIN metrics (from log)
    paladin_tp: int = 0
    paladin_tn: int = 0
    paladin_fp: int = 0
    paladin_fn: int = 0
    # Denial source breakdown (OPA-Flat sees ALL denial sources)
    opa_flat_rbac_denials: int = 0
    opa_flat_abac_denials: int = 0
    opa_flat_tsphol_denials: int = 0

    @property
    def agreement_rate_flat(self) -> float:
        return self.agreement_flat / self.total if self.total else 0.0

    @property
    def agreement_rate_layered(self) -> float:
        return self.agreement_layered / self.total if self.total else 0.0

    def _f1(self, tp, fp, fn) -> float:
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def _secfail(self, tp, fn) -> float:
        return fn / (tp + fn) if (tp + fn) > 0 else 0.0

    @property
    def paladin_f1(self) -> float:
        return self._f1(self.paladin_tp, self.paladin_fp, self.paladin_fn)

    @property
    def paladin_secfail(self) -> float:
        return self._secfail(self.paladin_tp, self.paladin_fn)

    @property
    def opa_flat_f1(self) -> float:
        return self._f1(self.opa_flat_tp, self.opa_flat_fp, self.opa_flat_fn)

    @property
    def opa_flat_secfail(self) -> float:
        return self._secfail(self.opa_flat_tp, self.opa_flat_fn)

    @property
    def opa_layered_f1(self) -> float:
        return self._f1(self.opa_layered_tp, self.opa_layered_fp, self.opa_layered_fn)

    @property
    def opa_layered_secfail(self) -> float:
        return self._secfail(self.opa_layered_tp, self.opa_layered_fn)


# ═══════════════════════════════════════════════════════════════════════
# Main comparison runner
# ═══════════════════════════════════════════════════════════════════════

def run_opa_comparison(log_path: str,
                       experiment: str = "E1",
                       progress_callback=None) -> Tuple[ComparisonMetrics, List[Dict]]:
    """
    Run OPA baseline comparison against a saved PALADIN experiment log.

    Reads the log, reconstructs inputs, evaluates through OPA-Flat and
    OPA-Layered modes, and computes agreement + standard metrics.
    """
    # Load experiment log
    with open(log_path, "r", encoding="utf-8") as f:
        log_data = json.load(f)

    mode = log_data.get("evaluation_mode", "selection")
    exp_data = log_data["experiments"].get(experiment)
    if not exp_data:
        raise ValueError(f"Experiment {experiment} not found in log")

    rows = exp_data["rows"]

    # Load policy files for OPA engine
    rbac_data = PolicyLoader.load_yaml("policies/rbac.yaml")
    rbac_policies = rbac_data.get("policies", [])
    # Normalize RBAC policies
    for p in rbac_policies:
        for r in p.get("rules", []):
            if "mcp" in r and r["mcp"] != "*":
                r["mcp"] = normalize_mcp_name(r["mcp"])
            if "tools" in r:
                r["tools"] = [t if t == "*" else t for t in r["tools"]]

    abac_data = PolicyLoader.load_yaml("policies/abac_rules.yaml")
    abac_rules = abac_data.get("rules", [])

    tsphol_data = PolicyLoader.load_yaml("policies/tsphol_rules.yaml")
    tsphol_rules = tsphol_data.get("rules", [])

    mcp_attrs = _load_mcp_attributes()

    engine = OPAEngine(rbac_policies, abac_rules, tsphol_rules)

    metrics = ComparisonMetrics()
    detail_rows = []
    total = len(rows)

    for i, row in enumerate(rows):
        # Skip LLM failures
        if row.get("llm_failed"):
            continue

        inp = _reconstruct_input(row, mcp_attrs, mode)

        opa_flat = engine.evaluate_flat(inp)
        opa_layered = engine.evaluate_layered(inp)

        paladin_decision = row["final_decision"]
        paladin_denied = paladin_decision in ("DENY", "DECEPTION_ROUTED")
        is_legitimate = row["is_legitimate"]

        # OPA decisions
        flat_denied = opa_flat["decision"] == "DENY"
        layered_denied = opa_layered["decision"] == "DENY"

        metrics.total += 1

        # PALADIN counts
        if paladin_decision == "ALLOW":
            metrics.paladin_allow += 1
        elif paladin_decision == "DECEPTION_ROUTED":
            metrics.paladin_deception += 1
            metrics.paladin_deny += 1
        else:
            metrics.paladin_deny += 1

        # OPA counts
        if flat_denied:
            metrics.opa_flat_deny += 1
        else:
            metrics.opa_flat_allow += 1

        if layered_denied:
            metrics.opa_layered_deny += 1
        else:
            metrics.opa_layered_allow += 1

        # Agreement
        if paladin_denied == flat_denied:
            metrics.agreement_flat += 1
        if paladin_denied == layered_denied:
            metrics.agreement_layered += 1

        # Disagreement analysis
        if paladin_denied and not flat_denied:
            metrics.paladin_only_deny += 1
        if flat_denied and not paladin_denied:
            metrics.opa_only_deny += 1
        if paladin_decision == "DECEPTION_ROUTED":
            metrics.deception_gap += 1

        # Confusion matrix — PALADIN
        if is_legitimate:
            if not paladin_denied:
                metrics.paladin_tn += 1
            else:
                metrics.paladin_fp += 1
        else:
            if paladin_denied:
                metrics.paladin_tp += 1
            else:
                metrics.paladin_fn += 1

        # Confusion matrix — OPA-Flat
        if is_legitimate:
            if not flat_denied:
                metrics.opa_flat_tn += 1
            else:
                metrics.opa_flat_fp += 1
        else:
            if flat_denied:
                metrics.opa_flat_tp += 1
            else:
                metrics.opa_flat_fn += 1

        # Confusion matrix — OPA-Layered
        if is_legitimate:
            if not layered_denied:
                metrics.opa_layered_tn += 1
            else:
                metrics.opa_layered_fp += 1
        else:
            if layered_denied:
                metrics.opa_layered_tp += 1
            else:
                metrics.opa_layered_fn += 1

        # OPA-Flat denial source breakdown
        if flat_denied:
            for src in opa_flat.get("denial_sources", []):
                if src == "RBAC":
                    metrics.opa_flat_rbac_denials += 1
                elif src == "ABAC":
                    metrics.opa_flat_abac_denials += 1
                elif src == "TS-PHOL":
                    metrics.opa_flat_tsphol_denials += 1

        # Detail row for drill-down
        detail_rows.append({
            "persona": row["persona"],
            "domain": row["domain"],
            "match_tag": row["match_tag"],
            "is_legitimate": is_legitimate,
            "paladin": paladin_decision,
            "opa_flat": opa_flat["decision"],
            "opa_layered": opa_layered["decision"],
            "flat_sources": opa_flat.get("denial_sources", []),
            "layered_source": opa_layered.get("denial_source"),
            "agrees_flat": paladin_denied == flat_denied,
            "agrees_layered": paladin_denied == layered_denied,
        })

        if progress_callback and (i + 1) % 200 == 0:
            progress_callback({"current": i + 1, "total": total})

    if progress_callback:
        progress_callback({"current": total, "total": total})

    return metrics, detail_rows
