from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class DecisionResult(BaseModel):
    spiffe_id: str
    spiffe_verified: bool
    transport_allowed: bool
    rbac_allowed: bool
    tsphol_decision: str  # "allow", "deny", "flag"
    final_decision: str  # "ALLOW", "DENY", "FLAG"
    reason: str
    trace: List[str]
    context: Optional[Dict[str, Any]] = None
