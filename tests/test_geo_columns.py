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


# ---------------------------------------------------------------------------
# Read-back, canonical metadata, and stable error codes (#47 A4/A7).
# ---------------------------------------------------------------------------

# Exterior CCW square 0..10 with one CW hole 2..4 (both closed).
_SHELL = [0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0, 0.0, 0.0]
_HOLE = [2.0, 2.0, 2.0, 4.0, 4.0, 4.0, 4.0, 2.0, 2.0, 2.0]
_SECOND = [20.0, 20.0, 30.0, 20.0, 30.0, 30.0, 20.0, 30.0, 20.0, 20.0]

# Offsets of the XYGM v1 document (see crates/xyg-engine/src/geo.rs).
_XYGM_GEOMETRY = 8
_XYGM_CRS = 12
_XYGM_FEATURES = 16
_XYGM_VERTICES = 24
_XYGM_NULLS = 32
_XYGM_RINGS = 64


def _u32(doc: bytes, at: int) -> int:
    return int.from_bytes(doc[at : at + 4], "little")


def _u64(doc: bytes, at: int) -> int:
    return int.from_bytes(doc[at : at + 8], "little")


def _polygon_with_hole(**extra: object) -> int:
    return _native.geo_column_new(
        geometry=_native.GEO_GEOMETRY_POLYGON,
        crs=_native.GEO_CRS_EPSG_4326,
        xy=_SHELL + _HOLE,
        validity=[1],
        offsets0=[0, 2],
        offsets1=[0, 5, 10],
        **extra,  # type: ignore[arg-type]
    )


def test_polygon_with_hole_reads_back_exactly() -> None:
    handle = _polygon_with_hole(feature_ids=[901])
    try:
        planes = _native.geo_column_read(handle)
        np.testing.assert_array_equal(
            planes["xy"], np.asarray(_SHELL + _HOLE, dtype=np.float64), strict=True
        )
        np.testing.assert_array_equal(
            planes["validity"], np.array([1], dtype=np.uint8), strict=True
        )
        np.testing.assert_array_equal(
            planes["feature_ids"], np.array([901], dtype=np.uint64), strict=True
        )
        np.testing.assert_array_equal(
            planes["offsets0"], np.array([0, 2], dtype=np.uint32), strict=True
        )
        np.testing.assert_array_equal(
            planes["offsets1"], np.array([0, 5, 10], dtype=np.uint32), strict=True
        )
        assert planes["offsets2"].size == 0
        # Orientation is recorded, never rewritten: CCW shell, CW hole.
        np.testing.assert_array_equal(
            planes["orientations"], np.array([1, 2], dtype=np.uint8), strict=True
        )
        assert _native.geo_column_plane_lens(handle) == (20, 1, 1, 2, 3, 0, 2)
    finally:
        assert _native.geo_column_free(handle) is True


def test_multipolygon_with_holes_reads_back_exactly() -> None:
    xy = _SHELL + _HOLE + _SECOND
    handle = _native.geo_column_new(
        geometry=_native.GEO_GEOMETRY_MULTIPOLYGON,
        crs=_native.GEO_CRS_EPSG_4326,
        xy=xy,
        validity=[1, 1],
        offsets0=[0, 1, 2],
        offsets1=[0, 2, 3],
        offsets2=[0, 5, 10, 15],
    )
    try:
        planes = _native.geo_column_read(handle)
        np.testing.assert_array_equal(planes["xy"], np.asarray(xy, dtype=np.float64), strict=True)
        np.testing.assert_array_equal(planes["offsets2"], np.array([0, 5, 10, 15], dtype=np.uint32))
        np.testing.assert_array_equal(planes["feature_ids"], np.array([0, 1], dtype=np.uint64))
        assert planes["orientations"].tolist() == [1, 2, 1]
    finally:
        assert _native.geo_column_free(handle) is True


def test_read_back_preserves_f64_bits() -> None:
    # Values that are not exactly representable in f32 and a signed zero.
    xy = [-104.99030000000001, 39.739199999999997, -0.0, 0.1 + 0.2]
    handle = _native.geo_column_new(
        geometry=_native.GEO_GEOMETRY_MULTIPOINT,
        crs=_native.GEO_CRS_EPSG_4326,
        xy=xy,
        validity=[1],
        offsets0=[0, 2],
    )
    try:
        got = _native.geo_column_read(handle)["xy"]
        assert (
            got.view(np.uint64).tolist()
            == np.asarray(xy, dtype=np.float64).view(np.uint64).tolist()
        )
    finally:
        _native.geo_column_free(handle)


