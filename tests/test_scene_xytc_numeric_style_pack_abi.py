"""ABI 264 scene_xytc_numeric_style_pack parity."""

from __future__ import annotations

import math

from xyg import kernels


def test_scene_xytc_numeric_style_pack_empty() -> None:
    flags, size, size_ch, stroke, width, line = kernels.scene_xytc_numeric_style_pack(
        0, 0, 0, 0, 0, 0, float("nan"), float("nan"), 0.0, 0.0, 0.0
    )
    assert flags == 0
    assert math.isnan(size)
    assert math.isnan(size_ch)
    assert stroke == width == line == 0.0


def test_scene_xytc_numeric_style_pack_full() -> None:
    flags, size, size_ch, stroke, width, line = kernels.scene_xytc_numeric_style_pack(
        1, 1, 1, 1, 1, 1, 4.0, 2.5, 1.0, 2.0, 3.0
    )
    assert flags == (1 << 3) | (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7)
    assert (size, size_ch, stroke, width, line) == (4.0, 2.5, 1.0, 2.0, 3.0)


def test_scene_xytc_numeric_style_pack_size_ch_without_constant() -> None:
    flags, _size, size_ch, *_rest = kernels.scene_xytc_numeric_style_pack(
        0, 1, 0, 0, 0, 0, float("nan"), float("nan"), 0.0, 0.0, 0.0
    )
    assert flags == 1 << 7
    assert math.isnan(size_ch)
