"""#1006 / #889 family 4: ordinary layered figures export with Rust autorange.

Every Scene compile takes an absent primary domain from the shared Rust figure
autorange the browser uses, so leaving the domain unauthored must produce the
same document as authoring that resolved domain explicitly.
"""

from __future__ import annotations

import numpy as np
import pytest

import xyg
from xyg import _static_document as sd

X = np.arange(12.0)
Y = np.sin(X)


def _chart(*axes, children=None):
    marks = children or [xyg.line(x=X, y=Y), xyg.line(x=X, y=-Y), xyg.scatter(x=X, y=2 * Y)]
    return xyg.chart(*marks, *axes, width=320, height=240)


@pytest.mark.parametrize(
    "children",
    [
        None,
        [xyg.scatter(x=X, y=Y), xyg.line(x=X, y=Y)],  # the CodSpeed warm-up shape
        [xyg.bar(x=X, y=np.abs(Y)), xyg.line(x=X, y=Y)],
    ],
)
@pytest.mark.parametrize("format", ["svg", "png", "pdf"])
def test_layered_figures_autorange_like_an_authored_domain(children, format):
    axes = (xyg.x_axis(label="Time", format=".1f"), xyg.y_axis(label="Value"))
    figure = _chart(*axes, children=children).figure()
    x_domain, y_domain = tuple(figure._range("x")), tuple(figure._range("y"))
    authored = _chart(
        xyg.x_axis(label="Time", format=".1f", domain=x_domain),
        xyg.y_axis(label="Value", domain=y_domain),
        children=children,
    )
    assert _chart(*axes, children=children).to_image(format, scale=1) == authored.to_image(
        format, scale=1
    )


def test_domain_shaping_axis_options_still_require_an_authored_domain():
    with pytest.raises(sd.UnsupportedStaticExport, match="XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS"):
        _chart(xyg.x_axis(margin=0.2)).to_svg()
