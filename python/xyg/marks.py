"""The declarative mark core: the single implementation of every chart kind.

Each function here IS both public dialects: `Figure` binds them as its fluent
methods (`Figure.scatter is marks.scatter`), and the composition API's
appliers call those same bound methods. One body, one signature, one set of
defaults — the parity tests assert the identity. Functions take the figure
as `self` (they are written as methods; `__figure.py` assigns them in the class
body) and reach engine state — store, traces, checkpoint/rollback, ingest and
axis-position helpers — through it.
"""

from __future__ import annotations

from typing import Any

from ._marks_bar import (
    bar,  # noqa: F401
    column,  # noqa: F401
)
from ._marks_bar import (
    bar_like as _bar_like,  # noqa: F401
)
from ._marks_contour import (
    contour,  # noqa: F401
)
from ._marks_distribution import (
    box,  # noqa: F401
    violin,  # noqa: F401
)
from ._marks_distribution import (
    distribution_stats as _distribution_stats,  # noqa: F401
)
from ._marks_errorbar import (
    error_band,  # noqa: F401
    errorbar,  # noqa: F401
)
from ._marks_graph import (
    graph,  # noqa: F401
)
from ._marks_heatmap import (
    heatmap,  # noqa: F401
)
from ._marks_hexbin import (
    hexbin,  # noqa: F401
)
from ._marks_histogram import (
    hist,  # noqa: F401
    histogram,  # noqa: F401
)
from ._marks_line import (
    area,  # noqa: F401
    line,  # noqa: F401
)
from ._marks_ribbon import (
    ribbon,  # noqa: F401
)
from ._marks_sankey import (
    sankey,  # noqa: F401
)
from ._marks_scatter import (
    scatter,  # noqa: F401
)
from ._marks_segments import (
    segments,  # noqa: F401
)
from ._marks_step import (
    ecdf,  # noqa: F401
    stairs,  # noqa: F401
    stem,  # noqa: F401
    step,  # noqa: F401
)
from ._marks_style import (
    SYMBOL_CODES as _SYMBOL_CODES,  # noqa: F401
)
from ._marks_style import (
    append_segment_trace as _append_segment_trace,  # noqa: F401
)
from ._marks_style import (
    direct_style as _direct_style,  # noqa: F401
)
from ._marks_style import (
    stroke_channel as _stroke_channel,  # noqa: F401
)
from ._marks_style import (
    validated_marker_path as _validated_marker_path,  # noqa: F401
)
from ._marks_triangle_mesh import (
    triangle_mesh,  # noqa: F401
)

# Bound by `_figure` after `Figure` is defined (breaks the import cycle).
Figure: Any = None
