"""
OPA-equivalent policy engine for baseline comparison.

Provides two evaluation modes:
  - Flat:    All rules evaluated simultaneously, deny-wins (OPA default semantics)
  - Layered: Sequential RBAC → ABAC → TS-PHOL with short-circuit, but binary DENY/ALLOW only

Both modes lack PALADIN's DECEPTION_ROUTED third outcome.
Formal Rego translations live in policies/rego/ for paper reference.
"""

import hashlib
import logging
from typing import Dict, Any, List, Set, Optional

from app.services.normalization import normalize_mcp_name, normalize_tool_name
from app.services.experiment_config import PERSONAS

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Write-keyword detection (mirrors tool_classifier logic)
# ═══════════════════════════════════════════════════════════════════════
_WRITE_KW = {"create", "update", "delete", "drop", "insert", "add", "remove",
             "put", "post", "patch", "set", "cancel", "refund", "execute",
             "finalize", "transition", "link", "batch_create"}
_DELETE_KW = {"delete", "drop", "remove", "cancel", "refund"}
_READ_KW = {"get", "list", "fetch", "query", "search", "find", "retrieve",
            "explore", "summarize", "extract", "read", "count", "aggregate"}


def _tool_has_action(tool: str, keywords: set) -> bool:
    parts = tool.lower().replace("-", "_").split("_")
    return bool(set(parts) & keywords)


# ═══════════════════════════════════════════════════════════════════════
# RBAC evaluation (mirrors decision_engine._evaluate_rbac)
# ═══════════════════════════════════════════════════════════════════════

class _RBACEvaluator:
    """Per-tool RBAC check using the same YAML rule semantics."""

    def __init__(self, policies: list):
        self.policies = policies

    def evaluate(self, spiffe_id: str, mcps: List[str], tools: List[str]) -> Dict[str, Any]:
        if not mcps or not tools:
            return {"decision": "ALLOW", "denial_source": None}

        policy = self._get_policy(spiffe_id)
        if not policy:
            return {"decision": "DENY", "denial_source": "RBAC"}

        rules = policy.get("rules", [])
        for mcp, tool in zip(mcps, tools):
            mcp = normalize_mcp_name(mcp)
            tool = normalize_tool_name(tool)
            if not self._tool_allowed(rules, mcp, tool):
                return {"decision": "DENY", "denial_source": "RBAC"}
        return {"decision": "ALLOW", "denial_source": None}

    def _get_policy(self, spiffe_id: str):
        for p in self.policies:
            if p.get("spiffe_id") == spiffe_id:
                return p
        return None

    def _tool_allowed(self, rules, mcp, tool) -> bool:
        for rule in rules:
            rule_mcp = rule.get("mcp", "")
            if rule_mcp != "*":
                rule_mcp = normalize_mcp_name(rule_mcp)
            mcp_match = (rule_mcp == "*" or rule_mcp == mcp)
            if mcp_match:
                tool_list = rule.get("tools", [])
                norm_tools = [normalize_tool_name(t) if t != "*" else t for t in tool_list]
                tool_match = ("*" in norm_tools or tool in norm_tools)
                if tool_match:
                    return rule.get("action", "deny").upper() == "ALLOW"
                else:
                    return False
        return False


# ═══════════════════════════════════════════════════════════════════════
# ABAC evaluation (mirrors abac_engine.evaluate)
# ═══════════════════════════════════════════════════════════════════════

class _ABACEvaluator:
    """Attribute-based deny rules — all conditions must match."""

    def __init__(self, rules: list):
        self.rules = rules

    def evaluate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        for rule in self.rules:
            match_specs = rule.get("match_attributes", [])
            if not match_specs:
                continue
            if self._all_match(match_specs, attrs):
                return {
                    "decision": "DENY",
                    "denial_source": "ABAC",
                    "matched_rule": rule.get("id", "unknown"),
                }
        return {"decision": "ALLOW", "denial_source": None}

    def _all_match(self, specs, attrs) -> bool:
        for spec in specs:
            source = spec.get("source")
            attr_name = spec.get("attribute")
            expected = spec.get("value")
            op = spec.get("op", "==")
            actual = self._get_nested(attrs, source, attr_name)
            if not self._compare(actual, expected, op):
                return False
        return True

    @staticmethod
    def _get_nested(data, source, path):
        root = data.get(source, {})
        for part in path.split("."):
            if isinstance(root, dict):
                root = root.get(part)
            else:
                return None
        return root

    @staticmethod
    def _compare(actual, expected, op) -> bool:
        try:
            if op == "==":
                return actual == expected
            if op == "!=":
                return actual != expected
            if op == ">":
                return float(actual) > float(expected)
            if op == "<":
                return float(actual) < float(expected)
            if op == ">=":
                return float(actual) >= float(expected)
            if op == "<=":
                return float(actual) <= float(expected)
            if op == "in":
                return actual in expected if isinstance(expected, list) else expected in str(actual)
            return False
        except (ValueError, TypeError):
            return False


