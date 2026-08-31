"""Native vector PDF export — thin host binding over the Rust converter.

`svg_to_pdf` turns the output of Scene SVG and the compatibility `_svg.to_svg`
generator into a single-page vector PDF with no browser. Rust owns the closed
subset, path lowering, Helvetica metrics, ExtGState/shading/image embedding,
and deterministic object numbering (M2 #274). This module only coerces a
Python ``str`` and raises the same ``ValueError("unsupported SVG feature: ...")``
wording the historical stdlib converter used.
"""

from __future__ import annotations

from . import _native

__all__ = ["svg_to_pdf"]


def svg_to_pdf(svg: str) -> bytes:
    """Convert an xy-generated SVG document into a single-page vector PDF.

    Raises ``ValueError("unsupported SVG feature: ...")`` for any element,
    attribute, or value outside the closed subset the SVG generators emit.
    """
    return _native.svg_to_pdf(svg)
