"""Native baseline JPEG export — thin host binding over the Rust encoder.

`encode` turns an RGB/RGBA8 array into a sequential JFIF JPEG. Rust owns
YCbCr 4:4:4, Annex K tables, the libjpeg quality curve, and Huffman packing
(M2 #274). This module only coerces a NumPy array and forwards `quality`.
"""

from __future__ import annotations

import numpy as np

from . import _native

__all__ = ["encode"]


def encode(rgba: np.ndarray, *, quality: int = 90) -> bytes:
    """Encode an `(h, w, 4)` RGBA (alpha ignored) or `(h, w, 3)` RGB uint8
    image as a baseline JFIF JPEG. Deterministic for identical input."""
    return _native.encode_jpeg(rgba, quality=quality)
