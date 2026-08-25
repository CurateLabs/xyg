"""Standalone density without WASM keeps its Rust-authored overview visibly.

The former JavaScript re-bin worker has no fallback role. This drives the real
client after deliberately withholding the self-contained WASM artifact and
proves a zoom leaves the overview untouched while emitting the stable explicit
degradation event.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import xyg
from conftest import run_browser_probe
from xyg.export import find_chromium

_RENDER_CALL = 'xy.renderStandalone(document.getElementById("chart"), spec, buf);'

_PROBE = """
  // Simulate a self-contained document whose optional WASM bootstrap did not
  // load, without changing the generated page's actual CSP or client bundle.
  globalThis.__xygInlineWasm = null;
  const diagnostics = [];
  document.addEventListener("xy:wasm_density_no_refinement", (event) => diagnostics.push(event.detail));
  const view = xy.renderStandalone(document.getElementById("chart"), spec, buf);
  try {
    view._drawNow();
    view._raf = null;
    const g = view.gpuTraces.find((t) => t.tier === "density");
    const v0 = view.view0;
    const sx = v0.x1 - v0.x0, sy = v0.y1 - v0.y0;
    const overview = g.density;
    const cx = (v0.x0 + v0.x1) / 2, cy = (v0.y0 + v0.y1) / 2;
    view._scheduleSampleRebin(
      { x0: cx - sx * 0.25, x1: cx + sx * 0.25, y0: cy - sy * 0.25, y1: cy + sy * 0.25 },
      { delay: 0 },
    );

    document.body.setAttribute("data-xy-rebin-probe", JSON.stringify({
      hasDensity: !!g,
      overviewRetained: g.density === overview,
      diagnostics,
    }));
  } catch (err) {
    document.body.setAttribute(
      "data-xy-rebin-probe-error",
      String((err && err.stack) || err),
    );
  }
"""


def _density_html() -> str:
    rng = np.random.default_rng(0)
    n = 60_000
    x = rng.normal(0.0, 1.0, n)
    y = rng.normal(0.0, 1.0, n)
    # density=True forces the density tier (overview grid + retained sample)
    # regardless of point count, so the export exercises the standalone re-bin
    # path deterministically and cheaply.
    chart = xyg.scatter_chart(
        xyg.scatter(x, y, density=True),
        xyg.x_axis(),
        xyg.y_axis(),
        width=480,
        height=360,
    )
    html = chart.to_html()
    assert _RENDER_CALL in html
    return html


def test_standalone_missing_wasm_keeps_overview_and_reports_no_refinement(tmp_path: Path) -> None:
    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")

    document = _density_html().replace(_RENDER_CALL, _PROBE)
    result = run_browser_probe(
        chromium,
        document,
        tmp_path / "density_pan.html",
        "data-xy-rebin-probe",
        label="density pan re-bin probe",
    )

    assert result["hasDensity"] is True
    assert result["overviewRetained"] is True
    assert result["diagnostics"] == [
        {
            "code": "XYG_WASM_UNAVAILABLE",
            "message": "self-contained Rust/WASM density artifact is unavailable",
            "traceIds": [0],
        }
    ]
