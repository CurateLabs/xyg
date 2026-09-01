"""Scene wire-format unpack helpers for tests and introspection.

Product encode uses ``scene_encode_product`` end-to-end; these split Rust-owned
blobs when tests probe intermediate records (XYCC chrome, XYAS annotation splice).
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np

_XYCC_HEADER = struct.Struct("<4sIII4d16I48x")
_XYAS_HEADER = struct.Struct("<4sIIIII")
_XYAS_STYLE = struct.Struct("<4s4sd")

_GRAD_DIR_FROM_CODE = {0: "down", 1: "up", 2: "right", 3: "left"}


def _xycc_tick_labels(blob: bytes) -> list[str] | None:
    if not blob:
        return None
    if len(blob) < 12 or blob[:4] != b"XYTL":
        raise ValueError("invalid scene chrome packing")
    count = int.from_bytes(blob[8:12], "little")
    at = 12
    labels: list[str] = []
    for _ in range(count):
        length = int.from_bytes(blob[at : at + 4], "little")
        at += 4
        labels.append(blob[at : at + length].decode("utf-8"))
        at += length
    if at != len(blob):
        raise ValueError("invalid scene chrome packing")
    return labels


def _unpack_xycc(blob: bytes) -> dict[str, Any]:
    """Split Rust-owned XYCC chrome into encode-ready chrome fields."""
    if len(blob) < _XYCC_HEADER.size or blob[:4] != b"XYCC":
        raise ValueError("invalid scene chrome packing")
    (
        _magic,
        version,
        _flags,
        _reserved,
        margin_left,
        margin_right,
        margin_top,
        margin_bottom,
        chrome_len,
        title_len,
        xlabel_len,
        ylabel_len,
        x_major_count,
        x_major_auto,
        x_minor_count,
        y_major_count,
        y_major_auto,
        y_minor_count,
        x_labels_len,
        y_labels_len,
        x_format_len,
        y_format_len,
        legend_len,
        colorbar_len,
    ) = _XYCC_HEADER.unpack_from(blob)
    if version != 1:
        raise ValueError("invalid scene chrome facts version")
    at = _XYCC_HEADER.size

    def take(length: int) -> bytes:
        nonlocal at
        chunk = blob[at : at + length]
        at += length
        return chunk

    chrome_style = take(chrome_len)
    title = take(title_len).decode("utf-8")
    x_label = take(xlabel_len).decode("utf-8")
    y_label = take(ylabel_len).decode("utf-8")
    x_major = (
        list(struct.unpack(f"<{x_major_count}d", take(x_major_count * 8))) if x_major_count else []
    )
    x_minor = (
        list(struct.unpack(f"<{x_minor_count}d", take(x_minor_count * 8))) if x_minor_count else []
    )
    y_major = (
        list(struct.unpack(f"<{y_major_count}d", take(y_major_count * 8))) if y_major_count else []
    )
    y_minor = (
        list(struct.unpack(f"<{y_minor_count}d", take(y_minor_count * 8))) if y_minor_count else []
    )
    x_tick_labels = _xycc_tick_labels(take(x_labels_len))
    y_tick_labels = _xycc_tick_labels(take(y_labels_len))
    x_format_b = take(x_format_len)
    y_format_b = take(y_format_len)
    legend_input = take(legend_len)
    colorbar_input = take(colorbar_len)
    if at != len(blob):
        raise ValueError("invalid scene chrome packing")
    return {
        "margins": (margin_left, margin_right, margin_top, margin_bottom),
        "chrome_style": chrome_style,
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "x_major_ticks": None if x_major_auto else x_major,
        "x_minor_ticks": x_minor,
        "y_major_ticks": None if y_major_auto else y_major,
        "y_minor_ticks": y_minor,
        "x_tick_labels": x_tick_labels,
        "y_tick_labels": y_tick_labels,
        "x_format": None if not x_format_b else x_format_b.decode("utf-8"),
        "y_format": None if not y_format_b else y_format_b.decode("utf-8"),
        "legend_input": legend_input,
        "colorbar_input": colorbar_input,
    }


def _unpack_marker_blob(blob: bytes) -> dict[str, Any] | None:
    if len(blob) < 8:
        return None
    n_contours = struct.unpack_from("<I", blob, 0)[0]
    filled = blob[4] != 0
    at = 8
    contours: list[list[float]] = []
    for _ in range(int(n_contours)):
        n_values = struct.unpack_from("<I", blob, at)[0]
        at += 4
        values = list(struct.unpack_from(f"<{n_values}d", blob, at))
        at += int(n_values) * 8
        contours.append(values)
    return {"contours": contours, "filled": bool(filled)}


def _unpack_gradient_blob(blob: bytes) -> dict[str, Any] | None:
    if len(blob) < 4:
        return None
    space, direction, n_stops = blob[0], blob[1], blob[2]
    at = 4
    stops: list[tuple[float, tuple[int, int, int, int]]] = []
    for _ in range(int(n_stops)):
        t = float(struct.unpack_from("<f", blob, at)[0])
        rgba = (int(blob[at + 4]), int(blob[at + 5]), int(blob[at + 6]), int(blob[at + 7]))
        at += 8
        stops.append((t, rgba))
    return {
        "space": "plot" if space else "mark",
        "dir": _GRAD_DIR_FROM_CODE.get(int(direction), "down"),
        "stops": stops,
    }


def _unpack_xyas(blob: bytes) -> dict[str, Any]:
    """Split Rust-owned XYAS splice output into Scene styles, rows, and XYAD."""
    if len(blob) < _XYAS_HEADER.size or blob[:4] != b"XYAS":
        raise ValueError("invalid scene annotation splice packing")
    _magic, version, n_styles, n_rows, xyad_len, _reserved = _XYAS_HEADER.unpack_from(blob, 0)
    if version != 1:
        raise ValueError("invalid scene annotation splice version")
    at = _XYAS_HEADER.size
    need = int(n_styles) * _XYAS_STYLE.size + int(n_rows) * 56 + int(xyad_len)
    if at + need > len(blob):
        raise ValueError("invalid scene annotation splice packing")
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    for _ in range(int(n_styles)):
        fill, stroke, width = _XYAS_STYLE.unpack_from(blob, at)
        styles.append((tuple(fill), tuple(stroke), float(width)))
        at += _XYAS_STYLE.size
    kinds: list[int] = []
    stable_ids: list[int] = []
    style_refs: list[int] = []
    diameters: list[float] = []
    symbols: list[int] = []
    expansion_modes: list[int] = []
    coordinates: list[list[float]] = [[], [], [], []]
    if n_rows:
        raw = np.frombuffer(blob[at : at + int(n_rows) * 56], dtype=np.uint8).reshape(
            int(n_rows), 56
        )
        kinds.extend(int(value) for value in raw[:, 0])
        symbols.extend(int(value) for value in raw[:, 1])
        expansion_modes.extend(int(value) for value in raw[:, 2])
        style_refs.extend(int(value) for value in np.frombuffer(raw[:, 4:8].tobytes(), dtype="<u4"))
        stable_ids.extend(
            int(value) for value in np.frombuffer(raw[:, 8:16].tobytes(), dtype="<u8")
        )
        nums = np.frombuffer(raw[:, 16:56].tobytes(), dtype="<f8").reshape(-1, 5)
        diameters.extend(float(value) for value in nums[:, 0])
        for axis in range(4):
            coordinates[axis].extend(float(value) for value in nums[:, axis + 1])
        at += int(n_rows) * 56
    xyad = bytes(blob[at : at + int(xyad_len)])
    if at + int(xyad_len) != len(blob):
        raise ValueError("invalid scene annotation splice packing")
    return {
        "styles": styles,
        "kinds": kinds,
        "stable_ids": stable_ids,
        "style_refs": style_refs,
        "diameters": diameters,
        "symbols": symbols,
        "expansion_modes": expansion_modes,
        "coordinates": coordinates,
        "xyad": xyad,
    }
