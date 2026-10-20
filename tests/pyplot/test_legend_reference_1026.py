"""Legend ``loc`` placement against the released Matplotlib 3.11 reference (#1026).

Matplotlib's legend bounding box is converted to axes-fraction coordinates and
compared with XYG's static-export legend box (relative to the axes plot box).
The documented tolerance is 0.01 axes fraction per edge (measured spread is
below 0.005: font metrics differ slightly between the two renderers).
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys

import numpy as np
import pytest

import xyg.pyplot as plt

TOLERANCE = 0.01
LOCS = ["upper left", "upper right", "lower left", "lower right", "center", "best"]

_REFERENCE = r"""
import json, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
out = {}
for loc in json.loads(sys.argv[1]):
    fig = plt.figure(figsize=(6.4, 4.8))
    ax = fig.add_subplot()
    ax.plot(np.arange(8), np.arange(8), label="series")
    leg = ax.legend(loc=loc)
    fig.canvas.draw()
    bbox = leg.get_window_extent().transformed(ax.transAxes.inverted())
    out[loc] = [bbox.x0, bbox.y0, bbox.x1, bbox.y1]
print(json.dumps(out))
"""


def _has_reference() -> bool:
    try:
        import matplotlib
    except ImportError:
        return False
    return tuple(int(part) for part in matplotlib.__version__.split(".")[:2]) >= (3, 11)


pytestmark = pytest.mark.skipif(
    not _has_reference(), reason="requires the pinned released Matplotlib 3.11 reference"
)


@pytest.fixture(scope="module")
def reference() -> dict[str, list[float]]:
    # A fresh process keeps the reference's pyplot state apart from xyg.pyplot.
    done = subprocess.run(
        [sys.executable, "-c", _REFERENCE, json.dumps(LOCS)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(done.stdout)


def _xyg_axes_fraction_box(loc: str) -> list[float]:
    plt.figure(figsize=(6.4, 4.8))
    x = np.arange(8)
    plt.plot(x, x, label="series")
    plt.legend(loc=loc)
    buffer = io.BytesIO()
    plt.gcf().savefig(buffer, format="svg")
    plt.close("all")
    svg = buffer.getvalue().decode()
    px, py, pw, ph = (
        float(v)
        for v in re.search(
            r'data-xy-chrome="plot-background"[^>]*?x="([\d.]+)" y="([\d.]+)"'
            r' width="([\d.]+)" height="([\d.]+)"',
            svg,
        ).groups()
    )
    lx, ly, lw, lh = (
        float(v)
        for v in re.search(
            r'data-xy-static-legend="">\s*<rect x="([\d.]+)" y="([\d.]+)"'
            r' width="([\d.]+)" height="([\d.]+)"',
            svg,
        ).groups()
    )
    # SVG y grows downward; Matplotlib's axes fraction grows upward.
    return [
        (lx - px) / pw,
        1.0 - (ly + lh - py) / ph,
        (lx + lw - px) / pw,
        1.0 - (ly - py) / ph,
    ]


@pytest.mark.parametrize("loc", LOCS)
def test_legend_box_matches_matplotlib_in_axes_fractions(loc, reference):
    xyg_box = _xyg_axes_fraction_box(loc)
    assert xyg_box == pytest.approx(reference[loc], abs=TOLERANCE), (loc, xyg_box, reference[loc])
