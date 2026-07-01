"""Emit the verb -> VerbNet/Levin/FrameNet derivation table for the paper appendix.

Provenance is anchored at the class level (Levin class + FrameNet frame — high confidence);
per-verb VerbNet class IDs are given where the verb is a canonical member of a general-English
VerbNet class, and marked 'verify' otherwise. Technical/neologistic verbs (deploy, configure,
trigger, …) are not Levin/VerbNet members and are assigned by their nearest FrameNet frame.

CAVEAT: confirm every VerbNet class id against the VerbNet browser (verbs.colorado.edu)
before publication — this table is a derivation scaffold, not a verified citation.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))
import app.services.verb_action_classifier as vac

# group -> (operation class, Levin class, FrameNet frame, canonical VerbNet class family)
GROUP_META = {
    "_REMOVING":        ("destructive", "10 Verbs of Removing",            "Removing",            "remove-10.1 / clear-10.3 / wipe-10.4 / destroy-44"),
    "_CREATION":        ("write",       "26 Creation & Transformation",    "Intentionally_create","build-26.1 / create-26.4"),
    "_CHANGE_OF_STATE": ("write",       "45 Verbs of Change of State",     "Cause_change",        "other_cos-45.4"),
    "_PLACEMENT":       ("write",       "9 Put Verbs",                     "Placing",             "put-9.1"),
    "_COMMUNICATION":   ("write",       "11 Verbs of Sending & Carrying",  "Sending",             "send-11.1"),
    "_ACQUISITION":     ("read",        "13.5.1 Get Verbs",                "Getting",             "get-13.5.1"),
    "_PERCEPTION":      ("read",        "30 Verbs of Perception",          "Perception_active",   "see-30.1 / sight-30.2"),
    "_SEARCHING":       ("read",        "35 Verbs of Searching",           "Scrutiny / Seeking",  "search-35.2 / hunt-35.1"),
    "_EPHEMERAL":       ("read",        "(non-persisting effect)",         "(Getting/Operating)", "n/a — see note"),
    "AMBIGUOUS":        ("ambiguous",   "light/support verbs",             "(object-dependent)",  "n/a — resolved by SRL read-guard"),
}

# Per-verb VerbNet class id where the verb is a confident canonical member; else "".
VERBNET_ID = {
    "remove": "remove-10.1", "delete": "remove-10.1", "discard": "remove-10.1",
    "erase": "wipe-10.4.1", "wipe": "wipe-10.4.1", "clear": "clear-10.3",
    "destroy": "destroy-44", "drop": "remove-10.1", "purge": "remove-10.1",
    "create": "create-26.4", "add": "mix-22.1-1", "insert": "put-9.1",
    "send": "send-11.1", "post": "send-11.1", "move": "send-11.1",
    "put": "put-9.1", "place": "put-9.1", "set": "put-9.1",
    "get": "get-13.5.1", "fetch": "get-13.5.1", "retrieve": "get-13.5.1", "extract": "get-13.5.1",
    "see": "see-30.1", "view": "see-30.1", "watch": "see-30.1", "monitor": "see-30.1",
    "search": "search-35.2", "find": "search-35.2", "explore": "search-35.2",
    "read": "see-30.1", "write": "scribble-25.2",
}


def main():
    print("| verb | op class | Levin class | FrameNet frame | VerbNet class | source |")
    print("|---|---|---|---|---|---|")
    rows = 0
    for grp, (opc, levin, frame, vn_family) in GROUP_META.items():
        members = sorted(getattr(vac, grp))
        for v in members:
            vid = VERBNET_ID.get(v, "")
            if vid:
                src = "VerbNet canonical"
            elif opc == "ambiguous":
                src = "light verb (SRL)"
            elif grp == "_EPHEMERAL":
                src = "frame-assigned (read-side)"
            else:
                src = "frame-assigned (verify)"
            print("| %s | %s | %s | %s | %s | %s |"
                  % (v, opc, levin, frame, vid or vn_family, src))
            rows += 1
    print("\n_%d verbs. VerbNet ids marked 'verify' are assigned by Levin class + FrameNet "
          "frame; confirm exact subclass against the VerbNet browser before publication._" % rows)


if __name__ == "__main__":
    main()
