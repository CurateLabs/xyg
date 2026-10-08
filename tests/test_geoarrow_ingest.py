"""Optional pyarrow GeoArrow → GeoColumn adapter (#47)."""

from __future__ import annotations

import json

import pytest

pa = pytest.importorskip("pyarrow")

from xyg import _geoarrow, _native  # noqa: E402


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


# ---------------------------------------------------------------------------
# Nested kinds, holes, feature identity, and Rust read-back (#47 A4).
# ---------------------------------------------------------------------------

import numpy as np  # noqa: E402

_COORD = pa.struct([("x", pa.float64()), ("y", pa.float64())])
_SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
_HOLE = [(2.0, 2.0), (2.0, 4.0), (4.0, 4.0), (4.0, 2.0), (2.0, 2.0)]
_FAR = [(20.0, 20.0), (22.0, 20.0), (22.0, 22.0), (20.0, 22.0), (20.0, 20.0)]


def _pts(coords: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in coords]


def _field(name: str, storage: pa.DataType, crs: str = "EPSG:4326") -> pa.Field:
    meta = {
        b"ARROW:extension:name": name.encode(),
        b"ARROW:extension:metadata": json.dumps({"crs": crs}).encode(),
    }
    return pa.field("geometry", storage, metadata=meta)


def _polygon_field() -> pa.Field:
    return _field("geoarrow.polygon", pa.list_(pa.list_(_COORD)))


def _polygon_array(rows: list[list[list[tuple[float, float]]] | None]) -> pa.Array:
    py_rows = [None if row is None else [_pts(ring) for ring in row] for row in rows]
    return pa.array(py_rows, type=pa.list_(pa.list_(_COORD)))


def test_polygon_with_hole_round_trips_through_rust() -> None:
    field = _polygon_field()
    arr = _polygon_array([[_SQUARE, _HOLE]])
    handle = _geoarrow.ingest_geoarrow(arr, field, feature_ids=[77])
    try:
        planes = _native.geo_column_read(handle)
        flat = [v for ring in (_SQUARE, _HOLE) for pt in ring for v in pt]
        np.testing.assert_array_equal(planes["xy"], np.asarray(flat), strict=True)
        assert planes["offsets0"].tolist() == [0, 2]
        assert planes["offsets1"].tolist() == [0, 5, 10]
        assert planes["feature_ids"].tolist() == [77]
        assert planes["orientations"].tolist() == [1, 2]
    finally:
        assert _native.geo_column_free(handle) is True


def test_hole_outside_shell_is_rejected_with_stable_code() -> None:
    arr = _polygon_array([[_SQUARE, _FAR]])
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.ingest_geoarrow(arr, _polygon_field())
    assert exc.value.status == -11
    assert "20" not in str(exc.value)


def test_null_linestring_that_owns_vertices_is_rejected() -> None:
    values = pa.array(_pts([(0.0, 0.0), (1.0, 1.0)]), type=_COORD)
    offsets = pa.array([0, 2], type=pa.int32())
    arr = pa.ListArray.from_arrays(offsets, values, mask=pa.array([True]))
    assert arr.null_count == 1
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.ingest_geoarrow(arr, _field("geoarrow.linestring", pa.list_(_COORD)))
    assert exc.value.status == -14


def test_feature_ids_pass_through_from_arrow_numpy_and_chunked() -> None:
    field = _point_field()
    arr = pa.array([{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}], type=field.type)
    sources = [
        pa.array([10, 20], type=pa.int64()),
        pa.array([10, 20], type=pa.uint64()),
        pa.chunked_array([pa.array([10], type=pa.uint64()), pa.array([20], type=pa.uint64())]),
        np.array([10, 20], dtype=np.int32),
        [10, 20],
    ]
    for ids in sources:
        desc = _geoarrow.descriptor_from_geoarrow(arr, field, feature_ids=ids)
        assert desc["feature_ids"].dtype == np.uint64
        assert desc["feature_ids"].tolist() == [10, 20]
        handle = _native.geo_column_new(**desc)
        try:
            assert _native.geo_column_read(handle)["feature_ids"].tolist() == [10, 20]
        finally:
            _native.geo_column_free(handle)
    assert _geoarrow.descriptor_from_geoarrow(arr, field)["feature_ids"] is None


def test_feature_ids_default_to_row_index_when_absent() -> None:
    field = _point_field()
    arr = pa.array([{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}], type=field.type)
    handle = _geoarrow.ingest_geoarrow(arr, field)
    try:
        assert _native.geo_column_read(handle)["feature_ids"].tolist() == [0, 1]
    finally:
        _native.geo_column_free(handle)


@pytest.mark.parametrize(
    "bad_ids",
    [
        [1],  # too short
        [1, 2, 3],  # too long
        [-1, 2],  # negative
        pa.array([1, None], type=pa.int64()),  # nulls
        np.array([1.0, 2.0]),  # floats
    ],
)
def test_feature_ids_mismatch_is_rejected_before_publish(bad_ids: object) -> None:
    field = _point_field()
    arr = pa.array([{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}], type=field.type)
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.ingest_geoarrow(arr, field, feature_ids=bad_ids)
    assert exc.value.status == -1


def test_null_points_use_mask_gather_and_keep_feature_alignment() -> None:
    field = _point_field()
    arr = pa.array(
        [None, {"x": -104.0, "y": 39.0}, None, {"x": -105.0, "y": 40.0}], type=field.type
    )
    handle = _geoarrow.ingest_geoarrow(arr, field, feature_ids=[5, 6, 7, 8])
    try:
        planes = _native.geo_column_read(handle)
        assert planes["xy"].tolist() == [-104.0, 39.0, -105.0, 40.0]
        assert planes["validity"].tolist() == [0, 1, 0, 1]
        assert planes["feature_ids"].tolist() == [5, 6, 7, 8]
    finally:
        _native.geo_column_free(handle)


