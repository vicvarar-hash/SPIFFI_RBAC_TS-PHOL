import json
from typing import List
from app.models.astra import AstraTask
from app.models.mcp import MCPPersona
from app.models.selection import SelectionResult
from app.services.llm_provider import LLMProvider
import re

from app.services.intent_engine import IntentEngine
from app.services.tool_classifier import ToolClassifier
from app.services.intent_taxonomy import IntentTaxonomy

class PredictionService:
    def __init__(self, llm: LLMProvider, personas: List[MCPPersona], intent_engine: IntentEngine = None):
        self.llm = llm
        self.personas = personas
        self.persona_map = {p.name: p for p in personas}
        self.intent_engine = intent_engine or IntentEngine()
        self.classifier = ToolClassifier()

    def run_selection(self, task: AstraTask) -> SelectionResult:
        if not self.llm.is_configured():
            return SelectionResult(
                selected_mcp=[],
                selected_tools=[],
                justification="LLM provider not configured. Please check your API key.",
                confidence=0.0,
                validation_errors=["LLM_NOT_CONFIGURED"]
            )

        # 5: Pre-Selection Capability Inference
        # Determine primary domain and intent first
        primary_domain = "General"
        primary_intent = None
        
        if task.candidate_mcp:
            domain_enum = IntentTaxonomy.get_domain_for_mcp(task.candidate_mcp[0])
            primary_domain = domain_enum.value
            
            # 5: Quick intent detection for selection context
            # We don't have tools yet, so we use task text + domain keywords
            domain_intents = IntentTaxonomy.get_intents_for_domain(domain_enum)
            task_lower = task.task.lower()
            for intent, keywords in domain_intents.items():
                if any(kw in task_lower for kw in keywords):
                    primary_intent = intent
                    break
            
        required_caps, optional_caps, _ = self.intent_engine.inference_svc.get_task_required_capabilities(
            primary_domain, task.task, intent=primary_intent
        )
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(task, list(required_caps), list(optional_caps))
        
        try:
            raw_output = self.llm.query(system_prompt, user_prompt)
            data = self._parse_json(raw_output)
            
            # Use paired selections for alignment
            selections = data.get("selections", [])
            selected_mcp = []
            selected_tools = []
            validation_errors = []
            
            # Enforce exactly 3
            if len(selections) > 3:
                selections = selections[:3]
                validation_errors.append("Model returned >3 pairs. Truncated to 3.")
            elif len(selections) < 3 and len(selections) > 0:
                validation_errors.append(f"Model returned only {len(selections)} pairs; expected 3.")
            
            for s in selections:
                selected_mcp.append(s.get("mcp", "Unknown"))
                selected_tools.append(s.get("tool", "Unknown"))
            
            # 6: Explicit Missing Capability Calculation (Final Consistency)
            # We determine what's ACTUALLY missing from the selected tools
            provided_caps = set()
            for tool in selected_tools:
                audit = self.classifier.classify_tools([tool])
                if audit:
                    provided_caps.update(audit[0].get("capabilities", []))
            
            # Mission critical: only flag missing REQUIRED capabilities
            actual_missing = [cap for cap in required_caps if cap not in provided_caps]
            
            prediction = SelectionResult(
                selected_mcp=selected_mcp,
                selected_tools=selected_tools,
                justification=data.get("justification", "No justification provided."),
                confidence=float(data.get("confidence", 0.0)),
                capability_coverage_score=float(data.get("capability_coverage_score", 0.0)),
                missing_capabilities=actual_missing, # 6: Real mission gap
                raw_output=raw_output,
                validation_errors=validation_errors
            )
            
            # Validate
            errors = self._validate_prediction(prediction)
            prediction.validation_errors.extend(errors)
            
            return prediction
        except Exception as e:
            return SelectionResult(
                selected_mcp=[],
                selected_tools=[],
                justification=f"Error during selection: {str(e)}",
                confidence=0.0,
                raw_output=None,
                validation_errors=[str(e)]
            )

    def _build_system_prompt(self) -> str:
        prompt = """
        You are an expert orchestrator for an agentic system that uses Model Context Protocol (MCP) servers. 
        Your task is to select EXACTLY 3 tools and their corresponding MCP servers to fulfill a user request.
        
        This selection is CAPABILITY-AWARE. You must prioritize tools that cover the required capabilities.
        
        Return your answer ONLY in structured JSON format with the following fields:
        {
          "selections": [
            {"tool": "tool_name1", "mcp": "mcp_name1"},
            {"tool": "tool_name2", "mcp": "mcp_name2"},
            {"tool": "tool_name3", "mcp": "mcp_name3"}
          ],
          "justification": "Why you chose these specific 3 tools, focusing on capability coverage.",
          "confidence": 0.85,
          "capability_coverage_score": 0.67,
          "missing_capabilities": []
        }
        
        SCORING RULES:
        - +1.0 for each REQUIRED capability covered by the selected tools.
        - +0.5 for each OPTIONAL capability covered.
        - -1.0 for each IRRELEVANT tool selected that doesn't contribute to the task.
        
        RULES:
        1. Select ONLY from the provided MCP personas and their listed tools.
        2. Do NOT invent new tool names or MCP names.
        3. You MUST select EXACTLY 3 tool-mcp pairs.
        4. ALL 3 tools MUST come from the EXACT SAME MCP server. You cannot mix tools from different MCP servers.
        5. If one tool covers multiple capabilities, that is ideal.
        6. List EACH tool-mcp pair separately, repeating the same MCP server name 3 times.
        7. Confidence and Capability Coverage Score must be between 0.0 and 1.0.
        """
        return prompt

    def _build_user_prompt(self, task: AstraTask, required_caps: List[str], optional_caps: List[str]) -> str:
        persona_context = []
        for p in self.personas:
            p_text = f"MCP Persona: {p.name}\nDescription: {p.description}\nTools:\n"
            for t in p.tools:
                p_text += f" - {t.name}: {t.description}\n"
            persona_context.append(p_text)
            
        context_str = "\n\n".join(persona_context)
        
        user_prompt = f"""
        Available MCP Personas and Tools:
        {context_str}
        
        Inferred Capability Requirements:
        - REQUIRED: {', '.join(required_caps) if required_caps else 'None'}
        - OPTIONAL: {', '.join(optional_caps) if optional_caps else 'None'}
        
        User Task: {task.task}
        
        Please select EXACTLY 3 tool-mcp pairs from a single MCP server that maximize capability coverage for this task.
        """
        return user_prompt

    def _parse_json(self, text: str) -> dict:
        """Robustly parse JSON even if surrounded by markdown code blocks."""
        try:
            # Try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # Look for any { ... } block
            match = re.search(r'(\{.*\})', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            
            raise ValueError("Could not extract valid JSON from LLM output.")

    def _validate_prediction(self, prediction: SelectionResult) -> List[str]:
        errors = []
        # Check lengths
        if len(prediction.selected_tools) != 3:
            errors.append(f"Selection contains {len(prediction.selected_tools)} tools instead of exactly 3.")

        # Check single MCP constraint
        unique_mcps = set(prediction.selected_mcp)
        if len(unique_mcps) > 1:
            errors.append(f"Tools must come from a single MCP server. Found multiple: {list(unique_mcps)}")


        # Check MCP existence and tool-mcp mapping
        for i, (mcp, tool) in enumerate(zip(prediction.selected_mcp, prediction.selected_tools)):
            if mcp not in self.persona_map:
                errors.append(f"Pair {i+1}: Invalid MCP '{mcp}'")
            else:
                persona = self.persona_map[mcp]
                tool_names = [t.name for t in persona.tools]
                if tool not in tool_names:
                    errors.append(f"Pair {i+1}: Tool '{tool}' not found in MCP '{mcp}'")
                
        return errors
