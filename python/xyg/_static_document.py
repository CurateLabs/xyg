"""Thin XYST marshal and Rust StaticDocument product adapter (M2 #873)."""

from __future__ import annotations

import copy
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Any, Optional

import numpy as np

from . import _native

_HEADER = struct.Struct("<4s6I4B4BfffBB2xII4x")
_PANEL = struct.Struct("<2i6I12fII2f4B2I")
_DECORATION_HEADER = struct.Struct("<4s7I")
_DOCUMENT_LABELS_HEADER = struct.Struct("<4s3I")
_DOCUMENT_LABEL = struct.Struct("<2I5d")
_DOCUMENT_LEGEND_HEADER = struct.Struct("<4s3IiI5d")
_DOCUMENT_LEGEND_ITEM = struct.Struct("<2I4d")
_LAYOUT_HEADER = struct.Struct("<4s9I3d")
_LAYOUT_PANEL = struct.Struct("<2I4d")
_LAYOUT_OUTPUT = struct.Struct("<4s5I3d")
_PANEL_CHROME_HEADER = struct.Struct("<4s13I8x17d")
_PANEL_CHROME_TITLE = struct.Struct("<3d2I")
_PANEL_CHROME_OUTPUT = struct.Struct("<4s3I9d")
_LEGEND_FIT_HEADER = struct.Struct("<4s11I12d")
_LEGEND_FIT_ENTRY = struct.Struct("<6I")
_LEGEND_FIT_OUTPUT = struct.Struct("<4s3I21d")
_ANNOTATION_STYLE_HEADER = struct.Struct("<4s3I")
_ANNOTATION_STYLE_OUTPUT = struct.Struct("<4s3I2f2I")
_MAX_U32 = (1 << 32) - 1
_MAX_PANELS = 256
_MAX_TITLE_BYTES = 4096
_FLAG_BACKGROUND = 1
_FLAG_OPTIMIZE_PNG = 2
_FLAG_TIGHT_CROP = 4
_FLAG_TITLE_X_CENTER = 8


class UnsupportedStaticExport(RuntimeError):
    """A native static journey rejected by the Rust product predicate."""


#: Live-only legend toggles: they gate interactive hover behavior in the
#: browser client and carry no static-render meaning, so both hosts drop them
#: before marshaling the document legend.
_INTERACTIVE_LEGEND_KEYS = frozenset({"highlight", "toggle"})


#: Pyplot grid dash spellings -> XYST fact codes; the pattern table is Rust's.
_GRID_DASH_CODES = {"solid": 0, "dashed": 1, "dotted": 2, "dashdot": 3}


def _grid_dash_fact(
    major: dict[str, "Optional[int]"], minor: dict[str, "Optional[int]"]
) -> "Optional[tuple[int, int, int, int]]":
    if all(value is None for value in major.values()) and all(
        value is None for value in minor.values()
    ):
        return None
    return (
        major["x"] or 0,
        major["y"] or 0,
        minor["x"] or 0,
        minor["y"] or 0,
    )


@dataclass(frozen=True)
class Panel:
    scene: bytes
    x: int
    y: int
    width: int
    height: int
    # x tick-label size, x label size, x tick padding, then y equivalents.
    # ``None`` preserves the canonical Scene metrics.
    chrome_metrics: Optional[tuple[float, float, float, float, float, float]] = None
    # shrink, anchor-x, anchor-y for a canonical Scene colorbar.
    colorbar_layout: Optional[tuple[float, float, float]] = None
    # One pyplot panel-wide annotation size; heterogeneous sizes fail closed.
    annotation_font_size: Optional[float] = None
    # uniform pyplot arrow head size and start/end shaft widths.
    arrow_metrics: Optional[tuple[float, float, float]] = None
    # x low/high and y low/high visible-spine bitmasks.
    axis_sides: Optional[tuple[int, int]] = None
    # uniform deterministic italic/bold bits and label-box padding.
    annotation_text_flags: Optional[int] = None
    annotation_padding: Optional[float] = None
    # resolved panel title size/color and uniform annotation vertical align.
    title_style: Optional[tuple[float, str]] = None
    annotation_vertical_align: Optional[int] = None
    # XYST-only pyplot colorbar compatibility flags. Scene keeps the canonical
    # color scale while Rust owns log projection, endpoint extends, and label
    # orientation for the static product.
    colorbar_scale: Optional[str] = None
    colorbar_extend: Optional[str] = None
    colorbar_pyplot_label: bool = False
    # Explicit pyplot cax consumes the Scene plot rectangle itself.
    colorbar_fill_plot: bool = False
    # XYST-only pyplot grid dash codes (0=solid, 1=dashed, 2=dotted,
    # 3=dashdot) for (x major, y major, x minor, y minor). Rust owns the
    # pattern table; the canonical Scene wire keeps its solid contract.
    grid_dash: Optional[tuple[int, int, int, int]] = None


@dataclass(frozen=True)
class ResolvedLayout:
    width: int
    height: int
    offsets: tuple[tuple[int, int], ...]
    title_reserve: int
    title_x: float
    title_baseline: float
    title_band: float
    panel_sizes: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class ResolvedAnnotationStyles:
    annotations: list[dict[str, Any]]
    font_size: Optional[float]
    text_flags: Optional[int]
    padding: Optional[float]
    vertical_align: Optional[int]


@dataclass(frozen=True)
class PanelChromeTitle:
    text: str
    size: float
    pad: float
    y: float
    automatic_y: bool


