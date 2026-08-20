"""Optional pyarrow GeoArrow → GeoColumn adapter (#47)."""

from __future__ import annotations

import json

import pytest

pa = pytest.importorskip("pyarrow")

from xy import _geoarrow, _native  # noqa: E402


def _point_field(crs: str = "EPSG:4326") -> pa.Field:
    meta = {
        b"ARROW:extension:name": b"geoarrow.point",
        b"ARROW:extension:metadata": json.dumps({"crs": crs}).encode("utf-8"),
    }
    return pa.field(
        "geometry", pa.struct([("x", pa.float64()), ("y", pa.float64())]), metadata=meta
    )


def _linestring_field(crs: str = "EPSG:4326") -> pa.Field:
    coord = pa.struct([("x", pa.float64()), ("y", pa.float64())])
    meta = {
        b"ARROW:extension:name": b"geoarrow.linestring",
        b"ARROW:extension:metadata": json.dumps({"crs": crs}).encode("utf-8"),
    }
    return pa.field("geometry", pa.list_(coord), metadata=meta)


def test_ingest_geoarrow_points() -> None:
    field = _point_field()
    arr = pa.array([{"x": -104.9903, "y": 39.7392}, {"x": -105.0, "y": 40.0}], type=field.type)
    handle = _geoarrow.ingest_geoarrow(arr, field)
    try:
        length, vertices, geometry, crs = _native.geo_column_meta(handle)
        assert (length, vertices, geometry, crs) == (2, 2, _native.GEO_GEOMETRY_POINT, 4326)
    finally:
        assert _native.geo_column_free(handle) is True


def test_ingest_geoarrow_linestring() -> None:
    field = _linestring_field()
    arr = pa.array(
        [[{"x": -105.0, "y": 39.7}, {"x": -104.9, "y": 39.8}]],
        type=field.type,
    )
    handle = _geoarrow.ingest_geoarrow(arr, field)
    try:
        length, vertices, geometry, crs = _native.geo_column_meta(handle)
        assert length == 1
        assert vertices == 2
        assert geometry == _native.GEO_GEOMETRY_LINESTRING
        assert crs == 4326
    finally:
        assert _native.geo_column_free(handle) is True


def test_ingest_rejects_unsupported_crs() -> None:
    field = _point_field("EPSG:9999")
    arr = pa.array([{"x": 0.0, "y": 0.0}], type=field.type)
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.ingest_geoarrow(arr, field)
    assert exc.value.status == -2
    assert "9999" not in str(exc.value)


def test_ingest_null_point_skips_vertex() -> None:
    field = _point_field()
    arr = pa.array([None, {"x": -104.0, "y": 39.0}], type=field.type)
    handle = _geoarrow.ingest_geoarrow(arr, field)
    try:
        length, vertices, geometry, crs = _native.geo_column_meta(handle)
        assert length == 2
        assert vertices == 1
        assert geometry == _native.GEO_GEOMETRY_POINT
        assert crs == 4326
    finally:
        assert _native.geo_column_free(handle) is True
