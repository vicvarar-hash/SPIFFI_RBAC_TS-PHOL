import re
from typing import Optional

def normalize_tool_name(raw: str) -> str:
    """Normalizes a tool name (e.g. from 'Some Tool-Name ' to 'some_tool_name')."""
    if not raw:
        return ""
    normalized = raw.lower().strip()
    # Replace spaces and dashes with underscores
    normalized = re.sub(r'[\s\-]+', '_', normalized)
    return normalized

def normalize_mcp_name(raw: str) -> str:
    """Normalizes an MCP name."""
    if not raw:
        return ""
    normalized = raw.lower().strip()
    normalized = re.sub(r'[\s\-]+', '_', normalized)
    return normalized

def normalize_domain_name(raw: str) -> str:
    """Normalizes a domain representation specifically for alignment mapping."""
    if not raw:
        return "uncertain"
    normalized = raw.lower().strip()
    return normalized
