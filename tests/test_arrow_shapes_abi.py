"""ABI 257 arrow shapes orchestration — wrapper over xyg_arrow_shapes."""

from __future__ import annotations

import math

from xyg import kernels
from xyg._arrowgeom import arrow_shapes


def test_kernels_arrow_shapes_linear_head() -> None:
    meta, xs, ys = kernels.arrow_shapes(
        0.0,
        0.0,
        100.0,
        0.0,
        [float("nan")] * 12,
        "triangle",
        "none",
        math.nan,
        math.nan,
        math.nan,
        False,
    )
    assert meta.tolist() == [2, 0, 1, 3, 0, 0]
    assert len(xs) == 5
    assert xs[0] == 0.0
    assert xs[1] == 100.0
    assert xs[2] == 100.0


def test_arrow_shapes_wrapper_matches_kernel() -> None:
    shapes = arrow_shapes(0.0, 0.0, 80.0, 0.0, {"head_style": "triangle", "tail_style": "none"})
    assert shapes["taper"] is None
    assert shapes["shaft"] is not None
    assert len(shapes["shaft"]) == 2
    assert shapes["head"] is not None
    assert shapes["head"]["kind"] == "fill"
    assert len(shapes["head"]["points"]) == 3
    assert shapes["tail"] is None


def test_arrow_shapes_taper_path() -> None:
    shapes = arrow_shapes(
        0.0,
        0.0,
        40.0,
        0.0,
        {"shaft_width_start": 2.0, "shaft_width_end": 1.0, "head_size": 8.0},
    )
    assert shapes["shaft"] is None
    assert shapes["taper"] is not None
    assert len(shapes["taper"]) > 0
    assert shapes["head"] is not None
