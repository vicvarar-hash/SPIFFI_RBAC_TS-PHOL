"""Prototype: deterministic VERB-LEXICON action classifier over (name + description).

Transparent, dependency-free, auditable: find the description's leading action verb
(lemmatised, word-boundary), map it via curated agnostic lexicons, read-guard ambiguous
verbs (execute/run a *query* -> read), and fuse the name (escalate-only to destructive).
Measured against (a) the current name classifier and (b) MCP author annotations.
"""
import glob, json, os, re, sys
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services.tool_classifier import ToolClassifier
from app.services.normalization import normalize_tool_name
from app.loaders.astra_loader import load_astra_dataset

DESTRUCTIVE = {"delete", "remove", "drop", "purge", "truncate", "erase", "destroy",
               "wipe", "discard", "clear", "uninstall"}
WRITE = DESTRUCTIVE | {"create", "update", "set", "add", "insert", "rename", "move",
                       "edit", "modify", "post", "put", "patch", "send", "publish",
                       "write", "register", "assign", "link", "unlink", "transition",
                       "comment", "label", "lock", "unlock", "finalize", "place",
                       "enable", "disable", "start", "stop", "restart", "deploy",
                       "configure", "apply", "save", "upload", "attach", "approve",
                       "reject", "merge", "close", "reopen", "schedule", "trigger",
                       "cancel", "refund", "generate", "connect", "import", "export"}
# generate/connect/export are read operations (see READ); strip them from WRITE so the
# WRITE branch (checked before READ) does not mis-escalate them.
WRITE -= {"generate", "connect", "export"}
READ = {"get", "list", "search", "find", "read", "query", "describe", "fetch",
        "retrieve", "show", "view", "summarize", "summarise", "explore", "count",
        "check", "analyze", "analyse", "inspect", "monitor", "watch", "explain",
        "lookup", "download", "aggregate", "profile", "validate", "compare",
        "predict", "calculate", "return", "extract", "browse", "scan",
        # read-ish verbs that do not mutate state (per MCP annotations): producing a
        # URL/link, opening a connection, or exporting results are all read operations.
        "generate", "connect", "export"}
AMBIGUOUS = {"execute", "run", "perform", "manage", "handle", "process", "batch"}
READ_NOUNS = {"query", "search", "report", "analysis", "aggregation", "statistic",
              "summary", "profile", "metric", "log", "detail", "information", "data",
              "status", "history", "changelog", "schema", "index", "result"}
ALL_VERBS = WRITE | READ | AMBIGUOUS


def lemma(w):
    w = w.lower()
    for suf in ("ing", "es", "ed", "s"):
        if w.endswith(suf) and (w[:-len(suf)] in ALL_VERBS):
            return w[:-len(suf)]
    return w


def verb_classify(name, description):
    toks = re.findall(r"[a-zA-Z]+", description or "")[:12]
    verbs = [lemma(t) for t in toks if lemma(t) in ALL_VERBS]
    cls = None
    if verbs:
        head = verbs[0]
        if head in DESTRUCTIVE:
            cls = "destructive"
        elif head in AMBIGUOUS:
            cls = "read" if any(n in (description or "").lower() for n in READ_NOUNS) else "write"
        elif head in WRITE:
            cls = "write"
        elif head in READ:
            cls = "read"
    # escalate-only to destructive if any destructive verb appears in the window or name
    if any(v in DESTRUCTIVE for v in verbs):
        cls = "destructive"
    segs = [lemma(s) for s in re.split(r"[_\-]+", name or "")]
    if any(s in DESTRUCTIVE for s in segs):
        cls = "destructive"
    elif cls is None and any(s in WRITE for s in segs):
        cls = "write"
    elif cls is None and any(s in READ for s in segs):
        cls = "read"
    if cls is None:
        cls = "read"  # conservative-for-availability default; flagged as lexicon gap
    return cls in ("write", "destructive"), cls == "destructive", bool(verbs or any(s in ALL_VERBS for s in segs))


def main():
    reg = {}
    for p in glob.glob("mcp_servers/*.json"):
        for t in json.load(open(p, encoding="utf-8")).get("tools", []):
            ann = t.get("annotations") or {}
            reg[normalize_tool_name(t.get("name", ""))] = {
                "name": t.get("name", ""), "desc": (t.get("description") or "").strip(),
                "readOnly": ann.get("readOnlyHint"), "destructive": ann.get("destructiveHint")}

    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    tools = set()
    for t in tasks:
        for x in list(getattr(t, "candidate_tools", []) or []) + list(getattr(t, "groundtruth_tools", []) or []):
            tools.add(normalize_tool_name(x))
    covered = [x for x in tools if x in reg]
    clf = ToolClassifier()

    # accuracy vs annotation (ground-truth subset)
    name_w_ok = name_d_ok = verb_w_ok = verb_d_ok = anno_n = 0
    no_verb = 0
    fixes_write, fixes_destr, regress = [], [], []
    for tool in covered:
        a = reg[tool]
        audit = clf.classify_tools([tool])[0]
        nw, nd = bool(audit["is_write"]), "delete" in (audit.get("actions") or [])
        vw, vd, recognised = verb_classify(a["name"], a["desc"])
        if not recognised:
            no_verb += 1
        if a["readOnly"] is not None:
            anno_n += 1
            aw, ad = (not a["readOnly"]), bool(a["destructive"])
            name_w_ok += (nw == aw); name_d_ok += (nd == ad)
            verb_w_ok += (vw == aw); verb_d_ok += (vd == ad)
            if nw != aw and vw == aw:
                fixes_write.append((tool, aw, a["desc"]))
            if nw == aw and vw != aw:
                regress.append((tool, aw, vw, a["desc"]))
            if nd != ad and vd == ad:
                fixes_destr.append((tool, a["desc"]))

    print("covered tools: %d | annotated (ground truth): %d | verb-unrecognised: %d"
          % (len(covered), anno_n, no_verb))
    print("\n=== ACCURACY vs MCP annotations (n=%d) ===" % anno_n)
    print("  WRITE-class   : name %.1f%%  ->  verb %.1f%%"
          % (100*name_w_ok/anno_n, 100*verb_w_ok/anno_n))
    print("  DESTRUCTIVE   : name %.1f%%  ->  verb %.1f%%"
          % (100*name_d_ok/anno_n, 100*verb_d_ok/anno_n))
    print("\nverb FIXES name's write-class errors: %d" % len(fixes_write))
    for tool, aw, desc in fixes_write[:12]:
        print("   %-32s truth=%s :: %s" % (tool, "WRITE" if aw else "read", desc[:60]))
    print("verb FIXES name's destructive errors: %d" % len(fixes_destr))
    for tool, desc in fixes_destr[:12]:
        print("   %-32s :: %s" % (tool, desc[:60]))
    print("verb REGRESSES (name right, verb wrong): %d" % len(regress))
    for tool, aw, vw, desc in regress[:12]:
        print("   %-32s truth=%s verb=%s :: %s" % (tool, aw, vw, desc[:55]))

    # the specific "execute a query" reads that the naive substring version mis-flagged
    print("\n=== read-guard check: 'execute/run query' tools ===")
    for tool in ("azmcp_monitor_log_query", "query_loki_logs", "azmcp_cosmos_database_container_item_query",
                 "jira_get_issue", "get_orders"):
        nt = normalize_tool_name(tool)
        if nt in reg:
            vw, vd, _ = verb_classify(reg[nt]["name"], reg[nt]["desc"])
            print("   %-42s verb-> write=%s destr=%s (want read)" % (tool, vw, vd))


if __name__ == "__main__":
    main()
