"""Property tests for the GeoColumn descriptor boundary (#47).

Hypothesis builds structurally valid descriptors for all six GeoArrow kinds,
optionally mutates them adversarially (offset corruption, non-finite and
out-of-range coordinates, broken nulls, unsupported CRS, truncated planes), and
asserts the boundary contract:

* an unmutated descriptor is accepted and reads back bit-for-bit;
* any descriptor either yields a handle or raises ``GeoNativeError`` with a
  stable ``-1..-14`` status (never another exception, never a crash);
* a rejected descriptor publishes no handle (the registry hands out handles
  from a monotonic counter, so a failed call must not advance it);
* error text never carries coordinate values.
"""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")
given = hypothesis.given
settings = hypothesis.settings

import numpy as np  # noqa: E402

from xyg import _native  # noqa: E402

_KINDS = (
    _native.GEO_GEOMETRY_POINT,
    _native.GEO_GEOMETRY_LINESTRING,
    _native.GEO_GEOMETRY_POLYGON,
    _native.GEO_GEOMETRY_MULTIPOINT,
    _native.GEO_GEOMETRY_MULTILINESTRING,
    _native.GEO_GEOMETRY_MULTIPOLYGON,
)
_STABLE_CODES = set(range(-14, 0)) - {-10, -13}
_BAD_VALUES = (float("nan"), float("inf"), float("-inf"), 181.0, -181.0, 1e8, 91.0)


def _ring(cx: float, cy: float, half: float, reverse: bool) -> list[tuple[float, float]]:
    pts = [
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
        (cx - half, cy - half),
    ]
    return pts[::-1] if reverse else pts


@st.composite
def _polygon_rings(draw: st.DrawFn) -> list[list[tuple[float, float]]]:
    """Exterior square plus 0-2 holes strictly inside it (valid by construction)."""
    cx = draw(st.floats(-60, 60))
    cy = draw(st.floats(-60, 60))
    half = draw(st.floats(5, 20))
    rings = [_ring(cx, cy, half, draw(st.booleans()))]
    for i in range(draw(st.integers(0, 2))):
        shift = (i - 0.5) * half * 0.8
        rings.append(_ring(cx + shift, cy, half / 8, draw(st.booleans())))
    return rings


