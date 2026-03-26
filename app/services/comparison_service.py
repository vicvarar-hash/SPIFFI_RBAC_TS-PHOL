from typing import Set, List
from app.models.astra import AstraTask
from app.models.comparison import ComparisonResult

class ComparisonService:
    def compare(self, gt_mcp: List[str], gt_tools: List[str], pred_mcp: List[str], pred_tools: List[str]) -> ComparisonResult:
        s_pred_mcp = set(pred_mcp)
        s_gt_mcp = set(gt_mcp)
        
        s_pred_tools = set(pred_tools)
        s_gt_tools = set(gt_tools)
        
        mcp_match = (s_pred_mcp == s_gt_mcp)
        tool_match = (s_pred_tools == s_gt_tools)
        
        mcp_overlap = self._overlap(s_pred_mcp, s_gt_mcp)
        tool_overlap = self._overlap(s_pred_tools, s_gt_tools)
        
        if mcp_match and tool_match:
            status = "exact_match"
        elif mcp_overlap > 0 or tool_overlap > 0:
            status = "partial_match"
        else:
            status = "mismatch"
            
        details = f"MCP Overlap Score: {round(mcp_overlap, 2)}. Tool Overlap Score: {round(tool_overlap, 2)}."
        
        return ComparisonResult(
            mcp_match=mcp_match,
            tool_match=tool_match,
            mcp_overlap=mcp_overlap,
            tool_overlap=tool_overlap,
            status=status,
            details=details
        )

    def _overlap(self, set1: Set[str], set2: Set[str]) -> float:
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0
        return len(set1 & set2) / len(set1 | set2)
