"""Parity check: the grounded production lexicon must classify identically to before."""
import glob, json, os, sys
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

from app.services import verb_action_classifier as vac
from app.services.normalization import normalize_tool_name
from app.loaders.astra_loader import load_astra_dataset

# 1. Exact set membership must equal the pre-grounding lexicon.
EXP_DESTRUCTIVE = {"delete","remove","drop","purge","truncate","erase","destroy","wipe","discard","clear","uninstall"}
EXP_WRITE = (EXP_DESTRUCTIVE | {"create","update","set","add","insert","rename","move","edit","modify","post","put",
    "patch","send","publish","write","register","assign","link","unlink","transition","comment","label","lock",
    "unlock","finalize","place","enable","disable","start","stop","restart","deploy","configure","apply","save",
    "upload","attach","approve","reject","merge","close","reopen","schedule","trigger","cancel","refund","import"})
EXP_READ = {"get","list","search","find","read","query","describe","fetch","retrieve","show","view","summarize",
    "summarise","explore","count","check","analyze","analyse","inspect","monitor","watch","explain","lookup",
    "download","aggregate","profile","validate","compare","predict","calculate","return","extract","browse","scan",
    "generate","connect","export"}
EXP_AMBIG = {"execute","run","perform","manage","handle","process","batch"}
print("DESTRUCTIVE identical:", vac.DESTRUCTIVE == EXP_DESTRUCTIVE)
print("WRITE identical:      ", vac.WRITE == EXP_WRITE, "| diff:", vac.WRITE ^ EXP_WRITE)
print("READ identical:       ", vac.READ == EXP_READ, "| diff:", vac.READ ^ EXP_READ)
print("AMBIGUOUS identical:  ", vac.AMBIGUOUS == EXP_AMBIG)

# 2. Accuracy vs annotations using the shipped module classify_action.
reg = {}
for p in glob.glob("mcp_servers/*.json"):
    for t in json.load(open(p, encoding="utf-8")).get("tools", []):
        ann = t.get("annotations") or {}
        reg[normalize_tool_name(t.get("name",""))] = {"name": t.get("name",""), "desc": (t.get("description") or "").strip(),
            "ro": ann.get("readOnlyHint"), "de": ann.get("destructiveHint")}
tasks = load_astra_dataset("datasets/astra_03_tools.json")
tools = set()
for t in tasks:
    for x in list(getattr(t,"candidate_tools",[]) or []) + list(getattr(t,"groundtruth_tools",[]) or []):
        tools.add(normalize_tool_name(x))
ann = [x for x in tools if x in reg and reg[x]["ro"] is not None]
w_ok = d_ok = 0
for x in ann:
    vw, vd, _ = vac.classify_action(reg[x]["name"], reg[x]["desc"])
    w_ok += (vw == (not reg[x]["ro"])); d_ok += (vd == bool(reg[x]["de"]))
print("\nvs annotations (n=%d): WRITE %.1f%% | DESTRUCTIVE %.1f%%" % (len(ann), 100*w_ok/len(ann), 100*d_ok/len(ann)))
for tl in ("drop_database","azmcp_monitor_log_query","jira_get_issue","rename_collection"):
    n = normalize_tool_name(tl)
    if n in reg:
        vw, vd, mv = vac.classify_action(reg[n]["name"], reg[n]["desc"])
        print("  %-26s write=%-5s destr=%-5s verb=%s" % (tl, vw, vd, mv))
