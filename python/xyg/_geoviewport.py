"""Thin typed byte adapters for Rust's geographic camera protocol (#48)."""

from __future__ import annotations

import ctypes
import struct
from typing import Any

import numpy as np

from . import _native

OPERATIONS = {
    "normalize": 0,
    "project": 1,
    "inverse": 2,
    "pan": 3,
    "zoom": 4,
    "resize": 5,
    "bearing": 6,
    "pitch": 7,
    "center": 8,
    "fit": 9,
    "column": 10,
}


def encode_request(
    camera: dict[str, Any],
    operation: int = 0,
    args: tuple[float, ...] = (),
    descriptor: bytes = b"",
) -> bytes:
    """Frame numeric source values without owning camera/geometry policy."""
    if operation not in range(11) or len(args) > 5 or (descriptor and operation != 10):
        raise ValueError("invalid camera protocol framing")
    if len(descriptor) + 128 > 256 * 1024 * 1024:
        raise ValueError("camera request exceeds transport budget")
    if not isinstance(camera.get("world_wrap", False), bool):
        raise TypeError("world_wrap must be a boolean")
    out = bytearray(128 + len(descriptor))
    struct.pack_into(
        "<4s5I",
        out,
        0,
        b"XYVC",
        1,
        operation,
        camera["crs"],
        bool(camera.get("world_wrap", False)),
        0,
    )
    struct.pack_into(
        "<7d",
        out,
        24,
        *(camera[name] for name in ("center_x", "center_y", "zoom", "width", "height")),
        camera.get("bearing", 0.0),
        camera.get("pitch", 0.0),
    )
    struct.pack_into("<5d", out, 80, *args, *([0.0] * (5 - len(args))))
    out[128:] = descriptor
    return bytes(out)


def encode_column_request(camera: dict[str, Any], descriptor: dict[str, Any]) -> bytes:
    """Pack the existing GeoArrow descriptor into one prefixed typed packet."""
    if not isinstance(camera.get("world_wrap", False), bool):
        raise TypeError("world_wrap must be a boolean")
    for code in (camera["crs"], descriptor["crs"], descriptor["geometry"]):
        if not isinstance(code, (int, np.integer)) or not 0 <= code <= 0xFFFFFFFF:
            raise TypeError("camera and descriptor codes must be u32")
    names = ("xy", "validity", "feature_ids", "offsets0", "offsets1", "offsets2")
    dtypes = ("<f8", "u1", "<u8", "<u4", "<u4", "<u4")
    planes = []
    for name, dtype in zip(names, dtypes, strict=True):
        value = descriptor.get(name)
        plane = np.empty(0, dtype=dtype) if value is None else np.asarray(value)
        if plane.ndim != 1 or plane.dtype != np.dtype(dtype):
            raise TypeError(
                "GeoArrow descriptor planes must retain their exact typed representation"
            )
        planes.append(plane)
    if len(planes[0]) % 2 or (
        descriptor.get("feature_ids") is not None and len(planes[2]) != len(planes[1])
    ):
        raise ValueError("inconsistent typed descriptor plane lengths")
    length = 192 + sum((plane.nbytes + 7) & ~7 for plane in planes)
    if length > 256 * 1024 * 1024:
        raise ValueError("camera descriptor exceeds transport budget")
    out = bytearray(length)
    struct.pack_into(
        "<4s5I", out, 0, b"XYVC", 1, 10, camera["crs"], camera.get("world_wrap", False), 0
    )
    struct.pack_into(
        "<7d",
        out,
        24,
        *(camera[name] for name in ("center_x", "center_y", "zoom", "width", "height")),
        camera.get("bearing", 0.0),
        camera.get("pitch", 0.0),
    )
    struct.pack_into(
        "<4s5I5Q",
        out,
        128,
        b"XYGD",
        1,
        descriptor["geometry"],
        descriptor["crs"],
        descriptor.get("feature_ids") is not None,
        0,
        len(planes[1]),
        len(planes[0]) // 2,
        *(len(plane) for plane in planes[3:]),
    )
    cursor = 192
    for plane in planes:
        # Exact dtype admission excludes narrowing. tobytes preserves each source bit.
        source = memoryview(plane).cast("B") if plane.flags.c_contiguous else plane.tobytes()
        memoryview(out)[cursor : cursor + plane.nbytes] = source
        cursor += (plane.nbytes + 7) & ~7
    return bytes(out)


