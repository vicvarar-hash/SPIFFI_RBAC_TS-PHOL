import json
import re
from typing import List
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona
from app.models.validation import ValidationResult
from app.services.llm_provider import LLMProvider

class ValidationService:
    def __init__(self, llm: LLMProvider, personas: List[MCPPersona]):
        self.llm = llm
        self.personas = personas
        self.persona_map = {p.name: p for p in personas}

    def run_validation(self, task: AstraTask) -> ValidationResult:
        if not self.llm.is_configured():
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason="LLM provider not configured.",
                issues=["LLM_NOT_CONFIGURED"]
            )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(task)
        
        try:
            raw_output = self.llm.query(system_prompt, user_prompt)
            data = self._parse_json(raw_output)
            
            return ValidationResult(
                is_valid=bool(data.get("is_valid", False)),
                confidence=float(data.get("confidence", 0.0)),
                reason=data.get("reason", "No reason provided."),
                issues=data.get("issues", []),
                issue_codes=data.get("issue_codes", []),
                expected_domain=data.get("expected_domain", "Unknown"),
                actual_domain=data.get("actual_domain", "Unknown"),
                task_alignment_score=float(data.get("task_alignment_score", 0.0)),
                task_alignment_details=data.get("task_alignment_details"),
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
        You are an expert security and logic validator for an agentic system.
        Your task is to evaluate whether a PRE-SELECTED bundle of MCP servers and tools is appropriate and safe for a given user task.
        
        You will be provided with:
        1. The User Task.
        2. Available MCP Catalog (for context).
        3. The Proposed Bundle (MCPs and Tools).
        
        Judge the validity based on:
        - Relevance: Do the tools actually solve the user's problem?
        - Specificity: Are there better tools available that weren't selected?
        - Correctness: Do the tool names exist in the catalog for those MCPs?
        - Risk: Is the bundle excessive or unnecessary?
        
        Return your answer ONLY in structured JSON format:
        {
          "is_valid": true/false,
          "confidence": 0.9,
          "reason": "Detailed explanation of your judgment.",
          "issues": ["List of specific human-readable issues"],
          "issue_codes": ["WRONG_DOMAIN", "IRRELEVANT_TOOLS", "MISSING_CAPABILITY", etc.],
          "expected_domain": "e.g. Grafana",
          "actual_domain": "e.g. Hummingbot",
          "task_alignment_score": 0.0 to 1.0,
          "task_alignment_details": {
            "domain_match": 1.0,
            "capability_match": 1.0,
            "tool_semantic_similarity": 0.7
          }
        }
        
        DO NOT compare against any 'groundtruth' knowledge you might have. Judge only the provided bundle against the task and catalog context.
        """
        return prompt

    def _build_user_prompt(self, task: AstraTask) -> str:
        persona_context = []
        for p in self.personas:
            p_text = f"MCP Persona: {p.name}\nTools: {', '.join([t.name for t in p.tools])}"
            persona_context.append(p_text)
            
        context_str = "\n".join(persona_context)
        
        user_prompt = f"""
        [MCP CATALOG]
        {context_str}
        
        [USER TASK]
        {task.task}
        
        [PROPOSED BUNDLE]
        Proposed MCPs: {task.candidate_mcp}
        Proposed Tools: {task.candidate_tools}
        
        Please evaluate this bundle.
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
