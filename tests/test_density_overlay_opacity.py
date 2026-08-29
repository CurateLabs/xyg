"""ABI 220 density overlay opacity — Python host wrapper over xyg_density_overlay_opacity."""

from __future__ import annotations

import math

from xyg import kernels


def test_density_overlay_opacity_caps_and_non_finite() -> None:
    assert kernels.density_overlay_opacity(0.8) == 0.55
    assert kernels.density_overlay_opacity(0.3) == 0.3
    assert kernels.density_overlay_opacity(1.0) == 0.55
    assert kernels.density_overlay_opacity(float("nan")) == 0.55
    assert kernels.density_overlay_opacity(math.inf) == 0.55
    assert kernels.density_overlay_opacity(-math.inf) == 0.55
