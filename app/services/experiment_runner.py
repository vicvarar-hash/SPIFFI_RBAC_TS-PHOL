"""
Experiment runner — batch execution of experiment configurations.

Writes temporary policy files, builds a fresh DecisionEngine per config,
runs all (persona × task) evaluations, and computes aggregate metrics.
"""

import os
import json
import yaml
import shutil
import tempfile
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Callable, Any
from collections import defaultdict

from app.services.experiment_config import (
    ExperimentConfig, EXPERIMENTS, EXPERIMENT_MAP,
    PERSONAS, LEGITIMATE_PAIRINGS, simulate_llm_output,
)
from app.services.normalization import normalize_mcp_name
from app.services.spiffe_registry_service import SpiffeRegistryService
from app.services.spiffe_allowlist_service import SpiffeAllowlistService
from app.services.rbac_service import RBACService
from app.services.tsphol_rule_service import TSPHOLRuleService
from app.services.mcp_attribute_service import MCPAttributeService
from app.services.decision_engine import DecisionEngine
from app.loaders.mcp_loader import load_mcp_personas


# ═══════════════════════════════════════════════════════════════════════
# Result types
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class RunResult:
    experiment: str
    group: str
    persona: str
    task_idx: int
    domain: str
    match_tag: str
    is_legitimate: bool
    final_decision: str
    denial_source: Optional[str]
    identity_state: str
    transport_state: str
    rbac_state: str
    abac_state: str
    tsphol_state: str
    confidence: float
    has_write: bool


@dataclass
class ExperimentMetrics:
    name: str
    description: str
    total: int = 0
    allow_count: int = 0
    deny_count: int = 0
    deception_count: int = 0
    true_positive: int = 0
    true_negative: int = 0
    false_positive: int = 0
    false_negative: int = 0
    identity_denials: int = 0
    transport_denials: int = 0
    rbac_denials: int = 0
    abac_denials: int = 0
    tsphol_denials: int = 0
    other_denials: int = 0

    @property
    def precision(self) -> float:
        d = self.true_positive + self.false_positive
        return self.true_positive / d if d > 0 else 0.0

    @property
    def recall(self) -> float:
        d = self.true_positive + self.false_negative
        return self.true_positive / d if d > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def security_failure_rate(self) -> float:
        illegit = self.true_positive + self.false_negative
        return self.false_negative / illegit if illegit > 0 else 0.0

    @property
    def allow_rate(self) -> float:
        return self.allow_count / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(precision=self.precision, recall=self.recall, f1=self.f1,
                 security_failure_rate=self.security_failure_rate, allow_rate=self.allow_rate)
        return d


# ═══════════════════════════════════════════════════════════════════════
# Engine builder with temp policy files
# ═══════════════════════════════════════════════════════════════════════

def _write_temp_policies(policies: Dict[str, dict], tmp_dir: str):
    """Write policy dicts to temp directory as files the services can load."""
    # Registry
    with open(os.path.join(tmp_dir, "spiffe_registry.json"), "w") as f:
        json.dump(policies["registry"], f, indent=2)
    # Allowlist
    with open(os.path.join(tmp_dir, "spiffe_allowlist.json"), "w") as f:
        json.dump(policies["allowlist"], f, indent=2)
    # RBAC
    with open(os.path.join(tmp_dir, "rbac.yaml"), "w") as f:
        yaml.dump(policies["rbac"], f, default_flow_style=False)
    # ABAC
    with open(os.path.join(tmp_dir, "abac_rules.yaml"), "w") as f:
        yaml.dump(policies["abac"], f, default_flow_style=False)
    # TS-PHOL
    with open(os.path.join(tmp_dir, "tsphol_rules.yaml"), "w") as f:
        yaml.dump(policies["tsphol"], f, default_flow_style=False)


