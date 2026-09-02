"""LOD dataclasses and shared sampling constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

_UINT64_MAX_INT = (1 << 64) - 1
_DEFAULT_SAMPLE_BASE_FRACTION = 1.0 / 1024.0
# Integer categories at or above this go through np.unique instead of serving
# directly as group codes, bounding the native kernel's per-group state.
_MAX_DIRECT_CATEGORY_CODE = 1 << 20


@dataclass(frozen=True)
class LodPlan:
    """Chart-agnostic tier decision for a trace in a viewport.

    `mode` is the wire/client representation (`points`, `density`, future
    `buckets`, etc.). `tier` is the semantic reduction class used by docs,
    verifiers, and future adapters. `reduction` records what changed relative
    to direct marks.
    """

    mode: str
    tier: str
    visible: int
    budget: float
    grid_w: int
    grid_h: int
    reduction: str
    exact: bool

    def metadata(self) -> dict[str, Any]:
        """The downsampling decision as recorded in the chart spec —
        reductions are always disclosed there, never silent."""
        return {
            "mode": self.mode,
            "tier": self.tier,
            "visible": self.visible,
            "reduction": self.reduction,
        }


@dataclass(frozen=True)
class EncodedColumn:
    """Offset/scaled f32 column plus its wire metadata.

    First-payload builds, line/area re-decimation, scatter drilldown, and
    future bucketed chart updates all ship the same primitive: raw f32 values
    plus enough metadata for the client to recover data-space coordinates.
    """

    meta: dict[str, Any]
    values: np.ndarray

    @property
    def length(self) -> int:
        """Number of encoded values."""
        return int(len(self.values))