@dataclass(frozen=True)
class ResolvedPanelChrome:
    left: float
    top: float
    right: float
    bottom: float
    outside_top: float
    outside_right: float
    outside_bottom: float
    probe_width: float
    probe_height: float
    compact: bool

    @property
    def gutters(self) -> tuple[float, float, float, float]:
        return self.left, self.top, self.right, self.bottom

    @property
    def outside(self) -> tuple[float, float, float]:
        return self.outside_top, self.outside_right, self.outside_bottom


@dataclass(frozen=True)
class LegendFitEntry:
    kind: int
    x: Sequence[float]
    y: Sequence[float]
    base: Sequence[float] = ()
    width: Sequence[float] = ()


@dataclass(frozen=True)
class ResolvedLegendFit:
    location: str
    box_width: float
    box_height: float
    pad_x_fraction: float
    pad_y_fraction: float


def resolve_legend_fit(
    *,
    plot: tuple[float, float, float, float],
    x_domain: tuple[float, float],
    y_domain: tuple[float, float],
    reverse_x: bool,
    reverse_y: bool,
    names: Sequence[str],
    entries: Sequence[LegendFitEntry],
    title: str = "",
    ncols: int = 1,
    font_size_css: str = "",
    padding_css: str = "",
    row_gap_css: str = "",
    handlelength: Optional[float] = None,
    handletextpad: Optional[float] = None,
    handleheight: Optional[float] = None,
    border_pad: float = 0.0,
) -> ResolvedLegendFit:
    """Marshal legend observations; Rust owns footprint, scoring, and choice."""
    texts = [
        _chrome_text(title, "legend title"),
        _chrome_text(font_size_css, "legend font size"),
        _chrome_text(padding_css, "legend padding"),
        _chrome_text(row_gap_css, "legend row gap"),
    ]
    name_bytes = [_chrome_text(name, "legend item") for name in names]
    flags = (
        int(reverse_x)
        | (int(reverse_y) << 1)
        | (int(handlelength is not None) << 2)
        | (int(handletextpad is not None) << 3)
        | (int(handleheight is not None) << 4)
    )
    out = bytearray(
        _LEGEND_FIT_HEADER.pack(
            b"XYLF",
            1,
            flags,
            len(name_bytes),
            len(entries),
            int(ncols),
            *(len(text) for text in texts),
            0,
            0,
            *map(float, plot),
            float(x_domain[0]),
            float(x_domain[1]),
            float(y_domain[0]),
            float(y_domain[1]),
            0.0 if handlelength is None else float(handlelength),
            0.0 if handletextpad is None else float(handletextpad),
            0.0 if handleheight is None else float(handleheight),
            float(border_pad),
        )
    )
    out.extend(b"".join(texts))
    for name in name_bytes:
        out.extend(struct.pack("<I", len(name)))
        out.extend(name)
    for entry in entries:
        columns = [
            np.ascontiguousarray(np.asarray(column, dtype="<f8").reshape(-1))
            for column in (entry.x, entry.y, entry.base, entry.width)
        ]
        out.extend(_LEGEND_FIT_ENTRY.pack(int(entry.kind), *(len(column) for column in columns), 0))
        for column in columns:
            out.extend(memoryview(column).cast("B"))
    try:
        resolved = _native.static_legend_fit(bytes(out))
    except ValueError as error:
        reason = str(error)
        if reason.startswith("XYG_STATIC_UNSUPPORTED_"):
            raise UnsupportedStaticExport(reason) from None
        raise
    if len(resolved) != _LEGEND_FIT_OUTPUT.size:
        raise RuntimeError("invalid native static legend fit result")
    magic, version, chosen, _used, *values = _LEGEND_FIT_OUTPUT.unpack(resolved)
    names_by_index = (
        "upper right",
        "upper left",
        "lower left",
        "lower right",
        "right",
        "center left",
        "lower center",
        "upper center",
        "center",
    )
    if magic != b"XYLR" or version != 1 or chosen >= len(names_by_index):
        raise RuntimeError("invalid native static legend fit result")
    return ResolvedLegendFit(
        names_by_index[chosen],
        float(values[4]),
        float(values[5]),
        float(values[6]),
        float(values[7]),
    )


def _chrome_text(value: object, label: str) -> bytes:
    encoded = str(value).encode("utf-8")
    if len(encoded) > 4096 or b"\0" in encoded:
        raise ValueError(f"{label} is invalid")
    return encoded


