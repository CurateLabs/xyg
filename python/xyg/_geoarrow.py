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
    if not isinstance(payload, dict):
        raise _native.GeoNativeError(-2)
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


def _coordinate_xy(coords: Any, validity: np.ndarray | None = None) -> np.ndarray:
    """Pack certified separated XY f64, preserving nullable point alignment."""
    pa = _require_pyarrow()
    if (
        not pa.types.is_struct(coords.type)
        or coords.type.names != ["x", "y"]
        or any(coords.type.field(name).type != pa.float64() for name in ("x", "y"))
    ):
        raise _native.GeoNativeError(-3)
    present = np.ones(len(coords), dtype=bool) if validity is None else validity.astype(bool)
    if validity is None and coords.null_count:
        raise _native.GeoNativeError(-5)
    for name in ("x", "y"):
        child = coords.field(name)
        if child.null_count and np.any(child.is_null().to_numpy(zero_copy_only=False) & present):
            raise _native.GeoNativeError(-5)
    x = coords.field("x").to_numpy(zero_copy_only=False)
    y = coords.field("y").to_numpy(zero_copy_only=False)
    out = np.empty(int(present.sum()) * 2, dtype=np.float64)
    out[0::2] = x[present]
    out[1::2] = y[present]
    return out


def _list_children(array: Any) -> tuple[np.ndarray, Any]:
    """Rebase one Arrow List slice and retain only its referenced children."""
    pa = _require_pyarrow()
    if not pa.types.is_list(array.type):
        raise _native.GeoNativeError(-3)
    offsets = array.offsets.to_numpy(zero_copy_only=False)
    start, end = int(offsets[0]), int(offsets[-1])
    return np.ascontiguousarray(offsets - start, dtype=np.uint32), array.values.slice(
        start, end - start
    )


def _validity(array: Any) -> np.ndarray:
    n = len(array)
    if array.null_count == 0:
        return np.ones(n, dtype=np.uint8)
    bits = array.is_valid()
    return np.ascontiguousarray(bits.to_numpy(zero_copy_only=False), dtype=np.uint8)


def _feature_ids(feature_ids: Any, n_features: int) -> np.ndarray | None:
    """Normalise explicit feature identity to a contiguous u64 array.

    Accepts a pyarrow ``Array`` / ``ChunkedArray`` (int64 or uint64, no nulls),
    a numpy array, or any sequence of non-negative integers. Length must equal
    the feature count; anything else is the Rust-stable ``-1`` (incomplete or
    inconsistent descriptor), never a silent truncation or re-numbering.
    """
    if feature_ids is None:
        return None
    if hasattr(feature_ids, "null_count") or hasattr(feature_ids, "num_chunks"):
        arrow_ids = feature_ids
        if hasattr(arrow_ids, "num_chunks"):
            arrow_ids = _as_array(arrow_ids)
        if arrow_ids.null_count:
            raise _native.GeoNativeError(-1)
        raw = np.asarray(arrow_ids.to_numpy(zero_copy_only=False))
    else:
        raw = np.asarray(feature_ids)
    if raw.ndim != 1 or len(raw) != n_features:
        raise _native.GeoNativeError(-1)
    if raw.dtype.kind == "u":
        return np.ascontiguousarray(raw, dtype=np.uint64)
    if raw.dtype.kind != "i":
        raise _native.GeoNativeError(-1)
    if len(raw) and int(raw.min()) < 0:
        raise _native.GeoNativeError(-1)
    return np.ascontiguousarray(raw, dtype=np.uint64)


def descriptor_from_geoarrow(column: Any, field: Any, feature_ids: Any = None) -> dict[str, Any]:
    """Decode a GeoArrow array into keyword args for ``geo_column_new``.

    ``feature_ids`` (optional) carries producer feature identity (for example
    GraphForge row IDs) through to Rust unchanged. The returned dict always
    holds a ``feature_ids`` key: ``None`` when absent, else a ``uint64`` array.
    """
    array = _as_array(column)
    if field is None:
        raise TypeError("GeoArrow ingest requires an Arrow Field carrying extension metadata")

    geometry = _geometry_kind(field)
    crs = _parse_crs(_field_metadata_str(field))
    validity = _validity(array)
    ids = _feature_ids(feature_ids, len(array))

    if array.type != field.type:
        raise _native.GeoNativeError(-3)
    depth = {
        _native.GEO_GEOMETRY_POINT: 0,
        _native.GEO_GEOMETRY_LINESTRING: 1,
        _native.GEO_GEOMETRY_MULTIPOINT: 1,
        _native.GEO_GEOMETRY_POLYGON: 2,
        _native.GEO_GEOMETRY_MULTILINESTRING: 2,
        _native.GEO_GEOMETRY_MULTIPOLYGON: 3,
    }[geometry]
    planes: list[np.ndarray | None] = [None, None, None]
    children = array
    for level in range(depth):
        if level > 0 and children.null_count:
            raise _native.GeoNativeError(-5)
        planes[level], children = _list_children(children)
    xy = _coordinate_xy(children, validity if depth == 0 else None)
    return {
        "geometry": geometry,
        "crs": crs,
        "xy": xy,
        "validity": validity,
        "feature_ids": ids,
        "offsets0": planes[0],
        "offsets1": planes[1],
        "offsets2": planes[2],
    }


def ingest_geoarrow(column: Any, field: Any, feature_ids: Any = None) -> int:
    """Decode GeoArrow and publish a Rust-owned ``GeoColumn`` handle.

    ``feature_ids`` is forwarded to Rust so producer identity survives ingest.
    """
    desc = descriptor_from_geoarrow(column, field, feature_ids=feature_ids)
    return _native.geo_column_new(**desc)
