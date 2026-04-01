from typing import List, Optional, Dict
from pydantic import BaseModel

class ValidationResult(BaseModel):
    is_valid: bool
    confidence: float
    reason: str
    issues: List[str] = []
    expected_domain: str = "Unknown"
    actual_domain: str = "Unknown"
    task_alignment_score: float = 0.0
    task_alignment_details: Dict[str, float] = None # 4O: Transparency breakdown
    issue_codes: List[str] = []
    raw_output: Optional[str] = None
