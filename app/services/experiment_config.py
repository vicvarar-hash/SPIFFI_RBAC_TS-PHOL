"""
Experiment configurations and policy generators for SPIFFI experiments.

Defines 34 experiment configurations (Groups A-G) with associated policy
generator functions. Policy generators return in-memory dicts that can be
written to temp files for DecisionEngine construction.
"""

import os
import copy
import json
import yaml
import hashlib  # noqa: F401
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Callable, Optional

from app.services.normalization import normalize_mcp_name


# ═══════════════════════════════════════════════════════════════════════
# Persona & ground-truth definitions
# ═══════════════════════════════════════════════════════════════════════

PERSONAS: Dict[str, dict] = {
    "devops_agent": {
        "display_name": "DevOps Agent",
        "spiffe_id": "spiffe://demo.local/agent/devops",
        "description": "Handles monitoring and operational diagnostics",
        "attributes": {"clearance_level": "L3", "department": "Engineering", "trust_score": 1.0},
    },
    "incident_agent": {
        "display_name": "Incident Agent",
        "spiffe_id": "spiffe://demo.local/agent/incident",
        "description": "Handles incident tracking and escalation",
        "attributes": {"clearance_level": "L2", "department": "Operations", "trust_score": 0.88},
    },
    "finance_agent": {
        "display_name": "Finance Agent",
        "spiffe_id": "spiffe://demo.local/agent/finance",
        "description": "Handles billing and financial workflows",
        "attributes": {"clearance_level": "L2", "department": "Finance", "trust_score": 0.95},
    },
    "research_agent": {
        "display_name": "Research Agent",
        "spiffe_id": "spiffe://demo.local/agent/research",
        "description": "Handles low-risk information discovery",
        "attributes": {"clearance_level": "L1", "department": "Research", "trust_score": 0.75},
    },
    "automation_gateway": {
        "display_name": "Automation Gateway",
        "spiffe_id": "spiffe://demo.local/service/gateway",
        "description": "Executes approved tool operations",
        "attributes": {"clearance_level": "L3", "department": "Infrastructure", "trust_score": 1.0},
    },
    "security_engine": {
        "display_name": "Security Engine",
        "spiffe_id": "spiffe://demo.local/service/security",
        "description": "Evaluates transport, RBAC, and TS-PHOL rules",
        "attributes": {"clearance_level": "L3", "department": "Security", "trust_score": 1.0},
    },
}

ALL_SPIFFE_IDS = [p["spiffe_id"] for p in PERSONAS.values()]

LEGITIMATE_PAIRINGS: Dict[str, Set[str]] = {
    "devops_agent":       {"grafana", "atlassian", "azure", "mongodb"},
    "incident_agent":     {"grafana", "atlassian"},
    "finance_agent":      {"stripe", "hummingbot-mcp"},
    "research_agent":     {"wikipedia-mcp", "paper-search", "notion"},
    "automation_gateway": {"grafana", "atlassian", "azure", "mongodb", "stripe",
                           "notion", "hummingbot-mcp", "wikipedia-mcp", "paper-search"},
    "security_engine":    {"grafana", "atlassian", "azure", "mongodb", "stripe",
                           "notion", "hummingbot-mcp", "wikipedia-mcp", "paper-search"},
}

EXPERIMENT_GROUPS: Dict[str, str] = {
    "E1": "All tasks × full pipeline (RBAC + ABAC + TS-PHOL) — baseline",
    "E2": "All tasks × ABAC + TS-PHOL only (no RBAC) — isolates RBAC contribution",
    "E3": "All tasks × TS-PHOL only (no RBAC, no ABAC) — isolates TS-PHOL capability",
    "E4": "All tasks × no pipeline — control group (everything ALLOWed)",
}


# ═══════════════════════════════════════════════════════════════════════
# Policy generator functions (return in-memory dicts)
# ═══════════════════════════════════════════════════════════════════════

POLICY_DIR = "policies"
BACKUP_DIR = os.path.join(POLICY_DIR, "_backup")


def _load_from_backup_or_current(filename: str, loader: str = "yaml") -> dict:
    backup = os.path.join(BACKUP_DIR, filename)
    current = os.path.join(POLICY_DIR, filename)
    # Prefer current (production) policies; fall back to backup only if current doesn't exist
    src = current if os.path.exists(current) else backup
    if loader == "json":
        with open(src, encoding="utf-8") as f:
            return json.load(f)
    else:
        with open(src, encoding="utf-8") as f:
            return yaml.safe_load(f)


# --- Registry ---
def registry_production() -> dict:
    return copy.deepcopy(PERSONAS)


# --- Allowlist ---
def allowlist_production() -> dict:
    return _load_from_backup_or_current("spiffe_allowlist.json", "json")


def allowlist_all_allowed() -> dict:
    return {"allowed_callers": list(ALL_SPIFFE_IDS)}


# --- RBAC ---
def rbac_production() -> dict:
    return _load_from_backup_or_current("rbac.yaml")


