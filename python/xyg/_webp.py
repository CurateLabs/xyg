"""Native lossless WebP export — thin host binding over the Rust encoder.

`encode` turns an RGB/RGBA8 array into a RIFF/WEBP VP8L bitstream. Rust owns
the simple-lossless subset, length-limited prefix codes, and distance-1 run
packing (M2 #274). This module only coerces a NumPy array.
"""

from __future__ import annotations

import numpy as np

from . import _native

__all__ = ["encode"]


def encode(rgba: np.ndarray) -> bytes:
    """Encode an `(h, w, 4)` uint8 RGBA image (or `(h, w, 3)`, treated as
    opaque) as a lossless WebP. Alpha survives bit-exact."""
    return _native.encode_webp(rgba)