def resolve_panel_chrome(
    *,
    plot_width: float,
    canvas_height: float,
    rows: int,
    dpi: float,
    table_bottom_points: float,
    x_tick_labels: Sequence[str] = (),
    y_tick_labels: Sequence[str] = (),
    x_label: str = "",
    y_label: str = "",
    titles: Sequence[PanelChromeTitle] = (),
    x_tick_size: float = 11.0,
    x_tick_angle: float = 0.0,
    x_label_size: float = 12.0,
    y_tick_size: float = 11.0,
    y_tick_angle: float = 0.0,
    y_label_size: float = 12.0,
    y_tick_length: float = 0.0,
    y_tick_padding: float = 4.0,
    y_label_offset: Optional[float] = None,
    y_tick_labels_visible: bool = True,
    x_axis_top: bool = False,
    right_secondary: bool = False,
    y_tick_direction: str = "out",
    colorbar: int = 0,
    colorbar_has_label: bool = False,
    colorbar_zero_pad: bool = False,
    compact: Optional[bool] = None,
    measured_gutters: Optional[tuple[float, float, float, float]] = None,
    unsupported: int = 0,
) -> ResolvedPanelChrome:
    """Marshal authored panel facts; Rust owns every gutter/layout decision."""
    if len(x_tick_labels) > 4096 or len(y_tick_labels) > 4096 or len(titles) > 3:
        raise ValueError("static panel chrome exceeds its bounded text-plane limits")
    x_label_bytes = _chrome_text(x_label, "x label")
    y_label_bytes = _chrome_text(y_label, "y label")
    x_tick_bytes = [_chrome_text(label, "x tick label") for label in x_tick_labels]
    y_tick_bytes = [_chrome_text(label, "y tick label") for label in y_tick_labels]
    title_bytes = [_chrome_text(title.text, "panel title") for title in titles]
    direction = {"out": 0, "in": 1, "inout": 2}.get(str(y_tick_direction))
    if direction is None:
        raise ValueError("y tick direction must be out, in, or inout")
    flags = (
        int(y_tick_labels_visible)
        | (int(x_axis_top) << 1)
        | (int(right_secondary) << 2)
        | (int(y_label_offset is not None) << 3)
        | (int(measured_gutters is not None) << 4)
    )
    colorbar_flags = int(colorbar_has_label) | (int(colorbar_zero_pad) << 1)
    measurements = measured_gutters or (0.0, 0.0, 0.0, 0.0)
    out = bytearray(
        _PANEL_CHROME_HEADER.pack(
            b"XYPC",
            1,
            flags,
            int(rows),
            len(x_tick_bytes),
            len(y_tick_bytes),
            len(titles),
            len(x_label_bytes),
            len(y_label_bytes),
            int(unsupported),
            direction,
            int(colorbar),
            colorbar_flags,
            0 if compact is None else 1 if compact else 2,
            float(plot_width),
            float(canvas_height),
            float(dpi),
            float(table_bottom_points),
            float(x_tick_size),
            float(x_tick_angle),
            float(x_label_size),
            float(y_tick_size),
            float(y_tick_angle),
            float(y_label_size),
            float(y_tick_length),
            float(y_tick_padding),
            0.0 if y_label_offset is None else float(y_label_offset),
            *map(float, measurements),
        )
    )
    out.extend(x_label_bytes)
    out.extend(y_label_bytes)
    for text in (*x_tick_bytes, *y_tick_bytes):
        out.extend(struct.pack("<I", len(text)))
        out.extend(text)
    for title, text in zip(titles, title_bytes, strict=True):
        out.extend(
            _PANEL_CHROME_TITLE.pack(
                float(title.size),
                float(title.pad),
                float(title.y),
                int(title.automatic_y),
                len(text),
            )
        )
        out.extend(text)
    try:
        resolved = _native.static_panel_chrome(bytes(out))
    except ValueError as error:
        reason = str(error)
        if reason.startswith("XYG_STATIC_UNSUPPORTED_"):
            raise UnsupportedStaticExport(reason) from None
        raise
    if len(resolved) != _PANEL_CHROME_OUTPUT.size:
        raise RuntimeError("invalid native static panel chrome result")
    magic, version, compact_flag, reserved, *values = _PANEL_CHROME_OUTPUT.unpack(resolved)
    if magic != b"XYPO" or version != 1 or compact_flag not in {0, 1} or reserved != 0:
        raise RuntimeError("invalid native static panel chrome result")
    return ResolvedPanelChrome(*values, bool(compact_flag))


def _resolved_layout(encoded: bytes, count: int, *, facet: bool = False) -> ResolvedLayout:
    resolved = _native.static_document_layout(encoded)
    record_size = 16 if facet else 8
    if len(resolved) != _LAYOUT_OUTPUT.size + count * record_size:
        raise RuntimeError("invalid native StaticDocument layout result")
    magic, version, width, height, actual_count, reserve, title_x, baseline, band = (
        _LAYOUT_OUTPUT.unpack_from(resolved)
    )
    if magic != b"XYLO" or version != 1 or actual_count != count:
        raise RuntimeError("invalid native StaticDocument layout result")
    offsets: list[tuple[int, int]] = []
    panel_sizes: list[tuple[int, int]] = []
    for index in range(count):
        row = _LAYOUT_OUTPUT.size + index * record_size
        offsets.append(struct.unpack_from("<2i", resolved, row))
        if facet:
            panel_sizes.append(struct.unpack_from("<2I", resolved, row + 8))
    return ResolvedLayout(
        width,
        height,
        tuple(offsets),
        reserve,
        title_x,
        baseline,
        band,
        tuple(panel_sizes),
    )


def resolve_layout(
    panel_sizes: Sequence[tuple[int, int]],
    *,
    nrows: int,
    ncols: int,
    title: Optional[str],
    title_size: float,
    title_x_fraction: float,
    title_y_fraction: float,
    positions: Optional[Sequence[tuple[float, float, float, float]]] = None,
    canvas_size: Optional[tuple[int, int]] = None,
    shared_colorbar: bool = False,
) -> ResolvedLayout:
    """Marshal XYSL facts; Rust owns all document placement and title layout."""
    count = len(panel_sizes)
    mode = int(positions is not None)
    if mode != int(canvas_size is not None):
        raise ValueError("StaticDocument normalized layout needs positions and canvas size")
    if positions is not None and len(positions) != count:
        raise ValueError("StaticDocument position count must match panels")
    title_bytes = (title or "").encode("utf-8")
    canvas_width, canvas_height = canvas_size or (0, 0)
    out = bytearray(
        _LAYOUT_HEADER.pack(
            b"XYSL",
            1,
            mode,
            0 if mode else nrows,
            0 if mode else ncols,
            count,
            int(canvas_width),
            int(canvas_height),
            int(shared_colorbar and not mode),
            len(title_bytes),
            float(title_size),
            float(title_x_fraction),
            float(title_y_fraction),
        )
    )
    fractions = positions or [(0.0, 0.0, 0.0, 0.0)] * count
    for (width, height), rectangle in zip(panel_sizes, fractions, strict=True):
        out.extend(_LAYOUT_PANEL.pack(int(width), int(height), *map(float, rectangle)))
    out.extend(title_bytes)
    return _resolved_layout(bytes(out), count)


