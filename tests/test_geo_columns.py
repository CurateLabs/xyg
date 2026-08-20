"""Python host wrappers for Rust-owned GeoColumn descriptors (#47)."""

from __future__ import annotations

import numpy as np
import pytest

from xyg import _native


def test_point_descriptor_round_trip() -> None:
    handle = _native.geo_column_new(
        geometry=_native.GEO_GEOMETRY_POINT,
        crs=_native.GEO_CRS_EPSG_4326,
        xy=[-104.9903, 39.7392],
        validity=[1],
        feature_ids=[42],
    )
    try:
        length, vertices, geometry, crs = _native.geo_column_meta(handle)
        assert (length, vertices, geometry, crs) == (1, 1, 1, 4326)
    finally:
        assert _native.geo_column_free(handle) is True
        assert _native.geo_column_free(handle) is False


def test_polygon_and_unsupported_crs() -> None:
    handle = _native.geo_column_new(
        geometry=_native.GEO_GEOMETRY_POLYGON,
        crs=_native.GEO_CRS_EPSG_4326,
        xy=[-105.0, 39.7, -104.9, 39.7, -104.9, 39.8, -105.0, 39.7],
        validity=[1],
        offsets0=[0, 1],
        offsets1=[0, 4],
    )
    try:
        length, vertices, geometry, crs = _native.geo_column_meta(handle)
        assert length == 1
        assert vertices == 4
        assert geometry == _native.GEO_GEOMETRY_POLYGON
        assert crs == 4326
    finally:
        assert _native.geo_column_free(handle) is True

    with pytest.raises(_native.GeoNativeError) as exc:
        _native.geo_column_new(
            geometry=_native.GEO_GEOMETRY_POINT,
            crs=9999,
            xy=[0.0, 0.0],
            validity=[1],
        )
    assert exc.value.status == -2
    assert "EPSG:4326" in str(exc.value)
    assert "9999" not in str(exc.value)


def test_non_finite_rejected_without_leaking_values() -> None:
    with pytest.raises(_native.GeoNativeError) as exc:
        _native.geo_column_new(
            geometry=_native.GEO_GEOMETRY_POINT,
            crs=_native.GEO_CRS_EPSG_4326,
            xy=[np.nan, 0.0],
            validity=[1],
        )
    assert exc.value.status == -6
    assert "NaN" not in str(exc.value)