def rbac_open() -> dict:
    policies = []
    for p in PERSONAS.values():
        policies.append({
            "spiffe_id": p["spiffe_id"],
            "description": "Open RBAC (wildcard allow)",
            "rules": [{"mcp": "*", "tools": ["*"], "action": "allow"}],
        })
    return {"policies": policies}


def rbac_complete() -> dict:
    policies = []
    for pkey, pdata in PERSONAS.items():
        legit = LEGITIMATE_PAIRINGS.get(pkey, set())
        rules = [{"mcp": d, "tools": ["*"], "action": "allow", "rule_name": f"allow_{d}"}
                 for d in legit]
        if legit and "*" not in [r["mcp"] for r in rules]:
            rules.append({"mcp": "*", "tools": ["*"], "action": "deny", "rule_name": "default_deny"})
        policies.append({"spiffe_id": pdata["spiffe_id"], "description": f"Complete RBAC for {pkey}", "rules": rules})
    return {"policies": policies}


# --- ABAC ---
def abac_production() -> dict:
    return _load_from_backup_or_current("abac_rules.yaml")


def abac_open() -> dict:
    return {"rules": []}


def abac_strict() -> dict:
    base = abac_production()
    base["rules"].extend([
        {"id": "abac_write_medium_risk", "action": "deny",
         "description": "Write on medium-risk requires L2+",
         "failure_reason": "Clearance insufficient for medium-risk write",
         "match_attributes": [
             {"source": "resource", "attribute": "risk_level", "value": "medium", "op": "=="},
             {"source": "action", "attribute": "contains_write", "value": True, "op": "=="},
             {"source": "subject", "attribute": "attributes.clearance_level", "value": "L1", "op": "=="},
         ]},
        {"id": "abac_cross_department_financial", "action": "deny",
         "description": "Engineering cannot access Financial data",
         "failure_reason": "Department mismatch for financial data",
         "match_attributes": [
             {"source": "resource", "attribute": "data_sensitivity", "value": "Financial", "op": "=="},
             {"source": "subject", "attribute": "attributes.department", "value": "Engineering", "op": "=="},
         ]},
        {"id": "abac_strict_trust_write", "action": "deny",
         "description": "Writes require trust >= 0.9",
         "failure_reason": "Trust score below 0.9 for write operations",
         "match_attributes": [
             {"source": "action", "attribute": "contains_write", "value": True, "op": "=="},
             {"source": "subject", "attribute": "attributes.trust_score", "value": "0.9", "op": "<"},
         ]},
        {"id": "abac_third_party_write", "action": "deny",
         "description": "Third-party resources are read-only",
         "failure_reason": "Write access denied on third-party trust boundary",
         "match_attributes": [
             {"source": "resource", "attribute": "trust_boundary", "value": "Third-Party", "op": "=="},
             {"source": "action", "attribute": "contains_write", "value": True, "op": "=="},
         ]},
    ])
    return base


def abac_extreme() -> dict:
    return {"rules": [
        {"id": "abac_deny_all_high_risk", "action": "deny", "description": "Blanket deny high risk",
         "failure_reason": "High risk denied",
         "match_attributes": [{"source": "resource", "attribute": "risk_level", "value": "high", "op": "=="}]},
        {"id": "abac_deny_all_writes", "action": "deny", "description": "Blanket deny writes",
         "failure_reason": "Writes denied",
         "match_attributes": [{"source": "action", "attribute": "contains_write", "value": True, "op": "=="}]},
        {"id": "abac_high_trust_only", "action": "deny", "description": "Only perfect-trust agents allowed",
         "failure_reason": "Trust score below 1.0",
         "match_attributes": [{"source": "subject", "attribute": "attributes.trust_score", "value": "1.0", "op": "<"}]},
        {"id": "abac_l3_only", "action": "deny", "description": "Only L3 clearance allowed",
         "failure_reason": "L3 clearance required",
         "match_attributes": [{"source": "subject", "attribute": "attributes.clearance_level", "value": "L3", "op": "!="}]},
    ]}


# --- TS-PHOL ---
def tsphol_production() -> dict:
    return _load_from_backup_or_current("tsphol_rules.yaml")


def tsphol_open() -> dict:
    return {"rules": []}


def tsphol_minimal() -> dict:
    return {"rules": [
        {"rule_name": "destructive_write_prevention", "description": "Deny destructive ops without read",
         "if": [{"predicate": "ContainsDelete", "equals": True}, {"predicate": "ContainsRead", "equals": False}],
         "then": "DENY", "derive": "UnsafeDestructiveWrite", "priority": 100},
        {"rule_name": "task_bundle_domain_mismatch", "description": "Deny domain mismatch",
         "if": [{"predicate": "TaskBundleDomainMismatch", "equals": True},
                {"predicate": "SelectionToleranceActive", "equals": False}],
         "then": "DENY", "priority": 120},
    ]}


def tsphol_strict() -> dict:
    base = tsphol_production()
    for rule in base["rules"]:
        rn = rule.get("rule_name", "")
        if rn == "low_task_alignment":
            for c in rule["if"]:
                if c.get("predicate") == "TaskAlignmentScore" and "lt" in c:
                    c["lt"] = 0.6
    return base