def test_null_points_with_garbage_under_the_mask_are_ignored() -> None:
    # A producer may leave NaN under a null slot; null points own no vertex.
    field = _point_field()
    x = pa.array([float("nan"), 1.0], type=pa.float64())
    y = pa.array([float("nan"), 2.0], type=pa.float64())
    arr = pa.StructArray.from_arrays([x, y], names=["x", "y"], mask=pa.array([True, False]))
    handle = _geoarrow.ingest_geoarrow(arr, field)
    try:
        assert _native.geo_column_read(handle)["xy"].tolist() == [1.0, 2.0]
    finally:
        _native.geo_column_free(handle)


def test_multipoint_and_multilinestring_read_back() -> None:
    mp_field = _field("geoarrow.multipoint", pa.list_(_COORD))
    mp = pa.array([_pts([(0.0, 0.0), (1.0, 1.0)]), _pts([(2.0, 2.0)])], type=pa.list_(_COORD))
    handle = _geoarrow.ingest_geoarrow(mp, mp_field)
    try:
        planes = _native.geo_column_read(handle)
        assert planes["offsets0"].tolist() == [0, 2, 3]
        assert planes["xy"].tolist() == [0.0, 0.0, 1.0, 1.0, 2.0, 2.0]
    finally:
        _native.geo_column_free(handle)

    ml_field = _field("geoarrow.multilinestring", pa.list_(pa.list_(_COORD)))
    ml = pa.array(
        [[_pts([(0.0, 0.0), (1.0, 1.0)]), _pts([(2.0, 2.0), (3.0, 3.0)])]],
        type=pa.list_(pa.list_(_COORD)),
    )
    handle = _geoarrow.ingest_geoarrow(ml, ml_field)
    try:
        planes = _native.geo_column_read(handle)
        assert planes["offsets0"].tolist() == [0, 2]
        assert planes["offsets1"].tolist() == [0, 2, 4]
        assert planes["orientations"].size == 0
    finally:
        _native.geo_column_free(handle)


@pytest.mark.parametrize(
    "geometry,depth",
    [
        ("linestring", 1),
        ("multipoint", 1),
        ("polygon", 2),
        ("multilinestring", 2),
        ("multipolygon", 3),
    ],
)
def test_nested_slices_rebase_every_plane_and_preserve_only_selected_geometry(
    geometry: str, depth: int
) -> None:
    storage = _COORD
    row = _pts(_SQUARE if geometry in ("polygon", "multipolygon") else [(0.0, 0.0), (1.0, 1.0)])
    for _ in range(depth):
        storage = pa.list_(storage)
    for _ in range(depth - 1):
        row = [row]
    field = _field("geoarrow." + geometry, storage)
    array = pa.array([row, row, row], type=storage)
    expected = _geoarrow.descriptor_from_geoarrow(pa.array([row], type=storage), field, [99])
    actual = _geoarrow.descriptor_from_geoarrow(array.slice(1, 1), field, [99])
    for name in ("xy", "validity", "feature_ids", "offsets0", "offsets1", "offsets2"):
        if expected[name] is None:
            assert actual[name] is None
        else:
            np.testing.assert_array_equal(actual[name], expected[name])
    handle = _native.geo_column_new(**actual)
    try:
        assert _native.geo_column_read(handle)["feature_ids"].tolist() == [99]
    finally:
        _native.geo_column_free(handle)


@pytest.mark.parametrize("metadata", ["[]", "null", "42", '"EPSG:4326"'])
def test_non_object_crs_metadata_has_stable_error(metadata: str) -> None:
    field = _point_field().with_metadata(
        {b"ARROW:extension:name": b"geoarrow.point", b"ARROW:extension:metadata": metadata.encode()}
    )
    array = pa.array([{"x": 0.0, "y": 0.0}], type=field.type)
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.descriptor_from_geoarrow(array, field)
    assert exc.value.status == -2


@pytest.mark.parametrize(
    "storage",
    [
        pa.struct([("x", pa.int64()), ("y", pa.int64())]),
        pa.struct([("x", pa.float64()), ("y", pa.float64()), ("z", pa.float64())]),
    ],
)
def test_uncertified_coordinate_schema_fails_closed(storage: pa.DataType) -> None:
    field = _field("geoarrow.point", storage)
    array = pa.array([dict.fromkeys(storage.names, 1)], type=storage)
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.descriptor_from_geoarrow(array, field)
    assert exc.value.status == -3


def test_nested_coordinate_struct_null_is_not_reconstructed_from_children() -> None:
    coords = pa.StructArray.from_arrays(
        [pa.array([0.0, 1.0]), pa.array([0.0, 1.0])], names=["x", "y"], mask=pa.array([True, False])
    )
    array = pa.ListArray.from_arrays(pa.array([0, 2], type=pa.int32()), coords)
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.descriptor_from_geoarrow(array, _linestring_field())
    assert exc.value.status == -5


def test_nested_list_null_is_rejected() -> None:
    array = pa.array([[None]], type=pa.list_(pa.list_(_COORD)))
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.descriptor_from_geoarrow(array, _polygon_field())
    assert exc.value.status == -5


def test_present_point_coordinate_null_is_rejected() -> None:
    array = pa.array([{"x": None, "y": 1.0}], type=_COORD)
    with pytest.raises(_native.GeoNativeError) as exc:
        _geoarrow.descriptor_from_geoarrow(array, _point_field())
    assert exc.value.status == -5
