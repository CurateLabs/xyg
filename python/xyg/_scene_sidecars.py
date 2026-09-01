"""Scene sidecar record packers and thin Rust ABI delegates.

Hosts marshal XYCL/XYNM column/name sidecars plus small pack helpers
(colormap, marker blob, gradient spec, linecap, rect flags) before Rust
owns compile/attach. Kept separate from ``_scene_v3`` pack entry.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np

from . import _native
from ._scene_observations import (
    UnsupportedSceneV3,
    _admitted_fill_gradient_from_fill,
    _colormap_stop_bytes,
    _trace_column,
)

_XYCL_HEADER = struct.Struct("<4sIII")
_XYCL_PREFIX = struct.Struct("<HBxIQ7I4x")
_XYNM_HEADER = struct.Struct("<4sIII")
_XYNM_PREFIX = struct.Struct("<H")
_XYFS_TRACE_RECT_GRADIENT = 1 << 5
_XYFS_TRACE_CORNER_RADIUS = 1 << 6
_XYFS_TRACE_WEDGE_GAP = 1 << 7


def pack_xycl_column(column: np.ndarray | None) -> tuple[int, bytes]:
    if column is None or len(column) == 0:
        return 0, b""
    arr = np.ascontiguousarray(np.asarray(column, dtype=np.float64).reshape(-1))
    return int(arr.size), arr.tobytes()


def pack_xycl(figure: Any) -> bytes:
    """Pack authored kind/coords/id plus canonical columns as XYCL v1."""
    traces = list(getattr(figure, "traces", None) or [])
    figure_plan = _native.scene_xycl_figure_plan(
        polar=str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar"
    )
    coords = 1 if figure_plan["polar"] else 0
    records = bytearray(_XYCL_HEADER.pack(b"XYCL", 1, len(traces), 0))
    for trace in traces:
        kind = str(trace.kind).encode("utf-8")
        packed = [
            pack_xycl_column(_trace_column(trace, name))
            for name in ("x", "y", "x0", "y0", "x1", "y1", "base")
        ]
        records.extend(
            _XYCL_PREFIX.pack(
                len(kind),
                coords,
                0,
                int(trace.id),
                *(count for count, _payload in packed),
            )
        )
        records.extend(kind)
        for _count, payload in packed:
            records.extend(payload)
    return bytes(records)


def pack_xynm(figure: Any) -> bytes:
    """Pack authored legend names as XYNM v1; Rust owns legend-name gating."""
    traces = list(getattr(figure, "traces", None) or [])
    _native.scene_xynm_figure_plan(show_legend=bool(getattr(figure, "show_legend", True)))
    records = bytearray(_XYNM_HEADER.pack(b"XYNM", 1, len(traces), 0))
    for trace in traces:
        name = getattr(trace, "name", None)
        raw = b"" if name is None else str(name).encode("utf-8")
        records.extend(_XYNM_PREFIX.pack(len(raw)))
        records.extend(raw)
    return bytes(records)


def pack_xyta_colormap(style: dict[str, Any]) -> tuple[int, bytes, bytes]:
    colormap = style.get("colormap")
    if isinstance(colormap, str):
        mode = 1
        named = colormap.encode("utf-8")
        stop_rgb = b""
    elif colormap is not None:
        mode = 2
        named = b""
        try:
            stop_rgb = _colormap_stop_bytes(colormap, "heatmap")
        except (TypeError, ValueError, UnsupportedSceneV3):
            stop_rgb = b""
    else:
        mode = 0
        named = b""
        stop_rgb = b""
    return _native.scene_xyta_colormap_pack(mode, named, stop_rgb)


def parse_scene_linecap(value: Any) -> int | None | bool:
    """Return 0=butt or 2=square, None for round/omitted, False if unusable."""
    if value is None:
        return None
    name = str(value)
    if not name.strip():
        return False
    return _native.scene_linecap_admit(name)


def pack_marker_blob(value: Any) -> bytes | None:
    if not isinstance(value, dict):
        return None
    contours = value.get("contours")
    if not isinstance(contours, (list, tuple)):
        return None
    values: list[float] = []
    lens: list[int] = []
    try:
        for contour in contours:
            if not isinstance(contour, (list, tuple)):
                return None
            floats = [float(item) for item in contour]
            values.extend(floats)
            lens.append(len(floats))
    except (TypeError, ValueError):
        return None
    filled = 1 if value.get("filled", True) else 0
    return _native.scene_marker_blob_pack(filled, values, lens)


def pack_gradient_spec(fill: dict[str, Any]) -> bytes | None:
    stops = fill.get("stops")
    if not isinstance(stops, (list, tuple)):
        return None
    stop_t: list[float] = []
    css_parts: list[bytes] = []
    css_lens: list[int] = []
    try:
        for stop in stops:
            if not isinstance(stop, (list, tuple)) or len(stop) != 2:
                return None
            stop_t.append(float(stop[0]))
            css = str(stop[1]).encode("utf-8")
            css_parts.append(css)
            css_lens.append(len(css))
    except (TypeError, ValueError):
        return None
    space = fill.get("space")
    dir_ = fill.get("dir")
    return _native.scene_gradient_spec_pack(
        b"" if space is None else str(space).encode("utf-8"),
        b"" if dir_ is None else str(dir_).encode("utf-8"),
        stop_t,
        b"".join(css_parts),
        css_lens,
    )


def rect_extra_flags(style: dict[str, Any], kind: str, polar: bool) -> int:
    """Pack Scene-unsupported rect extras as XYFS v2 trace flags."""
    fill = style.get("fill")
    gradient_fail = (
        isinstance(fill, dict) and _admitted_fill_gradient_from_fill(fill, "#3987e5") is None
    )
    radius = style.get("corner_radius", 0.0)
    if isinstance(radius, (list, tuple)):
        values = [float(value) for value in radius]
        radius_seq = True
    else:
        values = [float(radius)]
        radius_seq = False
    gap = float(style.get("wedge_gap", 0.0) or 0.0)
    return _native.scene_rect_extra_flags(kind, polar, gradient_fail, values, radius_seq, gap)
