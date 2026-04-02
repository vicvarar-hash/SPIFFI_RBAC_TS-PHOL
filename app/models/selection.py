from typing import List, Optional
from pydantic import BaseModel

class SelectionResult(BaseModel):
    selected_mcp: List[str]
    selected_tools: List[str]
    justification: str
    confidence: float
    capability_coverage_score: float = 0.0 # 5: Selection coverage score
    missing_capabilities: List[str] = []   # 5: Missing from requested set
    raw_output: Optional[str] = None
    validation_errors: List[str] = []
