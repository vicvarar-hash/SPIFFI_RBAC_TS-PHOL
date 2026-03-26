from typing import List, Optional
from pydantic import BaseModel

class ValidationResult(BaseModel):
    is_valid: bool
    confidence: float
    reason: str
    issues: List[str] = []
    raw_output: Optional[str] = None
