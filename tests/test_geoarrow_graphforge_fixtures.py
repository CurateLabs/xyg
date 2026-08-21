"""Conformance against GraphForge's producer-neutral GeoArrow v1 fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pa = pytest.importorskip("pyarrow")
ipc = pytest.importorskip("pyarrow.ipc")
pq = pytest.importorskip("pyarrow.parquet")

from xyg import _geoarrow, _native  # noqa: E402

_ROOT = Path(__file__).parent
_CONTRACT_PATH = _ROOT / "contracts" / "geoarrow-interchange-v1.json"
_FIXTURE_DIR = _ROOT / "fixtures" / "geoarrow-v1"
_GEOMETRY = {
    "point": _native.GEO_GEOMETRY_POINT,
    "line_string": _native.GEO_GEOMETRY_LINESTRING,
    "polygon": _native.GEO_GEOMETRY_POLYGON,
    "multi_point": _native.GEO_GEOMETRY_MULTIPOINT,
    "multi_line_string": _native.GEO_GEOMETRY_MULTILINESTRING,
    "multi_polygon": _native.GEO_GEOMETRY_MULTIPOLYGON,
}


def _contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _tables() -> tuple[dict[str, Any], list[int]]:
    reader = ipc.open_stream(_FIXTURE_DIR / "canonical.arrow")
    batches = list(reader)
    ipc_table = pa.Table.from_batches(batches, schema=reader.schema)
    return (
        {
            "canonical.arrow": ipc_table,
            "canonical.parquet": pq.read_table(_FIXTURE_DIR / "canonical.parquet"),
        },
        [len(batch) for batch in batches],
    )


def _assert_descriptor_equal(left: dict[str, Any], right: dict[str, Any]) -> None:
    assert left.keys() == right.keys()
    for key in left:
        lhs = left[key]
        rhs = right[key]
        if isinstance(lhs, np.ndarray):
            assert isinstance(rhs, np.ndarray)
            np.testing.assert_array_equal(lhs, rhs, strict=True)
        else:
            assert lhs == rhs


def test_graphforge_fixture_hashes_are_pinned() -> None:
    expected = {}
    for line in (_FIXTURE_DIR / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        expected[name] = digest
    assert expected
    assert {"canonical.arrow", "canonical.parquet"} <= expected.keys()
    for name, digest in expected.items():
        assert hashlib.sha256((_FIXTURE_DIR / name).read_bytes()).hexdigest() == digest


def test_graphforge_ipc_and_parquet_descriptors_match_exactly() -> None:
    contract = _contract()
    assert contract["schema"] == "graphforge.geoarrow-interchange.v1"
    assert contract["rows"] == {"populated": 0, "null": 1, "batchSizes": [2]}

    tables, batch_sizes = _tables()
    assert batch_sizes == contract["rows"]["batchSizes"]
    ipc_table = tables["canonical.arrow"]
    parquet_table = tables["canonical.parquet"]
    assert ipc_table.schema.metadata == parquet_table.schema.metadata

    for case in contract["cases"]:
        name = case["name"]
        ipc_field = ipc_table.schema.field(name)
        parquet_field = parquet_table.schema.field(name)
        assert ipc_field.metadata == parquet_field.metadata
        assert ipc_field.metadata[b"ARROW:extension:name"].decode() == case["extensionName"]
        assert ipc_field.metadata[b"ARROW:extension:metadata"].decode() == case["extensionMetadata"]

        if case.get("preservedOnly"):
            # GraphForge transports this value losslessly, while XYG v1 deliberately
            # fails closed because its certified compute profile is EPSG:4326/3857.
            with pytest.raises(_native.GeoNativeError) as exc:
                _geoarrow.descriptor_from_geoarrow(ipc_table[name], ipc_field)
            assert exc.value.status in {-2, -3}
            continue

        ipc_desc = _geoarrow.descriptor_from_geoarrow(ipc_table[name], ipc_field)
        parquet_desc = _geoarrow.descriptor_from_geoarrow(parquet_table[name], parquet_field)
        _assert_descriptor_equal(ipc_desc, parquet_desc)
        assert isinstance(ipc_desc["validity"], np.ndarray)
        np.testing.assert_array_equal(
            ipc_desc["validity"], np.array([1, 0], dtype=np.uint8), strict=True
        )
        assert isinstance(ipc_desc["xy"], np.ndarray)
        np.testing.assert_array_equal(
            ipc_desc["xy"], np.asarray(case["flat"], dtype=np.float64), strict=True
        )

        handle = _native.geo_column_new(**ipc_desc)
        try:
            length, vertices, geometry, crs = _native.geo_column_meta(handle)
            assert length == 2
            assert vertices == len(case["flat"]) // 2
            assert geometry == _GEOMETRY[case["geometry"]]
            assert crs == int(case["crs"].split(":", maxsplit=1)[1])
        finally:
            assert _native.geo_column_free(handle) is True