# ═══════════════════════════════════════════════════════════════════════
# TS-PHOL evaluation (mirrors tsphol_interpreter)
# ═══════════════════════════════════════════════════════════════════════

class _TSPHOLEvaluator:
    """Predicate-based rule evaluation with priority ordering."""

    def __init__(self, rules: list):
        self.rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)

    def evaluate(self, predicates: Dict[str, Any], mode: str = "selection") -> Dict[str, Any]:
        skip_alignment = (mode == "selection")

        for rule in self.rules:
            rule_name = rule.get("rule_name", "")
            action = rule.get("then", "ALLOW")
            conditions = rule.get("if", [])

            is_alignment = rule_name == "low_task_alignment"
            if is_alignment and skip_alignment:
                continue

            if self._conditions_match(conditions, predicates) and action.upper() == "DENY":
                return {
                    "decision": "DENY",
                    "denial_source": "TS-PHOL",
                    "matched_rule": rule_name,
                }
        return {"decision": "ALLOW", "denial_source": None}

    @staticmethod
    def _conditions_match(conditions, predicates) -> bool:
        for cond in conditions:
            pred_name = cond.get("predicate")
            actual = predicates.get(pred_name)
            if actual is None:
                return False

            if "equals" in cond:
                if actual != cond["equals"]:
                    return False
            if "lt" in cond:
                try:
                    if not (float(actual) < float(cond["lt"])):
                        return False
                except (ValueError, TypeError):
                    return False
            if "gt" in cond:
                try:
                    if not (float(actual) > float(cond["gt"])):
                        return False
                except (ValueError, TypeError):
                    return False
        return True


# ═══════════════════════════════════════════════════════════════════════
# Public API — OPA-equivalent engine
# ═══════════════════════════════════════════════════════════════════════

class OPAEngine:
    """
    OPA-equivalent policy evaluator.

    Implements the same RBAC, ABAC, and TS-PHOL rules from PALADIN's YAML
    using OPA's flat evaluation semantics (deny-wins, no deception routing).
    Formal Rego translations are in policies/rego/.
    """

    def __init__(self, rbac_policies: list, abac_rules: list, tsphol_rules: list):
        self.rbac = _RBACEvaluator(rbac_policies)
        self.abac = _ABACEvaluator(abac_rules)
        self.tsphol = _TSPHOLEvaluator(tsphol_rules)

    def evaluate_flat(self, inp: Dict[str, Any]) -> Dict[str, Any]:
        """
        OPA-Flat: All three rule packages evaluated independently.
        Final decision = DENY if ANY package denies. No short-circuit.
        No deception routing. Binary ALLOW/DENY only.
        """
        rbac_res = self.rbac.evaluate(inp["spiffe_id"], inp["mcps"], inp["tools"])
        abac_res = self.abac.evaluate(inp["abac_attrs"])
        tsphol_res = self.tsphol.evaluate(inp["predicates"], inp.get("mode", "selection"))

        denial_sources = []
        if rbac_res["decision"] == "DENY":
            denial_sources.append("RBAC")
        if abac_res["decision"] == "DENY":
            denial_sources.append("ABAC")
        if tsphol_res["decision"] == "DENY":
            denial_sources.append("TS-PHOL")

        if denial_sources:
            return {
                "decision": "DENY",
                "denial_sources": denial_sources,
                "denial_source": denial_sources[0],
            }
        return {"decision": "ALLOW", "denial_sources": [], "denial_source": None}

    def evaluate_layered(self, inp: Dict[str, Any]) -> Dict[str, Any]:
        """
        OPA-Layered: Sequential RBAC → ABAC → TS-PHOL with short-circuit.
        Same layer ordering as PALADIN, but binary ALLOW/DENY only.
        No deception routing.
        """
        rbac_res = self.rbac.evaluate(inp["spiffe_id"], inp["mcps"], inp["tools"])
        if rbac_res["decision"] == "DENY":
            return {"decision": "DENY", "denial_source": "RBAC", "denial_sources": ["RBAC"]}

        abac_res = self.abac.evaluate(inp["abac_attrs"])
        if abac_res["decision"] == "DENY":
            return {"decision": "DENY", "denial_source": "ABAC", "denial_sources": ["ABAC"]}

        tsphol_res = self.tsphol.evaluate(inp["predicates"], inp.get("mode", "selection"))
        if tsphol_res["decision"] == "DENY":
            return {"decision": "DENY", "denial_source": "TS-PHOL", "denial_sources": ["TS-PHOL"]}

        return {"decision": "ALLOW", "denial_source": None, "denial_sources": []}
