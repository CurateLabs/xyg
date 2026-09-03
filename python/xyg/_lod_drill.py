"""Drill-down subset bookkeeping on traces."""

from __future__ import annotations

from typing import Any

import numpy as np

from .config import DRILL_HISTORY_KEEP


def enter_drill(trace: Any, sel: np.ndarray) -> int:
    """Adopt `sel` as the trace's shipped subset. Picks/selections translate
    through it, and the version bump invalidates in-flight replies built
    against the previous subset (exact or nothing; design dossier §16/§17).
    Returns the seq."""
    trace.drill_mode = True
    trace.shipped_sel = sel
    trace.drill_seq += 1
    # Remember recent subsets (T13): the client can serve a view from a
    # RETIRED cached point window whose drill_seq is no longer current, and a
    # pick against it should still translate exactly. Bounded FIFO — an
    # expired seq resolves to None (a dropped pick), never to a wrong row.
    history = trace.drill_history
    history[trace.drill_seq] = sel
    while len(history) > DRILL_HISTORY_KEEP:
        del history[next(iter(history))]
    return trace.drill_seq


def exit_drill(trace: Any) -> None:
    """Back to the aggregate: no per-point marks, no pick mapping. Bumps the
    version when leaving an actual drill so a drilled-index pick arriving late
    is rejected instead of being read as a *canonical* index. Remembered
    subsets survive the exit — client-side cached point windows outlive the
    kernel's current-tier choice (T13) — until a data change clears them."""
    if trace.drill_mode:
        trace.drill_seq += 1
    trace.drill_mode = False
    trace.shipped_sel = None


def drill_history(trace: Any, seq: int) -> np.ndarray | None:
    """The shipped subset a recent `drill_seq` named, or None when expired.

    None must stay None at the call site (drop the pick): translating through
    the wrong subset would read an arbitrary canonical row (§16)."""
    return trace.drill_history.get(seq)


def clear_drill_history(trace: Any) -> None:
    """Forget remembered subsets after a data change: the retained indices
    were computed against the previous canonical state, and a client window
    built on them is rebuilt anyway (append/update rebuilds GPU traces)."""
    trace.drill_history.clear()
