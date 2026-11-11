"""Native geographic membership/clip work; source framing is outside measurement.

Both processors retain their normal capacity-query/copy C ABI calls. These
bounded cases protect temporary ordering changes, not browser/scale acceptance.
Run through CodSpeed; normal CI also checks the untimed output assertions.
"""

from __future__ import annotations

import numpy as np
import pytest

from xyg import _geocatalog as catalog
from xyg import _geoviewport as viewport
from xyg import _native


@pytest.fixture(scope="module", autouse=True)
def require_native():
    assert _native._lib.xyg_abi_version() == _native.ABI_VERSION


@pytest.fixture(params=[1_000, 10_000], ids=["1k", "10k"])
def geographic_density_request(request):
    n = request.param
    rows = np.arange(n, dtype=np.int64)
    xy = np.column_stack(((rows * 37 % 241) - 120, (rows * 13 % 61) - 30)).astype("<f8")
    source = dict(
        geometry=1,
        crs=4326,
        xy=xy.ravel(),
        validity=np.ones(n, dtype="u1"),
        feature_ids=np.arange(n, dtype="<u8") + np.uint64(1 << 63),
    )
    raw = catalog.encode_request(
        dict(
            camera=dict(
                crs=4326,
                center_x=0.0,
                center_y=0.0,
                zoom=0.0,
                width=1024.0,
                height=512.0,
                world_wrap=False,
            ),
            layers=[dict(layer_id=1, kind=7, source=source, density=dict(columns=32, rows=16))],
        ),
        budget=64 << 20,
    )
    expected = catalog.execute(raw, 64 << 20)
    decoded = catalog.decode_response(expected)
    bins = decoded["layers"][0]["density"]
    assert int(bins["counts"].sum()) == n
    assert int(bins["offsets"][-1]) == n
    np.testing.assert_array_equal(np.sort(bins["feature_indices"]), np.arange(n, dtype="<u4"))
    return raw, expected


def test_geo_density_membership_ordering(benchmark, geographic_density_request):
    raw, expected = geographic_density_request
    actual = benchmark(catalog.execute, raw, 64 << 20)
    assert actual == expected


@pytest.fixture(params=[64, 256], ids=["64polygons", "256polygons"])
def geographic_clipping_request(request):
    n = request.param
    camera = dict(
        crs=4326,
        center_x=0.0,
        center_y=0.0,
        zoom=0.0,
        width=4.0,
        height=2.0,
        world_wrap=False,
    )
    screen = [
        (0.5, -2.0),
        (3.5, -2.0),
        (3.5, 2.0),
        (2.5, 2.0),
        (2.5, -1.0),
        (1.5, -1.0),
        (1.5, 2.0),
        (0.5, 2.0),
        (0.5, -2.0),
    ]
    ring = np.asarray(
        [
            viewport.geo_viewport(camera, viewport.OPERATIONS["inverse"], point)["result"]
            for point in screen
        ],
        dtype="<f8",
    )
    ids = np.uint64((1 << 64) - 1) - np.arange(n, dtype="<u8")
    raw = viewport.encode_column_request(
        camera,
        dict(
            geometry=3,
            crs=4326,
            xy=np.tile(ring.ravel(), n),
            validity=np.ones(n, dtype="u1"),
            feature_ids=ids,
            offsets0=np.arange(n + 1, dtype="<u4"),
            offsets1=np.arange(n + 1, dtype="<u4") * len(screen),
        ),
    )
    expected = viewport.execute(raw, 64 << 20)
    decoded = viewport.decode_response(expected)
    assert len(decoded["polygon_offsets"]) == 2 * n + 1
    np.testing.assert_array_equal(decoded["polygon_feature_ids"], np.repeat(ids, 2))
    assert np.isfinite(decoded["polygon_xy"]).all()
    return raw, expected


def test_geo_clipping_edge_ordering(benchmark, geographic_clipping_request):
    raw, expected = geographic_clipping_request
    actual = benchmark(viewport.execute, raw, 64 << 20)
    assert actual == expected
