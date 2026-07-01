"""End-to-end OPA demo: Python evidence extraction -> Rego decision over the data dictionary.

Shows the verb lexicon living as an OPA `data` document and the classification done by
real `opa eval`, agreeing with the in-process Python classifier.
"""
import json, os, re, subprocess, sys
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.abspath("."))

import app.services.verb_action_classifier as vac

OPA = os.path.join(os.environ.get("TEMP", "."), "opa.exe")
INPUT = os.path.join(__import__("tempfile").gettempdir(), f"_opa_demo_{os.getpid()}.json")
TOOLS = {
    "drop-database": "Removes the specified database, deleting the associated data files",
    "azmcp-monitor-log-query": "Execute a KQL query against a Log Analytics workspace. Requires workspace.",
    "rename-collection": "Renames a collection in a MongoDB database",
    "jira_get_issue": "Get details of a specific Jira issue including its Epic links",
    "jira_create_issue": "Create a new Jira issue in a project",
    "delete-many": "Removes all documents that match the filter from a MongoDB collection",
}


def extract(name, desc):
    toks = re.findall(r"[a-zA-Z]+", desc)[:12]
    verbs = [vac._lemma(t) for t in toks if vac._lemma(t) in vac.ALL_VERBS]
    segs = [vac._lemma(s) for s in re.split(r"[_\-]+", name)]
    return {"tool": {"head_verb": verbs[0] if verbs else "", "verbs": verbs,
                     "name_segments": segs, "description_lower": desc.lower()}}


def opa_class(inp):
    with open(INPUT, "w", encoding="utf-8") as f:
        json.dump(inp, f)
    r = subprocess.run([OPA, "eval", "-d", "policies/rego/action_classifier.rego",
                        "-d", "policies/rego/data/action_lexicon.json", "-i", INPUT,
                        "-f", "raw", "data.paladin.action.action_class"],
                       capture_output=True, text=True)
    return (r.stdout.strip() or r.stderr.strip())


def main():
    print("%-26s %-12s %-12s %s" % ("tool", "OPA/Rego", "Python", "agree"))
    ok = True
    for name, desc in TOOLS.items():
        rego = opa_class(extract(name, desc))
        vw, vd, _ = vac.classify_action(name, desc)
        py = "destructive" if vd else ("write" if vw else "read")
        agree = rego == py
        ok = ok and agree
        print("%-26s %-12s %-12s %s" % (name, rego, py, "OK" if agree else "MISMATCH"))
    if os.path.exists(INPUT):
        os.remove(INPUT)
    print("\nALL AGREE:" , ok)


if __name__ == "__main__":
    main()
