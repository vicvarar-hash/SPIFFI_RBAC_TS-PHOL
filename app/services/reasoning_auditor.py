import json
import logging
from typing import Dict, Any, List
from app.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

class ReasoningAuditor:
    """
    Service for generating post-mortem assessments of reasoning runs.
    """
    
    def __init__(self, llm_provider: LLMProvider = None):
        self.llm = llm_provider or LLMProvider()
        
    def _serialize_sets(self, obj: Any) -> Any:
        """Recursively converts sets to lists for JSON serialization."""
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, dict):
            return {k: self._serialize_sets(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize_sets(v) for v in obj]
        return obj

    def generate_assessment(self, task: str, metadata: Dict[str, Any], decision_data: Dict[str, Any], benchmark_status: str) -> Dict[str, Any]:
        """
        Queries the LLM to audit the reasoning flow.
        """
        
        # Pre-process for JSON safety (convert sets to lists)
        metadata = self._serialize_sets(metadata)
        decision_data = self._serialize_sets(decision_data)

        system_prompt = """
        You are the 'Post-Reasoning Auditor' for an authoritative Zero-Trust pipeline.
        Your mission is to perform a deep-dive analysis of a specific reasoning run (Selection or Validation) and provide the user with a "Post-Mortem Assessment" and "Strategic Recommendations."
        
        ### Output Structure Requirements:
        Your 'sections' MUST follow this intuitive order to align with the system's 3-Phase architecture:
        1. "Phase I: Identity & Context Audit" - Analyze SPIFFE ID stability, mTLS context, and attribute veracity.
        2. "Phase II: Inference & Mission Alignment" - Evaluate the LLM's tool choices/validation reasoning against the user task.
        3. "Phase III: Logical Authority & TS-PHOL Trace" - Critique the formal rules triggered and the logical finality.
        4. "Research Benchmark Analysis" - Reconcile the results with the ASTRA Groundtruth.
        
        ### Recommendation Requirements:
        Your 'recommendations' MUST be highly specific and actionable. Avoid generic advice like "Improve security."
        - INSTEAD USE: "Harden ABAC rule 'trait_mismatch' to require a TrustScore > 0.8 for this persona."
        - INSTEAD USE: "Update DomainCapabilityOntology to include 'GeographicAnalysis' for the 'Wikipedia' domain."
        - INSTEAD USE: "Relax TS-PHOL rule 'domain_mismatch' when 'SelectionTolerance' is active to prevent false-positives in research tasks."
        
        Provide a JSON response:
        {
          "summary": "Short 1-sentence summary of the assessment.",
          "sections": [
            {"title": "Phase I: Identity & Context Audit", "content": "..."},
            {"title": "Phase II: Inference & Mission Alignment", "content": "..."},
            {"title": "Phase III: Logical Authority & TS-PHOL Trace", "content": "..."},
            {"title": "Research Benchmark Analysis", "content": "..."}
          ],
          "recommendations": ["Clear Actionable Step 1", "Clear Actionable Step 2"]
        }
        
        Focus on logic reconciliation: If the benchmark shows a Mismatch but the logic shows ALLOW, explain the specific logical gap.
        """
        
        user_prompt = f"""
        TASK: {task}
        METADATA: {json.dumps(metadata, indent=2)}
        DECISION_DATA: {json.dumps(decision_data, indent=2)}
        BENCHMARK_STATUS: {benchmark_status}
        
        AUDIT REQUEST: Please analyze this run and provide a technical assessment and policy improvement recommendations.
        """
        
        try:
            raw_output = self.llm.query(system_prompt, user_prompt)
            data = json.loads(raw_output)
            return data
        except Exception as e:
            logger.error(f"Auditor failed: {str(e)}")
            return {
                "summary": "Error generating audit report.",
                "sections": [{"title": "Error", "content": str(e)}],
                "recommendations": ["Check LLM configuration."]
            }
