"""Conservative, deterministic task-action intent from the natural-language task text.

This is the *task* half of an action-coherence check: the tool-bundle's action class is
already derived cleanly by the VerbNet-grounded ``verb_action_classifier`` (which reads the
crisp, imperative tool *descriptions*). Task text is far noisier — "give me an updated
report" reads like a write but is a read — so this classifier is deliberately
HIGH-PRECISION / abstain-by-default and is meant to feed an **advisory**, never a hard deny:

    a task is "read-only intent" ONLY when it contains a read/interrogative marker AND
    NO write/destructive marker.

Any mutation signal makes it abstain (returns False), so a genuine write task never trips
the advisory. The marker sets are **derived from the single VerbNet-grounded lexicon**
(``verb_action_classifier``) so there is one source of verb semantics; task phrasing adds
only the non-verb interrogative / nominal cues that mark a read request.
"""
import re

from app.services.verb_action_classifier import (
    READ as _VN_READ,
    WRITE as _VN_WRITE,
    AMBIGUOUS as _VN_AMBIGUOUS,
)

# Non-verb read cues specific to task phrasing (interrogatives + nominal asks). These are not
# verbs, so they legitimately live here rather than in the verb lexicon.
_READ_CUES = {
    "what", "which", "how", "when", "where", "who", "why",
    "report", "tell", "status", "overview", "details", "information",
}

# Read-intent markers: the VerbNet READ class + task-phrasing interrogative / nominal cues.
READ_MARKERS = _VN_READ | _READ_CUES

# Mutation markers: any VerbNet write/destructive verb, plus the ambiguous light verbs
# (execute/run/perform/…) — present in task text these signal "do something", so abstain.
WRITE_MARKERS = _VN_WRITE | _VN_AMBIGUOUS


def task_readonly_intent(task_text: str) -> bool:
    """True iff the task clearly reads (has a read marker) and shows no mutation marker."""
    toks = set(re.findall(r"[a-z]+", (task_text or "").lower()))
    return bool(toks & READ_MARKERS) and not bool(toks & WRITE_MARKERS)