def resolve_facet_layout(
    count: int,
    *,
    columns: int,
    width: int,
    panel_height: int,
    gap: int,
    title: Optional[str],
) -> ResolvedLayout:
    """Marshal facet facts; Rust owns cells, gaps, title strip, and offsets."""
    title_bytes = (title or "").encode("utf-8")
    out = bytearray(
        _LAYOUT_HEADER.pack(
            b"XYSL",
            1,
            2,
            0,
            int(columns),
            int(count),
            int(width),
            int(panel_height),
            0,
            len(title_bytes),
            16.0,
            0.5,
            0.98,
        )
    )
    for _ in range(count):
        out.extend(_LAYOUT_PANEL.pack(0, 0, float(gap), 0.0, 0.0, 0.0))
    out.extend(title_bytes)
    return _resolved_layout(bytes(out), count, facet=True)


def _u32(value: object, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if value < (1 if positive else 0) or value > _MAX_U32:
        qualifier = "positive " if positive else "non-negative "
        raise ValueError(f"{label} must be a {qualifier}u32 integer")
    return value


def _i32(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not -(1 << 31) <= value < (1 << 31):
        raise ValueError(f"{label} must be a signed i32 integer")
    return value


def _rgba(value: Optional[str]) -> tuple[int, int, int, int]:
    if value is None:
        return (0, 0, 0, 0)
    if value == "transparent":
        return (0, 0, 0, 0)
    return _native.css_color_rgba(value)


def resolve_annotation_styles(
    sources: Sequence[dict[str, Any]],
) -> ResolvedAnnotationStyles:
    """Marshal authored maps; Rust returns mechanical patches and XYST facts."""
    annotations = [copy.deepcopy(dict(source)) for source in sources]
    request = bytearray(_ANNOTATION_STYLE_HEADER.pack(b"XYAS", 1, len(annotations), 0))

    def put_text(value: Any, *, optional: bool = False) -> None:
        if optional and value is None:
            request.extend(_MAX_U32.to_bytes(4, "little"))
            return
        encoded = str(value).encode("utf-8")
        request.extend(len(encoded).to_bytes(4, "little"))
        request.extend(encoded)

    for annotation in annotations:
        style = dict(annotation.get("style") or {})
        entries = sorted(style.items(), key=lambda item: str(item[0]))
        request.extend(struct.pack("<2I", len(entries), 0))
        put_text(annotation.get("text"), optional=True)
        put_text(annotation.get("kind"), optional=True)
        for key, value in entries:
            put_text(key)
            if value is None:
                request.extend(struct.pack("<I", 0))
            elif isinstance(value, str):
                request.extend(struct.pack("<I", 1))
                put_text(value)
            elif isinstance(value, bool):
                request.extend(struct.pack("<2I", 3, int(value)))
            elif isinstance(value, Real):
                request.extend(struct.pack("<Id", 2, float(value)))
            else:
                request.extend(struct.pack("<I", 4))
        annotation["style"] = style

    try:
        output = _native.static_annotation_style(bytes(request))
    except ValueError as error:
        reason = str(error)
        if reason.startswith("XYG_STATIC_UNSUPPORTED_"):
            raise UnsupportedStaticExport(reason) from None
        raise
    if len(output) < _ANNOTATION_STYLE_OUTPUT.size:
        raise RuntimeError("invalid XYAO output")
    magic, version, count, presence, size, padding, text_flags, vertical = (
        _ANNOTATION_STYLE_OUTPUT.unpack_from(output)
    )
    if magic != b"XYAO" or version != 1 or count != len(annotations) or presence & ~0xF:
        raise RuntimeError("invalid XYAO output")
    at = _ANNOTATION_STYLE_OUTPUT.size

    def take(length: int) -> bytes:
        nonlocal at
        end = at + length
        if end > len(output):
            raise RuntimeError("invalid XYAO output")
        value = output[at:end]
        at = end
        return value

    def get_u32() -> int:
        return int.from_bytes(take(4), "little")

    def get_text() -> str:
        return take(get_u32()).decode("utf-8")

    retained: list[dict[str, Any]] = []
    for annotation in annotations:
        drop = get_u32()
        patch_count = get_u32()
        if drop not in {0, 1} or (drop and patch_count):
            raise RuntimeError("invalid XYAO output")
        style = annotation["style"]
        for _ in range(patch_count):
            key = get_text()
            operation = get_u32()
            if operation == 0:
                style.pop(key, None)
            elif operation == 1:
                style[key] = get_text()
            elif operation == 2:
                style[key] = struct.unpack("<d", take(8))[0]
            else:
                raise RuntimeError("invalid XYAO output")
        if not drop:
            retained.append(annotation)
    if at != len(output):
        raise RuntimeError("invalid XYAO output")
    return ResolvedAnnotationStyles(
        retained,
        float(size) if presence & 1 else None,
        int(text_flags) if presence & 2 else None,
        float(padding) if presence & 4 else None,
        int(vertical) if presence & 8 else None,
    )


def _label_bytes(labels: Sequence[dict[str, Any]]) -> bytes:
    out = bytearray(_DOCUMENT_LABELS_HEADER.pack(b"XYDA", 1, len(labels), 0))

    def text(value: Any) -> None:
        if value is None:
            out.extend(_MAX_U32.to_bytes(4, "little"))
            return
        encoded = str(value).encode("utf-8")
        out.extend(len(encoded).to_bytes(4, "little"))
        out.extend(encoded)

    for label in labels:
        flags = sum(
            bit
            for key, bit in (("x", 1), ("y", 2), ("size", 4), ("rotation", 8), ("opacity", 16))
            if label.get(key) is not None
        )
        out.extend(
            _DOCUMENT_LABEL.pack(
                flags,
                0,
                float(label["x"]) if flags & 1 else 0.0,
                float(label["y"]) if flags & 2 else 0.0,
                float(label["size"]) if flags & 4 else 0.0,
                float(label["rotation"]) if flags & 8 else 0.0,
                float(label["opacity"]) if flags & 16 else 0.0,
            )
        )
        for value in (
            label.get("text"),
            label.get("family"),
            label.get("anchor"),
            label.get("vertical_align"),
            label.get("font_style"),
            label.get("weight"),
            label.get("color"),
        ):
            text(value)
    try:
        return _native.static_document_labels(bytes(out))
    except ValueError as error:
        reason = str(error)
        if reason.startswith("XYG_STATIC_UNSUPPORTED_"):
            raise UnsupportedStaticExport(reason) from None
        raise


def _decorations(
    labels: Optional[Sequence[dict[str, Any]]],
    legend: Optional[dict[str, Any]],
    colorbar: Optional[str],
) -> bytes:
    if not labels and not legend and not colorbar:
        return b""
    if len(labels or ()) > 64:
        raise ValueError("StaticDocument supports at most 64 document labels")
    colorbar_bytes = (colorbar or "").encode("utf-8")
    if len(colorbar_bytes) > 256 or b"\0" in colorbar_bytes:
        raise ValueError("StaticDocument colorbar name is invalid")
    actual_labels = labels or ()
    label_bytes = _label_bytes(actual_labels)
    legend_bytes = _legend_bytes(legend)
    out = bytearray(
        _DECORATION_HEADER.pack(
            b"XYDD", 1, len(actual_labels), len(legend_bytes), len(colorbar_bytes), 0, 0, 0
        )
    )
    out.extend(label_bytes)
    out.extend(legend_bytes)
    out.extend(colorbar_bytes)
    return bytes(out)


def _legend_bytes(legend: Optional[dict[str, Any]]) -> bytes:
    if not legend or not legend.get("items"):
        return b""
    items = list(legend["items"])
    style = dict(legend.get("style") or {})
    raw_anchor = legend.get("anchor")
    if raw_anchor is not None:
        if len(raw_anchor) != 2:
            raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_PANEL_LEGEND_ANCHOR")
        anchor = tuple(float(value) for value in raw_anchor)
    else:
        anchor = (0.0, 0.0)
    flags = sum(
        bit
        for key, bit in (
            ("ncols", 1),
            ("handlelength", 2),
            ("handletextpad", 4),
            ("border_pad", 8),
        )
        if legend.get(key) is not None
    )
    if raw_anchor is not None:
        flags |= 16
    raw_ncols = int(legend["ncols"]) if flags & 1 else 0
    if not -(1 << 31) <= raw_ncols < (1 << 31):
        raise ValueError("StaticDocument legend ncols must fit signed i32")
    out = bytearray(
        _DOCUMENT_LEGEND_HEADER.pack(
            b"XYDL",
            1,
            flags,
            len(items),
            raw_ncols,
            0,
            float(legend["handlelength"]) if flags & 2 else 0.0,
            float(legend["handletextpad"]) if flags & 4 else 0.0,
            float(legend["border_pad"]) if flags & 8 else 0.0,
            *anchor,
        )
    )

    def text(value: Any) -> None:
        if value is None:
            out.extend(_MAX_U32.to_bytes(4, "little"))
            return
        encoded = str(value).encode("utf-8")
        out.extend(len(encoded).to_bytes(4, "little"))
        out.extend(encoded)

    for value in (
        legend.get("title"),
        legend.get("loc"),
        legend.get("figure_loc"),
        style.get("fontSize"),
        style.get("padding"),
        style.get("rowGap"),
        style.get("color"),
        style.get("background"),
        style.get("borderColor"),
        style.get("--xy-legend-frame-alpha"),
        style.get("fontFamily"),
    ):
        text(value)
    for item in items:
        item_style = dict(item.get("style") or {})
        item_flags = sum(
            bit
            for key, bit in (("width", 1), ("stroke_width", 2), ("opacity", 8))
            if item_style.get(key) is not None
        )
        # XYDL requires a positive marker size for every item; absent authored
        # sizes default to the scatter marker size of 8 px.
        item_flags |= 4
        if item_style.get("dash"):
            item_flags |= 16
        out.extend(
            _DOCUMENT_LEGEND_ITEM.pack(
                item_flags,
                0,
                float(item_style["width"]) if item_flags & 1 else 0.0,
                float(item_style["stroke_width"]) if item_flags & 2 else 0.0,
                float(item_style.get("size") or 8.0),
                float(item_style["opacity"]) if item_flags & 8 else 0.0,
            )
        )
        for value in (
            item.get("kind"),
            item.get("name"),
            item_style.get("color"),
            item_style.get("symbol"),
        ):
            text(value)
    try:
        return _native.static_document_legend(bytes(out))
    except ValueError as error:
        reason = str(error)
        if reason.startswith("XYG_STATIC_UNSUPPORTED_"):
            raise UnsupportedStaticExport(reason) from None
        raise


def encode(
    panels: Sequence[Panel],
    *,
    width: int,
    height: int,
    background: Optional[str] = None,
    title: Optional[str] = None,
    title_color: str = "#262626",
    title_size: float = 14.0,
    title_x: Optional[float] = None,
    title_y: float = 16.0,
    title_anchor: int = 1,
    title_flags: int = 0,
    optimize_png: bool = False,
    labels: Optional[Sequence[dict[str, Any]]] = None,
    tight_crop: bool = False,
    crop_padding: int = 0,
    colorbar: Optional[str] = None,
    legend: Optional[dict[str, Any]] = None,
) -> bytes:
    """Marshal literal document facts; all validation/rendering is Rust-owned."""
    document_width = _u32(width, "StaticDocument width", positive=True)
    document_height = _u32(height, "StaticDocument height", positive=True)
    if not panels or len(panels) > _MAX_PANELS:
        raise ValueError(f"StaticDocument needs 1..{_MAX_PANELS} panels")
    title_bytes = (title or "").encode("utf-8")
    if len(title_bytes) > _MAX_TITLE_BYTES or b"\0" in title_bytes:
        raise ValueError(
            f"StaticDocument title must be NUL-free UTF-8 within {_MAX_TITLE_BYTES} bytes"
        )
    if title_anchor not in (0, 1, 2):
        raise ValueError("StaticDocument title anchor must be 0, 1, or 2")
    if title_flags not in (0, 1, 2, 3):
        raise ValueError("StaticDocument title flags must contain only italic/bold bits")
    decorations = _decorations(labels, legend, colorbar)
    flags = (
        (_FLAG_BACKGROUND if background is not None else 0)
        | (_FLAG_OPTIMIZE_PNG if optimize_png else 0)
        | (_FLAG_TIGHT_CROP if tight_crop else 0)
        | (_FLAG_TITLE_X_CENTER if title_x is None else 0)
    )
    records = bytearray()
    scenes = bytearray()
    for index, panel in enumerate(panels):
        scene = bytes(panel.scene)
        if not scene:
            raise ValueError(f"StaticDocument panel {index} has an empty Scene")
        offset = len(scenes)
        metric_flags = 0
        metrics = (0.0,) * 6
        if panel.chrome_metrics is not None:
            if len(panel.chrome_metrics) != 6:
                raise ValueError(
                    f"StaticDocument panel {index} chrome metrics must contain six numbers"
                )
            metrics = tuple(float(value) for value in panel.chrome_metrics)
            metric_flags = 3
        colorbar_layout = (0.0, 0.0, 0.0)
        if panel.colorbar_layout is not None:
            if len(panel.colorbar_layout) != 3:
                raise ValueError(
                    f"StaticDocument panel {index} colorbar layout must contain three numbers"
                )
            colorbar_layout = tuple(float(value) for value in panel.colorbar_layout)
            metric_flags |= 4
        annotation_bits = 0
        if panel.annotation_font_size is not None:
            annotation_bits = struct.unpack(
                "<I", struct.pack("<f", float(panel.annotation_font_size))
            )[0]
            metric_flags |= 8
        arrow_metrics = (0.0, 0.0, 0.0)
        if panel.arrow_metrics is not None:
            if len(panel.arrow_metrics) != 3:
                raise ValueError(
                    f"StaticDocument panel {index} arrow metrics must contain three numbers"
                )
            arrow_metrics = tuple(float(value) for value in panel.arrow_metrics)
            metric_flags |= 16
        axis_sides = 0
        if panel.axis_sides is not None:
            if len(panel.axis_sides) != 2:
                raise ValueError(f"StaticDocument panel {index} axis sides must contain two masks")
            x_sides, y_sides = panel.axis_sides
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in (x_sides, y_sides)
            ):
                raise ValueError(f"StaticDocument panel {index} axis side masks must be integers")
            if x_sides & ~3 or y_sides & ~3:
                raise ValueError(
                    f"StaticDocument panel {index} axis side masks must use only low/high bits"
                )
            axis_sides = x_sides | (y_sides << 8)
            metric_flags |= 32
        annotation_text_flags = 0
        if panel.annotation_text_flags is not None:
            annotation_text_flags = _u32(
                panel.annotation_text_flags,
                f"StaticDocument panel {index} annotation text flags",
            )
            if annotation_text_flags & ~3:
                raise ValueError(
                    f"StaticDocument panel {index} annotation text flags use only italic/bold bits"
                )
            metric_flags |= 64
        annotation_padding = 0.0
        if panel.annotation_padding is not None:
            annotation_padding = float(panel.annotation_padding)
            metric_flags |= 128
        panel_title_size = 0.0
        panel_title_rgba = (0, 0, 0, 0)
        if panel.title_style is not None:
            if len(panel.title_style) != 2:
                raise ValueError(f"StaticDocument panel {index} title style needs size/color")
            panel_title_size = float(panel.title_style[0])
            panel_title_rgba = _rgba(str(panel.title_style[1]))
            metric_flags |= 256
        annotation_vertical_align = 0
        if panel.annotation_vertical_align is not None:
            annotation_vertical_align = _u32(
                panel.annotation_vertical_align,
                f"StaticDocument panel {index} annotation vertical align",
            )
            if annotation_vertical_align > 3:
                raise ValueError(
                    f"StaticDocument panel {index} annotation vertical align must be 0..3"
                )
            metric_flags |= 512
        if panel.colorbar_scale is not None:
            if panel.colorbar_scale not in {"linear", "log"}:
                raise ValueError(
                    f"StaticDocument panel {index} colorbar scale must be linear or log"
                )
            if panel.colorbar_scale == "log":
                metric_flags |= 1 << 10
        if panel.colorbar_extend is not None:
            if panel.colorbar_extend not in {"neither", "min", "max", "both"}:
                raise ValueError(
                    f"StaticDocument panel {index} colorbar extend must be neither/min/max/both"
                )
            if panel.colorbar_extend in {"min", "both"}:
                metric_flags |= 1 << 11
            if panel.colorbar_extend in {"max", "both"}:
                metric_flags |= 1 << 12
        if panel.colorbar_pyplot_label:
            metric_flags |= 1 << 13
        grid_dash = 0
        if panel.grid_dash is not None:
            if len(panel.grid_dash) != 4:
                raise ValueError(f"StaticDocument panel {index} grid dash needs four axis codes")
            for code in panel.grid_dash:
                if isinstance(code, bool) or not isinstance(code, int) or not 0 <= code <= 3:
                    raise ValueError(f"StaticDocument panel {index} grid dash codes must be 0..3")
            x_major, y_major, x_minor, y_minor = panel.grid_dash
            grid_dash = x_major | (y_major << 4) | (x_minor << 16) | (y_minor << 24)
            metric_flags |= 1 << 14
        if panel.colorbar_fill_plot:
            metric_flags |= 1 << 24
        values = (
            _i32(panel.x, f"StaticDocument panel {index} x"),
            _i32(panel.y, f"StaticDocument panel {index} y"),
            _u32(panel.width, f"StaticDocument panel {index} width", positive=True),
            _u32(panel.height, f"StaticDocument panel {index} height", positive=True),
            _u32(offset, f"StaticDocument panel {index} offset"),
            _u32(len(scene), f"StaticDocument panel {index} Scene length", positive=True),
            metric_flags,
            annotation_bits,
            *metrics,
            *colorbar_layout,
            *arrow_metrics,
            axis_sides,
            annotation_text_flags,
            annotation_padding,
            panel_title_size,
            *panel_title_rgba,
            annotation_vertical_align,
            grid_dash,
        )
        records.extend(_PANEL.pack(*values))
        scenes.extend(scene)
    x = 0.0 if title_x is None else float(title_x)
    header = _HEADER.pack(
        b"XYST",
        1,
        document_width,
        document_height,
        flags,
        len(panels),
        len(title_bytes),
        *_rgba(background),
        *_rgba(title_color),
        float(title_size),
        x,
        float(title_y),
        title_anchor,
        title_flags,
        len(decorations),
        _u32(crop_padding, "StaticDocument crop padding"),
    )
    assert len(header) == 64
    return header + records + title_bytes + decorations + scenes


def project_figure(
    figure: Any,
    *,
    width: int,
    height: int,
    background: Optional[str] = None,
    optimize_png: bool = False,
) -> tuple[Panel, Optional[dict[str, Any]]]:
    """Project one public Figure onto panel facts plus its canonical Scene.

    Shared by the single-panel document route and the facet grid: validates
    authored styles, extracts chrome metrics and grid dash codes, resolves
    annotation styles, lifts the document legend, and compiles the Scene.
    """
    from . import _scene_v3

    projected = copy.deepcopy(figure)
    root_style = dict(getattr(projected, "style", None) or {})
    if getattr(projected, "_pyplot_static_mathtext", False):
        raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_MATHTEXT_STYLE")
    allowed_root = {
        "background",
        "--chart-bg",
        "--chart-grid",
        "--chart-axis",
        "--chart-text",
        "font-family",
        "font-size",
    }
    if set(root_style) - allowed_root:
        raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_BROWSER_CSS")
    family = str(root_style.get("font-family", "DejaVu Sans, sans-serif")).lower().replace(" ", "")
    if family not in {"dejavusans,sans-serif", "system-ui,sans-serif", "sans-serif"}:
        raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_CUSTOM_FONT")
    chrome_styles = copy.deepcopy(getattr(projected, "chrome_styles", None) or {})
    for slot, chrome_style in chrome_styles.items():
        if slot not in {"title", "axis_title", "tick_label"} or set(chrome_style) - {
            "font-size",
            "color",
            "font-weight",
            "font-family",
        }:
            raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_CHROME_STYLE")
        chrome_family = str(chrome_style.get("font-family", "DejaVu Sans")).lower()
        if chrome_family not in {"dejavu sans", "dejavusans", "sans-serif"}:
            raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_CUSTOM_FONT")
    projected.style = {
        key: value for key, value in root_style.items() if key in {"background", "--chart-bg"}
    }
    projected.chrome_styles = {}
    chrome_metrics: dict[str, tuple[float, float, float]] = {}
    grid_dash: dict[str, Optional[int]] = {"x": None, "y": None}
    grid_dash_minor: dict[str, Optional[int]] = {"x": None, "y": None}
    for axis_id, options in projected.axis_options.items():
        style = dict(options.get("style") or {})
        minor = dict(options.get("minor_style") or {})
        if axis_id in {"x", "y"}:
            chrome_metrics[axis_id] = (
                float(style.pop("tick_label_size", style.pop("tick_size", 12.0))),
                float(style.pop("label_size", 12.0)),
                float(style.pop("tick_padding", 4.0)),
            )
            raw_dash = style.pop("grid_dash", None)
            if raw_dash is not None:
                if raw_dash not in _GRID_DASH_CODES:
                    raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_GRID_DASH")
                grid_dash[axis_id] = _GRID_DASH_CODES[raw_dash]
            raw_minor_dash = minor.pop("grid_dash", None)
            if raw_minor_dash is not None:
                if raw_minor_dash not in _GRID_DASH_CODES:
                    raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_GRID_DASH")
                grid_dash_minor[axis_id] = _GRID_DASH_CODES[raw_minor_dash]
        for key in ("tick_label_size", "tick_size", "label_size", "tick_padding"):
            minor.pop(key, None)
        if root_style.get("--chart-grid") is not None:
            style["grid_color"] = root_style["--chart-grid"]
            minor["grid_color"] = root_style["--chart-grid"]
        if root_style.get("--chart-axis") is not None:
            style["axis_color"] = root_style["--chart-axis"]
            style["tick_color"] = root_style["--chart-axis"]
            minor["tick_color"] = root_style["--chart-axis"]
        if root_style.get("--chart-text") is not None:
            style.setdefault("label_color", root_style["--chart-text"])
            style.setdefault("tick_label_color", root_style["--chart-text"])
        if style:
            options["style"] = style
        else:
            options.pop("style", None)
        if minor:
            options["minor_style"] = minor
        else:
            options.pop("minor_style", None)
    for trace in projected.traces:
        trace.style = {
            key: value
            for key, value in (trace.style or {}).items()
            if not str(key).startswith("_legend_")
        }
    annotation_style = resolve_annotation_styles(
        list(getattr(projected, "annotations", None) or [])
    )
    projected.annotations = annotation_style.annotations
    legend = None
    if getattr(projected, "show_legend", False):
        if projected.extra_legends:
            raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_MULTIPLE_PANEL_LEGENDS")
        items = []
        for trace in projected.traces:
            if not trace.name:
                continue
            item_style = dict(trace.style or {})
            color_channel = getattr(trace, "color_ch", None)
            if getattr(color_channel, "mode", None) == "constant":
                item_style.setdefault("color", color_channel.constant)
            size_channel = getattr(trace, "size_ch", None)
            if getattr(size_channel, "mode", None) == "constant":
                item_style.setdefault("size", size_channel.constant)
            items.append({"kind": trace.kind, "name": trace.name, "style": item_style})
        if items:
            legend_options = {
                key: value
                for key, value in copy.deepcopy(projected.legend_options).items()
                if key not in _INTERACTIVE_LEGEND_KEYS
            }
            legend = {**legend_options, "items": items}
    projected.show_legend = False
    projected.legend_options = {}
    projected.extra_legends = []
    reason, scene = _scene_v3._public_scene_or_reason(projected, width=width, height=height)
    if reason is not None or scene is None:
        raise UnsupportedStaticExport(reason or "XYG_STATIC_UNSUPPORTED_PANEL")
    frame_sides = set(getattr(projected, "frame_sides", None) or ("left", "bottom"))
    title_style = None
    if getattr(projected, "title", None):
        authored = dict(chrome_styles.get("title") or {})
        raw_size = str(authored.get("font-size", "14px"))
        if not raw_size.endswith("px"):
            raise UnsupportedStaticExport("XYG_STATIC_UNSUPPORTED_TITLE_STYLE")
        title_style = (
            float(raw_size[:-2]),
            str(authored.get("color", root_style.get("--chart-text", "#262626"))),
        )
    panel = Panel(
        scene,
        0,
        0,
        width,
        height,
        chrome_metrics=(*chrome_metrics["x"], *chrome_metrics["y"]),
        annotation_font_size=annotation_style.font_size,
        axis_sides=(
            (1 if "bottom" in frame_sides else 0) | (2 if "top" in frame_sides else 0),
            (1 if "left" in frame_sides else 0) | (2 if "right" in frame_sides else 0),
        ),
        annotation_text_flags=annotation_style.text_flags,
        annotation_padding=annotation_style.padding,
        title_style=title_style,
        annotation_vertical_align=annotation_style.vertical_align,
        grid_dash=_grid_dash_fact(grid_dash, grid_dash_minor),
    )
    return panel, legend


def figure_document(
    figure: Any,
    *,
    width: int,
    height: int,
    background: Optional[str] = None,
    optimize_png: bool = False,
) -> bytes:
    """Compile one public Figure into its single-panel XYST document."""
    panel, legend = project_figure(
        figure, width=width, height=height, background=background, optimize_png=optimize_png
    )
    return encode(
        [panel],
        width=width,
        height=height,
        background=background,
        optimize_png=optimize_png,
        legend=legend,
    )


def export_figure(
    figure: Any,
    format: str,
    *,
    width: int,
    height: int,
    scale: float = 1.0,
    background: Optional[str] = None,
    quality: int = 90,
    optimize_png: bool = False,
) -> bytes:
    document = figure_document(
        figure,
        width=width,
        height=height,
        background=background,
        optimize_png=optimize_png,
    )
    return _native.static_document_export(document, format, scale=scale, quality=quality)
