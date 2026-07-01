"""L1 evaluation: name-based action classification vs MCP annotations (description-level).

The current classifier infers read/write/delete from the tool NAME (curated map + prefix
heuristics). MCP tool metadata carries author-declared `readOnlyHint` / `destructiveHint`
(plus a description). This measures how many dataset tools the name-only path misclassifies
relative to those hints — split into the dangerous direction (name=read but actually a
write/destructive op) and the over-strict direction (name=write but actually read).
"""
import glob, json, os, sys
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services.tool_classifier import ToolClassifier
from app.services.normalization import normalize_tool_name
from app.loaders.astra_loader import load_astra_dataset


def main():
    # 1. registry: normalized tool -> annotation hints + description
    reg = {}
    for p in glob.glob("mcp_servers/*.json"):
        d = json.load(open(p, encoding="utf-8"))
        for t in d.get("tools", []):
            nm = normalize_tool_name(t.get("name", ""))
            ann = t.get("annotations") or {}
            reg[nm] = {"readOnly": ann.get("readOnlyHint"),
                       "destructive": ann.get("destructiveHint"),
                       "desc": (t.get("description") or "").strip()}

    # 2. unique tools actually used by the dataset (candidate + groundtruth)
    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    dataset_tools = set()
    for t in tasks:
        for tool in list(getattr(t, "candidate_tools", []) or []) + list(getattr(t, "groundtruth_tools", []) or []):
            dataset_tools.add(normalize_tool_name(tool))

    covered = [x for x in dataset_tools if x in reg]
    annotated = [x for x in covered if reg[x]["readOnly"] is not None]
    print("dataset unique tools: %d | in MCP registry: %d | with readOnlyHint: %d"
          % (len(dataset_tools), len(covered), len(annotated)))

    clf = ToolClassifier()
    write_mismatch, delete_mismatch = [], []
    for tool in annotated:
        audit = clf.classify_tools([tool])[0]
        name_write = bool(audit["is_write"])
        name_delete = "delete" in (audit.get("actions") or [])
        a = reg[tool]
        anno_write = not bool(a["readOnly"])
        anno_destr = bool(a["destructive"])
        if name_write != anno_write:
            write_mismatch.append((tool, name_write, anno_write, a["desc"]))
        if name_delete != anno_destr:
            delete_mismatch.append((tool, name_delete, anno_destr, a["desc"]))

    n = len(annotated)
    print("\n=== WRITE-CLASS: name vs annotation ===")
    print("mismatches: %d / %d (%.1f%%)" % (len(write_mismatch), n, 100*len(write_mismatch)/n if n else 0))
    danger = [m for m in write_mismatch if not m[1] and m[2]]   # name=read, actually write
    overs = [m for m in write_mismatch if m[1] and not m[2]]    # name=write, actually read
    print("  DANGEROUS  name=read but actually WRITE: %d  (ABAC write-gates + write_safety would miss these)" % len(danger))
    for tool, _, _, desc in danger[:15]:
        print("     %-34s :: %s" % (tool, desc[:72]))
    print("  OVER-STRICT name=write but actually READ: %d  (over-denies / false write concern)" % len(overs))
    for tool, _, _, desc in overs[:10]:
        print("     %-34s :: %s" % (tool, desc[:72]))

    print("\n=== DESTRUCTIVE-CLASS: name 'delete' vs annotation destructiveHint ===")
    print("mismatches: %d / %d" % (len(delete_mismatch), n))
    missed = [m for m in delete_mismatch if not m[1] and m[2]]  # name missed a destructive op
    extra = [m for m in delete_mismatch if m[1] and not m[2]]   # name over-flagged
    print("  name MISSED destructive (write_safety advisory would not fire): %d" % len(missed))
    for tool, _, _, desc in missed[:15]:
        print("     %-34s :: %s" % (tool, desc[:72]))
    print("  name OVER-flagged destructive: %d" % len(extra))
    for tool, _, _, desc in extra[:10]:
        print("     %-34s :: %s" % (tool, desc[:72]))

    # ── Description-keyword classifier (works for ALL tools, not just annotated) ──
    DESTRUCTIVE_KW = ("delete", "remove", "drop", "purge", "destroy", "truncate", "erase", "clear")
    WRITE_KW = DESTRUCTIVE_KW + ("create", "update", "modify", "set ", "add ", "insert",
                                 "rename", "move", "edit", "post", "put ", "patch", "write",
                                 "send", "publish", "cancel", "refund", "execute", "place ")

    def desc_class(desc):
        d = " " + desc.lower() + " "
        return (any(k in d for k in WRITE_KW), any(k in d for k in DESTRUCTIVE_KW))

    name_vs_desc_write, name_vs_desc_destr = [], []
    desc_vs_anno_agree = desc_vs_anno_total = 0
    for tool in covered:
        audit = clf.classify_tools([tool])[0]
        name_write = bool(audit["is_write"])
        name_delete = "delete" in (audit.get("actions") or [])
        dw, dd = desc_class(reg[tool]["desc"])
        if name_write != dw:
            name_vs_desc_write.append((tool, name_write, dw, reg[tool]["desc"]))
        if name_delete != dd:
            name_vs_desc_destr.append((tool, name_delete, dd, reg[tool]["desc"]))
        # precision proxy: where an annotation exists, does the description-class agree?
        if reg[tool]["readOnly"] is not None:
            desc_vs_anno_total += 1
            if dw == (not reg[tool]["readOnly"]) and dd == bool(reg[tool]["destructive"]):
                desc_vs_anno_agree += 1

    print("\n=== DESCRIPTION-KEYWORD classifier over ALL %d covered tools ===" % len(covered))
    print("description-vs-annotation agreement (precision proxy): %d/%d (%.1f%%)"
          % (desc_vs_anno_agree, desc_vs_anno_total, 100*desc_vs_anno_agree/desc_vs_anno_total if desc_vs_anno_total else 0))
    dgr = [m for m in name_vs_desc_write if not m[1] and m[2]]
    print("name=read but DESCRIPTION says WRITE: %d (dangerous misses across full tool set)" % len(dgr))
    for tool, _, _, desc in dgr[:20]:
        print("     %-34s :: %s" % (tool, desc[:72]))
    dmiss = [m for m in name_vs_desc_destr if not m[1] and m[2]]
    print("name missed DESTRUCTIVE but description flags it: %d" % len(dmiss))
    for tool, _, _, desc in dmiss[:20]:
        print("     %-34s :: %s" % (tool, desc[:72]))


if __name__ == "__main__":
    main()