@st.composite
def _valid_columns(draw: st.DrawFn) -> dict[str, object]:
    geometry = draw(st.sampled_from(_KINDS))
    crs = draw(st.sampled_from((4326, 3857)))
    n = draw(st.integers(0, 4))
    validity = [draw(st.sampled_from((0, 1, 1))) for _ in range(n)]
    coord = st.tuples(st.floats(-170, 170), st.floats(-80, 80))

    xy: list[float] = []
    o0: list[int] = [0]
    o1: list[int] = [0]
    o2: list[int] = [0]

    def emit(points: list[tuple[float, float]]) -> int:
        for x, y in points:
            xy.extend((x, y))
        return len(points)

    for ok in validity:
        if geometry == _native.GEO_GEOMETRY_POINT:
            if ok:
                emit([draw(coord)])
        elif geometry in (_native.GEO_GEOMETRY_LINESTRING, _native.GEO_GEOMETRY_MULTIPOINT):
            floor = 2 if geometry == _native.GEO_GEOMETRY_LINESTRING else 0
            count = draw(st.integers(floor, 5)) if ok else 0
            if ok and geometry == _native.GEO_GEOMETRY_LINESTRING and count == 0:
                count = 2
            emit(draw(st.lists(coord, min_size=count, max_size=count)))
            o0.append(len(xy) // 2)
        elif geometry == _native.GEO_GEOMETRY_MULTILINESTRING:
            lines = draw(st.integers(0, 3)) if ok else 0
            for _ in range(lines):
                emit(draw(st.lists(coord, min_size=2, max_size=4)))
                o1.append(len(xy) // 2)
            o0.append(len(o1) - 1)
        elif geometry == _native.GEO_GEOMETRY_POLYGON:
            if ok:
                for ring in draw(_polygon_rings()):
                    emit(ring)
                    o1.append(len(xy) // 2)
            o0.append(len(o1) - 1)
        else:  # multipolygon
            polygons = draw(st.integers(0, 2)) if ok else 0
            for _ in range(polygons):
                for ring in draw(_polygon_rings()):
                    emit(ring)
                    o2.append(len(xy) // 2)
                o1.append(len(o2) - 1)
            o0.append(len(o1) - 1)

    depth = {
        _native.GEO_GEOMETRY_POINT: 0,
        _native.GEO_GEOMETRY_LINESTRING: 1,
        _native.GEO_GEOMETRY_MULTIPOINT: 1,
        _native.GEO_GEOMETRY_POLYGON: 2,
        _native.GEO_GEOMETRY_MULTILINESTRING: 2,
        _native.GEO_GEOMETRY_MULTIPOLYGON: 3,
    }[geometry]
    planes = [o0, o1, o2]
    return {
        "geometry": geometry,
        "crs": crs,
        "xy": np.asarray(xy, dtype=np.float64),
        "validity": np.asarray(validity, dtype=np.uint8),
        "feature_ids": (
            np.asarray(draw(st.lists(st.integers(0, 2**63), min_size=n, max_size=n)), np.uint64)
            if draw(st.booleans())
            else None
        ),
        "offsets0": np.asarray(planes[0], dtype=np.uint32) if depth >= 1 else None,
        "offsets1": np.asarray(planes[1], dtype=np.uint32) if depth >= 2 else None,
        "offsets2": np.asarray(planes[2], dtype=np.uint32) if depth >= 3 else None,
    }


@st.composite
def _mutated(draw: st.DrawFn, desc: dict[str, object]) -> dict[str, object]:
    out = dict(desc)
    for key in ("xy", "validity", "offsets0", "offsets1", "offsets2"):
        if out[key] is not None:
            out[key] = np.array(out[key], copy=True)
    kind = draw(
        st.sampled_from(
            (
                "bad_coordinate",
                "inflate_offset",
                "shuffle_offset",
                "truncate_xy",
                "bad_validity",
                "unsupported_crs",
                "wrong_kind",
                "drop_plane",
                "nullify_with_data",
                "break_ring",
                "collapse",
            )
        )
    )
    xy = out["xy"]
    assert isinstance(xy, np.ndarray)
    offsets = [k for k in ("offsets0", "offsets1", "offsets2") if out[k] is not None]
    if kind == "bad_coordinate" and len(xy):
        xy[draw(st.integers(0, len(xy) - 1))] = draw(st.sampled_from(_BAD_VALUES))
    elif kind == "inflate_offset" and offsets:
        plane = out[draw(st.sampled_from(offsets))]
        assert isinstance(plane, np.ndarray)
        plane[-1] = np.uint32(draw(st.sampled_from((2**31, 2**32 - 1, int(plane[-1]) + 1))))
    elif kind == "shuffle_offset" and offsets:
        plane = out[draw(st.sampled_from(offsets))]
        assert isinstance(plane, np.ndarray)
        if len(plane) >= 2:
            i = draw(st.integers(0, len(plane) - 1))
            j = draw(st.integers(0, len(plane) - 1))
            plane[i], plane[j] = plane[j], plane[i]
    elif kind == "truncate_xy" and len(xy) >= 2:
        # Even length: odd interleaved lengths are rejected by the host wrapper itself.
        out["xy"] = xy[: 2 * draw(st.integers(0, len(xy) // 2 - 1))]
    elif kind == "bad_validity" and len(out["validity"]):  # type: ignore[arg-type]
        out["validity"][draw(st.integers(0, len(out["validity"]) - 1))] = 2  # type: ignore[index,arg-type]
    elif kind == "unsupported_crs":
        out["crs"] = draw(st.sampled_from((0, 4269, 9999)))
    elif kind == "wrong_kind":
        out["geometry"] = draw(st.sampled_from(_KINDS))
    elif kind == "drop_plane" and offsets:
        out[draw(st.sampled_from(offsets))] = None
    elif kind == "nullify_with_data" and len(out["validity"]):  # type: ignore[arg-type]
        out["validity"][draw(st.integers(0, len(out["validity"]) - 1))] = 0  # type: ignore[index,arg-type]
    elif kind == "collapse" and len(xy) >= 2:
        xy[0::2] = xy[0]  # every vertex identical: zero-length lines, zero-area rings
        xy[1::2] = xy[1]
    elif kind == "break_ring" and len(xy) >= 2:
        xy[-1] = xy[-1] + 1.0  # opens the last ring / moves the last vertex
    return out


def _probe() -> int:
    return _native.geo_column_new(
        geometry=_native.GEO_GEOMETRY_POINT,
        crs=_native.GEO_CRS_EPSG_4326,
        xy=[0.0, 0.0],
        validity=[1],
    )


def _bits(values: np.ndarray) -> list[int]:
    return np.ascontiguousarray(values, dtype=np.float64).view(np.uint64).tolist()


@settings(max_examples=200, deadline=None)
@given(desc=_valid_columns())
def test_valid_descriptors_are_accepted_and_read_back_exactly(desc: dict[str, object]) -> None:
    handle = _native.geo_column_new(**desc)  # type: ignore[arg-type]
    twin = _native.geo_column_new(**desc)  # type: ignore[arg-type]
    try:
        planes = _native.geo_column_read(handle)
        xy = desc["xy"]
        assert isinstance(xy, np.ndarray)
        assert _bits(planes["xy"]) == _bits(xy)
        assert planes["validity"].tolist() == np.asarray(desc["validity"]).tolist()
        for key in ("offsets0", "offsets1", "offsets2"):
            want = desc[key]
            assert planes[key].tolist() == ([] if want is None else np.asarray(want).tolist())
        ids = desc["feature_ids"]
        n = len(planes["validity"])
        want_ids = list(range(n)) if ids is None else np.asarray(ids).tolist()
        assert planes["feature_ids"].tolist() == want_ids
        # Orientation entries exist exactly for polygon rings.
        is_polygon = desc["geometry"] in (
            _native.GEO_GEOMETRY_POLYGON,
            _native.GEO_GEOMETRY_MULTIPOLYGON,
        )
        assert (len(planes["orientations"]) > 0) == (is_polygon and len(xy) > 0)
        assert set(planes["orientations"].tolist()) <= {1, 2}
        # Canonical metadata is a pure function of the retained planes.
        assert _native.geo_column_metadata(handle) == _native.geo_column_metadata(twin)
    finally:
        _native.geo_column_free(handle)
        _native.geo_column_free(twin)


@settings(max_examples=500, deadline=None)
@given(data=st.data())
def test_mutated_descriptors_fail_closed_with_stable_codes(data: st.DataObject) -> None:
    desc = data.draw(_mutated(data.draw(_valid_columns())))
    before = _probe()
    handle = 0
    try:
        try:
            handle = _native.geo_column_new(**desc)  # type: ignore[arg-type]
        except _native.GeoNativeError as exc:
            assert exc.status in _STABLE_CODES
            assert exc.args[0] == _native.GeoNativeError._MESSAGES[exc.status]
            for value in ("181", "1e+08", "9999", "4269", "nan", "inf"):
                assert value not in exc.args[0]
            published = False
        else:
            published = True
        after = _probe()
        try:
            # A rejected descriptor publishes no handle: the counter advanced by
            # exactly one (our own probe); an accepted one advanced by two.
            assert after == before + (2 if published else 1)
        finally:
            _native.geo_column_free(after)
    finally:
        if handle:
            _native.geo_column_free(handle)
        _native.geo_column_free(before)