def test_canonical_metadata_header_and_determinism() -> None:
    a = _polygon_with_hole()
    b = _polygon_with_hole()
    try:
        doc = _native.geo_column_metadata(a)
        assert doc[:4] == b"XYGM"
        assert _u32(doc, 4) == 1
        assert len(doc) % 8 == 0
        assert _u32(doc, _XYGM_GEOMETRY) == _native.GEO_GEOMETRY_POLYGON
        assert _u32(doc, _XYGM_CRS) == 4326
        assert _u64(doc, _XYGM_FEATURES) == 1
        assert _u64(doc, _XYGM_VERTICES) == 10
        assert _u64(doc, _XYGM_NULLS) == 0
        assert _u64(doc, _XYGM_RINGS) == 2
        assert b"geoarrow.polygon" in doc
        assert b'"crs":"EPSG:4326"' in doc
        # Same column built twice is byte-identical (handles are not encoded).
        assert _native.geo_column_metadata(b) == doc
    finally:
        _native.geo_column_free(a)
        _native.geo_column_free(b)


def test_canonical_metadata_digests_track_every_plane() -> None:
    base = _polygon_with_hole(feature_ids=[1])
    other_ids = _polygon_with_hole(feature_ids=[2])
    try:
        assert _native.geo_column_metadata(base) != _native.geo_column_metadata(other_ids)
    finally:
        _native.geo_column_free(base)
        _native.geo_column_free(other_ids)


def test_stale_handle_read_paths_raise_stable_error() -> None:
    handle = _polygon_with_hole()
    assert _native.geo_column_free(handle) is True
    for call in (
        _native.geo_column_metadata,
        _native.geo_column_plane_lens,
        _native.geo_column_read,
    ):
        with pytest.raises(_native.GeoNativeError) as exc:
            call(handle)
        assert exc.value.status == -10


def test_copy_with_undersized_plane_writes_nothing() -> None:
    import ctypes

    handle = _polygon_with_hole()
    try:
        xy = np.full(20, -1.0, dtype=np.float64)
        validity = np.full(1, 7, dtype=np.uint8)
        ids = np.full(1, 7, dtype=np.uint64)
        o0 = np.full(2, 7, dtype=np.uint32)
        o1 = np.full(2, 7, dtype=np.uint32)  # one short of the 3 required
        o2 = np.zeros(1, dtype=np.uint32)
        orient = np.full(2, 7, dtype=np.uint8)
        status = _native._lib.xyg_geo_column_copy(
            ctypes.c_uint64(handle),
            xy.ctypes.data,
            20,
            validity.ctypes.data,
            1,
            ids.ctypes.data,
            1,
            o0.ctypes.data,
            2,
            o1.ctypes.data,
            2,
            o2.ctypes.data,
            0,
            orient.ctypes.data,
            2,
        )
        assert status == -13
        assert _native.GeoNativeError(status).status == -13
        assert (xy == -1.0).all()
        assert (validity == 7).all() and (ids == 7).all()
        assert (o0 == 7).all() and (o1 == 7).all() and (orient == 7).all()
    finally:
        _native.geo_column_free(handle)


def test_metadata_size_query_and_short_buffer() -> None:
    import ctypes

    handle = _polygon_with_hole()
    try:
        needed = int(_native._lib.xyg_geo_column_metadata(ctypes.c_uint64(handle), None, 0))
        assert needed == len(_native.geo_column_metadata(handle))
        short = np.full(needed, 0xAB, dtype=np.uint8)
        got = int(
            _native._lib.xyg_geo_column_metadata(
                ctypes.c_uint64(handle), short.ctypes.data, needed - 1
            )
        )
        assert got == needed
        assert (short == 0xAB).all(), "no partial write when cap < required"
    finally:
        _native.geo_column_free(handle)