def tsphol_relaxed() -> dict:
    base = tsphol_production()
    for rule in base["rules"]:
        rn = rule.get("rule_name", "")
        if rn == "low_task_alignment":
            for c in rule["if"]:
                if c.get("predicate") == "TaskAlignmentScore" and "lt" in c:
                    c["lt"] = 0.3
    return base


def _tsphol_without_rule(rule_to_remove: str) -> dict:
    base = tsphol_production()
    base["rules"] = [r for r in base["rules"] if r.get("rule_name") != rule_to_remove]
    return base


# ═══════════════════════════════════════════════════════════════════════
# Policy generator registry
# ═══════════════════════════════════════════════════════════════════════

POLICY_GENERATORS: Dict[str, Dict[str, Callable]] = {
    "registry":  {"production": registry_production},
    "allowlist": {"production": allowlist_production, "all_allowed": allowlist_all_allowed},
    "rbac":      {"production": rbac_production, "open": rbac_open, "complete": rbac_complete},
    "abac":      {"production": abac_production, "open": abac_open, "strict": abac_strict, "extreme": abac_extreme},
    "tsphol": {
        "production": tsphol_production, "open": tsphol_open,
        "minimal": tsphol_minimal,
        "strict": tsphol_strict, "relaxed": tsphol_relaxed,
        "no_hard_cap":          lambda: _tsphol_without_rule("hard_capability_violation"),
        "no_destructive":       lambda: _tsphol_without_rule("destructive_write_prevention"),
        "no_domain_mismatch":   lambda: _tsphol_without_rule("task_bundle_domain_mismatch"),
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Experiment configuration
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ExperimentConfig:
    name: str
    group: str
    description: str
    registry_fn: str = "production"
    allowlist_fn: str = "production"
    rbac_fn: str = "production"
    abac_fn: str = "production"
    tsphol_fn: str = "production"
    match_tag_filter: Optional[str] = None  # "correct", "wrong", or None for all

    def get_policies(self) -> Dict[str, dict]:
        """Generate all policy dicts for this configuration."""
        return {
            "registry":  POLICY_GENERATORS["registry"][self.registry_fn](),
            "allowlist":  POLICY_GENERATORS["allowlist"][self.allowlist_fn](),
            "rbac":       POLICY_GENERATORS["rbac"][self.rbac_fn](),
            "abac":       POLICY_GENERATORS["abac"][self.abac_fn](),
            "tsphol":     POLICY_GENERATORS["tsphol"][self.tsphol_fn](),
        }


EXPERIMENTS: List[ExperimentConfig] = [
    # E1: Full pipeline — baseline governance (all layers active)
    ExperimentConfig("E1", "E1",
                     "All tasks × full pipeline (RBAC + ABAC + TS-PHOL) — baseline"),

    # E2: No RBAC — isolates RBAC's contribution (subtractive ablation step 1)
    ExperimentConfig("E2", "E2",
                     "All tasks × ABAC + TS-PHOL only — isolates RBAC contribution",
                     rbac_fn="open"),

    # E3: TS-PHOL only — isolates TS-PHOL's solo capability (subtractive step 2)
    ExperimentConfig("E3", "E3",
                     "All tasks × TS-PHOL only — isolates TS-PHOL capability",
                     rbac_fn="open", abac_fn="open"),

    # E4: No pipeline — control group, everything ALLOWed
    ExperimentConfig("E4", "E4",
                     "All tasks × no pipeline — control group (no governance)",
                     rbac_fn="open", abac_fn="open", tsphol_fn="open"),
]

EXPERIMENT_MAP: Dict[str, ExperimentConfig] = {e.name: e for e in EXPERIMENTS}


# ═══════════════════════════════════════════════════════════════════════
# LLM output simulation
# ═══════════════════════════════════════════════════════════════════════

def simulate_llm_output(task, mode: str = "selection", seed_extra: str = "") -> dict:
    """Deterministic LLM simulation — no API calls, seeded by task content."""
    # Support both raw dicts and AstraTask objects
    if isinstance(task, dict):
        tools = task["input"]["tools"]
        mcps = task["input"]["mcp_servers"]
        task_text = task["input"]["task"]
        match_tag = task.get("match_tag", "null")
    else:
        tools = task.candidate_tools
        mcps = task.candidate_mcp
        task_text = task.task
        match_tag = getattr(task, "match_tag", "null")

    base_out = {
        "selected_tools": tools,
        "selected_mcps": mcps,
        "justification": f"Simulated {mode} for task: {task_text[:80]}...",
        "id_source": "Simulation",
        "expected_domain": normalize_mcp_name(mcps[0]) if mcps else "uncertain",
    }

    if mode == "validation":
        is_correct = match_tag == "correct"
        # Validation-specific fields
        base_out["is_valid"] = is_correct
        base_out["reason"] = "Tools match task requirements" if is_correct else "Tool-task mismatch detected"
        base_out["issues"] = [] if is_correct else ["domain_mismatch"]
        base_out["issue_codes"] = [] if is_correct else ["DOMAIN_MISMATCH"]

    return base_out