def execute(request: bytes, budget: int = 64 * 1024 * 1024) -> bytes:
    """Invoke the shared native processor; query/copy failures expose stable errors."""
    if not 0 <= budget <= 384 * 1024 * 1024:
        raise ValueError("invalid camera byte budget")
    if len(request) > budget:
        raise _native.GeoNativeError(-9)
    if len(request) < 128:
        raise _native.GeoNativeError(-1)
    source = ctypes.create_string_buffer(request)
    length = ctypes.c_size_t()
    function = _native._lib.xyg_geo_viewport_execute
    code = function(source, len(request), budget, None, 0, ctypes.byref(length))
    if code:
        raise _native.GeoNativeError(code)
    if length.value > budget:
        raise _native.GeoNativeError(-9)
    out = ctypes.create_string_buffer(length.value)
    code = function(source, len(request), budget, out, len(out), ctypes.byref(length))
    if code:
        raise _native.GeoNativeError(code)
    return out.raw


def decode_response(data: bytes) -> dict[str, Any]:
    """Read exact aligned output planes; no host projection or narrowing."""

    def bad() -> ValueError:
        return ValueError("malformed Rust geographic camera response")

    if len(data) < 256:
        raise bad()
    magic, version, operation, crs, wrap, kind = struct.unpack_from("<4s5I", data)
    has_bounds = struct.unpack_from("<I", data, 168)[0]
    if (
        magic != b"XYVR"
        or version != 1
        or operation > 10
        or crs not in (4326, 3857)
        or wrap > 1
        or kind > 2
        or has_bounds > 1
        or any(data[172:176])
        or any(data[232:256])
    ):
        raise bad()
    counts = struct.unpack_from("<9Q", data, 96)
    names = (
        "xy",
        "feature_ids",
        "offsets",
        "visible_feature_ids",
        "polygon_xy",
        "ring_offsets",
        "polygon_offsets",
        "polygon_feature_ids",
        "ring_is_hole",
    )
    dtypes = ("<f4", "<u8", "<u4", "<u8", "<f4", "<u4", "<u4", "<u8", "u1")
    cursor = 256
    planes = {}
    for name, dtype, count in zip(names, dtypes, counts, strict=True):
        size = np.dtype(dtype).itemsize
        end = cursor + count * size
        padded = (end + 7) & ~7
        if padded > len(data) or any(data[end:padded]):
            raise bad()
        plane = np.frombuffer(data, dtype=dtype, count=count, offset=cursor)
        if dtype == "<f4" and not np.isfinite(plane).all():
            raise bad()
        planes[name] = plane
        cursor = padded
    if cursor != len(data):
        raise bad()
    values = struct.unpack_from("<9d", data, 24)
    bounds = struct.unpack_from("<4d", data, 184)
    polygon_origin = struct.unpack_from("<2d", data, 216)
    if not all(np.isfinite(v) for v in (*values, *bounds, *polygon_origin)):
        raise bad()
    camera = dict(
        zip(
            ("center_x", "center_y", "zoom", "width", "height", "bearing", "pitch"),
            values[:7],
            strict=True,
        )
    )
    camera.update(crs=crs, world_wrap=bool(wrap))
    return dict(
        camera=camera,
        rebuild_key=data[12:20] + data[24:80],
        operation=operation,
        kind=kind,
        result=values[7:],
        bounds=bounds if has_bounds else None,
        metadata_digest=data[176:184],
        polygon_origin=polygon_origin,
        **planes,
    )


def geo_viewport(
    camera: dict[str, Any],
    operation: int = 0,
    args: tuple[float, ...] = (),
    descriptor: bytes = b"",
    budget: int = 64 * 1024 * 1024,
) -> dict[str, Any]:
    return decode_response(execute(encode_request(camera, operation, args, descriptor), budget))
