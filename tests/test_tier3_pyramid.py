"""Tier-3 Phase-3 pyramid product path — first paint + compose evidence.

Testing contract: ``spec/design/tier3-testing.md``. Does **not** allocate
100M/1B points; uses ``PYRAMID_MIN_POINTS`` for the auto path and modest N
for compose mass conservation.
"""

from __future__ import annotations

import numpy as np

import xyg as xy
from xyg import kernels
from xyg.config import DENSITY_GRID, PYRAMID_MIN_POINTS


def test_first_paint_records_pyramid_binning():
    n = PYRAMID_MIN_POINTS
    rng = np.random.default_rng(1)
    x = rng.random(n)
    y = rng.random(n)
    fig = xy.scatter_chart(xy.scatter(x, y, density=True), width=320, height=240).figure()
    spec, _blob = fig.build_payload()
    dens = spec["traces"][0]["density"]
    assert dens["binning"].startswith("pyramid-L")
    assert dens["reduction"] == "pyramid-count"
    assert dens["enc"] == "log-u8"
    assert dens["w"] * dens["h"] == DENSITY_GRID[0] * DENSITY_GRID[1]


def test_pyramid_compose_mass_matches_bin2d():
    n = 8192
    rng = np.random.default_rng(2)
    x = rng.random(n)
    y = rng.random(n)
    handle = kernels.pyramid_build(x, y, 0.0, 1.0, 0.0, 1.0, 128)
    assert handle
    res = kernels.pyramid_compose(handle, 0.0, 1.0, 0.0, 1.0, 64, 48, max_upsample=16)
    assert res is not None
    grid, _level = res
    direct = kernels.bin_2d(x, y, 0.0, 1.0, 0.0, 1.0, 64, 48)
    assert abs(float(grid.sum()) - float(direct.sum())) < 1e-3
    assert kernels.pyramid_free(handle)


def test_pyramid_resident_bytes_far_below_raw_xy():
    from xyg.interaction import _pyramid_resident_bytes

    n = 1_000_000
    resident = _pyramid_resident_bytes(256, colored=False)
    assert resident < n * 16
