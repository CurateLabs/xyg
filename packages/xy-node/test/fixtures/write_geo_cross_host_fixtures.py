#!/usr/bin/env python3
"""Write the Python-authoritative GeoColumn cross-host golden (#47).

Produces ``tests/fixtures/geo_cross_host.json``, consumed by
``tests/test_geo_cross_host.py`` and
``packages/xy-node/test/geo-cross-host.test.mjs``.

Node cannot read Arrow (``@curatelabs/xyg-node`` has no Arrow dependency), so
each case stores the *decoded GeoArrow planes* (the ``arrow`` block: child
coordinate arrays, validity, list offsets, optional feature IDs) next to what
the Python adapter lowered them to (``descriptor``), what Rust retained
(``read_back``) and the canonical ``XYGM`` v1 metadata bytes. Python pins its
adapter + Rust against the golden; Node rebuilds the descriptor from the planes
with ``geoDescriptorFromGeoArrow`` and must reach the same descriptor, the same
read-back planes and byte-identical metadata. Error cases pin the stable status
code both hosts must return.

Every f64 is stored as the 16-hex-digit big-endian image of its IEEE-754 bits
(``"3ff0000000000000"``) so parity is bitwise and NaN / signed zero survive
JSON. u64 feature IDs are decimal strings (JSON numbers cannot hold them).

Run from repo root::

    uv run python packages/xy-node/test/fixtures/write_geo_cross_host_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "python"))

import pyarrow as pa  # noqa: E402
import pyarrow.ipc as ipc  # noqa: E402

from xyg import _geoarrow, _native  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "geo_cross_host.json"
GRAPHFORGE = ROOT / "tests" / "fixtures" / "geoarrow-v1" / "canonical.arrow"
CONTRACT = ROOT / "tests" / "contracts" / "geoarrow-interchange-v1.json"

_COORD = pa.struct([("x", pa.float64()), ("y", pa.float64())])
_SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
_HOLE = [(2.0, 2.0), (2.0, 4.0), (4.0, 4.0), (4.0, 2.0), (2.0, 2.0)]
_SECOND = [(20.0, 20.0), (30.0, 20.0), (30.0, 30.0), (20.0, 30.0), (20.0, 20.0)]
_THIRD_HOLE = [(22.0, 22.0), (22.0, 24.0), (24.0, 24.0), (24.0, 22.0), (22.0, 22.0)]


def bits(values: Any) -> list[str]:
    arr = np.ascontiguousarray(values, dtype=np.float64)
    return [f"{int(v):016x}" for v in arr.view(np.uint64)]


def ints(values: Any) -> list[int]:
    return [int(v) for v in values]


def u64s(values: Any) -> list[str]:
    return [str(int(v)) for v in values]


def _pts(coords: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in coords]


def _field(extension: str, storage: pa.DataType, crs: str = "EPSG:4326") -> pa.Field:
    meta = json.dumps({"crs": crs, "crs_type": "authority_code"}, separators=(",", ":"))
    return pa.field(
        "geometry",
        storage,
        metadata={
            b"ARROW:extension:name": extension.encode(),
            b"ARROW:extension:metadata": meta.encode(),
        },
    )


def _arrow_planes(array: Any, feature_ids: Any) -> dict[str, Any]:
    """GeoArrow planes read straight from the Arrow nesting (independent of the adapter)."""
    offsets: list[list[int]] = []
    level = array
    while hasattr(level, "offsets"):
        offsets.append(ints(level.offsets.to_numpy(zero_copy_only=False)))
        level = level.values
    x = np.asarray(level.field("x").to_numpy(zero_copy_only=False), dtype=np.float64)
    y = np.asarray(level.field("y").to_numpy(zero_copy_only=False), dtype=np.float64)
    return {
        "x": bits(x),
        "y": bits(y),
        "validity": ints(array.is_valid().to_numpy(zero_copy_only=False)),
        "offsets": offsets,
        "feature_ids": None if feature_ids is None else u64s(np.asarray(feature_ids)),
    }


def _descriptor_block(desc: dict[str, Any]) -> dict[str, Any]:
    def plane(key: str) -> list[int] | None:
        value = desc.get(key)
        return None if value is None else ints(value)

    ids = desc.get("feature_ids")
    return {
        "xy": bits(desc["xy"]),
        "validity": ints(desc["validity"]),
        "feature_ids": None if ids is None else u64s(ids),
        "offsets0": plane("offsets0"),
        "offsets1": plane("offsets1"),
        "offsets2": plane("offsets2"),
    }


def _read_back_block(planes: dict[str, np.ndarray]) -> dict[str, Any]:
    return {
        "xy": bits(planes["xy"]),
        "validity": ints(planes["validity"]),
        "feature_ids": u64s(planes["feature_ids"]),
        "offsets0": ints(planes["offsets0"]),
        "offsets1": ints(planes["offsets1"]),
        "offsets2": ints(planes["offsets2"]),
        "orientations": ints(planes["orientations"]),
    }


def _publish(desc: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    """Run the descriptor through Rust; return ``(status, ok-block)``."""
    try:
        handle = _native.geo_column_new(**desc)
    except _native.GeoNativeError as exc:
        return exc.status, None
    try:
        metadata = _native.geo_column_metadata(handle)
        block = {
            "read_back": _read_back_block(_native.geo_column_read(handle)),
            "metadata_len": len(metadata),
            "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
            "metadata_hex": metadata.hex(),
        }
    finally:
        _native.geo_column_free(handle)
    return 0, block


def case_from_arrow(
    name: str,
    field: pa.Field,
    array: Any,
    *,
    feature_ids: Any = None,
    expect: int = 0,
) -> dict[str, Any]:
    meta = field.metadata
    entry: dict[str, Any] = {
        "name": name,
        "extension_name": meta[b"ARROW:extension:name"].decode(),
        "extension_metadata": meta[b"ARROW:extension:metadata"].decode(),
        "arrow": _arrow_planes(array, feature_ids),
        "pyarrow": True,
        "descriptor": None,
    }
    try:
        desc = _geoarrow.descriptor_from_geoarrow(array, field, feature_ids=feature_ids)
    except _native.GeoNativeError as exc:
        status = exc.status
    else:
        entry["descriptor"] = _descriptor_block(desc)
        status, block = _publish(desc)
        if block is not None:
            entry.update(block)
    assert status == expect, (name, status, expect)
    entry["status"] = status
    return entry


def case_from_planes(
    name: str,
    extension: str,
    *,
    geometry: int,
    x: list[float],
    y: list[float],
    validity: list[int],
    offsets: list[list[int]],
    expect: int,
    crs: str = "EPSG:4326",
) -> dict[str, Any]:
    """Hand-authored planes Arrow cannot express (offsets that overrun the values)."""
    xy = np.empty(len(x) * 2, dtype=np.float64)
    xy[0::2], xy[1::2] = x, y
    desc: dict[str, Any] = {
        "geometry": geometry,
        "crs": int(crs.split(":")[1]),
        "xy": xy,
        "validity": np.asarray(validity, dtype=np.uint8),
        "feature_ids": None,
        **{f"offsets{i}": np.asarray(plane, dtype=np.uint32) for i, plane in enumerate(offsets)},
    }
    status, block = _publish(desc)
    assert status == expect, (name, status, expect)
    entry: dict[str, Any] = {
        "name": name,
        "extension_name": extension,
        "extension_metadata": json.dumps(
            {"crs": crs, "crs_type": "authority_code"}, separators=(",", ":")
        ),
        "arrow": {
            "x": bits(x),
            "y": bits(y),
            "validity": validity,
            "offsets": offsets,
            "feature_ids": None,
        },
        "pyarrow": False,
        "descriptor": _descriptor_block(desc),
        "status": status,
    }
    if block is not None:
        entry.update(block)
    return entry


def graphforge_cases() -> list[dict[str, Any]]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    reader = ipc.open_stream(GRAPHFORGE)
    table = pa.Table.from_batches(list(reader), schema=reader.schema)
    cases = []
    for case in contract["cases"]:
        name = case["name"]
        field = table.schema.field(name)
        array = table[name].combine_chunks()
        # preserved-only vendor kinds fail closed at the adapter (-3: unknown kind).
        expect = -3 if case.get("preservedOnly") else 0
        entry = case_from_arrow(f"graphforge_{name}", field, array, expect=expect)
        entry["source"] = "tests/fixtures/geoarrow-v1/canonical.arrow"
        cases.append(entry)
    return cases


def local_cases() -> list[dict[str, Any]]:
    poly_t = pa.list_(pa.list_(_COORD))
    multipoly_t = pa.list_(pa.list_(pa.list_(_COORD)))
    line_t = pa.list_(_COORD)

    def polygons(rows: list[Any]) -> pa.Array:
        return pa.array(
            [None if r is None else [_pts(ring) for ring in r] for r in rows], type=poly_t
        )

    def multipolygons(rows: list[Any]) -> pa.Array:
        return pa.array(
            [None if r is None else [[_pts(ring) for ring in poly] for poly in r] for r in rows],
            type=multipoly_t,
        )

    cases: list[dict[str, Any]] = []
    cases.append(
        case_from_arrow(
            "polygon_with_hole_4326",
            _field("geoarrow.polygon", poly_t),
            polygons([[_SQUARE, _HOLE]]),
            feature_ids=[901],
        )
    )
    cases.append(
        case_from_arrow(
            "polygon_clockwise_shell_null_feature",
            _field("geoarrow.polygon", poly_t),
            polygons([None, [_SQUARE[::-1], _HOLE[::-1]]]),
        )
    )
    cases.append(
        case_from_arrow(
            "multipolygon_two_polygons_with_holes",
            _field("geoarrow.multipolygon", multipoly_t),
            multipolygons([[[_SQUARE, _HOLE], [_SECOND, _THIRD_HOLE]], None, [[_SECOND]]]),
        )
    )
    cases.append(
        case_from_arrow(
            "linestring_3857",
            _field("geoarrow.linestring", line_t, "EPSG:3857"),
            pa.array(
                [_pts([(-11687469.0, 4825942.0), (-11687000.5, 4826000.25)])],
                type=line_t,
            ),
        )
    )
    cases.append(
        case_from_arrow(
            "multipoint_with_null",
            _field("geoarrow.multipoint", line_t),
            pa.array([_pts([(0.0, 0.0), (1.0, 1.0)]), None, _pts([(2.0, 2.0)])], type=line_t),
        )
    )
    cases.append(
        case_from_arrow(
            "multilinestring_empty_part_and_null",
            _field("geoarrow.multilinestring", poly_t),
            pa.array(
                [
                    [_pts([(0.0, 0.0), (1.0, 1.0)]), [], _pts([(2.0, 2.0), (3.0, 3.0)])],
                    None,
                ],
                type=poly_t,
            ),
        )
    )
    cases.append(
        case_from_arrow(
            "point_nulls_u64_feature_ids",
            _field("geoarrow.point", _COORD),
            pa.array(
                [None, {"x": -104.9903, "y": 39.7392}, None, {"x": 0.1 + 0.2, "y": -0.0}],
                type=_COORD,
            ),
            feature_ids=np.array([2**63 + 5, 2**53 + 1, 0, 2**64 - 1], dtype=np.uint64),
        )
    )
    cases.append(
        case_from_arrow(
            "point_f64_not_f32_representable",
            _field("geoarrow.point", _COORD),
            pa.array([{"x": -104.99030000000001, "y": 39.739199999999997}], type=_COORD),
        )
    )
    cases.append(
        case_from_arrow(
            "empty_linestring_column",
            _field("geoarrow.linestring", line_t),
            pa.array([], type=line_t),
        )
    )

    # Error cases: both hosts must return the same stable status and publish nothing.
    cases.append(
        case_from_arrow(
            "error_hole_outside_shell",
            _field("geoarrow.polygon", poly_t),
            polygons([[_SQUARE, _SECOND]]),
            expect=-11,
        )
    )
    cases.append(
        case_from_arrow(
            "error_ring_not_closed",
            _field("geoarrow.polygon", poly_t),
            polygons([[_SQUARE[:4]]]),
            expect=-8,
        )
    )
    cases.append(
        case_from_arrow(
            "error_zero_area_ring",
            _field("geoarrow.polygon", poly_t),
            polygons([[[(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (0.0, 0.0)]]]),
            expect=-12,
        )
    )
    cases.append(
        case_from_arrow(
            "error_one_vertex_linestring",
            _field("geoarrow.linestring", line_t),
            pa.array([_pts([(1.0, 1.0)])], type=line_t),
            expect=-12,
        )
    )
    cases.append(
        case_from_arrow(
            "error_null_linestring_owns_vertices",
            _field("geoarrow.linestring", line_t),
            pa.ListArray.from_arrays(
                pa.array([0, 2], pa.int32()),
                pa.array(_pts([(0.0, 0.0), (1.0, 1.0)]), type=_COORD),
                mask=pa.array([True]),
            ),
            expect=-14,
        )
    )
    cases.append(
        case_from_arrow(
            "error_non_finite_coordinate",
            _field("geoarrow.point", _COORD),
            pa.array([{"x": float("nan"), "y": 0.0}], type=_COORD),
            expect=-6,
        )
    )
    cases.append(
        case_from_arrow(
            "error_out_of_range_longitude",
            _field("geoarrow.point", _COORD),
            pa.array([{"x": 181.0, "y": 0.0}], type=_COORD),
            expect=-7,
        )
    )
    cases.append(
        case_from_arrow(
            "error_unsupported_crs",
            _field("geoarrow.point", _COORD, "EPSG:9999"),
            pa.array([{"x": 0.0, "y": 0.0}], type=_COORD),
            expect=-2,
        )
    )
    cases.append(
        case_from_arrow(
            "error_feature_ids_length_mismatch",
            _field("geoarrow.point", _COORD),
            pa.array([{"x": 0.0, "y": 0.0}], type=_COORD),
            feature_ids=[1, 2],
            expect=-1,
        )
    )
    # Offsets Arrow itself refuses to build: the Rust validator is the only gate.
    cases.append(
        case_from_planes(
            "error_offset_overruns_vertices",
            "geoarrow.linestring",
            geometry=_native.GEO_GEOMETRY_LINESTRING,
            x=[0.0, 1.0],
            y=[0.0, 1.0],
            validity=[1],
            offsets=[[0, 2**31]],
            expect=-4,
        )
    )
    cases.append(
        case_from_planes(
            "error_non_monotonic_offsets",
            "geoarrow.multipoint",
            geometry=_native.GEO_GEOMETRY_MULTIPOINT,
            x=[0.0, 1.0],
            y=[0.0, 1.0],
            validity=[1, 1],
            offsets=[[0, 2, 1]],
            expect=-4,
        )
    )
    return cases


def build_document() -> dict[str, Any]:
    """The golden document; ``tests/test_geo_cross_host.py`` diffs it against the checked-in file."""
    cases = graphforge_cases() + local_cases()
    names = [c["name"] for c in cases]
    assert len(names) == len(set(names))
    return {
        "schema": "xyg.geo-cross-host/v1",
        "authority": "python/xyg/_geoarrow.py + crates/xyg-engine/src/geo.rs (XYGM v1)",
        "abi_version": int(_native.ABI_VERSION),
        "encoding": {
            "f64": "16 hex digits, big-endian IEEE-754 bit pattern",
            "u64": "decimal string",
        },
        "cases": cases,
    }


def main() -> None:
    doc = build_document()
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(doc['cases'])} cases)")


if __name__ == "__main__":
    main()
