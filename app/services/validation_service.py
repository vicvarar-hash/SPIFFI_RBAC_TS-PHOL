import json
import re
from typing import List
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona
from app.models.validation import ValidationResult
from app.services.llm_provider import LLMProvider

from app.services.tool_classifier import ToolClassifier

class ValidationService:
    def __init__(self, llm: LLMProvider, personas: List[MCPPersona]):
        self.llm = llm
        self.personas = personas
        self.persona_map = {p.name: p for p in personas}
        self.classifier = ToolClassifier()

    def run_validation(self, task: AstraTask) -> ValidationResult:
        if not self.llm.is_configured():
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason="LLM provider not configured.",
                issues=["LLM_NOT_CONFIGURED"]
            )

        system_prompt = self._build_system_prompt()
        
        # Phase 1: Grounded Artifact Extraction & Requirement Pulse
        # Before calling the LLM, we ground the proposed tools into Action Classes and Capabilities
        grounded_artifacts = self.classifier.classify_tools(task.candidate_tools)
        
        from app.services.intent_engine import IntentEngine
        intent_engine = IntentEngine()
        required_caps, optional_caps, _ = intent_engine.inference_svc.get_task_required_capabilities("General", task.task)
        
        user_prompt = self._build_user_prompt(task, grounded_artifacts, list(required_caps), list(optional_caps))
        
        try:
            raw_output = self.llm.query(system_prompt, user_prompt)
            data = self._parse_json(raw_output)
            
            # Map unified schema back to ValidationResult
            metrics = data.get("mission_metrics", {})
            issue_meta = data.get("issue_metadata", {})
            domain_ctx = data.get("domain_context", {})
            
            return ValidationResult(
                is_valid=bool(data.get("is_valid", False)),
                confidence=float(data.get("confidence", 0.0)),
                reason=data.get("justification", "No justification provided."),
                issues=issue_meta.get("details", []),
                issue_codes=issue_meta.get("codes", []),
                expected_domain=domain_ctx.get("expected", "unknown"),
                actual_domain=domain_ctx.get("actual", "unknown"),
                task_alignment_score=float(metrics.get("task_alignment", 0.0)),
                task_alignment_details={}, # Unified as flat for now
                raw_output=raw_output
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason=f"Error during validation: {str(e)}",
                issues=[str(e)],
                raw_output=None
            )

    def _build_system_prompt(self) -> str:
        prompt = """
        You are the 'Meta-Level Logic Checker' of an authoritative Automated Reasoning pipeline. Your role is to evaluate whether a proposed bundle of logic hypotheses (tools) belongs to an allowed mathematical fragment and is safe for the mission.
        
        You will be provided with:
        1. The User Task.
        2. Available MCP Catalog (for context).
        3. The Proposed Bundle (MCPs and Tools).
        4. GROUNDED METADATA for each proposed tool (Action Classes and Concrete Capabilities).
        
        Judge the validity based on:
        - Mission Sufficiency: Do the tools satisfy ALL 'REQUIRED' capabilities listed in the prompt?
        - Domain Alignment: Does the bundle belong to the appropriate domain (e.g. Jira tools for a Jira task)?
        - Logic Bounding: Is the bundle dangerously excessive? (e.g. 5+ distinct tools for a simple task).
        
        PHILOSOPHY: VALIDITY IS SUFFICIENCY.
        - If the bundle satisfies all REQUIRED capabilities and the domain is correct, mark it as `is_valid: true`.
        - Do NOT mark as `is_valid: false` for minor redundancies, "better tool" opinions, or sub-optimal choices if the mission is technically covered.
        - Mark as `is_valid: false` ONLY for: MISSING_CAPABILITY (REQUIRED ones only), WRONG_DOMAIN, or INVALID_TOOL names.
        
        Return your answer ONLY in structured JSON format with the following fields:
        {
          "is_valid": true,
          "confidence": 0.9,
          "justification": "Detailed explanation of your judgment, referencing the GROUNDED METADATA.",
          "selections": [{"tool": "...", "mcp": "..."}],
          "mission_metrics": {
            "capability_coverage": 1.0,
            "task_alignment": 0.85
          },
          "issue_metadata": {
            "codes": ["MISSING_CAPABILITY"],
            "details": ["More details here"]
          },
          "domain_context": {
            "expected": "wikipedia",
            "actual": "jira"
          }
        }
        
        IMPORTANT: The proposed bundle MUST contain EXACTLY 3 tools to be considered valid in this specific evaluation fragment. If the bundle contains fewer or more than 3 tools, you MUST mark it as invalid (`is_valid`: false) and include "INVALID_TOOL_COUNT" in the `issue_codes`.
        Confidence and scores must be returned as actual calculated float numbers (e.g. 0.85). Do not just reply with fixed placeholders.
        """
        return prompt

    def _build_user_prompt(self, task: AstraTask, grounded_artifacts: List[dict], required_caps: List[str], optional_caps: List[str]) -> str:
        persona_context = []
        for p in self.personas:
            p_text = f"MCP Persona: {p.name}\nTools: {', '.join([t.name for t in p.tools])}"
            persona_context.append(p_text)
            
        context_str = "\n".join(persona_context)
        
        artifact_str = ""
        for i, art in enumerate(grounded_artifacts):
            artifact_str += f"\n- Tool: {art['tool']}\n  - Grounded Actions: {', '.join(art['actions'] or [])}\n  - Grounded Capabilities: {', '.join(art['capabilities'] or [])}\n"
        
        user_prompt = f"""
        [MCP CATALOG]
        {context_str}
        
        [GROUND-TRUTH REQUIREMENTS]
        REQUIRED CAPABILITIES: {', '.join(required_caps) if required_caps else 'None'}
        OPTIONAL ENRICHMENT: {', '.join(optional_caps) if optional_caps else 'None'}
        
        [USER TASK]
        {task.task}
        
        [PROPOSED BUNDLE]
        Proposed MCPs: {task.candidate_mcp}
        Proposed Tools: {task.candidate_tools}
        
        [GROUNDED METADATA (Artifacts)]
        {artifact_str}
        
        Please evaluate if the PROPOSED BUNDLE satisfies the REQUIRED CAPABILITIES for the MISSION.
        """
        return user_prompt

    def _parse_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            match = re.search(r'(\{.*\})', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            raise ValueError("Could not extract valid JSON from LLM output.")
