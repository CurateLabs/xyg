"""Thin XYLK/XYLM typed framing for Rust-owned geographic layer catalogs."""

from __future__ import annotations

import ctypes
import struct
from typing import Any

import numpy as np

from . import _native

MAX_BYTES = 384 * 1024 * 1024


def _pad(n: int) -> int:
    return (n + 7) & ~7


def _uint(value: int, bits: int = 32) -> int:
    if (
        not isinstance(value, (int, np.integer))
        or isinstance(value, bool)
        or not 0 <= value < 1 << bits
    ):
        raise TypeError(f"expected u{bits}")
    return int(value)


def _text(value: str) -> bytes:
    if not isinstance(value, str) or len(value) > 8192:
        raise TypeError("text exceeds catalog framing")
    out = value.encode("utf-8")
    if len(out) > 8192:
        raise ValueError("text exceeds catalog framing")
    return out


def _paint(value: Any) -> bytes:
    if not isinstance(value, (bytes, bytearray, np.ndarray)):
        raise TypeError("paint requires RGBA8")
    if isinstance(value, np.ndarray) and (value.dtype != np.dtype("u1") or value.ndim != 1):
        raise TypeError("paint requires RGBA8")
    out = bytes(value)
    if len(out) != 4:
        raise ValueError("paint requires RGBA8")
    return out


def _patch(out: bytearray, at: int, patch: dict[str, Any]) -> None:
    mask = 0
    for name, bit, offset in (("fill", 1, 8), ("stroke", 2, 12)):
        if name in patch:
            mask |= bit
            out[at + offset : at + offset + 4] = _paint(patch[name])
    for name, bit, offset in (("stroke_width", 4, 16), ("diameter", 8, 24), ("opacity", 16, 32)):
        if name in patch:
            mask |= bit
            struct.pack_into("<d", out, at + offset, patch[name])
    if "symbol" in patch:
        mask |= 32
        struct.pack_into("<I", out, at + 4, _uint(patch["symbol"], 8))
    struct.pack_into("<I", out, at, mask)


def _descriptor(source: dict[str, Any] | bytes) -> tuple[int, Any]:
    if isinstance(source, bytes):
        if len(source) > 256 * 1024 * 1024:
            raise ValueError("column exceeds framing")
        return len(source), source
    _uint(source["geometry"])
    _uint(source["crs"])
    names = ("xy", "validity", "feature_ids", "offsets0", "offsets1", "offsets2")
    dtypes = ("<f8", "u1", "<u8", "<u4", "<u4", "<u4")
    planes = []
    for name, dtype in zip(names, dtypes, strict=True):
        value = source.get(name)
        plane = np.empty(0, dtype=dtype) if value is None else np.asarray(value)
        if plane.ndim != 1 or plane.dtype != np.dtype(dtype):
            raise TypeError("source requires exact typed planes")
        planes.append(plane)
    if len(planes[0]) % 2 or (
        source.get("feature_ids") is not None and len(planes[2]) != len(planes[1])
    ):
        raise ValueError("inconsistent source plane lengths")
    size = 64 + sum(_pad(p.nbytes) for p in planes)
    if size > 256 * 1024 * 1024:
        raise ValueError("column exceeds framing")
    return size, planes