def build_engine_from_policies(policies: Dict[str, dict], personas_list) -> DecisionEngine:
    """Build a DecisionEngine from in-memory policy dicts using temp files."""
    tmp_dir = tempfile.mkdtemp(prefix="spiffi_exp_")
    try:
        _write_temp_policies(policies, tmp_dir)

        registry_svc = SpiffeRegistryService(filepath=os.path.join(tmp_dir, "spiffe_registry.json"))
        allowlist_svc = SpiffeAllowlistService(
            filepath=os.path.join(tmp_dir, "spiffe_allowlist.json"),
            registry_service=registry_svc,
        )
        rbac_svc = RBACService(filepath=os.path.join(tmp_dir, "rbac.yaml"))
        tsphol_svc = TSPHOLRuleService(filepath=os.path.join(tmp_dir, "tsphol_rules.yaml"))
        # MCPAttributeService reads from policy_dir, copy original attributes file
        orig_attrs = "policies/mcp_attributes.yaml"
        if os.path.exists(orig_attrs):
            shutil.copy2(orig_attrs, os.path.join(tmp_dir, "mcp_attributes.yaml"))
        # Also copy heuristic_policy.json and inference_config.json
        for fname in ["heuristic_policy.json", "inference_config.json",
                       "domain_capability_catalog.json", "required_capability_rules.json",
                       "mcp_risk_levels.yaml"]:
            src = os.path.join("policies", fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(tmp_dir, fname))
        attribute_svc = MCPAttributeService(policy_dir=tmp_dir)

        engine = DecisionEngine(
            registry_svc=registry_svc,
            allowlist_svc=allowlist_svc,
            rbac_svc=rbac_svc,
            tsphol_svc=tsphol_svc,
            attribute_svc=attribute_svc,
            personas=personas_list,
        )
        # Keep reference to tmp_dir for cleanup
        engine._tmp_dir = tmp_dir
        return engine
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def cleanup_engine(engine: DecisionEngine):
    """Remove temp policy files after experiment completes."""
    tmp_dir = getattr(engine, "_tmp_dir", None)
    if tmp_dir and os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# Single evaluation
# ═══════════════════════════════════════════════════════════════════════

WRITE_KEYWORDS = {"create", "update", "delete", "transition", "place", "add", "set", "remove"}


def run_single(engine: DecisionEngine, persona_key: str, task: dict,
               task_idx: int, config: ExperimentConfig, mode: str = "selection") -> RunResult:
    """Run one (persona, task) pair through the decision engine."""
    persona = PERSONAS[persona_key]
    spiffe_id = persona["spiffe_id"]
    tools = task["input"]["tools"]
    mcps = task["input"]["mcp_servers"]
    task_text = task["input"]["task"]
    match_tag = task.get("match_tag", "null")

    task_domain = normalize_mcp_name(mcps[0]) if mcps else "unknown"
    domain_authorized = task_domain in LEGITIMATE_PAIRINGS.get(persona_key, set())
    is_legitimate = domain_authorized and match_tag == "correct"

    llm_out = simulate_llm_output(task, mode=mode, seed_extra=persona_key)
    confidence = llm_out["confidence"]
    mcp_filter = mcps[0] if mcps else "All"

    if config.bypass_pre_llm:
        pre_llm = {
            "passed": True, "decision": "ALLOW", "reason": "Pre-LLM bypassed",
            "denial_source": None, "trace": ["[SIM] Pre-LLM gate bypassed"],
            "context": {},
            "evaluation_states": {
                "identity": "ALLOW", "transport": "ALLOW",
                "rbac": "NOT_EVALUATED", "abac": "NOT_EVALUATED", "tsphol": "NOT_EVALUATED",
            },
        }
    else:
        pre_llm = engine.pre_llm_check(spiffe_id, mcps, tools)

    result = engine.evaluate(
        pre_llm_result=pre_llm,
        caller_spiffe_id=spiffe_id,
        mcps=mcps,
        tools=tools,
        confidence=confidence,
        llm_outputs=llm_out,
        task_text=task_text,
        mode=mode,
        mcp_filter=mcp_filter,
    )

    has_write = any(kw in t for t in tools for kw in WRITE_KEYWORDS)

    return RunResult(
        experiment=config.name,
        group=config.group,
        persona=persona_key,
        task_idx=task_idx,
        domain=task_domain,
        match_tag=match_tag,
        is_legitimate=is_legitimate,
        final_decision=result.final_decision,
        denial_source=result.denial_source,
        identity_state=result.evaluation_states.get("identity", "N/A"),
        transport_state=result.evaluation_states.get("transport", "N/A"),
        rbac_state=result.evaluation_states.get("rbac", "N/A"),
        abac_state=result.evaluation_states.get("abac", "N/A"),
        tsphol_state=result.evaluation_states.get("tsphol", "N/A"),
        confidence=confidence,
        has_write=has_write,
    )


