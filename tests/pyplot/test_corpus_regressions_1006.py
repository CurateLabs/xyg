"""Focused regressions for the Matplotlib 3.11 reference corpus restore (#1006).

Each test pins one distinct root cause behind a failing corpus program, through
the public ``xyg.pyplot`` surface and the canonical Rust Scene/XYST export.
"""

from __future__ import annotations

import numpy as np

import xyg.pyplot as plt


def test_tight_layout_measures_intrinsic_chrome_not_the_allocated_frame() -> None:
    """tight_layout must not collapse panels to slivers (corpus 27).

    The probe chart carries frame padding derived from the axes' current figure
    rectangle; echoing that padding back as measured chrome made every panel
    reserve its whole allocation as margin.
    """
    fig, axs = plt.subplots(2, 2, figsize=(8, 6))
    x = np.linspace(0, 5, 60)
    axs[0, 0].plot(x, np.sin(x))
    axs[0, 0].set_title("line")
    axs[1, 0].bar(["a", "b", "c"], [3, 7, 2])
    fig.tight_layout()
    try:
        for axes in axs.ravel():
            _x, _y, width, height = axes.get_position().bounds
            assert width > 0.3
            assert height > 0.3
    finally:
        plt.close("all")
