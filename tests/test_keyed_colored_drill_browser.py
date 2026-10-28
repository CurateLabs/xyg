"""Actual Rust XYDT color tiles hand off to channel-bearing marks at native alpha."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import numpy as np
import pytest

import xyg
from conftest import RENDER_CALLS, run_browser_probe
from xyg import interaction
from xyg.export import find_chromium

_PROBE = r"""
const view = xy.renderStandalone(document.getElementById("chart"), spec, buf);
try {
  const assert = (ok, message) => { if (!ok) throw Error(message); };
  const g = view.gpuTraces[0], gl = view.gl;
  cancelAnimationFrame(view._raf); view._raf = null; view.draw = () => {};
  let clock = 1000;
  view._now = () => clock;
  view._prefersReducedMotion = () => false;
  const decode = raw => Uint8Array.from(atob(raw), c => c.charCodeAt(0));
  const dispatch = item => view._onKernelMsg(
    {...item.message, type: "density_update", seq: view.seq}, item.buffers.map(decode));
  dispatch(input.initial);
  assert(g._tileCapable && g.density.tileSet.length &&
    g.density.tileSet.every(t => t.rgba), "native colored XYDT not admitted");
  const tileOwners = [...g._tileTextures.values()].map(t => t.tex);
  const allBuffers = new Set();
  const create = gl.createBuffer.bind(gl);
  gl.createBuffer = (...args) => { const b = create(...args); allBuffers.add(b); return b; };
  const apply = item => {
    const update = item.message.traces[0];
    view.view = {x0: update.x_range[0], x1: update.x_range[1],
      y0: update.y_range[0], y1: update.y_range[1]};
    dispatch(item);
    assert(g.drill && g.drill.exact, "canonical exact drill not admitted");
  };
  const frame = () => {
    let marks = 0, density = 0;
    const points = view._drawPoints, grid = view._drawDensity;
    view._drawPoints = function(d, ...args) { if (d === g.drill) marks++;
      return points.call(this, d, ...args); };
    view._drawDensity = function(...args) { density++; return grid.apply(this, args); };
    try { view._drawNow(); } finally { view._drawPoints = points; view._drawDensity = grid; }
    return {marks, density};
  };
  apply(input.a);
  const noHandoff = g.drill.lodBlend === 0 && g.drill._lodBlendNative === 0 && !g.drill.dBuf;
  const a = g.drill, seqA = a.seq;
  assert(a.colorMode === input.colorMode && a.sizeMode === 1 && a.sBuf &&
    a.strokeBuf && a.styleBuf && a._cpuStyle[2] > 0, "drill channels/styles lost");
  const entry = frame(); clock += 70;
  const midEntry = frame(), midAlpha = g._drillShownAlpha;
  clock += 500; frame(); clock += 500;
  const settled = frame();
  // Actual painted marks survive the backdrop retirement; compare the same
  // frame with only marks suppressed so the oracle cannot pass on tile ink.
  const pixels = () => { view._drawNow(); const p = new Uint8Array(view.canvas.width*view.canvas.height*4);
    gl.readPixels(0,0,view.canvas.width,view.canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,p); return p; };
  const painted = pixels(), drawPoints = view._drawPoints;
  view._drawPoints = () => {}; const blank = pixels(); view._drawPoints = drawPoints;
  let markPixels = 0;
  for (let i = 0; i < painted.length; i += 4)
    if (painted.subarray(i,i+4).some((v,j) => v !== blank[i+j])) markPixels++;
  apply(input.b); frame();
  assert(g.drillCache?.includes(a), "first colored window was not cached");
  const sent = [];
  view.comm = {send: message => sent.push(message)};
  const promoteView = {...a.win};
  view.view = promoteView;
  view._scheduleViewRequest(view._viewFrom(promoteView), {delay: 0});
  clearTimeout(view._viewTimer);
  const cachePromoted = g.drill === a && g.drill.seq === seqA &&
    !sent.some(message => message.type === "density_view");
  frame();
  const channelsRetained = g.drill.colorMode === input.colorMode &&
    g.drill.sBuf === a.sBuf && g.drill.strokeBuf === a.strokeBuf &&
    gl.isBuffer(a.sBuf) && gl.isBuffer(a.strokeBuf) && gl.isBuffer(a.styleBuf);
  const tilesSurvivedPoints = tileOwners.every(t => gl.isTexture(t));
  // A real keyed density reply marks the exact window dying. Zoom out first
  // so T11/T13 retires it; never-entered prefetches remain governed as before.
  view.view = {x0: 0, x1: 1, y0: 0, y1: 1};
  dispatch(input.final);
  const dying = g._drillDying;
  const exit = frame(); clock += 500; frame(); clock += 500;
  const returned = frame();
  const liveTiles = [...g._tileTextures.values()].map(t => t.tex);
  const owned = tilesSurvivedPoints && liveTiles.every(t => gl.isTexture(t)) &&
    (g.densityCache || []).every(d => !d.tileSet || d.tileSet.every(t => gl.isTexture(t.tex)));
  const noGlError = gl.getError() === gl.NO_ERROR;
  view.destroy();
  const disposed = [...tileOwners, ...liveTiles].every(t => !gl.isTexture(t)) &&
    [...allBuffers].every(b => !gl.isBuffer(b));
  document.body.setAttribute("data-keyed-drill", JSON.stringify({noHandoff, entry, midEntry,
    midAlpha, settled, markPixels, cachePromoted, channelsRetained, dying, exit, returned,
    owned, noGlError, disposed, host: input.host}));
} catch (error) {
  document.body.setAttribute("data-keyed-drill-error", String(error.stack || error));
}
"""


@pytest.mark.parametrize("color_kind", ["direct_rgba", "continuous", "custom", "categorical"])
def test_keyed_mean_color_drill_cache_and_density(
    color_kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    # Real 200k entry/230k exit thresholds; only the aggregate fixture is small.
    monkeypatch.setattr(interaction, "PYRAMID_MIN_POINTS", 1)
    monkeypatch.setattr(interaction, "PYRAMID_BASE_DIM", 256)
    monkeypatch.setattr(interaction, "DRILL_PAD_TARGETS", ())
    n = 262_144
    rows = np.arange(n)
    x, y = (rows * 17 % n) / n, (rows * 31 % n) / n
    rgba = np.where((rows % 3)[:, None], [240, 50, 40, 128], [20, 90, 230, 200]).astype(np.uint8)
    color = {
        "direct_rgba": rgba / 255.0,
        "continuous": rows / n,
        "custom": rows / n,
        "categorical": np.where(rows % 3, "red", "blue"),
    }[color_kind]
    mark = xyg.scatter(
        x,
        y,
        color=color,
        colormap=["#f03228", "#145ae6"] if color_kind == "custom" else "viridis",
        size=rows / n,
        size_range=(3, 9),
        opacity=0.65,
        stroke=rgba / 255.0,
        stroke_width=1 + rows % 2,
        density=True,
        pyramid_spill=True,
    )
    chart = xyg.scatter_chart(mark, width=480, height=360)
    fig = chart.figure()
    trace = fig.traces[0]
    interaction._ensure_pyramid(trace)
    assert trace._tile_store and not trace._pyr_handle
    control = struct.pack("<4sIQdiI", b"XYDC", 1, 0, -1.0, -1, 0)
    host_observations = []

    def endpoint(bounds: tuple[float, float, float, float], expected_mode: str):
        message, buffers = interaction.density_view(
            fig, trace.id, *bounds, 256, 256, tile_cache=control
        )
        entry = message["traces"][0]
        assert entry["mode"] == expected_mode
        if expected_mode == "points":
            assert entry["binning"] == "canonical-points" and entry["reduction"] == "none"
            assert entry["canonical_query"]["status"] == "complete"
        else:
            assert entry["binning"].endswith("-tiles") and entry["density"]["tile_frame"] == 0
        host_observations.append(
            {
                "window": bounds,
                "mode": entry["mode"],
                "binning": entry["binning"],
                "canonical_query": entry.get("canonical_query"),
            }
        )
        return {
            "message": message,
            "buffers": [base64.b64encode(b).decode() for b in buffers],
        }

    try:
        payload = {
            "initial": endpoint((0, 1, 0, 1), "density"),
            "a": endpoint((0.05, 0.45, 0.05, 0.45), "points"),
            "b": endpoint((0.55, 0.95, 0.55, 0.95), "points"),
            "final": endpoint((0, 1, 0, 1), "density"),
            "colorMode": {"direct_rgba": 3, "continuous": 1, "custom": 1, "categorical": 2}[
                color_kind
            ],
            "host": {"source_rows": n, "replies": host_observations},
        }
        document = chart.to_html()
    finally:
        interaction._free_pyramid(trace)
    render_call = next(call for call in RENDER_CALLS if call in document)
    document = document.replace(render_call, "const input=" + json.dumps(payload) + ";\n" + _PROBE)
    result = run_browser_probe(
        chromium,
        document,
        tmp_path / f"keyed-drill-{color_kind}.html",
        "data-keyed-drill",
        label=f"keyed {color_kind} drill cache",
        hosted=True,
    )
    (tmp_path / "observations.json").write_text(json.dumps(result, sort_keys=True) + "\n")
    assert result["noHandoff"] is True, result
    assert result["entry"]["density"] > 0
    assert result["midEntry"]["marks"] > 0
    assert 0 < result["midAlpha"] < 1
    assert result["settled"]["marks"] > 0
    assert result["markPixels"] > 100
    assert result["cachePromoted"] is True
    assert result["channelsRetained"] is True
    assert result["dying"] is True
    assert result["exit"]["density"] > 0
    assert result["returned"]["density"] > 0 and result["returned"]["marks"] == 0
    assert result["owned"] and result["noGlError"] and result["disposed"]