def encode_request(input: dict[str, Any], budget: int = MAX_BYTES) -> bytes:
    """Frame exact source planes once; native Rust owns all product defaults."""
    if not isinstance(budget, int) or not 65536 <= budget <= MAX_BYTES or len(input["layers"]) > 64:
        raise ValueError("invalid catalog budget/count")
    camera = input["camera"]
    if not isinstance(camera.get("world_wrap", False), bool):
        raise TypeError("world_wrap must be a boolean")
    _uint(camera["crs"])
    legend = input.get("legend")
    title = _text(legend["title"]) if legend else b""
    frames = []
    for layer in input["layers"]:
        _uint(layer["layer_id"], 64)
        _uint(layer["kind"])
        size, source = _descriptor(layer["source"])
        patches = layer.get("feature_styles", [])
        values = layer.get("values", np.empty(0, dtype="<f8"))
        stops = layer.get("color_stops", np.empty(0, dtype="u1"))
        state = layer.get("state_flags", np.empty(0, dtype="u1"))
        for p, dtype in ((values, "<f8"), (stops, "u1"), (state, "u1")):
            if not isinstance(p, np.ndarray) or p.ndim != 1 or p.dtype != np.dtype(dtype):
                raise TypeError("catalog planes require exact typed representation")
        labels = layer.get("labels", [])
        if len(stops) % 3 or len(stops) > 768 or len(labels) > 128:
            raise ValueError("catalog plane exceeds framing")
        texts = [_text(label["text"]) for label in labels]
        text_len = sum(map(len, texts))
        if text_len > 8192:
            raise ValueError("label text exceeds framing")
        label = _text(layer["legend_label"]) if "legend_label" in layer else b""
        counts = (
            size,
            len(patches),
            len(values),
            len(stops) // 3,
            len(state),
            len(labels),
            len(label),
            text_len,
        )
        lengths = (
            size,
            len(patches) * 48,
            values.nbytes,
            stops.nbytes,
            state.nbytes,
            len(labels) * 48,
            len(label),
            text_len,
        )
        frames.append(
            (layer, source, patches, values, stops, state, labels, label, texts, counts, lengths)
        )
    length = (
        128
        + _pad(len(title))
        + (64 if input.get("event") is not None else 0)
        + sum(384 + sum(map(_pad, f[-1])) for f in frames)
    )
    # bytearray→bytes has one bounded final framing copy, included in transport reserve.
    if 3 * length + 32768 > budget:
        raise ValueError("catalog packet exceeds peak framing budget")
    out = bytearray(length)
    struct.pack_into(
        "<4s5I7d",
        out,
        0,
        b"XYLK",
        1,
        len(frames),
        int(legend is not None) | (2 if input.get("event") is not None else 0),
        camera["crs"],
        camera.get("world_wrap", False),
        *(camera[k] for k in ("center_x", "center_y", "zoom", "width", "height")),
        camera.get("bearing", 0.0),
        camera.get("pitch", 0.0),
    )
    if legend:
        struct.pack_into(
            "<IId", out, 80, _uint(legend["location"]), len(title), legend["font_size"]
        )
    out[128 : 128 + len(title)] = title
    cursor = 128 + _pad(len(title))
    if input.get("event") is not None:
        event = input["event"]
        op = _uint(event["operation"])
        coords = event.get("coordinates", [])
        if len(coords) != (2 if op in (1, 2) else 4 if op == 3 else 0):
            raise ValueError("event coordinates have invalid count")
        delta = event.get("delta", 0)
        if (
            not isinstance(delta, int)
            or isinstance(delta, bool)
            or not -2147483648 <= delta <= 2147483647
        ):
            raise TypeError("delta must be i32")
        struct.pack_into(
            "<IIiIQQ4d",
            out,
            cursor,
            op,
            _uint(event.get("mode", 0)),
            delta,
            0,
            _uint(event.get("layer_id", 0), 64),
            _uint(event.get("feature_id", 0), 64),
            *coords,
            *([0.0] * (4 - len(coords))),
        )
        cursor += 64
    for (
        layer,
        source,
        patches,
        values,
        stops,
        state,
        labels,
        label,
        texts,
        counts,
        _lengths,
    ) in frames:
        at = cursor
        struct.pack_into("<QI", out, at, layer["layer_id"], layer["kind"])
        flags = 0
        _patch(out, at + 16, layer.get("style", {}))
        for key, bit, offset in (("selected", 32, 64), ("hovered", 64, 112), ("focused", 128, 160)):
            if key in layer:
                flags |= bit
                _patch(out, at + offset, layer[key])
        for key, bit, offset in (("value_domain", 1, 208), ("bubble_diameters", 2, 224)):
            if key in layer:
                flags |= bit
                struct.pack_into("<2d", out, at + offset, *layer[key])
        if "arc" in layer:
            flags |= 4
            struct.pack_into(
                "<dI", out, at + 240, layer["arc"]["bend"], _uint(layer["arc"]["steps"])
            )
        if "density" in layer:
            flags |= 8
            struct.pack_into(
                "<II",
                out,
                at + 252,
                _uint(layer["density"]["columns"]),
                _uint(layer["density"]["rows"]),
            )
        if "legend_label" in layer:
            flags |= 16
        struct.pack_into("<I", out, at + 12, flags)
        struct.pack_into("<8Q", out, at + 264, *counts)
        cursor += 384
        if isinstance(source, bytes):
            out[cursor : cursor + len(source)] = source
        else:
            descriptor = layer["source"]
            struct.pack_into(
                "<4s5I5Q",
                out,
                cursor,
                b"XYGD",
                1,
                descriptor["geometry"],
                descriptor["crs"],
                int(descriptor.get("feature_ids") is not None),
                0,
                len(source[1]),
                len(source[0]) // 2,
                *(len(p) for p in source[3:]),
            )
            pos = cursor + 64
            for plane in source:
                data = memoryview(plane).cast("B") if plane.flags.c_contiguous else plane.tobytes()
                memoryview(out)[pos : pos + plane.nbytes] = data
                pos += _pad(plane.nbytes)
        cursor += _pad(counts[0])
        for p in patches:
            _patch(out, cursor, p)
            cursor += 48
        for plane in (values, stops, state):
            data = memoryview(plane).cast("B") if plane.flags.c_contiguous else plane.tobytes()
            memoryview(out)[cursor : cursor + plane.nbytes] = data
            cursor += _pad(plane.nbytes)
        text_at = 0
        for label_row, text in zip(labels, texts, strict=True):
            struct.pack_into(
                "<IId2d4sIII",
                out,
                cursor,
                _uint(label_row["feature_index"]),
                _uint(label_row["anchor"]),
                label_row["font_size"],
                *label_row["coordinate"],
                _paint(label_row["rgba"]),
                0,
                text_at,
                len(text),
            )
            text_at += len(text)
            cursor += 48
        out[cursor : cursor + len(label)] = label
        cursor += _pad(len(label))
        for text in texts:
            out[cursor : cursor + len(text)] = text
            cursor += len(text)
        cursor = _pad(cursor)
    return bytes(out)


