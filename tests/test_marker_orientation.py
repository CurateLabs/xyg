"""Browser marker orientation matches the static export (#911).

GLSL ES puts ``gl_PointCoord``'s origin at the point's top, but some WebGL
implementations (SwiftShader/ANGLE) run it bottom-up, which painted every
marker vertically mirrored in the browser (triangle apex down, pentagon and
star upside down) while SVG/PNG export and legends drew them apex up. The
point shader now orients "up" from window y, so the browser agrees with the
export on every GPU.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import xyg

SIZE = 60.0

_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    view._layout(); view._drawNow(); view._raf = null;
    const gl = view.gl;
    const painted = (x, y) => {
      const px = new Uint8Array(4);
      gl.readPixels(
        Math.round((x - view.plot.x) * view.dpr),
        Math.round(view.canvas.height - (y - view.plot.y) * view.dpr),
        1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      return px[3] > 128;
    };
    const out = {};
    for (const trace of view.gpuTraces) {
      const [cx, cy] = view._projectDataPoint(trace.xAxis, trace.yAxis, __X__[trace.trace.id], 0, null);
      const r = __SIZE__ / 2;
      out[trace.trace.id] = {
        top: painted(cx + 0.3 * r, cy - 0.8 * r),
        bottom: painted(cx + 0.3 * r, cy + 0.8 * r),
      };
    }
    document.body.setAttribute("data-xy-marker-probe", JSON.stringify(out));
  } catch (error) {
    document.body.setAttribute("data-xy-marker-probe-error", String((error && error.stack) || error));
  }
})();
"""


def test_browser_triangles_point_the_same_way_as_the_export(tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    # Apex up ("triangle", matplotlib "^") and apex down ("triangle_down").
    chart = xyg.scatter_chart(
        xyg.scatter(x=[0.0], y=[0.0], symbol="triangle", size=SIZE),
        xyg.scatter(x=[1.0], y=[0.0], symbol="triangle_down", size=SIZE),
        width=400,
        height=240,
    )
    fig = chart.figure()
    xs = {trace.id: float(trace.x.values[0]) for trace in fig.traces}
    script = _PROBE.replace("__SIZE__", repr(SIZE)).replace("__X__", json.dumps(xs))
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{script}</script>"),
        tmp_path / "marker-orientation.html",
        "data-xy-marker-probe",
        label="marker orientation",
    )
    up, down = (result[str(trace.id)] for trace in fig.traces)
    # Sampled 0.3 r right of center: near its apex (0.8 r above center) an
    # apex-up triangle is narrower than that, while near its base (0.8 r
    # below) it is wider.
    assert up == {"top": False, "bottom": True}, result
    assert down == {"top": True, "bottom": False}, result
