"""Shared widget for selecting RA-ICL exemplar count.

Returns a :class:`RAICLChoice` describing how to build the retriever.
The widget is **mode-aware**:

* ``selection`` — the model must infer both the MCP and the tools. Using
  in-domain exemplars would leak the answer (every exemplar would carry
  the same ``Correct MCP: <X>`` label). We therefore only expose
  percentages of the *full* train pool drawn uniformly across all MCPs
  (``random_any`` strategy).

* ``validation`` — the candidate bundle already declares its MCP in the
  input. In-domain retrieval mirrors what the model already sees, so
  fixed-K in-domain options remain available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import streamlit as st


# Large sentinel; safely exceeds any per-domain pool (~90) and full train
# pool (~405). Used for "All …" options where we want the retriever to
# return its entire candidate list.
_HUGE = 10_000


@dataclass(frozen=True)
class RAICLChoice:
    """Result of a RA-ICL selectbox render.

    Attributes
    ----------
    label : str
        Human-readable label suitable for result tagging / info messages.
    strategy : str
        Retrieval strategy: ``"random_in_domain"`` or ``"random_any"``.
    pad_cross_domain : bool
        Forwarded to :class:`ExemplarRetriever`. Only meaningful when
        ``strategy == "random_in_domain"``.
    _k_literal : Optional[int]
        Exact K (e.g. 3, 10, 25, _HUGE for "all …").
    _fraction : Optional[float]
        Fraction of train pool; resolved at retriever build time.
    """

    label: str
    strategy: str
    pad_cross_domain: bool
    _k_literal: Optional[int] = None
    _fraction: Optional[float] = None

    def resolve_k(self, train_pool_size: int) -> int:
        """Compute the actual K to pass to ExemplarRetriever."""
        if self._fraction is not None:
            return max(1, int(round(self._fraction * train_pool_size)))
        if self._k_literal is not None:
            return self._k_literal
        return 0


# ── Option catalogues per mode ─────────────────────────────────────────

# Selection mode: only fair options are cross-domain (no MCP leak). We
# offer percentages of the train pool plus full pool. "0 (test cohort)"
# is the K=0 baseline that still applies the 70/30 split so it is
# directly comparable to K>0 runs.
SELECTION_OPTIONS = ["0 (test cohort)", "25% train", "50% train", "75% train", "All train"]

# Validation mode: bundle already declares MCP, so in-domain retrieval
# is fair. Percentage options (random_any) are also offered so validation
# K-curves can be compared directly against selection K-curves.
VALIDATION_OPTIONS = [
    "0 (test cohort)",
    "3", "10", "25", "All in-domain",
    "25% train", "50% train", "75% train", "All train",
]


def _resolve(choice: str) -> RAICLChoice:
    """Map a raw selectbox string to a RAICLChoice."""
    # K=0 baseline (no exemplars, but caller still applies split filter)
    if choice == "0 (test cohort)":
        return RAICLChoice("K=0 (test cohort)", "random_any", True, _k_literal=0)

    # Selection-mode percentage options
    if choice == "25% train":
        return RAICLChoice("25% train", "random_any", True, _fraction=0.25)
    if choice == "50% train":
        return RAICLChoice("50% train", "random_any", True, _fraction=0.50)
    if choice == "75% train":
        return RAICLChoice("75% train", "random_any", True, _fraction=0.75)

    # Validation-mode literal-K options
    if choice == "3":
        return RAICLChoice("K=3", "random_in_domain", True, _k_literal=3)
    if choice == "10":
        return RAICLChoice("K=10", "random_in_domain", True, _k_literal=10)
    if choice == "25":
        return RAICLChoice("K=25", "random_in_domain", True, _k_literal=25)
    if choice == "All in-domain":
        return RAICLChoice("K=all-in-domain", "random_in_domain", False, _k_literal=_HUGE)

    # Shared between modes
    if choice == "All train":
        return RAICLChoice("K=all-train", "random_any", True, _k_literal=_HUGE)

    raise ValueError(f"unknown RA-ICL choice: {choice!r}")


def render_k_selector(
    *,
    key: str,
    mode: str = "selection",
    default: Optional[str] = None,
    disabled: bool = False,
) -> RAICLChoice:
    """Render a mode-aware selectbox and return a RAICLChoice.

    Parameters
    ----------
    key : str
        Streamlit widget key.
    mode : {'selection', 'validation'}
        Drives which option catalogue is shown. ``selection`` exposes
        only cross-domain percentage options (fair for MCP inference);
        ``validation`` exposes literal-K in-domain options too.
    default : str, optional
        Default option label. Falls back to the second entry (sensible
        middle-of-the-road default) for selection mode, or "3" for
        validation mode.
    disabled : bool
        Greys out the selector (e.g., when the RA-ICL toggle is off).
    """
    if mode == "selection":
        options: List[str] = SELECTION_OPTIONS
        if default is None:
            default = "50% train"
        help_text = (
            "Percentage of the train pool to inject as exemplars. "
            "Selection mode uses cross-domain (random_any) sampling so "
            "the model still has to infer which MCP to use — in-domain "
            "exemplars would leak the answer via the 'Correct MCP' "
            "label on every example."
        )
    else:
        options = VALIDATION_OPTIONS
        if default is None:
            default = "3"
        help_text = (
            "How many train-pool exemplars to inject per prompt. "
            "Validation mode shows the candidate bundle (with MCP) "
            "alongside the query, so in-domain retrieval is fair. "
            "'All in-domain' uses every train task with the same primary "
            "MCP as the query; 'All train' uses the full pool across "
            "all MCPs."
        )

    if default not in options:
        default = options[0]

    choice = st.selectbox(
        "Exemplars per prompt",
        options,
        index=options.index(default),
        key=key,
        disabled=disabled,
        help=help_text,
    )
    return _resolve(choice)
