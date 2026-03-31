from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class DecisionResult(BaseModel):
    spiffe_id: str
    
    # State tracking: ALLOW, DENY, NOT_EVALUATED
    evaluation_states: Dict[str, str] = {
        "identity": "NOT_EVALUATED",
        "transport": "NOT_EVALUATED",
        "rbac": "NOT_EVALUATED",
        "abac": "NOT_EVALUATED",
        "tsphol": "NOT_EVALUATED"
    }
    
    # Legacy flags for UI rendering backward-compatibility if needed, but we should use states
    spiffe_verified: bool
    transport_allowed: bool
    rbac_allowed: bool
    tsphol_decision: str  # "allow", "deny", "flag", "not_evaluated"
    
    final_decision: str  # "ALLOW", "DENY", "FLAG", "NOT_EVALUATED"
    reason: str
    denial_source: Optional[str] = None
    trace: List[str]
    context: Optional[Dict[str, Any]] = None
    
    # Pipeline 4A.2 transparency features
    pre_llm_result: Optional[bool] = None
    llm_executed: bool = False
    llm_output: Optional[Dict[str, Any]] = None
    derived_features: Optional[Dict[str, Any]] = None
