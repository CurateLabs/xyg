"""Figure palette cycle and series color selection."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Optional

from .config import DEFAULT_PALETTE, default_palette_color

if TYPE_CHECKING:
    pass


def palette_cycle(self) -> Optional[list[str]]:
    """The chart palette as a positional cycle, or None when unset.

    A `{category: color}` palette pins colors by label; series that are not
    categories still need an order, and the mapping's own is the only one
    the author expressed."""
    if self.palette is None:
        return None
    if isinstance(self.palette, dict):
        return list(self.palette.values())
    return list(self.palette)


def colors(self) -> list[str]:
    """This chart's categorical cycle — its own palette, else the default."""
    return self.palette_cycle or list(DEFAULT_PALETTE)


def palette_color(self, index: int, *, stacklevel: int = 3) -> str:
    """Color for the `index`-th series (0-based): the chart palette, cycled.

    Wrapping is allowed but never silent (§28) — see
    `config.default_palette_color`, which owns the built-in-palette warning
    and its CVD-order rationale."""
    cycle = self.palette_cycle
    if cycle is None:
        return default_palette_color(index, stacklevel=stacklevel + 1)
    if index >= len(cycle):
        warnings.warn(
            f"more than {len(cycle)} series use default colors; the chart "
            f"palette repeats every {len(cycle)} (series "
            f"{len(cycle) + 1} wears series 1's color). Pass a longer "
            "xyg.theme(palette=...), or an explicit color= per series.",
            RuntimeWarning,
            stacklevel=stacklevel,
        )
    return cycle[index % len(cycle)]


def next_series_color(self, *, stacklevel: int = 4) -> str:
    """Take the next categorical slot for one logical series.

    Marks call this only when the caller gave no `color=`, so a mark that
    builds several traces (box, stem) — or that delegates to another mark
    body with the color already resolved — consumes exactly one slot."""
    index = self._series_cursor
    self._series_cursor += 1
    return self.palette_color(index, stacklevel=stacklevel)