@pytest.mark.parametrize(
    ("status", "kwargs"),
    [
        (
            -11,
            {
                "geometry": _native.GEO_GEOMETRY_POLYGON,
                "xy": _SHELL + _SECOND,  # second ring lies outside the shell
                "validity": [1],
                "offsets0": [0, 2],
                "offsets1": [0, 5, 10],
            },
        ),
        (
            -12,
            {
                "geometry": _native.GEO_GEOMETRY_LINESTRING,
                "xy": [1.0, 1.0],
                "validity": [1],
                "offsets0": [0, 1],
            },
        ),
        (
            -12,
            {  # zero-area (collinear) closed ring
                "geometry": _native.GEO_GEOMETRY_POLYGON,
                "xy": [0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 0.0, 0.0],
                "validity": [1],
                "offsets0": [0, 1],
                "offsets1": [0, 4],
            },
        ),
        (
            -14,
            {  # null feature that still owns vertices
                "geometry": _native.GEO_GEOMETRY_LINESTRING,
                "xy": [0.0, 0.0, 1.0, 1.0],
                "validity": [0],
                "offsets0": [0, 2],
            },
        ),
    ],
)
def test_new_validation_codes_are_stable_and_value_free(status: int, kwargs: dict) -> None:
    with pytest.raises(_native.GeoNativeError) as exc:
        _native.geo_column_new(crs=_native.GEO_CRS_EPSG_4326, **kwargs)
    assert exc.value.status == status
    assert str(exc.value) == _native.GeoNativeError._MESSAGES[status]
    assert "20.0" not in str(exc.value)


def test_empty_line_part_is_still_accepted() -> None:
    handle = _native.geo_column_new(
        geometry=_native.GEO_GEOMETRY_LINESTRING,
        crs=_native.GEO_CRS_EPSG_4326,
        xy=[0.0, 0.0, 1.0, 1.0],
        validity=[1, 1],
        offsets0=[0, 0, 2],
    )
    _native.geo_column_free(handle)


# Resource-limit / malformed proofs with cheap adversarial inputs (A7). The
# claimed counts are huge but no large buffer is ever allocated by the host.
@pytest.mark.parametrize(
    ("status", "kwargs"),
    [
        (  # offset claims 2**31 vertices but only 2 exist
            -4,
            {
                "geometry": _native.GEO_GEOMETRY_LINESTRING,
                "xy": [0.0, 0.0, 1.0, 1.0],
                "validity": [1],
                "offsets0": [0, 2**31],
            },
        ),
        (  # offsets wrap-around (u32 max) must not be trusted
            -4,
            {
                "geometry": _native.GEO_GEOMETRY_LINESTRING,
                "xy": [0.0, 0.0, 1.0, 1.0],
                "validity": [1],
                "offsets0": [0, 2**32 - 1],
            },
        ),
        (  # non-monotonic offsets
            -4,
            {
                "geometry": _native.GEO_GEOMETRY_MULTIPOINT,
                "xy": [0.0, 0.0, 1.0, 1.0],
                "validity": [1, 1],
                "offsets0": [0, 2, 1],
            },
        ),
        (  # depth mismatch: a point column must not carry offsets
            -3,
            {
                "geometry": _native.GEO_GEOMETRY_POINT,
                "xy": [0.0, 0.0],
                "validity": [1],
                "offsets0": [0, 1],
            },
        ),
        (  # polygon without its ring plane
            -3,
            {
                "geometry": _native.GEO_GEOMETRY_POLYGON,
                "xy": _SHELL,
                "validity": [1],
                "offsets0": [0, 1],
            },
        ),
        (  # validity flag outside {0, 1}: incomplete descriptor
            -1,
            {
                "geometry": _native.GEO_GEOMETRY_POINT,
                "xy": [0.0, 0.0],
                "validity": [2],
            },
        ),
    ],
)
def test_adversarial_descriptors_fail_with_stable_code_and_no_handle(
    status: int, kwargs: dict
) -> None:
    def probe() -> int:
        return _native.geo_column_new(
            geometry=_native.GEO_GEOMETRY_POINT,
            crs=_native.GEO_CRS_EPSG_4326,
            xy=[0.0, 0.0],
            validity=[1],
        )

    probe_before = probe()
    try:
        with pytest.raises(_native.GeoNativeError) as exc:
            _native.geo_column_new(crs=_native.GEO_CRS_EPSG_4326, **kwargs)
        assert exc.value.status == status
        probe_after = probe()
        # Handles are a monotonic counter: a rejected descriptor publishes none.
        assert probe_after == probe_before + 1
        _native.geo_column_free(probe_after)
    finally:
        _native.geo_column_free(probe_before)


def test_python_wrapper_rejects_feature_id_length_mismatch_before_ffi() -> None:
    with pytest.raises(ValueError, match="feature_ids"):
        _native.geo_column_new(
            geometry=_native.GEO_GEOMETRY_POINT,
            crs=_native.GEO_CRS_EPSG_4326,
            xy=[0.0, 0.0],
            validity=[1],
            feature_ids=[1, 2],
        )
