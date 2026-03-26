from typing import List
from pydantic import BaseModel

class AstraTask(BaseModel):
    task: str
    candidate_tools: List[str]
    candidate_mcp: List[str]
    groundtruth_tools: List[str]
    groundtruth_mcp: List[str]
    match_tag: str
