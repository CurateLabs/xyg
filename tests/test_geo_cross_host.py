"""Cross-host GeoColumn golden: Python authoring + Rust retention (#47, AC2).

``tests/fixtures/geo_cross_host.json`` is authored by
``packages/xy-node/test/fixtures/write_geo_cross_host_fixtures.py`` from real
pyarrow GeoArrow arrays. This module pins the Python side:

* the golden is current (rebuilding it from the adapter + Rust reproduces the
  checked-in bytes, so a behavior change must regenerate the file);
* every descriptor publishes through Rust, reads back bit-for-bit, and yields
  the canonical ``XYGM`` v1 metadata bytes recorded in the golden;
* the pyarrow adapter lowers the stored GeoArrow planes to the stored
  descriptor (needs pyarrow);
* error cases return the pinned stable status and publish no handle.

``packages/xy-node/test/geo-cross-host.test.mjs`` consumes the same file and
must reach the same bytes from Node, so both hosts agree byte for byte.

Regenerate::

    uv run python packages/xy-node/test/fixtures/write_geo_cross_host_fixtures.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from xyg import _geoarrow, _native

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "geo_cross_host.json"
FIXTURE_WRITER = (
    ROOT / "packages" / "xy-node" / "test" / "fixtures" / "write_geo_cross_host_fixtures.py"
)

_FIXTURE: dict[str, Any] = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
_CASES: list[dict[str, Any]] = _FIXTURE["cases"]
_OK = [c for c in _CASES if c["status"] == 0]
_ERRORS = [c for c in _CASES if c["status"] != 0]
_GEOMETRY = {
    "geoarrow.point": _native.GEO_GEOMETRY_POINT,
    "geoarrow.linestring": _native.GEO_GEOMETRY_LINESTRING,
    "geoarrow.polygon": _native.GEO_GEOMETRY_POLYGON,
    "geoarrow.multipoint": _native.GEO_GEOMETRY_MULTIPOINT,
    "geoarrow.multilinestring": _native.GEO_GEOMETRY_MULTILINESTRING,
    "geoarrow.multipolygon": _native.GEO_GEOMETRY_MULTIPOLYGON,
}


def _f64(bit_strings: list[str]) -> np.ndarray:
    return np.array([int(b, 16) for b in bit_strings], dtype=np.uint64).view(np.float64)


def _u64(values: list[str]) -> np.ndarray:
    return np.array([int(v) for v in values], dtype=np.uint64)


def _descriptor(case: dict[str, Any]) -> dict[str, Any]:
    block = case["descriptor"]
    crs = int(json.loads(case["extension_metadata"])["crs"].split(":")[1])
    return {
        "geometry": _GEOMETRY[case["extension_name"]],
        "crs": crs,
        "xy": _f64(block["xy"]),
        "validity": np.array(block["validity"], dtype=np.uint8),
        "feature_ids": None if block["feature_ids"] is None else _u64(block["feature_ids"]),
        **{
            key: None if block[key] is None else np.array(block[key], dtype=np.uint32)
            for key in ("offsets0", "offsets1", "offsets2")
        },
    }


def _bits(values: np.ndarray) -> list[int]:
    return np.ascontiguousarray(values, dtype=np.float64).view(np.uint64).tolist()


def test_golden_shape_and_abi_version() -> None:
    assert _FIXTURE["schema"] == "xyg.geo-cross-host/v1"
    assert int(_FIXTURE["abi_version"]) == int(_native.ABI_VERSION)
    names = [c["name"] for c in _CASES]
    assert len(names) == len(set(names))
    # Every GeoArrow kind, nulls, holes, both CRS values and the error classes are covered.
    assert {c["extension_name"] for c in _OK} == set(_GEOMETRY)
    assert {c["status"] for c in _ERRORS} >= {-1, -2, -3, -4, -6, -7, -8, -11, -12, -14}
    assert any(c["extension_metadata"].find("EPSG:3857") >= 0 for c in _OK)
    assert any(0 in c["arrow"]["validity"] for c in _OK)
    assert any(2 in c["read_back"]["orientations"] for c in _OK)


def test_golden_is_current() -> None:
    pytest.importorskip("pyarrow")
    spec = importlib.util.spec_from_file_location("write_geo_cross_host_fixtures", FIXTURE_WRITER)
    assert spec is not None and spec.loader is not None
    writer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(writer)
    assert json.loads(json.dumps(writer.build_document())) == _FIXTURE, (
        "geo_cross_host.json is stale; regenerate with "
        "`uv run python packages/xy-node/test/fixtures/write_geo_cross_host_fixtures.py`"
    )


@pytest.mark.parametrize("case", _OK, ids=lambda c: c["name"])
def test_descriptor_publishes_reads_back_and_matches_metadata(case: dict[str, Any]) -> None:
    desc = _descriptor(case)
    handle = _native.geo_column_new(**desc)
    try:
        planes = _native.geo_column_read(handle)
        want = case["read_back"]
        assert _bits(planes["xy"]) == [int(b, 16) for b in want["xy"]]
        assert planes["validity"].tolist() == want["validity"]
        assert planes["feature_ids"].tolist() == [int(v) for v in want["feature_ids"]]
        for key in ("offsets0", "offsets1", "offsets2", "orientations"):
            assert planes[key].tolist() == want[key], key
        # The source f64 bits are retained exactly as authored.
        assert _bits(planes["xy"]) == _bits(desc["xy"])

        metadata = _native.geo_column_metadata(handle)
        assert len(metadata) == case["metadata_len"]
        assert metadata.hex() == case["metadata_hex"]
        assert hashlib.sha256(metadata).hexdigest() == case["metadata_sha256"]
        assert metadata[:4] == b"XYGM"
    finally:
        assert _native.geo_column_free(handle) is True


@pytest.mark.parametrize(
    "case", [c for c in _ERRORS if c["descriptor"] is not None], ids=lambda c: c["name"]
)
def test_error_descriptors_return_pinned_status_and_publish_nothing(case: dict[str, Any]) -> None:
    def probe() -> int:
        return _native.geo_column_new(
            geometry=_native.GEO_GEOMETRY_POINT,
            crs=_native.GEO_CRS_EPSG_4326,
            xy=[0.0, 0.0],
            validity=[1],
        )

    before = probe()
    try:
        with pytest.raises(_native.GeoNativeError) as exc:
            _native.geo_column_new(**_descriptor(case))
        assert exc.value.status == case["status"]
        after = probe()
        assert after == before + 1  # monotonic handle counter: nothing was published
        _native.geo_column_free(after)
    finally:
        _native.geo_column_free(before)


def _arrow_array(pa: Any, case: dict[str, Any]) -> tuple[Any, Any]:
    """Rebuild the pyarrow GeoArrow array + field from the golden's stored planes."""
    planes = case["arrow"]
    coord = pa.struct([("x", pa.float64()), ("y", pa.float64())])
    x = pa.array(_f64(planes["x"]), type=pa.float64())
    y = pa.array(_f64(planes["y"]), type=pa.float64())
    validity = np.array(planes["validity"], dtype=bool)
    offsets = planes["offsets"]
    storage: Any = coord
    if not offsets:
        array: Any = pa.StructArray.from_arrays([x, y], names=["x", "y"], mask=pa.array(~validity))
    else:
        array = pa.StructArray.from_arrays([x, y], names=["x", "y"])
        for depth, plane in enumerate(reversed(offsets)):
            outermost = depth == len(offsets) - 1
            mask = pa.array(~validity) if outermost else None
            array = pa.ListArray.from_arrays(pa.array(plane, type=pa.int32()), array, mask=mask)
            storage = pa.list_(storage)
    field = pa.field(
        "geometry",
        storage,
        metadata={
            b"ARROW:extension:name": case["extension_name"].encode(),
            b"ARROW:extension:metadata": case["extension_metadata"].encode(),
        },
    )
    return array, field


@pytest.mark.parametrize("case", [c for c in _CASES if c["pyarrow"]], ids=lambda c: c["name"])
def test_pyarrow_adapter_lowers_stored_planes_to_the_golden_descriptor(
    case: dict[str, Any],
) -> None:
    pa = pytest.importorskip("pyarrow")
    array, field = _arrow_array(pa, case)
    ids = case["arrow"]["feature_ids"]
    feature_ids = None if ids is None else _u64(ids)
    if case["descriptor"] is None:
        with pytest.raises(_native.GeoNativeError) as exc:
            _geoarrow.descriptor_from_geoarrow(array, field, feature_ids=feature_ids)
        assert exc.value.status == case["status"]
        return
    got = _geoarrow.descriptor_from_geoarrow(array, field, feature_ids=feature_ids)
    want = _descriptor(case)
    assert got["geometry"] == want["geometry"]
    assert got["crs"] == want["crs"]
    assert _bits(got["xy"]) == _bits(want["xy"])
    assert got["validity"].tolist() == want["validity"].tolist()
    for key in ("feature_ids", "offsets0", "offsets1", "offsets2"):
        if want[key] is None:
            assert got[key] is None, key
        else:
            assert got[key].tolist() == want[key].tolist(), key
