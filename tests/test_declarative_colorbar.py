"""Declarative continuous-color marks drive built-in colorbar chrome."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import xyg
from conftest import probe_document, run_browser_probe
from xyg.export import find_chromium


def test_heatmap_colorbar_uses_compiled_scale_and_public_chrome_options() -> None:
    chart = xyg.heatmap_chart(
        xyg.heatmap(
            [[-2.0, 0.0], [2.0, 4.0]],
            name="temperature",
            colormap="coolwarm",
            domain=(-3.0, 5.0),
        ),
        xyg.colorbar(
            title="Temperature (°C)",
            orientation="horizontal",
            ticks=[-3, 0, 5],
            class_name="scale",
            style={"border-radius": 6},
        ),
    )

    spec, _ = chart.figure().build_payload()

    assert spec["colorbar"] == {
        "domain": [-3.0, 5.0],
        "colormap": "coolwarm",
        "label": "Temperature (°C)",
        "orientation": "horizontal",
        "ticks": [-3.0, 0.0, 5.0],
    }
    assert spec["dom"]["class_names"]["colorbar"] == "scale"
    assert spec["dom"]["styles"]["colorbar"] == {"border-radius": 6}


def test_heatmap_colorbar_autoscales_and_uses_the_mark_name() -> None:
    chart = xyg.chart(
        xyg.heatmap([[0.25, 0.75], [1.25, 1.75]], name="intensity", colormap="purples"),
        xyg.colorbar(),
    )

    spec, _ = chart.figure().build_payload()

    assert spec["colorbar"] == {
        "domain": [0.25, 1.75],
        "colormap": "purples",
        "label": "intensity",
        "orientation": "vertical",
    }


def test_continuous_scatter_colorbar_uses_color_column_not_trace_name() -> None:
    data = {
        "x": [0.0, 1.0, 2.0],
        "y": [2.0, 3.0, 5.0],
        "temperature": [12.0, 18.0, 31.0],
    }
    chart = xyg.scatter_chart(
        xyg.scatter(
            x="x",
            y="y",
            color="temperature",
            data=data,
            name="stations",
            colormap="plasma",
            color_domain=(10.0, 35.0),
        ),
        xyg.colorbar(),
    )

    spec, _ = chart.figure().build_payload()

    assert spec["colorbar"] == {
        "domain": [10.0, 35.0],
        "colormap": "plasma",
        "label": "temperature",
        "orientation": "vertical",
    }


@pytest.mark.parametrize(
    "color",
    ["#2563eb", ["low", "medium", "high"]],
)
def test_noncontinuous_scatter_does_not_invent_a_colorbar(color) -> None:
    chart = xyg.scatter_chart(
        xyg.scatter([0.0, 1.0, 2.0], [2.0, 3.0, 5.0], color=color),
        xyg.colorbar(),
    )

    spec, _ = chart.figure().build_payload()

    assert "colorbar" not in spec


def test_density_scatter_colorbar_labels_the_aggregated_color_channel() -> None:
    chart = xyg.scatter_chart(
        xyg.scatter(
            [0.0, 1.0, 2.0],
            [2.0, 3.0, 5.0],
            color=[10.0, 20.0, 30.0],
            density=True,
            colormap="plasma",
        ),
        xyg.colorbar(),
    )

    spec, _ = chart.figure().build_payload()

    # The aggregated surface wears the channel's own colors — per-cell mean
    # point color (LOD doc §2) — so the channel is not dropped and its
    # domain⇄colormap legend stays truthful at every tier.
    assert spec["traces"][0]["tier"] == "density"
    assert spec["traces"][0]["density"]["channels_dropped"] is False
    assert spec["traces"][0]["density"]["color_agg"] == "mean"
    assert spec["colorbar"]["domain"] == [10.0, 30.0]
    assert spec["colorbar"]["colormap"] == "plasma"


def test_hexbin_and_contour_colorbars_use_compiled_domains() -> None:
    x = np.array([-0.9, -0.8, -0.7, 0.1, 0.2, 0.3, 0.4])
    y = np.array([-0.8, -0.7, -0.6, 0.1, 0.2, 0.3, 0.4])
    hex_chart = xyg.hexbin_chart(
        xyg.hexbin(x, y, gridsize=4, mincnt=1, colormap="magma"),
        xyg.colorbar(),
    )
    hex_fig = hex_chart.figure()
    hex_spec, _ = hex_fig.build_payload()
    hex_channel = hex_fig.traces[0].color_ch

    assert hex_spec["colorbar"] == {
        "domain": list(hex_channel.domain),
        "colormap": "magma",
        "label": "count",
        "orientation": "vertical",
    }

    log_hex_chart = xyg.hexbin_chart(
        xyg.hexbin(x, y, gridsize=4, mincnt=1, bins="log", colormap="inferno"),
        xyg.colorbar(),
    )
    log_hex_fig = log_hex_chart.figure()
    log_hex_spec, _ = log_hex_fig.build_payload()
    log_hex_trace = log_hex_fig.traces[0]

    assert log_hex_trace.color_ch is not None
    assert log_hex_trace.color_ch.domain != log_hex_trace.colorbar_domain
    assert log_hex_spec["colorbar"] == {
        "domain": list(log_hex_trace.colorbar_domain),
        "colormap": "inferno",
        "label": "count",
        "orientation": "vertical",
        "scale": "log",
    }

    field = np.array(
        [
            [-2.0, -1.0, 0.0],
            [-1.0, 0.0, 1.0],
            [0.0, 1.0, 2.0],
        ]
    )
    contour_chart = xyg.contour_chart(
        xyg.contour(
            field,
            levels=[-1.5, -0.5, 0.5, 1.5],
            filled=True,
            name="elevation",
            colormap="spectral",
        ),
        xyg.colorbar(),
    )
    contour_spec, _ = contour_chart.figure().build_payload()

    assert contour_spec["colorbar"] == {
        "domain": [-1.5, 1.5],
        "colormap": "spectral",
        "label": "elevation",
        "levels": 3,
        "orientation": "vertical",
    }


def test_colorbar_uses_last_continuous_mark_and_show_false_removes_it() -> None:
    chart = xyg.chart(
        xyg.heatmap([[0.0, 1.0], [2.0, 3.0]], name="field", colormap="viridis"),
        xyg.scatter(
            [0.0, 1.0],
            [0.0, 1.0],
            color=[100.0, 200.0],
            name="quality",
            colormap="plasma",
        ),
        xyg.colorbar(),
    )
    hidden = xyg.chart(
        xyg.heatmap([[0.0, 1.0], [2.0, 3.0]], colormap="viridis"),
        xyg.colorbar(show=False),
    )

    spec, _ = chart.figure().build_payload()
    hidden_spec, _ = hidden.figure().build_payload()

    assert spec["colorbar"] == {
        "domain": [100.0, 200.0],
        "colormap": "plasma",
        "label": "quality",
        "orientation": "vertical",
    }
    assert "colorbar" not in hidden_spec


def test_colorbar_rejects_invalid_public_options() -> None:
    with pytest.raises(ValueError, match="colorbar orientation"):
        xyg.colorbar(orientation="diagonal")
    with pytest.raises(ValueError, match="colorbar orientation"):
        xyg.colorbar(orientation=["vertical"])
    with pytest.raises(ValueError, match="colorbar ticks"):
        xyg.colorbar(ticks="0, 1")
    with pytest.raises(ValueError, match="finite"):
        xyg.colorbar(ticks=[0.0, np.inf])


@pytest.mark.parametrize(
    ("node", "message"),
    [
        (xyg.Colorbar(show="yes"), "colorbar show"),
        (xyg.Colorbar(title=42), "colorbar title"),
        (xyg.Colorbar(orientation="diagonal"), "colorbar orientation"),
        (xyg.Colorbar(ticks=[0.0, np.inf]), "colorbar tick"),
        (xyg.Colorbar(class_name=42), "colorbar class_name"),
        (xyg.Colorbar(style="color: red"), "colorbar style"),
    ],
)
def test_direct_colorbar_instance_cannot_bypass_factory_validation(node, message) -> None:
    chart = xyg.heatmap_chart(
        xyg.heatmap([[0.0, 1.0], [2.0, 3.0]], colormap="viridis"),
        node,
    )

    with pytest.raises(ValueError, match=message):
        chart.figure()


def test_colorbar_uses_semantic_positional_fields_and_custom_render() -> None:
    renderer = object()
    node = xyg.Colorbar(
        True,
        "Temperature",
        "horizontal",
        [0.0, 1.0],
        "scale-class",
        {"color": "red"},
        renderer,
    )

    assert node.title == "Temperature"
    assert node.orientation == "horizontal"
    assert node.ticks == [0.0, 1.0]
    assert node.class_name == "scale-class"
    assert node.style == {"color": "red"}
    assert node.render is renderer

    custom = xyg.heatmap_chart(
        xyg.heatmap([[0.0, 1.0], [2.0, 3.0]], colormap="viridis"),
        node,
    )
    custom_spec, _ = custom.figure().build_payload()
    assert "colorbar" not in custom_spec


def test_declarative_colorbar_reaches_svg_export() -> None:
    svg = xyg.heatmap_chart(
        xyg.heatmap([[0.0, 0.5], [1.0, 1.5]], name="Intensity", colormap="purples"),
        xyg.colorbar(title="Intensity & confidence", ticks=[0.0, 1.5]),
        width=520,
        height=320,
    ).to_svg()

    assert '<linearGradient id="xy-colorbar-' in svg
    assert "Intensity &amp; confidence" in svg
    assert ">0<" in svg
    assert ">1.5<" in svg


def test_svg_explicit_colorbar_ticks_preserve_authored_precision() -> None:
    svg = xyg.heatmap_chart(
        xyg.heatmap([[0.0, 1.0], [2.0, 3.0]], colormap="viridis"),
        xyg.colorbar(ticks=[0.123, 2.987]),
        width=520,
        height=320,
    ).to_svg()

    assert ">0.123<" in svg
    assert ">2.987<" in svg


def _browser_colorbar_probe(chromium: str, chart: xyg.Chart, page: Path) -> dict:
    probe = """<script>
