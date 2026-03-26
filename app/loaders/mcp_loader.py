import json
import os
from typing import List, Tuple
from app.models.mcp import MCPPersona, MCPTool

def load_mcp_personas(directory_path: str) -> Tuple[List[MCPPersona], List[str]]:
    if not os.path.isdir(directory_path):
        raise NotADirectoryError(f"MCP directory not found at {directory_path}")
    
    personas = []
    errors = []
    for filename in os.listdir(directory_path):
        if filename.endswith(".json"):
            file_path = os.path.join(directory_path, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Normalize tools
                tools = []
                for tool_data in data.get("tools", []):
                    # Basic mapping to handle potential schema variations
                    tools.append(MCPTool(
                        name=tool_data.get("name", "unnamed_tool"),
                        description=tool_data.get("description"),
                        inputSchema=tool_data.get("inputSchema") or tool_data.get("input_schema")
                    ))
                
                persona = MCPPersona(
                    name=data.get("name", os.path.splitext(filename)[0]),
                    description=data.get("description"),
                    tools=tools,
                    risk_level=data.get("risk_level", "unknown"),
                    source_file=filename
                )
                personas.append(persona)
            except Exception as e:
                errors.append(f"Error loading {filename}: {str(e)}")
    
    return personas, errors
