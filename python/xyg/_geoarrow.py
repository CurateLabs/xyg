"""Python host GeoArrow → GeoColumn descriptor adapter (#47).

``pyarrow`` is an optional *input* format only — never a runtime dependency of
``xy``. Callers that already hold decoded buffers should use
``xyg._native.geo_column_new`` directly. This module never imports Arrow at
module load; ``ingest_geoarrow`` raises ``ImportError`` when pyarrow is absent.
"""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np

from . import _native

_EXTENSION_TO_GEOMETRY = {
    "geoarrow.point": _native.GEO_GEOMETRY_POINT,
    "geoarrow.linestring": _native.GEO_GEOMETRY_LINESTRING,
    "geoarrow.polygon": _native.GEO_GEOMETRY_POLYGON,
    "geoarrow.multipoint": _native.GEO_GEOMETRY_MULTIPOINT,
    "geoarrow.multilinestring": _native.GEO_GEOMETRY_MULTILINESTRING,
    "geoarrow.multipolygon": _native.GEO_GEOMETRY_MULTIPOLYGON,
}

_CRS_RE = re.compile(r"^EPSG:(\d+)$")


def _require_pyarrow() -> Any:
    try:
        import pyarrow as pa
    except ImportError as exc:  # pragma: no cover - exercised via importorskip tests
        raise ImportError(
            "GeoArrow ingest requires pyarrow; install the xyg[dev] / CI pyarrow extra"
        ) from exc
    return pa


def _parse_crs(metadata: dict[str, str]) -> int:
    meta_json = metadata.get("ARROW:extension:metadata")
    if not meta_json:
        raise _native.GeoNativeError(-2)
    try:
        payload = json.loads(meta_json)
    except json.JSONDecodeError as exc:
        raise _native.GeoNativeError(-1) from exc
    crs = payload.get("crs")
    if not isinstance(crs, str):
        raise _native.GeoNativeError(-2)
    match = _CRS_RE.match(crs.strip())
    if match is None:
        raise _native.GeoNativeError(-2)
    code = int(match.group(1))
    if code not in (_native.GEO_CRS_EPSG_4326, _native.GEO_CRS_EPSG_3857):
        raise _native.GeoNativeError(-2)
    return code


def _geometry_kind(field: Any) -> int:
    extension = (field.metadata or {}).get(b"ARROW:extension:name")
    if extension is None and field.metadata:
        # pyarrow may expose str keys depending on construction path
        extension = field.metadata.get("ARROW:extension:name")
    if isinstance(extension, bytes):
        extension = extension.decode("utf-8")
    if not isinstance(extension, str):
        raise _native.GeoNativeError(-3)
    kind = _EXTENSION_TO_GEOMETRY.get(extension)
    if kind is None:
        raise _native.GeoNativeError(-3)
    return kind


def _field_metadata_str(field: Any) -> dict[str, str]:
    meta = field.metadata or {}
    out: dict[str, str] = {}
    for key, value in meta.items():
        k = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        v = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        out[k] = v
    return out


def _as_array(column: Any) -> Any:
    pa = _require_pyarrow()
    if isinstance(column, pa.ChunkedArray):
        if column.num_chunks == 0:
            return pa.array([], type=column.type)
        if column.num_chunks == 1:
            return column.chunk(0)
        return column.combine_chunks()
    if isinstance(column, pa.Array):
        return column
    raise TypeError("GeoArrow ingest expects a pyarrow Array or ChunkedArray")


def _coordinate_xy(coords: Any) -> np.ndarray:
    """Interleave Struct<x:f64, y:f64> into a contiguous f64 [x0,y0,…]."""
    if coords is None or len(coords) == 0:
        return np.empty(0, dtype=np.float64)
    x = np.ascontiguousarray(coords.field("x").to_numpy(zero_copy_only=False), dtype=np.float64)
    y = np.ascontiguousarray(coords.field("y").to_numpy(zero_copy_only=False), dtype=np.float64)
    if len(x) != len(y):
        raise _native.GeoNativeError(-1)
    out = np.empty(len(x) * 2, dtype=np.float64)
    out[0::2] = x
    out[1::2] = y
    return out


def _list_offsets(array: Any) -> np.ndarray:
    # Arrow list offsets are int32; copy to owned u32 for the descriptor.
    offsets = array.offsets.to_numpy(zero_copy_only=False)
    return np.ascontiguousarray(offsets, dtype=np.uint32)


def _validity(array: Any) -> np.ndarray:
    n = len(array)
    if array.null_count == 0:
        return np.ones(n, dtype=np.uint8)
    bits = array.is_valid()
    return np.ascontiguousarray(bits.to_numpy(zero_copy_only=False), dtype=np.uint8)


def descriptor_from_geoarrow(column: Any, field: Any) -> dict[str, Any]:
    """Decode a GeoArrow array into keyword args for ``geo_column_new``."""
    array = _as_array(column)
    if field is None:
        raise TypeError("GeoArrow ingest requires an Arrow Field carrying extension metadata")

    geometry = _geometry_kind(field)
    crs = _parse_crs(_field_metadata_str(field))
    validity = _validity(array)

    if geometry == _native.GEO_GEOMETRY_POINT:
        # Null points contribute no vertices; pack only present rows.
        if array.null_count == 0:
            xy = _coordinate_xy(array)
        else:
            present = [array[i].as_py() for i in range(len(array)) if array[i].is_valid]
            if not present:
                xy = np.empty(0, dtype=np.float64)
            else:
                xs = np.array([p["x"] for p in present], dtype=np.float64)
                ys = np.array([p["y"] for p in present], dtype=np.float64)
                xy = np.empty(len(xs) * 2, dtype=np.float64)
                xy[0::2] = xs
                xy[1::2] = ys
        return {
            "geometry": geometry,
            "crs": crs,
            "xy": xy,
            "validity": validity,
            "offsets0": None,
            "offsets1": None,
            "offsets2": None,
        }

    if geometry in (_native.GEO_GEOMETRY_LINESTRING, _native.GEO_GEOMETRY_MULTIPOINT):
        offsets0 = _list_offsets(array)
        xy = _coordinate_xy(array.values)
        return {
            "geometry": geometry,
            "crs": crs,
            "xy": xy,
            "validity": validity,
            "offsets0": offsets0,
            "offsets1": None,
            "offsets2": None,
        }

    if geometry in (_native.GEO_GEOMETRY_POLYGON, _native.GEO_GEOMETRY_MULTILINESTRING):
        offsets0 = _list_offsets(array)
        rings = array.values
        offsets1 = _list_offsets(rings)
        xy = _coordinate_xy(rings.values)
        return {
            "geometry": geometry,
            "crs": crs,
            "xy": xy,
            "validity": validity,
            "offsets0": offsets0,
            "offsets1": offsets1,
            "offsets2": None,
        }

    # MultiPolygon
    offsets0 = _list_offsets(array)
    polygons = array.values
    offsets1 = _list_offsets(polygons)
    rings = polygons.values
    offsets2 = _list_offsets(rings)
    xy = _coordinate_xy(rings.values)
    return {
        "geometry": geometry,
        "crs": crs,
        "xy": xy,
        "validity": validity,
        "offsets0": offsets0,
        "offsets1": offsets1,
        "offsets2": offsets2,
    }


def ingest_geoarrow(column: Any, field: Any) -> int:
    """Decode GeoArrow and publish a Rust-owned ``GeoColumn`` handle."""
    desc = descriptor_from_geoarrow(column, field)
    return _native.geo_column_new(**desc)
