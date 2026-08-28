"""Native PNG export — thin host binding over the Rust encoder.

`png_truecolor` and `encode` turn packed RGB/RGBA8 pixels into a PNG. Rust owns
filter-0 scanlines, zlib IDAT, indexed-palette selection (≤256 unique RGBA
colors + `tRNS`), and truecolor fallback (M2 #274). This module only coerces
host buffers and forwards `mode` / `compression`.
"""

from __future__ import annotations

import numpy as np

from . import _native

__all__ = ["encode", "png_truecolor"]

_COMPRESSION_LEVEL = 6


def png_truecolor(
    w: int,
    h: int,
    rgba: bytes | bytearray | memoryview | np.ndarray,
    *,
    compression_level: int = _COMPRESSION_LEVEL,
) -> bytes:
    """RGBA8 PNG (color type 6). `rgba` is row-major `w*h*4` bytes, top row
    first.

    Any buffer works: `bytes`/`bytearray`/`memoryview`, or a C-contiguous
    uint8 array. Only the first `w * h * 4` bytes are read.
    """
    width = int(w)
    height = int(h)
    count = width * height * 4
    if isinstance(rgba, np.ndarray):
        flat = np.ascontiguousarray(rgba, dtype=np.uint8).reshape(-1)
        if flat.size < count:
            raise ValueError("PNG pixel buffer length does not match width*height*4")
        pixels = flat[:count].reshape(height, width, 4)
    else:
        pixels = np.frombuffer(rgba, dtype=np.uint8, count=count).reshape(height, width, 4)
    return _native.encode_png(pixels, mode=1, compression=int(compression_level))


def encode(img: np.ndarray) -> bytes:
    """Encode an `(h, w, 4)` uint8 RGBA image, preferring an indexed palette
    (≤256 colors) for size, else truecolor."""
    if not isinstance(img, np.ndarray):
        raise ValueError(f"PNG image must be a numpy array, got {type(img).__name__}")
    if img.ndim != 3 or img.shape[2] != 4:
        raise ValueError("PNG image must be (h, w, 4) RGBA")
    return _native.encode_png(np.ascontiguousarray(img, dtype=np.uint8), mode=0, compression=6)