def execute(request: bytes, budget: int = MAX_BYTES) -> bytes:
    """Reject oversized input before allocating the ctypes source copy."""
    if (
        not isinstance(request, bytes)
        or not isinstance(budget, int)
        or not 65536 <= budget <= MAX_BYTES
    ):
        raise TypeError("invalid catalog request/budget")
    if len(request) > budget:
        raise _native.GeoNativeError(-9)
    if len(request) < 128:
        raise _native.GeoNativeError(-1)
    source = ctypes.create_string_buffer(request)
    length = ctypes.c_size_t()
    function = _native._lib.xyg_geo_catalog_compile
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
    """Read exact aligned planes; retain full u64 source IDs and layer identity."""

    def bad() -> None:
        raise ValueError("malformed Rust geographic catalog response")

    if (
        len(data) < 128
        or len(data) > MAX_BYTES
        or data[:4] != b"XYLM"
        or struct.unpack_from("<I", data, 4)[0] != 1
    ):
        bad()

    def u(at: int) -> int:
        return struct.unpack_from("<I", data, at)[0]

    def count(at: int) -> int:
        n = struct.unpack_from("<Q", data, at)[0]
        if n > MAX_BYTES:
            bad()
        return n

    def zero(start: int, end: int) -> None:
        if any(data[start:end]):
            bad()

    if u(8) not in (4326, 3857) or u(12) > 1:
        bad()
    if u(96) > 1:
        bad()
    zero(100, 104)
    if not u(96):
        zero(104, 120)
    n_hits = count(120)
    if n_hits > 1_000_000:
        bad()
    n_layers, n_owners = count(80), count(88)
    if n_layers > 64:
        bad()
    cursor = 128

    def plane(n: int, dtype: str) -> np.ndarray:
        nonlocal cursor
        size = np.dtype(dtype).itemsize
        end = cursor + n * size
        padded = _pad(end)
        if padded > len(data):
            bad()
        zero(end, padded)
        result = np.frombuffer(data, dtype=dtype, count=n, offset=cursor).copy()
        cursor = padded
        return result

    scene = plane(count(72), "u1").tobytes()
    if (
        len(scene) < 160
        or struct.unpack_from("<Q", scene, 24)[0] != n_owners
        or scene[:4] != b"XYGS"
    ):
        bad()
    owners = plane(n_owners, "<u4")
    if np.any((owners != 0xFFFFFFFF) & (owners >= n_layers)):
        bad()
    layers: list[dict[str, Any]] = []
    for _ in range(n_layers):
        at = cursor
        if at + 128 > len(data):
            bad()
        cursor += 128
        flags, kind, n, visible = u(at + 12), u(at + 8), count(at + 24), count(at + 32)
        cells, members = count(at + 48), count(at + 56)
        if flags & ~3 or kind not in range(1, 8) or u(at + 64) & ~7:
            bad()
        zero(at + 68, at + 72)
        zero(at + 104, at + 128)
        bounds = struct.unpack_from("<4d", data, at + 72)
        if not np.isfinite(bounds).all():
            bad()
        if not flags & 1:
            zero(at + 72, at + 104)
        ids, valid, state, visible_indices = (
            plane(n, "<u8"),
            plane(n, "u1"),
            plane(n, "u1"),
            plane(visible, "<u4"),
        )
        if np.any(valid > 1) or np.any(state & 240) or np.any(visible_indices >= n):
            bad()
        density = None
        if flags & 2:
            cols, rows = u(at + 40), u(at + 44)
            if not 0 < cols <= 4096 or not 0 < rows <= 4096 or cols * rows != cells:
                bad()
            counts, offsets, indices = (
                plane(cells, "<u4"),
                plane(cells + 1, "<u4"),
                plane(members, "<u4"),
            )
            if (
                offsets[0] != 0
                or offsets[-1] != members
                or np.any(indices >= n)
                or np.any(offsets[:-1] > offsets[1:])
                or np.any(offsets[1:] - offsets[:-1] > counts)
                or np.any((offsets[1:] == offsets[:-1]) != (counts == 0))
            ):
                bad()
            density = dict(
                columns=cols, rows=rows, counts=counts, offsets=offsets, feature_indices=indices
            )
        else:
            zero(at + 40, at + 64)
        layers.append(
            dict(
                layer_id=struct.unpack_from("<Q", data, at)[0],
                kind=kind,
                source_digest=data[at + 16 : at + 24],
                feature_ids=ids,
                validity=valid,
                state_flags=state,
                visible_feature_indices=visible_indices,
                bounds=bounds if flags & 1 else None,
                density=density,
                dropped_channels=u(at + 64),
            )
        )
    focus = (
        dict(
            layer_id=struct.unpack_from("<Q", data, 104)[0],
            feature_id=struct.unpack_from("<Q", data, 112)[0],
        )
        if u(96)
        else None
    )
    hits = []
    for _ in range(n_hits):
        if cursor + 24 > len(data):
            bad()
        layer_id, feature_id, n = struct.unpack_from("<3Q", data, cursor)
        cursor += 24
        indices = plane(n, "<u4")
        layer = next((entry for entry in layers if entry["layer_id"] == layer_id), None)
        if (
            layer is None
            or np.any(indices >= len(layer["feature_ids"]))
            or np.any(layer["feature_ids"][indices] != feature_id)
        ):
            bad()
        hits.append(dict(layer_id=layer_id, feature_id=feature_id, feature_indices=indices))
    if focus and not any(
        entry["layer_id"] == focus["layer_id"] and focus["feature_id"] in entry["feature_ids"]
        for entry in layers
    ):
        bad()
    if cursor != len(data):
        bad()
    values = struct.unpack_from("<7d", data, 16)
    if not np.isfinite(values).all():
        bad()
    camera = dict(
        zip(
            ("center_x", "center_y", "zoom", "width", "height", "bearing", "pitch"),
            values,
            strict=True,
        ),
        crs=u(8),
        world_wrap=bool(u(12)),
    )
    return dict(
        camera=camera,
        rebuild_key=data[8:72],
        scene=scene,
        style_owners=owners,
        layers=layers,
        focus=focus,
        hits=hits,
    )
