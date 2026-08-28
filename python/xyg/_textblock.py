"""Renderer-independent geometry for newline-delimited chart chrome.

Axis titles and tick labels are text *blocks*, not strings.  Keeping their
line splitting and geometry here lets SVG layout, native raster layout, and
the pyplot compositor reserve the same footprint.  The browser mirrors these
small formulas because it must resolve responsive layout client-side.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar, cast

from . import _native

LINE_HEIGHT = 1.2
_MeasurementKey = tuple[str, float, float, float | None]
_MEASUREMENTS: ContextVar[dict[_MeasurementKey, "TextBlock"] | None] = ContextVar(
    "xy_textblock_measurements",
    default=None,
)
_Return = TypeVar("_Return")


@dataclass(frozen=True)
class TextBlock:
    lines: tuple[str, ...]
    width: float
    height: float
    line_step: float
    ascent: float
    descent: float

    @property
    def line_count(self) -> int:
        return len(self.lines)


def split_lines(text: object) -> tuple[str, ...]:
    """Normalize line endings and preserve authored empty label lines."""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    return tuple(normalized.split("\n")) or ("",)


@contextmanager
def measurement_cache() -> Iterator[None]:
    """Reuse pure text metrics within one nested layout or export pass."""
    if _MEASUREMENTS.get() is not None:
        yield
        return
    token = _MEASUREMENTS.set({})
    try:
        yield
    finally:
        _MEASUREMENTS.reset(token)


def cached_measurements(
    function: Callable[..., _Return],
) -> Callable[..., _Return]:
    """Run ``function`` inside one pass-scoped text-measurement cache."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> _Return:
        with measurement_cache():
            return function(*args, **kwargs)

    return cast(Callable[..., _Return], wrapped)


def wrap_lines(lines: Sequence[str], font_size: float, max_width: float) -> tuple[str, ...]:
    """Greedy word wrap of already newline-split lines, at `max_width` px.

    Thin packer over Rust `textblock::wrap_lines` (ABI 125). Authored newlines
    are hard breaks; other whitespace collapses; an unbreakable word overflows.
    """
    if not lines:
        return ()
    return measure("\n".join(str(line) for line in lines), font_size, max_width=max_width).lines


def measure(
    text: object,
    font_size: float,
    line_height: float = LINE_HEIGHT,
    max_width: float | None = None,
) -> TextBlock:
    """Measure a newline-delimited block in the core DejaVu metrics.

    Thin packer over ``xyg_text_block_measure``. A finite positive `max_width`
    word-wraps first, so the measured height is the height the wrapped text
    actually occupies. Callers that wrap must draw `block.lines`, not the
    original string, or the reservation and the drawing disagree.
    """
    size = max(0.0, float(font_size))
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    resolved_line_height = float(line_height)
    limit: float | None = None if max_width is None else float(max_width)
    if limit is not None and not (math.isfinite(limit) and limit > 0.0):
        limit = None
    key = (normalized, size, resolved_line_height, limit)
    cache = _MEASUREMENTS.get()
    if cache is not None and key in cache:
        return cache[key]
    laid = _native.text_block_measure(normalized, size, resolved_line_height, limit)
    block = TextBlock(
        lines=tuple(laid["lines"]),
        width=float(laid["width"]),
        height=float(laid["height"]),
        line_step=float(laid["line_step"]),
        ascent=float(laid["ascent"]),
        descent=float(laid["descent"]),
    )
    if cache is not None:
        cache[key] = block
    return block


def rotated_extent(block: TextBlock, angle_degrees: float) -> tuple[float, float]:
    """Axis-aligned ``(width, height)`` after rotating ``block``."""
    return _native.text_block_rotated_extent(block.width, block.height, angle_degrees)
