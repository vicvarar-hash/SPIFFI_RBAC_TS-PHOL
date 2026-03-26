from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class MCPTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = Field(None, alias="inputSchema")

    class Config:
        populate_by_name = True

class MCPPersona(BaseModel):
    name: str
    description: Optional[str] = None
    tools: List[MCPTool] = []
    risk_level: str = "unknown"
    source_file: Optional[str] = None
