"""Task/MCP-agnostic capability model for TRAC.

A capability is simply ``{domain}:{action}`` where *domain* is the MCP a tool belongs
to and *action* is ``read`` or ``write``. There is **no per-MCP vocabulary, catalog,
ontology, or curated tool→capability map** — everything is derived mechanically from
the tool's MCP and whether it reads or writes, with the single agnostic subsumption
rule that *a write also grants the read* (``{d}:write`` ⊇ ``{d}:read``).

**Coverage is domain-only.** The bundle must operate in the task's declared domain; the
required capability is ``{domain}:read`` (the action floor — any in-domain tool, read or
write, satisfies it). We deliberately do **not** infer read-vs-write *intent* from task
text: that heuristic was substring/POS-fragile (``execut``⊂"executive", ``updat``⊂"updates")
and falsely denied correct read-only bundles. Write concerns are owned by ``write_safety``.

This is the only thing RBAC (persona→tool) and ABAC (attributes) structurally cannot
express — whether the proposed bundle is coherent with the task's domain.
"""
from __future__ import annotations

from typing import Dict, List, Set

from app.services.normalization import normalize_mcp_name


def bundle_capabilities(tool_audit: List[Dict], mcps: List[str]) -> Set[str]:
    """Agnostic capabilities a bundle provides: ``{domain}:{action}`` per tool, with
    ``write`` also yielding the corresponding ``read`` (a write subsumes the read)."""
    caps: Set[str] = set()
    pairs = (
        list(zip(tool_audit, mcps))
        if mcps and len(mcps) == len(tool_audit)
        else [(d, (mcps[0] if mcps else "")) for d in tool_audit]
    )
    for d, m in pairs:
        dom = normalize_mcp_name(m) if m else ""
        if not dom:
            continue
        act = "write" if d.get("is_write") else "read"
        caps.add(f"{dom}:{act}")
        if act == "write":
            caps.add(f"{dom}:read")
    return caps


def required_capability(domain: str) -> Set[str]:
    """Domain-only coverage: the bundle must operate in the task's declared domain.

    Required = ``{domain}:read`` — the action floor. Any in-domain tool satisfies it,
    since a write also grants the read. Read/write *intent* is intentionally not inferred
    from task text; ``write_safety`` owns mutation concerns.
    """
    if not domain or str(domain).lower() in ("uncertain", "unknown", "multi_domain", "all", ""):
        return set()
    return {f"{normalize_mcp_name(domain)}:read"}
