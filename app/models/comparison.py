from typing import List
from pydantic import BaseModel

class ComparisonResult(BaseModel):
    mcp_match: bool
    tool_match: bool
    mcp_overlap: float  # (intersect / union)
    tool_overlap: float # (intersect / union)
    status: str # "exact_match", "partial_match", "mismatch"
    details: str
