"""#1006 browser coverage for explicit annotation cells (the pyplot ``table`` vocabulary).

The render client draws a fixed-size label box for ``box_width``/``box_height``
(px, or ``"<n>%"`` of the plot rectangle on axes-fraction text), forces it to
vertical centering, keeps the horizontal padding inset (border included) from
the anchored edge, never culls axes-fraction text placed outside the plot, and
still culls figure-fraction text there. The same cells exported by Rust (SVG)
must land on the same rectangles.

Browser probes skip (never fail) without Chromium, like the repo's others;
``XY_REQUIRE_BROWSER=1`` turns the skip into a failure.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

import xyg
from conftest import probe_document, run_browser_probe
from xyg.export import find_chromium

_PROBE = """
<script>
const view = window.__fcProbeView;
const p = view.plot;
const layer = view.labels.getBoundingClientRect();
const scale = layer.width / view.size.w;
const local = (r) => [
  (r.left - layer.left) / scale, (r.top - layer.top) / scale, r.width / scale, r.height / scale,
];
const labels = {};
for (const d of view.labels.querySelectorAll('[data-xy-slot="annotation_label"]')) {
  const range = document.createRange();
  range.selectNodeContents(d);
  const cs = getComputedStyle(d);
  labels[d.textContent] = {
    box: local(d.getBoundingClientRect()),
    text: local(range.getBoundingClientRect()),
    display: cs.display,
    padLeft: parseFloat(cs.paddingLeft),
    padRight: parseFloat(cs.paddingRight),
    border: parseFloat(cs.borderLeftWidth),
  };
}
document.body.setAttribute(
  "data-xy-annotation-cells", JSON.stringify({ plot: [p.x, p.y, p.w, p.h], labels }),
);
</script>
"""


def _cell(x: float, y: float, text: str, anchor: str, **style: Any) -> xyg.Annotation:
    return xyg.text(
        x,
        y,
        text,
        dx=style.pop("dx", 0),
        dy=style.pop("dy", 0),
        anchor=anchor,
        style={
            "coordinate_space": "axes_fraction",
            "vertical_align": "center",
            "background": "#dbeafe",
            "border": "2px solid #000000",
            **style,
        },
    )


# Exported identically by Rust: a px cell hanging below the axes, a
# plot-percentage cell with a percentage inset, and a start-anchored px cell.
_STATIC_CELLS = (
    _cell(0.25, 0, "below", "middle", box_width=120, box_height=18, dy=12, padding="0px 6px"),
    _cell(
        0.95, 0.5, "pct", "end", box_width="40%", box_height="10%", padding="0px 5%", font_size=13
    ),
    _cell(0.1, 0.8, "left", "start", box_width=90, box_height=20, padding="0px 8px"),
)


def _chart(*annotations: xyg.Annotation) -> xyg.Chart:
    return xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
        *annotations,
        xyg.x_axis(domain=(0, 2), label="X"),
        xyg.y_axis(domain=(0, 4), label="Y"),
        xyg.legend(show=False),
        width=640,
        height=480,
    )


def _browser_labels(chart: xyg.Chart) -> dict[str, Any]:
    chromium = find_chromium()
    if not chromium:
        pytest.skip("no chromium available for the annotation-cell probe")
    with tempfile.TemporaryDirectory() as td:
        return run_browser_probe(
            chromium,
            probe_document(chart, _PROBE),
            Path(td) / "annotation_cells.html",
            "data-xy-annotation-cells",
            label="annotation cells",
        )


def _static_cells(svg: str) -> dict[str, tuple[float, ...]]:
    found = re.findall(
        r'<rect data-xy-slot="annotation_label_box"[^>]*? x="([-\d.]+)" y="([-\d.]+)" '
        r'width="([\d.]+)" height="([\d.]+)"[^>]*/><text[^>]*>([^<]*)</text>',
        svg,
    )
    return {text: tuple(map(float, box)) for *box, text in found}


def test_browser_cells_match_rust_static_cells_and_honor_the_inset() -> None:
    result = _browser_labels(
        _chart(
            *_STATIC_CELLS,
            # Browser-only: an explicit box always centers vertically (static
            # export rejects an uncentered box), and culling keeps
            # figure-fraction text below the plot out while axes-fraction text
            # outside the plot is drawn.
            _cell(0.6, 0.8, "forced", "middle", box_width=80, box_height=30, vertical_align="top"),
            xyg.text(
                0.5, -0.25, "axes-out", dx=0, dy=0, style={"coordinate_space": "axes_fraction"}
            ),
            xyg.text(
                0.5, 0.0, "fig-out", dx=0, dy=0, style={"coordinate_space": "figure_fraction"}
            ),
        )
    )
    px, py, pw, ph = result["plot"]
    labels = result["labels"]
    assert "axes-out" in labels, "axes-fraction text outside the plot is drawn"
    assert "fig-out" not in labels, "figure-fraction text outside the plot is still culled"
    below, pct, left, forced = (labels[name] for name in ("below", "pct", "left", "forced"))
    for cell in (below, pct, left, forced):
        assert cell["display"] == "flex" and cell["border"] == 2.0
    # Fixed px boxes, and percentages of the plot rectangle.
    assert below["box"][2:] == pytest.approx([120, 18], abs=0.01)
    assert pct["box"][2:] == pytest.approx([0.4 * pw, 0.1 * ph], abs=0.01)
    # The inset includes the border: padding is the remainder.
    assert (left["padLeft"], left["padRight"]) == (6.0, 6.0)
    assert pct["padRight"] == pytest.approx(0.05 * pw - 2, abs=0.01)
    # Text keeps the inset from the anchored edge.
    assert left["text"][0] - left["box"][0] == pytest.approx(8.0, abs=0.5)
    pct_right = pct["box"][0] + pct["box"][2]
    assert pct_right - (pct["text"][0] + pct["text"][2]) == pytest.approx(0.05 * pw, abs=0.5)
    assert pct_right == pytest.approx(px + 0.95 * pw + 0.05 * pw, abs=0.01)
    # Vertical centering on the anchor, forced even for vertical_align="top".
    forced_center = forced["box"][1] + forced["box"][3] / 2
    assert forced_center == pytest.approx(py + 0.2 * ph, abs=0.01)
    text_center = forced["text"][1] + forced["text"][3] / 2
    assert text_center == pytest.approx(forced_center, abs=1.0)
    below_center = below["box"][1] + below["box"][3] / 2
    assert below_center == pytest.approx(py + ph + 12, abs=0.01)
    # The browser cells are the Rust static-export cells.
    static = _static_cells(_chart(*_STATIC_CELLS).to_svg())
    assert set(static) == {"below", "pct", "left"}
    for name, box in static.items():
        assert labels[name]["box"] == pytest.approx(list(box), abs=0.05), name
