from typing import List, Optional
from pydantic import BaseModel

class SelectionResult(BaseModel):
    selected_mcp: List[str]
    selected_tools: List[str]
    justification: str
    confidence: float
    raw_output: Optional[str] = None
    validation_errors: List[str] = []
