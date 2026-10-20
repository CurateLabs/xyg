"""Live dual-axis rendering in the real browser client (#1006 round 4).

The Node live payload previously collapsed every trace onto the primary y
range and omitted the y2 axis; y2-bound annotation bindings were dropped by
both hosts. This drives the real client in headless Chromium against a Python
live payload for a dual chart with unequal y/y2 domains and asserts the
user-visible contract: the y2 axis chrome renders on the right with its own
tick ladder, and a y2-bound annotation is projected through the y2 scale — not
silently re-projected through the primary one.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import xyg
from conftest import probe_document, run_browser_probe
from xyg.export import find_chromium

_PROBE = """
<script>
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  try {
    const view = window.__fcProbeView;
    if (!view) throw new Error("no probe view captured");
    view._drawNow();
    view._raf = null;
    // Tick labels arrive from the WASM tick worker asynchronously; wait for
    // the y2 ladder like the legend probes wait for their rows.
    let y2Ticks = [];
    for (let i = 0; i < 200; i++) {
      y2Ticks = [...view.root.querySelectorAll(
        '[data-xy-axis="y2"][data-xy-label-kind="tick"]')];
      if (y2Ticks.length >= 5) break;
      await sleep(25);
    }
    const texts = y2Ticks.map((el) => el.textContent);
    const y2Sides = [...new Set([...view.root.querySelectorAll('[data-xy-axis="y2"]')]
      .map((el) => el.dataset.xyAxisSide))];
    const label = (text) => [...view.root.querySelectorAll('[data-xy-slot="annotation_label"]')]
      .find((el) => el.textContent === text);
    const anchorOf = (el) => ({
      left: Number.parseFloat(el.style.left),
      top: Number.parseFloat(el.style.top),
    });
    const secondary = label("secondary");
    const primary = label("primary");
    const viaY2 = view._dataPxPoint(2, 200, "x", "y2");
    const viaPrimary = view._dataPxPoint(2, 200, "x", "y");
    const viaPrimaryText = view._dataPxPoint(2, 2, "x", "y");
    document.body.setAttribute("data-xy-dual-live-probe", JSON.stringify({
      axisIds: view._axisIds(),
      ranges: view.view.ranges,
      y2Ticks: texts,
      y2Sides,
      secondary: secondary ? anchorOf(secondary) : null,
      primary: primary ? anchorOf(primary) : null,
      viaY2,
      viaPrimary,
      viaPrimaryText,
    }));
  } catch (err) {
    document.body.setAttribute(
      "data-xy-dual-live-probe-error",
      String((err && err.stack) || err)
    );
  }
})();
</script>
"""


def _chart():
    return xyg.line_chart(
        xyg.line(x=[1.0, 2.0, 3.0], y=[1.0, 2.0, 3.0]),
        xyg.line(x=[1.0, 2.0, 3.0], y=[100.0, 200.0, 300.0], y_axis="y2"),
        xyg.x_axis(domain=(0, 4)),
        xyg.y_axis(domain=(0, 4), label="L"),
        xyg.y_axis(id="y2", side="right", label="R", domain=(0, 400)),
        xyg.text(2.0, 200.0, "secondary", y_axis="y2"),
        xyg.text(2.0, 2.0, "primary"),
        width=480,
        height=320,
    )


def test_y2_axis_and_bound_annotation_render_on_their_own_scale() -> None:
    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")

    document = probe_document(_chart(), _PROBE)
    with tempfile.TemporaryDirectory() as td:
        result = run_browser_probe(
            chromium,
            document,
            Path(td) / "dual_axis_live.html",
            "data-xy-dual-live-probe",
            label="dual-axis live client probe",
        )

    # The live client carries the y2 axis and its own view range.
    assert "y2" in result["axisIds"]
    assert result["ranges"]["y2"] == pytest.approx([0.0, 400.0])
    assert result["ranges"]["y"] == pytest.approx([0.0, 4.0])

    # The y2 axis chrome renders on the right with its own tick ladder.
    assert result["y2Sides"] == ["right"]
    assert [float(t) for t in result["y2Ticks"]] == pytest.approx([0.0, 100.0, 200.0, 300.0, 400.0])

    # The bound annotation sits at the y2 projection of (2, 200) plus its
    # authored (dx, dy) offset — not at the primary-scale projection, which is
    # far away on these unequal domains.
    assert result["secondary"] is not None
    assert result["primary"] is not None
    via_y2, via_primary = result["viaY2"], result["viaPrimary"]
    assert abs(via_y2[1] - via_primary[1]) > 50
    assert result["secondary"]["left"] == pytest.approx(via_y2[0] + 6, abs=1.0)
    assert result["secondary"]["top"] == pytest.approx(via_y2[1] - 6, abs=1.0)
    assert result["secondary"]["top"] != pytest.approx(via_primary[1] - 6, abs=4.0)
    # The unbound annotation still reads the primary scale.
    assert result["primary"]["top"] == pytest.approx(result["viaPrimaryText"][1] - 6, abs=1.0)