(() => {
  try {
    const view = window.__fcProbeView;
    // Bare rAF may not tick under --virtual-time-budget --dump-dom. Drain the
    // initial scheduled draw synchronously before inspecting browser chrome.
    view._drawNow();
    view._raf = null;
    const bar = document.querySelector('[data-xy-slot="colorbar_bar"]');
    const title = document.querySelector('[data-xy-slot="colorbar_title"]');
    const ticks = [...document.querySelectorAll('[data-xy-slot="colorbar_tick"]')];
    document.body.setAttribute('data-xy-colorbar-probe', JSON.stringify({
      exists: !!bar,
      title: title && title.textContent,
      tooltip: view._colorbar && view._colorbar.title,
      gradient: bar && getComputedStyle(bar).backgroundImage,
      tickLabels: ticks.map((tick) => tick.textContent),
    }));
  } catch (err) {
    document.body.setAttribute(
      'data-xy-colorbar-probe-error',
      String((err && err.stack) || err)
    );
  }
})();
</script>"""
    return run_browser_probe(
        chromium,
        probe_document(chart, probe),
        page,
        "data-xy-colorbar-probe",
        label="colorbar chrome probe",
    )


def test_declarative_colorbar_reaches_browser_chrome(tmp_path: Path) -> None:
    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    chart = xyg.heatmap_chart(
        xyg.heatmap([[0.0, 1.0], [2.0, 3.0]], name="Intensity", colormap="purples"),
        xyg.colorbar(ticks=[0.123, 2.987]),
        width=480,
        height=300,
    )

    result = _browser_colorbar_probe(chromium, chart, tmp_path / "colorbar.html")

    assert result["exists"] is True
    assert result["title"] == "Intensity"
    assert result["tooltip"] == "Intensity: 0 \u2013 3"
    assert "linear-gradient" in result["gradient"]
    assert result["tickLabels"] == ["0.123", "2.987"]