# ═══════════════════════════════════════════════════════════════════════
# Metrics computation
# ═══════════════════════════════════════════════════════════════════════

def compute_metrics(results: List[RunResult], config: ExperimentConfig) -> ExperimentMetrics:
    m = ExperimentMetrics(name=config.name, description=config.description)
    m.total = len(results)

    for r in results:
        is_denied = r.final_decision in ("DENY", "DECEPTION_ROUTED")
        is_allowed = not is_denied

        if r.final_decision == "DECEPTION_ROUTED":
            m.deception_count += 1
            m.deny_count += 1
        elif is_denied:
            m.deny_count += 1
        else:
            m.allow_count += 1

        if r.is_legitimate:
            if is_allowed:
                m.true_negative += 1
            else:
                m.false_positive += 1
        else:
            if is_denied:
                m.true_positive += 1
            else:
                m.false_negative += 1

        if is_denied and r.denial_source:
            src = r.denial_source.lower()
            if "identity" in src:
                m.identity_denials += 1
            elif "transport" in src:
                m.transport_denials += 1
            elif "rbac" in src:
                m.rbac_denials += 1
            elif "abac" in src:
                m.abac_denials += 1
            elif any(k in src for k in ("ts-phol", "tsphol", "ts_phol")):
                m.tsphol_denials += 1
            else:
                m.other_denials += 1

    return m


def compute_domain_breakdown(results: List[RunResult]) -> Dict[str, Dict[str, int]]:
    """Per-domain metrics breakdown."""
    by_domain: Dict[str, list] = defaultdict(list)
    for r in results:
        by_domain[r.domain].append(r)

    breakdown = {}
    for domain, domain_results in sorted(by_domain.items()):
        tp = sum(1 for r in domain_results if not r.is_legitimate and r.final_decision in ("DENY", "DECEPTION_ROUTED"))
        tn = sum(1 for r in domain_results if r.is_legitimate and r.final_decision == "ALLOW")
        fp = sum(1 for r in domain_results if r.is_legitimate and r.final_decision in ("DENY", "DECEPTION_ROUTED"))
        fn = sum(1 for r in domain_results if not r.is_legitimate and r.final_decision == "ALLOW")
        total = len(domain_results)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * rec / (p + rec) if (p + rec) > 0 else 0.0
        breakdown[domain] = {"total": total, "TP": tp, "TN": tn, "FP": fp, "FN": fn,
                              "precision": p, "recall": rec, "f1": f1}
    return breakdown


# ═══════════════════════════════════════════════════════════════════════
# Batch experiment runner
# ═══════════════════════════════════════════════════════════════════════

def run_experiment(config: ExperimentConfig, tasks: list, personas_list,
                   mode: str = "selection",
                   progress_callback: Optional[Callable] = None) -> tuple:
    """
    Run a complete experiment: build engine, iterate all persona×task pairs, compute metrics.

    Returns: (metrics: ExperimentMetrics, results: List[RunResult])
    """
    policies = config.get_policies()
    engine = build_engine_from_policies(policies, personas_list)

    try:
        results: List[RunResult] = []
        active_personas = [k for k in PERSONAS if k != "security_engine"]
        total_evals = len(active_personas) * len(tasks)
        done = 0

        for persona_key in active_personas:
            for task_idx, task in enumerate(tasks):
                result = run_single(engine, persona_key, task, task_idx, config, mode=mode)
                results.append(result)
                done += 1
                if progress_callback and done % 100 == 0:
                    progress_callback(done / total_evals)

        if progress_callback:
            progress_callback(1.0)

        metrics = compute_metrics(results, config)
        return metrics, results
    finally:
        cleanup_engine(engine)
