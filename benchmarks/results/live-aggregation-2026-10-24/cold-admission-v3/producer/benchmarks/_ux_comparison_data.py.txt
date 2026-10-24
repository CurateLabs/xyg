"""Shared, versioned UX workload; source generation is outside chart build clocks."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

SEED = 20260713
SOURCE_ID = "ux-correlated-gaussian-f32-sentinels-v1"
SENTINELS = [(4.6, 2.2), (4.9, 2.45), (4.75, 2.05), (5.0, 2.3), (4.55, 2.5)]


def make_data(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Exactly n real rows, preserving the original UX harness's random stream."""
    if n < len(SENTINELS):
        raise ValueError("UX source needs at least five rows for its planted sentinels")
    rng = np.random.default_rng(SEED)
    x = rng.standard_normal(n, dtype=np.float32)
    y = rng.standard_normal(n, dtype=np.float32)
    y *= np.float32(1.2)
    y += x
    y *= np.float32(0.5)
    for i, (sx, sy) in enumerate(SENTINELS):
        x[i] = np.float32(sx)
        y[i] = np.float32(sy)
    return x, y


def source_identity(x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    """Hash exact little-endian column bytes in x-then-y order, never a row count."""
    digest = hashlib.sha256()
    for col in (x, y):
        digest.update(memoryview(np.asarray(col, dtype="<f4")).cast("B"))
    return {
        "id": SOURCE_ID,
        "seed": SEED,
        "actual_rows": len(x),
        "columns": ["x", "y"],
        "dtype": "little-endian float32",
        "source_bytes": x.nbytes + y.nbytes,
        "sha256_x_then_y": digest.hexdigest(),
        "sentinels": [list(s) for s in SENTINELS],
        "scope": "two real resident f32 columns; no color, mmap, spill or synthetic row multiplier",
    }
