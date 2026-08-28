"""Support-predicate parity for the #117 public static-export Scene router.

`scene_export_support_reason` is the single seam the public exporter uses to
decide whether a figure routes through the canonical Rust Scene or the
compatibility renderers. It is intentionally narrower than `figure_scene`:
explicit Scene APIs may exercise a migrating record before the public output
contract is complete. These tests pin both compiler rejection and public
preflight so the router cannot silently select a partial consumer. The public
router reuses that compiled Scene instead of encoding a second batch.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

import xyg
from xyg._figure import Figure
from xyg._scene_v3 import (
    UnsupportedSceneV3,
    figure_scene,
    public_static_export,
    scene_export_support_reason,
)
from xyg.channels import ColorChannel
from xyg.marks import _SYMBOL_CODES

BUILTIN_SYMBOLS = tuple(_SYMBOL_CODES)


def _public_svg(figure: Figure) -> str | None:
    data = public_static_export(figure, "svg")
    return None if data is None else data.decode("utf-8")


def _public_png(figure: Figure, *, scale: float = 1.0) -> bytes | None:
    return public_static_export(figure, "png", scale=scale)


def _public_pdf(figure: Figure) -> bytes | None:
    return public_static_export(figure, "pdf")


def _supported() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.scatter([1, 2], [2, 3], color="#3987e5", size=6, opacity=0.8)
    return figure


def _public_builtin_symbols() -> Figure:
    """Every constant built-in symbol, with deterministic cross-host identity."""
    figure = Figure(width=760, height=720)
    figure.axis_options["x"]["domain"] = (-1.0, 19.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    for code, symbol in enumerate(BUILTIN_SYMBOLS):
        figure.scatter(
            [float(code)],
            [0.5],
            name=symbol,
            color="#3987e5",
            size=8,
            opacity=1.0,
            symbol=symbol,
        )
        figure.traces[-1].id = code
    return figure


def _public_triangle_mesh(count: int = 2) -> Figure:
    """Literal unjoined PolyFill rows with deterministic cross-host identity."""
    figure = Figure(width=360, height=260)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    x0 = np.resize(np.asarray([-0.25, 1.0], dtype=np.float64), count)
    y0 = np.resize(np.asarray([0.25, 0.5], dtype=np.float64), count)
    x1 = np.resize(np.asarray([0.75, 2.25], dtype=np.float64), count)
    y1 = np.resize(np.asarray([0.25, 0.5], dtype=np.float64), count)
    x2 = np.resize(np.asarray([0.25, 1.5], dtype=np.float64), count)
    y2 = np.resize(np.asarray([1.25, 1.75], dtype=np.float64), count)
    figure.triangle_mesh(
        x0,
        y0,
        x1,
        y1,
        x2,
        y2,
        name="literal mesh",
        color="#22c55e",
        opacity=0.75,
    )
    figure.traces[-1].id = 0
    return figure


_PUBLIC_HEXBIN_X = [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0]
_PUBLIC_HEXBIN_Y = [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0]
_PUBLIC_HEXBIN_C = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]


def _public_hexbin(reduce: str = "count") -> Figure:
    """Constant-style Cartesian native hexbin with deterministic identity."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    options: dict[str, object] = {
        "gridsize": (4, 4),
        "range": ((0.0, 4.0), (0.0, 5.0)),
        "color": "#3987e5",
        "opacity": 0.75,
        "name": "hex",
    }
    if reduce == "count":
        figure.hexbin(_PUBLIC_HEXBIN_X, _PUBLIC_HEXBIN_Y, **options)
    elif reduce == "mean":
        figure.hexbin(
            _PUBLIC_HEXBIN_X,
            _PUBLIC_HEXBIN_Y,
            C=_PUBLIC_HEXBIN_C,
            reduce_C_function=np.mean,
            **options,
        )
    else:
        figure.hexbin(
            _PUBLIC_HEXBIN_X,
            _PUBLIC_HEXBIN_Y,
            C=_PUBLIC_HEXBIN_C,
            reduce_C_function=np.sum,
            **options,
        )
    figure.traces[-1].id = 0
    return figure


_PUBLIC_HEATMAP_Z = [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]
_PUBLIC_HEATMAP_X = [1.0, 2.0, 3.0]
_PUBLIC_HEATMAP_Y = [1.0, 3.0]


def _public_heatmap() -> Figure:
    """Constant-style Cartesian heatmap with deterministic identity."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.heatmap(
        _PUBLIC_HEATMAP_Z,
        x=_PUBLIC_HEATMAP_X,
        y=_PUBLIC_HEATMAP_Y,
        color="#3987e5",
        opacity=0.75,
        name="heat",
    )
    figure.traces[-1].id = 0
    return figure


def _polar() -> Figure:
    figure = _supported()
    figure.coords = "polar"
    return figure


def _polar_contour() -> Figure:
    figure = Figure(width=320, height=240, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 3.0)
    figure.contour([[1.0, 2.0], [3.0, 4.0]], levels=2, color="#3987e5")
    return figure


def _polar_density() -> Figure:
    figure = Figure(width=320, height=240, coords="polar")
    figure.scatter([0.0, 1.0], [0.5, 0.8], density=True, color="#3987e5")
    return figure


def _smooth_error_band() -> Figure:
    figure = _supported().error_band([0, 1, 2], [1, 2, 1], [2, 3, 2], color="#22c55e")
    figure.traces[-1].style["curve"] = "smooth"
    return figure


def _custom_font() -> Figure:
    figure = _supported()
    figure.chrome_styles = {"title": {"font-family": "Comic Sans"}}
    return figure


def _browser_css() -> Figure:
    figure = _supported()
    figure.class_name = "rounded-xl bg-white"
    return figure


def _colorbar() -> Figure:
    figure = _supported()
    figure.colorbar_options = {"label": "z"}
    return figure


def _extra_legend() -> Figure:
    figure = _supported()
    figure.extra_legends = [{"loc": "upper left"}]
    return figure


def _authored_tick_labels() -> Figure:
    figure = _supported()
    figure.axis_options["x"]["tick_values"] = [0.0, 2.0, 4.0]
    figure.axis_options["x"]["tick_labels"] = ["zero", "two", "four"]
    return figure


def test_authored_cartesian_tick_labels_are_a_supported_scene_v23_slice() -> None:
    figure = _authored_tick_labels()
    encoded = figure_scene(figure)
    assert encoded[4:8] == (31).to_bytes(4, "little")
    assert b"XYTL" in encoded


@pytest.mark.parametrize(
    "kind,domain,constant",
    [
        ("linear", (-10_000.0, 10_000.0), None),
        ("log", (0.001, 1.0), None),
        ("symlog", (-10.0, 10.0), 2.0),
    ],
)
def test_primary_numeric_axis_format_routes_through_rust_scene(
    kind: str, domain: tuple[float, float], constant: float | None
) -> None:
    from xyg import _native

    figure = _supported()
    figure.set_axis("y", type_=kind, domain=domain, constant=constant, format="$,.0f USD")
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYTL" in scene
    svg = _native.scene_svg(scene)
    if kind == "log":
        # Fixed precision would collapse sub-unit log ticks; Rust preserves
        # the default distinguishable labels and deliberately drops affixes.
        assert ">0.001<" in svg and "$0 USD" not in svg
    else:
        assert "$" in svg and " USD" in svg


def test_authored_numeric_tick_labels_override_format_and_invalid_format_falls_back() -> None:
    from xyg import _native

    authored = _authored_tick_labels()
    authored.axis_options["x"]["format"] = "$,.1f USD"
    authored_scene = figure_scene(authored)
    assert authored_scene == figure_scene(_authored_tick_labels())
    authored_svg = _native.scene_svg(authored_scene)
    assert all(label in authored_svg for label in (">zero<", ">two<", ">four<"))
    assert "$" not in authored_svg

    invalid = _supported()
    invalid.axis_options["x"]["format"] = "not-a-format"
    assert scene_export_support_reason(invalid) is None
    invalid_scene = figure_scene(invalid)
    assert b"XYTL" not in invalid_scene
    assert ">0<" in _native.scene_svg(invalid_scene)

    boundary = _supported()
    boundary.width = 1600
    boundary.axis_options["x"]["format"] = ".100f"
    boundary_scene = figure_scene(boundary)
    assert f">0.{('0' * 100)}<" in _native.scene_svg(boundary_scene)

    oversized = _supported()
    oversized.axis_options["x"]["format"] = ".101f"
    assert figure_scene(oversized) == figure_scene(_supported())


def _labeled_annotation() -> Figure:
    figure = _supported()
    figure.annotations = [{"kind": "marker", "x": 1.0, "y": 2.0, "text": "peak"}]
    return figure


def _callout() -> Figure:
    figure = _supported()
    figure.annotations = [{"kind": "callout", "x": 1.0, "y": 2.0, "text": "here"}]
    return figure


def _public_annotation_family() -> Figure:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.scatter([0.0, 1.0], [0.0, 1.0], color="#3987e5", size=6, opacity=0.8)
    figure.traces[-1].id = 0
    figure.annotations = fixture["public_annotation_family"]
    return figure


def _dashed_line() -> Figure:
    figure = _supported().line([1, 2, 3], [1, 4, 2], color="#ef4444", width=2)
    figure.traces[-1].style["dash"] = "4,2"
    return figure


def _public_literal_geometry() -> Figure:
    """One cross-host fixture for the public line/rect Scene slice."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2)
    figure.traces[-1].id = 0
    figure.bar([0.5, 1.5], [2, 3], color="#22c55e", opacity=0.8)
    figure.traces[-1].id = 1
    return figure


def _public_violin(orientation: str = "vertical") -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (-1.0, 5.0)
    figure.axis_options["y"]["domain"] = (-1.0, 5.0)
    figure.violin(
        [[1, 2, 2, 3, 4], [2, 2.5, 3.5]],
        bins=8,
        width=0.7,
        orientation=orientation,
        color="#7c3aed",
        opacity=0.6,
        style={"fill": "#22c55e"},
    )
    figure.traces[-1].id = 0
    return figure


def _public_box(orientation: str = "vertical") -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (-2.0, 102.0)
    figure.axis_options["y"]["domain"] = (-2.0, 102.0)
    figure.box(
        [[1, 2, 3, 100], [2, 3, 4, 5]],
        orientation=orientation,
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        name="dist",
    )
    for trace_id, trace in enumerate(figure.traces):
        trace.id = trace_id
    return figure


def _public_literal_geometry_variant(kind: str) -> Figure:
    """Build one exact cross-host transform fixture on fixed domains."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    if kind == "step":
        figure.step([0, 1, 2], [1, 3, 2], where="mid")
    elif kind == "histogram":
        figure.histogram([0, 1, 1, 2], bins=2)
    elif kind == "column_bar":
        # Node's public `bar` emits the same canonical Rect as Python's
        # `column`; the exact hash below pins that intentional host alias.
        figure.column([0, 1], [1, 2])
    else:  # pragma: no cover - closed fixture vocabulary
        raise AssertionError(f"unknown literal geometry fixture {kind!r}")
    figure.traces[-1].id = 0
    return figure


def _public_step_mode(where: str) -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.step([0, 1, 2], [1, 3, 2], where=where)
    figure.traces[-1].id = 0
    return figure


def _public_ribbon(scale: str) -> Figure:
    """One bounded solid ribbon whose compact pair Rust expands for every host."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 10.0)
    if scale == "linear":
        figure.set_axis("y", type_="linear", domain=(-10.0, 1000.0))
    elif scale == "log":
        figure.set_axis("y", type_="log", domain=(1.0, 1000.0))
    elif scale == "symlog":
        figure.set_axis("y", type_="symlog", domain=(-10.0, 1000.0), constant=2.0)
    else:  # pragma: no cover - closed fixture vocabulary
        raise AssertionError(f"unknown ribbon scale {scale!r}")
    figure.ribbon(
        [1.0],
        [9.0],
        [1.0],
        [10.0],
        [100.0],
        [1000.0],
        color="#7c3aed",
        opacity=0.75,
        stroke_width=2.0,
        style={"fill-opacity": 0.8, "stroke-opacity": 0.5},
    )
    figure.traces[-1].id = 7
    return figure


def _public_disconnected_segments() -> Figure:
    """One ordered literal fixture for the public endpoint-pair slice."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.segments([0.25, 2.5], [0.5, 0.75], [1.25, 3.5], [1.5, 2.0], color="#ef4444")
    figure.errorbar([1.0, 2.0], [2.0, 3.0], yerr=[0.25, 0.5], cap_size=0.2, color="#16a34a")
    # One combined, capless call proves both admitted error-bar roles without
    # duplicating the cap geometry already exercised above.
    figure.errorbar(
        [0.75, 1.5],
        [4.25, 4.5],
        yerr=[0.15, 0.25],
        xerr=[0.1, 0.2],
        cap_size=0.0,
        color="#9333ea",
    )
    figure.stem([3.0, 3.5], [3.5, 4.0], base=1.0, color="#2563eb", symbol="diamond")
    for index, trace in enumerate(figure.traces):
        trace.id = index
    return figure


# Each factory builds a figure that `figure_scene` rejects; the substring is the
# stable diagnostic token the predicate must surface for the router to log.
UNSUPPORTED: dict[str, tuple[Callable[[], Figure], str]] = {
    "custom_font": (_custom_font, "XYG_SCENE_UNSUPPORTED_CUSTOM_FONT"),
    "browser_css": (_browser_css, "XYG_SCENE_UNSUPPORTED_BROWSER_CSS"),
    "colorbar": (_colorbar, "XYG_SCENE_UNSUPPORTED_COLORBAR"),
    "extra_legend": (_extra_legend, "XYG_SCENE_UNSUPPORTED_EXTRA_LEGEND"),
}


def test_supported_figure_has_no_reason() -> None:
    figure = _supported()
    # Compiler accepts it, so the predicate must report None (route via Scene).
    figure_scene(figure)
    assert scene_export_support_reason(figure) is None


def test_constant_dash_line_is_public_scene_supported() -> None:
    figure = _dashed_line()
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"stroke-dasharray" in exported
    assert b"XYDS" in figure_scene(figure)


def test_constant_linecap_line_is_public_scene_supported() -> None:
    figure = _supported().line([1, 2, 3], [1, 4, 2], color="#ef4444", width=2)
    figure.traces[-1].style["linecap"] = "square"
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b'stroke-linecap="square"' in exported
    assert b"XYLC" in figure_scene(figure)


def test_smooth_line_is_public_scene_supported() -> None:
    figure = _supported().line([1, 2, 3], [1, 4, 2], color="#ef4444", width=2, curve="smooth")
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    svg = exported.decode("utf-8")
    counts = [len(points.split()) for points in re.findall(r'<polyline points="([^"]+)"', svg)]
    assert max(counts) == 1 + (3 - 1) * 16
    assert figure.to_svg() == svg


def test_smooth_area_is_public_scene_supported() -> None:
    figure = _supported().area([0, 1, 2], [1, 2, 1], color="#ef4444", curve="smooth")
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    svg = exported.decode("utf-8")
    counts = []
    for path in re.findall(r'<path d="([^"]+)"', svg):
        if "Z" not in path:
            continue
        tokens = path.replace("Z", " ").replace("M", " ").replace("L", " ").split()
        counts.append(len(tokens) // 2)
    assert max(counts) == (1 + (3 - 1) * 16) * 2
    assert figure.to_svg() == svg


def test_smooth_error_band_is_public_scene_supported() -> None:
    figure = _smooth_error_band()
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    svg = exported.decode("utf-8")
    counts = []
    for path in re.findall(r'<path d="([^"]+)"', svg):
        if "Z" not in path:
            continue
        tokens = path.replace("Z", " ").replace("M", " ").replace("L", " ").split()
        counts.append(len(tokens) // 2)
    assert max(counts) == (1 + (3 - 1) * 16) * 2
    assert figure.to_svg() == svg


def test_polar_smooth_line_is_scene_supported() -> None:
    figure = Figure(width=320, height=240, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 6.283185307179586)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.line([0.0, 1.5707963267948966, 3.141592653589793], [0.5, 1.0, 0.5], curve="smooth")
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<polyline" in exported or b"<path" in exported


def test_polar_smooth_step_line_is_scene_supported() -> None:
    figure = Figure(width=320, height=240, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 6.283185307179586)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.line(
        [0.0, 1.5707963267948966, 3.141592653589793],
        [0.5, 1.0, 0.5],
        curve="smooth",
        color="#ef4444",
    )
    figure.traces[-1].style["step"] = "mid"
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<polyline" in exported
    cartesian = _supported().line([0, 1, 2], [1, 2, 1], curve="smooth")
    cartesian.traces[-1].style["step"] = "mid"
    assert scene_export_support_reason(cartesian) is None
    cartesian_exported = public_static_export(cartesian, "svg")
    assert cartesian_exported is not None
    assert b"<polyline" in cartesian_exported
    cartesian_area = _supported().area([0, 1, 2], [1, 2, 1], curve="smooth")
    cartesian_area.traces[-1].style["step"] = "mid"
    assert scene_export_support_reason(cartesian_area) is None
    cartesian_area_exported = public_static_export(cartesian_area, "svg")
    assert cartesian_area_exported is not None
    assert b"<path d=" in cartesian_area_exported
    cartesian_band = _supported().error_band([0, 1, 2], [0, 1, 0], [1, 2, 1])
    cartesian_band.traces[-1].style["curve"] = "smooth"
    cartesian_band.traces[-1].style["step"] = "mid"
    assert scene_export_support_reason(cartesian_band) is None
    cartesian_band_exported = public_static_export(cartesian_band, "svg")
    assert cartesian_band_exported is not None
    assert b"<path d=" in cartesian_band_exported


def test_marker_glyph_scatter_is_scene_supported() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.scatter([1.0], [1.0], color="#336699", size=12, _marker_glyph="A")
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b'font-family="DejaVu Sans"' in exported
    assert b'dominant-baseline="central"' in exported
    assert b">A</text>" in exported
    invalid = Figure().scatter([1.0], [1.0])
    invalid.traces[-1].style["marker_glyph"] = "AB"
    assert scene_export_support_reason(invalid) is not None


def test_polar_scatter_is_scene_supported() -> None:
    figure = _polar()
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert exported.startswith(b"<svg") or b"<svg" in exported


def test_polar_density_is_scene_supported() -> None:
    figure = _polar_density()
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<path" in exported
    assert b"<image" not in exported
    png = public_static_export(figure, "png")
    assert png is not None


def test_polar_contour_is_scene_supported() -> None:
    figure = _polar_contour()
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<polyline" in exported or b"<path" in exported
    png = public_static_export(figure, "png")
    assert png is not None


def test_polar_heatmap_is_scene_supported() -> None:
    figure = Figure(width=320, height=240, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.heatmap([[1.0, 2.0], [3.0, 4.0]])
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<path" in exported
    assert b"<rect x=" not in exported
    constant = Figure(width=320, height=240, coords="polar")
    constant.axis_options["x"]["domain"] = (0.0, 2.0)
    constant.axis_options["y"]["domain"] = (0.0, 2.0)
    constant.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#3987e5")
    assert scene_export_support_reason(constant) is None
    constant_svg = public_static_export(constant, "svg")
    assert constant_svg is not None
    assert b"<path" in constant_svg


def test_polar_bar_is_scene_supported() -> None:
    figure = Figure(width=320, height=240, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.bar([0.0, 1.0], [0.5, 0.8], color="#3987e5")
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<path" in exported
    assert b'data-xy-grid="ring"' in exported or b"circle" in exported


def test_polar_bar_wedge_gap_is_scene_supported() -> None:
    figure = Figure(width=320, height=240, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.bar([0.0, 1.0], [0.5, 0.8], color="#3987e5", wedge_gap=8.0)
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert exported.count(b'<path d="M') == 2
    cartesian = _supported().bar([0, 1], [1, 2], wedge_gap=8.0)
    assert scene_export_support_reason(cartesian) is not None


def test_polar_bar_corner_radius_is_scene_supported() -> None:
    figure = Figure(width=320, height=240, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.bar([0.0, 1.0], [0.5, 0.8], color="#3987e5", corner_radius=8.0, base=0.15)
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert exported.count(b'<path d="M') == 2
    heatmap = Figure(width=320, height=240, coords="polar")
    heatmap.axis_options["x"]["domain"] = (0.0, 4.0)
    heatmap.axis_options["y"]["domain"] = (0.0, 5.0)
    heatmap.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#3987e5")
    heatmap.traces[-1].style["corner_radius"] = 8.0
    assert scene_export_support_reason(heatmap) is None
    exported_heatmap = public_static_export(heatmap, "svg")
    assert exported_heatmap is not None
    assert exported_heatmap.count(b'<path d="M') == 4
    cartesian = Figure(width=320, height=240)
    cartesian.axis_options["x"]["domain"] = (0.0, 4.0)
    cartesian.axis_options["y"]["domain"] = (0.0, 5.0)
    cartesian.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#3987e5")
    cartesian.traces[-1].style["corner_radius"] = 6.0
    assert scene_export_support_reason(cartesian) is None
    exported_cartesian = public_static_export(cartesian, "svg")
    assert exported_cartesian is not None
    assert exported_cartesian.count(b'<path d="M') == 4


def test_violin_box_corner_radius_is_scene_supported() -> None:
    violin = _public_violin()
    violin.traces[-1].style["corner_radius"] = 6.0
    assert scene_export_support_reason(violin) is None
    exported_violin = public_static_export(violin, "svg")
    assert exported_violin is not None
    assert b'<path d="M' in exported_violin
    square_violin = public_static_export(_public_violin(), "svg")
    assert square_violin is not None
    assert exported_violin != square_violin
    rounded_box = _public_box()
    next(trace for trace in rounded_box.traces if trace.kind == "box").style["corner_radius"] = 6.0
    assert scene_export_support_reason(rounded_box) is None
    exported_box = public_static_export(rounded_box, "svg")
    assert exported_box is not None
    assert b'<path d="M' in exported_box
    square_box = public_static_export(_public_box(), "svg")
    assert square_box is not None
    assert exported_box != square_box


def test_bounded_primary_cartesian_annotation_family_is_a_supported_public_scene_slice() -> None:
    figure = _callout()
    assert scene_export_support_reason(figure) is None
    assert b"here" in figure_scene(figure)
    figure.annotations.append({"kind": "callout", "x": 2.0, "y": 3.0, "text": "there", "dx": -24.0})
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert b"here" in scene and b"there" in scene


def test_proven_ordinary_and_wrapped_callout_fixture_is_a_supported_public_slice() -> None:
    """The v25 public evidence fixture must not fall back before Rust sees XYAW."""
    from scripts.generate_authored_scene_benchmark import authored_scene_figure

    figure = authored_scene_figure(100)
    assert scene_export_support_reason(figure) is None
    assert b"XYLB" in figure_scene(figure)


def test_primary_annotation_family_routes_all_public_static_exports_and_matches_scene_bytes() -> (
    None
):
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_annotation_family()
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["public_annotation_family_sha256"]
    svg = _native.scene_svg(scene)
    for text in ("plain", "rule", "band", "marker", "callout", "wrapped", "text"):
        assert text in svg
    assert figure.to_svg().encode() == svg.encode()
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)


def test_literal_geometry_routes_all_public_static_exports_and_matches_scene_bytes() -> None:
    """Lines and Rects consume one Rust-owned public Scene."""
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_literal_geometry()
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["public_literal_geometry_sha256"]
    svg = _native.scene_svg(scene)
    assert "<polyline " in svg
    assert "<rect " in svg
    assert figure.to_svg().encode() == svg.encode()
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_public_violin_is_rust_owned_and_routes_every_static_consumer(orientation: str) -> None:
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_violin(orientation)
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["public_violin_sha256"][orientation]
    svg = _native.scene_svg(scene)
    assert svg.count("<rect ") >= 8
    assert figure.to_svg().encode() == svg.encode()
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), 320, 240
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)
    assert _native.scene_browser_painter(scene).startswith(b"XYPB")


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_public_box_is_rust_owned_and_routes_every_static_consumer(orientation: str) -> None:
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_box(orientation)
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["public_box_sha256"][orientation]
    svg = _native.scene_svg(scene)
    assert "<rect " in svg and "<polyline " in svg
    assert figure.to_svg().encode() == svg.encode()
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), 320, 240
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)
    assert _native.scene_browser_painter(scene).startswith(b"XYPB")


@pytest.mark.parametrize("key", ["fill_opacity", "stroke_opacity"])
def test_public_violin_opacity_channels_are_scene_supported(key: str) -> None:
    figure = _public_violin()
    if key == "stroke_opacity":
        figure.traces[0].style["stroke"] = "#111111"
        figure.traces[0].style["stroke_width"] = 2.0
    figure.traces[0].style[key] = 0.5
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    baseline = _public_violin()
    if key == "stroke_opacity":
        baseline.traces[0].style["stroke"] = "#111111"
        baseline.traces[0].style["stroke_width"] = 2.0
    assert exported != public_static_export(baseline, "svg")
    rounded_box = _public_box()
    next(trace for trace in rounded_box.traces if trace.kind == "box").style[key] = 0.5
    if key == "stroke_opacity":
        next(trace for trace in rounded_box.traces if trace.kind == "box").style["stroke"] = (
            "#111111"
        )
    assert scene_export_support_reason(rounded_box) is None
    exported_box = public_static_export(rounded_box, "svg")
    assert exported_box is not None
    square_box = _public_box()
    if key == "stroke_opacity":
        next(trace for trace in square_box.traces if trace.kind == "box").style["stroke"] = (
            "#111111"
        )
    assert exported_box != public_static_export(square_box, "svg")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _supported().bar([0, 1], [1, 2], color="#22c55e"),
        lambda: _supported().column([0, 1], [1, 2], color="#22c55e"),
        lambda: _supported().histogram([0, 1, 1, 2], bins=2, color="#22c55e"),
    ],
)
def test_public_bar_column_histogram_opacity_channels_are_scene_supported(factory) -> None:
    figure = factory()
    figure.traces[-1].style["fill_opacity"] = 0.5
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert exported != public_static_export(factory(), "svg")
    stroked = factory()
    stroked.traces[-1].style["stroke"] = "#111111"
    stroked.traces[-1].style["stroke_width"] = 2.0
    stroked.traces[-1].style["stroke_opacity"] = 0.5
    assert scene_export_support_reason(stroked) is None
    assert public_static_export(stroked, "svg") is not None


def test_public_scatter_opacity_channels_are_scene_supported() -> None:
    figure = _supported()
    figure.traces[-1].style["fill_opacity"] = 0.5
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert exported != public_static_export(_supported(), "svg")
    stroked = _supported()
    stroked.traces[-1].style["stroke"] = "#111111"
    stroked.traces[-1].style["stroke_width"] = 2.0
    stroked.traces[-1].style["stroke_opacity"] = 0.5
    assert scene_export_support_reason(stroked) is None
    assert public_static_export(stroked, "svg") is not None


@pytest.mark.parametrize("kind", ["step", "histogram", "column_bar"])
def test_literal_geometry_cross_host_variants_match_exact_scene_bytes(kind: str) -> None:
    """Host transforms must converge before Rust consumes the Scene."""
    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_literal_geometry_variant(kind)
    assert scene_export_support_reason(figure) is None
    assert (
        hashlib.sha256(figure_scene(figure)).hexdigest()
        == fixture["public_literal_geometry_variants_sha256"][kind]
    )


@pytest.mark.parametrize("where", ["pre", "mid", "post"])
def test_rust_step_modes_match_exact_cross_host_bytes_and_every_static_consumer(
    where: str,
) -> None:
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_step_mode(where)
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["rust_step_modes_sha256"][where]
    svg = _native.scene_svg(scene)
    assert svg.count("<polyline ") == 1
    assert figure.to_svg().encode() == svg.encode()
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)
    painter = _native.scene_browser_painter(scene)
    assert painter.startswith(b"XYPB") and len(painter) > 300


@pytest.mark.parametrize("scale", ["linear", "log", "symlog"])
def test_rust_ribbon_expansion_matches_exact_cross_host_bytes(scale: str) -> None:
    from xyg import _native

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_ribbon(scale)
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["rust_ribbon_expansion_sha256"][scale]
    assert int.from_bytes(scene[16:24], "little") == 97
    assert scene[160:168] == bytes((124, 58, 237, 153, 124, 58, 237, 96))
    svg = _native.scene_svg(scene)
    assert svg.count('<path d="') == 1
    assert 'fill="rgb(124,58,237)" fill-opacity="0.6"' in svg
    assert 'stroke="rgb(124,58,237)" stroke-opacity="0.38"' in svg
    assert 'stroke-width="2"' in svg
    assert _native.scene_raster_commands(scene)
    painter = _native.scene_browser_painter(scene)
    assert painter.startswith(b"XYPB") and len(painter) > 300


def test_public_solid_ribbon_routes_svg_png_pdf_through_the_exact_scene() -> None:
    from xyg import _native, _pdf, kernels

    figure = _public_ribbon("linear")
    scene = figure_scene(figure)
    svg = _native.scene_svg(scene)
    assert figure.to_svg() == svg
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)


def test_all_builtin_symbols_match_exact_cross_host_scene_and_public_consumers() -> None:
    """The full fixed marker vocabulary leaves no Python static-policy fork."""
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_builtin_symbols()
    assert tuple(_SYMBOL_CODES.values()) == tuple(range(19))
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["public_builtin_symbols_sha256"]
    svg = _native.scene_svg(scene)
    assert svg.count('role="listitem"') == 19
    assert all(f">{symbol}</text>" in svg for symbol in BUILTIN_SYMBOLS)
    assert svg.count('fill="none" stroke="rgb(57,135,229)" stroke-width="1"') >= 8
    assert figure.to_svg() == svg
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)

    painter = _native.scene_browser_painter(scene)
    assert int.from_bytes(painter[20:24], "little") == 19
    header_bytes = int.from_bytes(painter[12:16], "little")
    descriptor_bytes = int.from_bytes(painter[16:20], "little")
    for code in range(19):
        descriptor = header_bytes + code * descriptor_bytes
        assert painter[descriptor] == 0
        assert painter[descriptor + 1] == code
        stroke_width = np.frombuffer(painter[descriptor + 40 : descriptor + 44], dtype="<f4")[0]
        assert stroke_width == (1.0 if code >= 15 else 0.0)
    assert b"XYLG" in painter


def test_public_triangle_mesh_matches_exact_cross_host_scene_and_consumers() -> None:
    """Two clipped literal triangles keep one canonical run per face."""
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_triangle_mesh()
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["public_triangle_mesh_sha256"]

    svg = _native.scene_svg(scene)
    assert svg.count('<path d="M ') == 2
    assert '<g clip-path="url(#xy-scene-plot)">' in svg
    assert svg.count('role="listitem"') == 1
    assert ">literal mesh</text>" in svg
    assert figure.to_svg() == svg
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)

    painter = _native.scene_browser_painter(scene)
    header_bytes = int.from_bytes(painter[12:16], "little")
    descriptor_bytes = int.from_bytes(painter[16:20], "little")
    assert int.from_bytes(painter[20:24], "little") == 2
    plot_left = np.frombuffer(painter[32:36], dtype="<f4")[0]
    for group in range(2):
        descriptor = header_bytes + group * descriptor_bytes
        assert painter[descriptor] == 4
        assert int.from_bytes(painter[descriptor + 4 : descriptor + 8], "little") == 3
        if group == 0:
            x_offset = int.from_bytes(painter[descriptor + 8 : descriptor + 12], "little")
            assert np.frombuffer(painter[x_offset : x_offset + 4], dtype="<f4")[0] < plot_left
    assert b"XYLG" in painter


def test_public_triangle_mesh_honors_the_browser_group_boundary() -> None:
    from xyg import _native

    boundary = _public_triangle_mesh(1024)
    assert scene_export_support_reason(boundary) is None
    painter = _native.scene_browser_painter(figure_scene(boundary))
    assert int.from_bytes(painter[20:24], "little") == 1024
    assert (
        scene_export_support_reason(_public_triangle_mesh(1025))
        == "XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH"
    )

    aggregate = _public_triangle_mesh(513)
    trace = aggregate.traces[0]
    aggregate.triangle_mesh(
        trace.x0.values,
        trace.y0.values,
        trace.x1.values,
        trace.y1.values,
        trace.x.values,
        trace.y.values,
        color="#22c55e",
    )
    assert scene_export_support_reason(aggregate) == "XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH"

    mixed = _public_triangle_mesh(1024)
    mixed.scatter([1.0], [1.0], color="#3987e5")
    assert scene_export_support_reason(mixed) == "XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH"


def test_public_triangle_mesh_keeps_custom_role_on_compatibility() -> None:
    figure = _public_triangle_mesh()
    figure.traces[0].style["role"] = "custom-mesh"
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE"


def test_public_triangle_mesh_joined_fill_is_scene_supported() -> None:
    disconnected = _public_triangle_mesh()
    disconnected.traces[0].style["joined_fill"] = True
    assert scene_export_support_reason(disconnected) is None
    exported = public_static_export(disconnected, "svg")
    assert exported is not None
    assert exported.count(b'<path d="M') == 2
    figure = Figure(width=360, height=260)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.triangle_mesh(
        [0.0, 1.0],
        [0.0, 0.0],
        [1.0, 1.0],
        [0.0, 1.0],
        [0.0, 0.0],
        [1.0, 1.0],
        color="#22c55e",
    )
    figure.traces[0].style["joined_fill"] = True
    assert scene_export_support_reason(figure) is None
    joined = public_static_export(figure, "svg")
    assert joined is not None
    assert joined.count(b'<path d="M') == 1
    unjoined = Figure(width=360, height=260)
    unjoined.axis_options["x"]["domain"] = (0.0, 1.0)
    unjoined.axis_options["y"]["domain"] = (0.0, 1.0)
    unjoined.triangle_mesh(
        [0.0, 1.0],
        [0.0, 0.0],
        [1.0, 1.0],
        [0.0, 1.0],
        [0.0, 0.0],
        [1.0, 1.0],
        color="#22c55e",
    )
    assert public_static_export(unjoined, "svg") != joined


def test_public_triangle_mesh_opacity_and_stroke_are_scene_supported() -> None:
    figure = _public_triangle_mesh()
    figure.traces[0].style["fill_opacity"] = 0.5
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert exported != public_static_export(_public_triangle_mesh(), "svg")
    stroked = _public_triangle_mesh()
    stroked.traces[0].style["stroke"] = "#111111"
    stroked.traces[0].style["stroke_width"] = 2.0
    stroked.traces[0].style["stroke_opacity"] = 0.5
    assert scene_export_support_reason(stroked) is None
    assert public_static_export(stroked, "svg") is not None


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Figure(width=360, height=260).triangle_mesh(
            [0, 1], [0, 0], [0.5, 1.5], [1, 1], [1, 2], [0, 0], color=[0.0, 1.0]
        ),
        lambda: Figure(width=360, height=260).triangle_mesh(
            [0, 1],
            [0, 0],
            [0.5, 1.5],
            [1, 1],
            [1, 2],
            [0, 0],
            color=np.asarray([[1, 0, 0, 1], [0, 1, 0, 1]], dtype=np.float64),
        ),
        lambda: Figure(width=360, height=260).triangle_mesh(
            [0, 1], [0, 0], [0.5, 1.5], [1, 1], [1, 2], [0, 0], opacity=[0.5, 1.0]
        ),
        lambda: Figure(width=360, height=260).triangle_mesh(
            [0, 1],
            [0, 0],
            [0.5, 1.5],
            [1, 1],
            [1, 2],
            [0, 0],
            stroke=["#ff0000", "#00ff00"],
        ),
        lambda: Figure(width=360, height=260).triangle_mesh(
            [0, 1],
            [0, 0],
            [0.5, 1.5],
            [1, 1],
            [1, 2],
            [0, 0],
            stroke_width=[1.0, 2.0],
        ),
    ],
)
def test_public_triangle_mesh_keeps_per_item_paint_on_compatibility(factory) -> None:
    figure = factory()
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    assert scene_export_support_reason(figure) is not None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda figure: setattr(figure, "coords", "polar"),
        lambda figure: setattr(figure.traces[0], "x_axis", "x2"),
        lambda figure: figure.axis_options["x"].__setitem__("domain", None),
        lambda figure: figure.axis_options["y"].__setitem__("domain", None),
        lambda figure: setattr(figure.traces[0], "hidden", True),
        lambda figure: figure.traces[0].x0.values.__setitem__(0, np.nan),
        lambda figure: setattr(figure.traces[0].x0, "values", np.asarray([0.0])),
    ],
)
def test_public_triangle_mesh_keeps_nonliteral_geometry_fail_closed(
    mutate: Callable[[Figure], None],
) -> None:
    figure = _public_triangle_mesh()
    mutate(figure)
    assert scene_export_support_reason(figure) is not None


@pytest.mark.parametrize("reduce", ["count", "mean", "sum"])
def test_public_hexbin_matches_exact_cross_host_scene_and_consumers(reduce: str) -> None:
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_hexbin(reduce)
    assert figure.traces[0].style["reduce"] == reduce
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    # Mean and sum share Scene bytes: constant paint ignores the metric, and
    # both reducers occupy the same native lattice for this fixture.
    assert hashlib.sha256(scene).hexdigest() == fixture["public_hexbin_sha256"][reduce]

    svg = _native.scene_svg(scene)
    assert svg.count('<path d="M ') == len(figure.traces[0].x.values)
    assert '<g clip-path="url(#xy-scene-plot)">' in svg
    assert ">hex</text>" in svg
    assert _public_svg(figure) == svg
    assert figure.to_svg() == svg
    png = _public_png(figure, scale=1)
    assert png == figure.to_png(scale=1)
    assert png == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    pdf = _public_pdf(figure)
    assert pdf == figure.to_image(format="pdf")
    assert pdf == _pdf.svg_to_pdf(svg)

    painter = _native.scene_browser_painter(scene)
    header_bytes = int.from_bytes(painter[12:16], "little")
    descriptor_bytes = int.from_bytes(painter[16:20], "little")
    groups = int.from_bytes(painter[20:24], "little")
    assert groups == len(figure.traces[0].x.values)
    for group in range(groups):
        descriptor = header_bytes + group * descriptor_bytes
        assert painter[descriptor] == 4
        assert int.from_bytes(painter[descriptor + 4 : descriptor + 8], "little") == 6
    assert b"XYLG" in painter


def test_public_hexbin_honors_the_painter_group_boundary() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.hexbin(
        [0.1, 0.9],
        [0.1, 0.9],
        gridsize=(23, 23),
        range=((0.0, 1.0), (0.0, 1.0)),
        color="#3987e5",
    )
    assert len(figure.traces[0].x.values) > 1024
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"
    assert figure.to_svg()


def test_colormap_hexbin_is_scene_supported() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.hexbin(
        _PUBLIC_HEXBIN_X, _PUBLIC_HEXBIN_Y, gridsize=(4, 4), range=((0.0, 4.0), (0.0, 5.0))
    )
    assert figure.traces[0].color_ch.mode == "continuous"
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    svg = exported.decode()
    assert svg.count('<path d="M ') == len(figure.traces[0].x.values)
    fills = {part.split('fill="', 1)[1].split('"', 1)[0] for part in svg.split("<path ")[1:]}
    assert len(fills) > 1
    assert figure.to_svg() == svg
    png = public_static_export(figure, "png")
    assert png is not None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda figure: setattr(figure, "coords", "polar"),
        lambda figure: setattr(figure.traces[0], "x_axis", "x2"),
        lambda figure: figure.traces[0].style.__setitem__("reduce", "custom"),
        lambda figure: figure.traces[0].x.values.__setitem__(0, np.nan),
    ],
)
def test_public_hexbin_compiler_rejects_polar_custom_and_nonfinite(
    mutate: Callable[[Figure], None],
) -> None:
    figure = _public_hexbin()
    mutate(figure)
    assert scene_export_support_reason(figure) is not None
    assert _public_svg(figure) is None
    assert _public_png(figure) is None
    assert _public_pdf(figure) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda figure: figure.axis_options["x"].__setitem__("domain", None),
        lambda figure: figure.traces[0].style.__setitem__("role", "hex-density"),
    ],
)
def test_public_hexbin_predicate_keeps_rich_style_on_compatibility(
    mutate: Callable[[Figure], None],
) -> None:
    figure = _public_hexbin()
    mutate(figure)
    assert scene_export_support_reason(figure) is not None
    assert figure.to_svg()


def test_public_hexbin_fill_opacity_is_scene_supported() -> None:
    figure = _public_hexbin()
    figure.traces[0].style["fill_opacity"] = 0.5
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert exported != public_static_export(_public_hexbin(), "svg")


def test_public_heatmap_matches_exact_cross_host_scene_and_consumers() -> None:
    from xyg import _native, _pdf, kernels

    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    figure = _public_heatmap()
    assert figure.traces[0].style.get("colormap") is None
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert hashlib.sha256(scene).hexdigest() == fixture["public_heatmap_sha256"]

    svg = _native.scene_svg(scene)
    rows, cols = figure.traces[0].grid_shape or (0, 0)
    clip_start = svg.find('<g clip-path="url(#xy-scene-plot)">')
    clip_end = svg.find("</g>", clip_start)
    assert svg[clip_start:clip_end].count("<rect ") == rows * cols
    assert '<g clip-path="url(#xy-scene-plot)">' in svg
    assert ">heat</text>" in svg
    assert _public_svg(figure) == svg
    assert figure.to_svg() == svg
    png = _public_png(figure, scale=1)
    assert png == figure.to_png(scale=1)
    assert png == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    pdf = _public_pdf(figure)
    assert pdf == figure.to_image(format="pdf")
    assert pdf == _pdf.svg_to_pdf(svg)

    painter = _native.scene_browser_painter(scene)
    header_bytes = int.from_bytes(painter[12:16], "little")
    groups = int.from_bytes(painter[20:24], "little")
    assert groups == 1
    assert painter[header_bytes] == 2
    assert int.from_bytes(painter[header_bytes + 4 : header_bytes + 8], "little") == rows * cols
    assert b"XYLG" in painter


def test_public_heatmap_honors_the_rect_budget() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.heatmap(np.zeros((101, 100)), color="#3987e5")
    assert figure.traces[0].count == 10_100
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"
    assert figure.to_svg()


def test_colormap_heatmap_is_scene_supported() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.heatmap(_PUBLIC_HEATMAP_Z, x=_PUBLIC_HEATMAP_X, y=_PUBLIC_HEATMAP_Y)
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<rect" in exported
    png = public_static_export(figure, "png")
    assert png is not None


def test_truecolor_heatmap_is_scene_supported() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.heatmap(
        [
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[0.0, 0.0, 1.0], [1.0, 1.0, 0.0]],
        ]
    )
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<rect" in exported
    png = public_static_export(figure, "png")
    assert png is not None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda figure: setattr(figure.traces[0], "x_axis", "x2"),
        lambda figure: figure.traces[0].grid.values.__setitem__(0, np.nan),
    ],
)
def test_public_heatmap_compiler_rejects_secondary_axis_and_nonfinite(
    mutate: Callable[[Figure], None],
) -> None:
    figure = _public_heatmap()
    mutate(figure)
    assert scene_export_support_reason(figure) is not None
    assert _public_svg(figure) is None
    assert _public_png(figure) is None
    assert _public_pdf(figure) is None


def test_public_heatmap_fill_opacity_is_scene_supported() -> None:
    figure = _public_heatmap()
    figure.traces[0].style["fill_opacity"] = 0.5
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert exported != public_static_export(_public_heatmap(), "svg")
    colormap = Figure(width=320, height=240)
    colormap.axis_options["x"]["domain"] = (0.0, 4.0)
    colormap.axis_options["y"]["domain"] = (0.0, 5.0)
    colormap.heatmap(_PUBLIC_HEATMAP_Z, x=_PUBLIC_HEATMAP_X, y=_PUBLIC_HEATMAP_Y)
    colormap.traces[0].style["fill_opacity"] = 0.5
    assert scene_export_support_reason(colormap) is None
    assert public_static_export(colormap, "svg") is not None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda figure: figure.traces[0].style.__setitem__("role", "heat-density"),
    ],
)
def test_public_heatmap_predicate_keeps_rich_style_on_compatibility(
    mutate: Callable[[Figure], None],
) -> None:
    figure = _public_heatmap()
    mutate(figure)
    assert scene_export_support_reason(figure) is not None
    assert figure.to_svg()


def test_public_heatmap_autoranges_without_authored_axis_domain() -> None:
    figure = Figure(width=320, height=240)
    figure.heatmap(_PUBLIC_HEATMAP_Z, x=_PUBLIC_HEATMAP_X, y=_PUBLIC_HEATMAP_Y, color="#3987e5")
    assert figure.axis_options["x"].get("domain") is None
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<rect" in exported
    assert b"data:image/png;base64," not in exported


def test_public_contour_autoranges_without_authored_axis_domain() -> None:
    figure = Figure(width=320, height=240)
    figure.contour([[1.0, 2.0], [3.0, 4.0]], levels=2, color="#3987e5")
    assert figure.axis_options["x"].get("domain") is None
    assert scene_export_support_reason(figure) is None
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"data:image/png;base64," not in exported


def test_custom_hexbin_reducer_stays_on_compatibility() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.hexbin(
        _PUBLIC_HEXBIN_X,
        _PUBLIC_HEXBIN_Y,
        C=_PUBLIC_HEXBIN_C,
        reduce_C_function=np.median,
        color="#3987e5",
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
    )
    assert figure.traces[0].style["reduce"] == "custom"
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE"
    assert figure.to_svg()


@pytest.mark.parametrize(
    "stroke",
    ["transparent", "#ff0000"],
)
def test_authored_constant_scatter_stroke_uses_public_scene(stroke: str) -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.scatter([1.0], [1.0], symbol="plus_line", color="#3987e5", stroke=stroke)
    assert figure.traces[-1].style["stroke_width"] == 1.0
    assert scene_export_support_reason(figure) is None


def test_width_only_scatter_stroke_uses_public_scene() -> None:
    from xyg import _native

    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.scatter([1.0], [1.0], symbol="plus_line", color="#3987e5", stroke_width=2.0)
    assert scene_export_support_reason(figure) is None
    svg = _native.scene_svg(figure.to_scene())
    assert 'stroke-width="2"' in svg
    assert figure.to_svg() == svg


@pytest.mark.parametrize("symbol", BUILTIN_SYMBOLS)
def test_generated_stem_markers_route_every_builtin_symbol(symbol: str) -> None:
    from xyg import _native

    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.stem([1.0], [1.5], base=0.25, symbol=symbol)
    assert figure.traces[-1].style.get("role") == "stem-marker"
    assert scene_export_support_reason(figure) is None
    assert figure.to_svg() == _native.scene_svg(figure_scene(figure))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda figure: figure.traces[0].style.__setitem__("marker_path", {"contours": []}),
        lambda figure: figure.scatter([2.5, 3.5], [2.5, 3.5], symbol=["circle", "square"]),
        lambda figure: figure.scatter([2.5, 3.5], [2.5, 3.5], color=[0.0, 1.0]),
        lambda figure: (
            setattr(figure, "coords", "polar"),
            figure.stem([1.0], [1.5], base=0.25),
        ),
        lambda figure: figure.scatter(range(10_001), range(10_001)),
    ],
)
def test_builtin_symbol_cutover_keeps_nonliteral_scatter_fail_closed(
    mutate: Callable[[Figure], None],
) -> None:
    figure = _supported()
    mutate(figure)
    assert scene_export_support_reason(figure) is not None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda figure: setattr(
            figure.traces[0],
            "color2_ch",
            ColorChannel(mode="direct_rgba", rgba=np.array([[0.2, 0.8, 0.5, 1.0]])),
        ),
        lambda figure: figure.traces[0].style.__setitem__("role", "custom-ribbon"),
        lambda figure: setattr(figure, "coords", "polar"),
    ],
)
def test_public_ribbon_route_fails_closed_for_unmodeled_behavior(
    mutate: Callable[[Figure], None],
) -> None:
    figure = _public_ribbon("linear")
    mutate(figure)
    assert scene_export_support_reason(figure) is not None


def test_public_ribbon_constant_color2_routes_through_scene() -> None:
    from xyg import _native

    figure = _public_ribbon("linear")
    figure.traces[0].color2_ch = ColorChannel(mode="constant", constant="#34d399")
    assert scene_export_support_reason(figure) is None
    svg = _native.scene_svg(figure_scene(figure))
    assert "<linearGradient" in svg
    assert figure.to_svg() == svg
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert b"<linearGradient" in exported


def test_public_ribbon_route_enforces_the_authored_band_ceiling() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    values = np.zeros(10_001)
    figure.ribbon(values, values + 1, values, values + 0.1, values + 0.2, values + 0.3)
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"


def test_migrated_scene_packers_have_no_host_step_geometry_expander() -> None:
    root = Path(__file__).parents[1]
    python_packer = (root / "python/xyg/_scene_v3.py").read_text()
    node_packer = (root / "packages/xy-node/src/scene.js").read_text()
    assert "def _step_arrays" not in python_packer
    assert "function stepArrays" not in node_packer
    assert "return _native.scene_encode_product(" in python_packer
    assert "return encodeProduct(" in node_packer
    assert "figure_support=_pack_figure_support(" in python_packer
    assert "packFigureSupport(figure, { colorbarUnsupported })" in node_packer
    assert "reason = _native.scene_figure_support_reason(" not in python_packer
    assert (
        "const reason = sceneFigureSupportReason(figure, { colorbarUnsupported });"
        not in node_packer
    )
    assert "reason, scene = _public_scene_or_reason(" in python_packer
    assert "viewport=(w, h)" not in python_packer
    assert "xAxis: xSceneAxis" not in node_packer
    assert "sidecars = _unpack_xysd(" not in python_packer
    assert "sidecars = unpackXySd(" not in node_packer
    assert "_ribbon_band_samples" not in python_packer
    assert "ribbon_edge" not in python_packer
    assert "function ribbonEdge" not in node_packer
    assert "RIBBON_STEPS" not in node_packer


@pytest.mark.parametrize(
    "annotation",
    [
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "collision", "collision": "hide"},
        {"kind": "callout", "x": 0.5, "y": 0.5, "text": "rich", "html": "<b>rich</b>"},
        {"kind": "callout", "x": 0.5, "y": 0.5, "text": "css", "class_name": "custom"},
    ],
)
def test_public_annotation_router_fails_closed_for_unmodeled_host_layout_and_css(
    annotation: dict[str, object],
) -> None:
    figure = _supported()
    figure.annotations = [annotation]
    reason = scene_export_support_reason(figure) or ""
    assert "UNSUPPORTED" in reason


@pytest.mark.parametrize(
    "annotation",
    [
        {"kind": "text", "x": 0.5, "y": 0.5, "text": "offset", "dx": 6},
        {"kind": "text", "x": 0.5, "y": 0.5, "text": "anchor", "anchor": "end"},
        {"kind": "text", "x": 0.5, "y": 0.5, "text": "rotated", "rotation": 30},
    ],
)
def test_public_unwrapped_text_layout_routes_through_scene(annotation: dict[str, object]) -> None:
    from xyg import _native

    figure = _supported()
    figure.annotations = [annotation]
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert str(annotation["text"]).encode() in scene
    svg = _native.scene_svg(scene)
    assert figure.to_svg() == svg
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert str(annotation["text"]).encode() in exported
    if "rotation" in annotation:
        assert f'transform="rotate(-{annotation["rotation"]} ' in svg
        assert f'transform="rotate(-{annotation["rotation"]} '.encode() in exported


@pytest.mark.parametrize(
    "annotation",
    [
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "offset", "dy": -8},
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "anchor", "anchor": "end"},
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "rotated", "rotation": 30},
    ],
)
def test_public_labelled_marker_layout_routes_through_scene(
    annotation: dict[str, object],
) -> None:
    from xyg import _native

    figure = _supported()
    figure.annotations = [annotation]
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert str(annotation["text"]).encode() in scene
    svg = _native.scene_svg(scene)
    assert figure.to_svg() == svg
    exported = public_static_export(figure, "svg")
    assert exported is not None
    assert str(annotation["text"]).encode() in exported
    if "rotation" in annotation:
        assert f'transform="rotate(-{annotation["rotation"]} ' in svg
        assert f'transform="rotate(-{annotation["rotation"]} '.encode() in exported


@pytest.mark.parametrize("name", sorted(UNSUPPORTED))
def test_unsupported_feature_reported(name: str) -> None:
    factory, token = UNSUPPORTED[name]
    reason = scene_export_support_reason(factory())
    assert reason is not None
    # The public router may reject an otherwise Scene-serializable feature
    # earlier, when the compatibility renderer carries output semantics the
    # Scene consumers have not modeled yet.
    assert token in reason or "XYG_SCENE_UNSUPPORTED_PUBLIC_" in reason


@pytest.mark.parametrize("name", sorted(UNSUPPORTED))
def test_predicate_never_claims_public_support_when_the_compiler_rejects(name: str) -> None:
    factory, _token = UNSUPPORTED[name]
    predicate_reason = scene_export_support_reason(factory())
    with pytest.raises(UnsupportedSceneV3) as excinfo:
        figure_scene(factory())
    assert predicate_reason is not None
    assert str(excinfo.value)


def test_scene_static_css_and_custom_font_are_fail_closed_product_contract() -> None:
    """#288: custom fonts / chart CSS / classes stay compatibility with stable diagnostics.

    Default-font Scene figures must not need `_svg.to_svg` / `_raster`. Scene
    static measure and paint are DejaVu Sans; live browser widgets still apply
    CSS outside this encoder.
    """
    from xyg import _native, _svg

    default = _supported()
    assert scene_export_support_reason(default) is None
    scene = figure_scene(default)
    svg = default.to_svg()
    assert svg == _native.scene_svg(scene)
    assert public_static_export(default, "svg") == svg.encode()
    png = public_static_export(default, "png")
    assert png is not None
    assert png.startswith(b"\x89PNG")
    assert png == default.to_png(scale=1)

    font = _custom_font()
    reason = scene_export_support_reason(font) or ""
    assert (
        "XYG_SCENE_UNSUPPORTED_CUSTOM_FONT" in reason
        or "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE" in reason
    )
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_CUSTOM_FONT"):
        figure_scene(font)
    assert public_static_export(font, "svg") is None
    assert public_static_export(font, "png") is None
    assert font.to_svg() == _svg.to_svg(font)

    css = _browser_css()
    reason = scene_export_support_reason(css) or ""
    assert "XYG_SCENE_UNSUPPORTED_BROWSER_CSS" in reason
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_BROWSER_CSS"):
        figure_scene(css)
    assert public_static_export(css, "svg") is None
    assert public_static_export(css, "png") is None
    assert css.to_svg().startswith("<svg")


def test_input_errors_are_not_support_decisions() -> None:
    figure = _supported()
    figure.traces[0].style["opacity"] = float("nan")
    # A bad opacity is invalid input, not an unsupported feature: it must raise
    # rather than be reported as a routing reason.
    with pytest.raises(ValueError):
        scene_export_support_reason(figure)


def test_too_small_valid_export_viewport_is_a_documented_routing_exception() -> None:
    figure = _supported()
    assert scene_export_support_reason(figure, width=64, height=32) == (
        "XYG_SCENE_UNSUPPORTED_VIEWPORT"
    )


@pytest.mark.parametrize(
    "factory,reason",
    [
        (lambda: _supported().line([0, 1], [0, 1]), None),
        (lambda: _supported().line([0, 1, 2], [1, 2, 1], curve="smooth"), None),
        (lambda: _supported().area([0, 1, 2], [1, 2, 1], curve="smooth"), None),
        (_smooth_error_band, None),
        (lambda: _supported().bar([0, 1], [1, 2]), None),
        (lambda: _supported().column([0, 1], [1, 2]), None),
        (lambda: _supported().column([0, 1], [1, 2], corner_radius=2), None),
        (lambda: _supported().histogram([0, 1, 1, 2], bins=2), None),
        (lambda: _supported().area([0, 1], [1, 2]), None),
        (lambda: _supported().error_band([0, 1], [0, 1], [1, 2]), None),
        (lambda: _supported().scatter([0, 1], [1, 2], symbol="square"), None),
        (lambda: _supported().scatter([0, 1], [1, 2], symbol="diamond"), None),
        (lambda: _supported(), None),
    ],
)
def test_public_router_selects_only_the_proven_literal_cartesian_geometry_subset(
    factory, reason: str | None
) -> None:
    assert scene_export_support_reason(factory()) == (
        None if reason is None else f"XYG_SCENE_UNSUPPORTED_{reason}"
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _supported().scatter(range(10_001), range(10_001)),
    ],
)
def test_public_literal_geometry_boundary_fails_closed_for_unmodeled_behavior(factory) -> None:
    """A successful internal record must not silently widen static routing."""
    reason = scene_export_support_reason(factory()) or ""
    assert reason


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _supported().bar(
            [0, 1], [1, 2], fill="linear-gradient(to bottom, #000000, #ffffff)"
        ),
        lambda: _supported().area(
            [0, 1], [1, 2], fill="linear-gradient(to bottom, #000000, #ffffff)"
        ),
    ],
)
def test_public_literal_linear_gradient_fills_route_through_scene(factory) -> None:
    figure = factory()
    assert scene_export_support_reason(figure) is None
    svg = figure.to_svg()
    assert "<linearGradient" in svg
    assert 'fill="url(#xy-scene-g' in svg


@pytest.mark.parametrize(
    "kind,count", [("area", 0), ("area", 1), ("error_band", 0), ("error_band", 1)]
)
def test_public_band_with_fewer_than_two_samples_retains_compatibility_export(
    kind: str, count: int
) -> None:
    from xyg import _svg

    figure = _supported()
    values = list(range(count))
    if kind == "area":
        figure.area(values, [1.0] * count)
    else:
        figure.error_band(values, [0.5] * count, [1.5] * count)

    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_BAND"
    assert figure.to_svg() == _svg.to_svg(figure)
    if kind == "area" and count == 1:
        assert figure.to_svg().count('<path d="') == 2


def test_public_router_routes_literal_disconnected_segments_through_all_static_consumers() -> None:
    from xyg import _native, _pdf, kernels

    figure = _public_disconnected_segments()
    assert scene_export_support_reason(figure) is None
    assert [trace.style.get("role") for trace in figure.traces] == [
        "segments",
        "y-errorbar",
        "y-errorbar",
        "x-errorbar",
        "stem",
        "stem-marker",
    ]
    scene = figure_scene(figure)
    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    assert hashlib.sha256(scene).hexdigest() == fixture["public_disconnected_segments_sha256"]
    # Two user segments, six capped vertical error-bar pairs, four capless
    # combined x/y error-bar pairs, then two stems and their endpoint scatter.
    # This order is the public paint contract.
    svg = _native.scene_svg(scene)
    assert svg.count("<polyline ") == 14
    assert svg.count("<path ") == 2  # two diamond endpoint markers
    assert svg.rfind("<polyline ") < svg.rfind("<path ")  # endpoint markers paint last
    assert figure.to_svg().encode() == svg.encode()
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), figure.width, figure.height
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda figure: figure.traces[0].style.__setitem__("role", "custom"), "PUBLIC_STYLE"),
        (lambda figure: figure.traces[0].x0.values.__setitem__(0, np.nan), "missing-data"),
    ],
)
def test_public_disconnected_segment_router_fails_closed(
    mutate: Callable[[Figure], None], reason: str
) -> None:
    figure = _public_disconnected_segments()
    mutate(figure)
    result = scene_export_support_reason(figure)
    if reason == "missing-data":
        with pytest.raises(UnsupportedSceneV3, match=reason):
            figure_scene(figure)
        assert result is not None
    else:
        assert result is not None and reason in result


def test_public_disconnected_segments_admit_constant_linecap() -> None:
    figure = _public_disconnected_segments()
    figure.traces[0].style["linecap"] = "butt"
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert b"XYLC" in scene
    assert 'stroke-linecap="butt"' in _public_svg(figure)


@pytest.mark.parametrize(
    "axis_id,key,value",
    [
        ("x", "domain", None),
        ("y", "domain", None),
        ("x", "side", "top"),
        ("y", "side", "right"),
    ],
)
def test_public_disconnected_segments_require_explicit_default_side_cartesian_axes(
    axis_id: str, key: str, value: object
) -> None:
    figure = _public_disconnected_segments()
    figure.axis_options[axis_id][key] = value
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS"


def test_public_disconnected_segments_reject_more_than_ten_thousand_endpoint_pairs() -> None:
    values = np.arange(10_001, dtype=np.float64)
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 10_001.0)
    figure.axis_options["y"]["domain"] = (0.0, 10_001.0)
    figure.segments(values, values, values + 0.5, values + 0.5)
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"


def test_compact_step_allows_only_the_binned_ecdf_anchor_above_ten_thousand() -> None:
    maximum_values = np.concatenate(
        (np.arange(10_000, dtype=np.float64) + 0.5, np.array([0.0, 10_000.0]))
    )
    binned = Figure(width=320, height=240).ecdf(maximum_values, bins=10_000)
    binned.axis_options["x"]["domain"] = (0.0, 10_000.0)
    binned.axis_options["y"]["domain"] = (0.0, 1.0)
    assert len(binned.traces[0].x.values) == 10_001
    assert scene_export_support_reason(binned) is None
    assert binned.to_scene()

    accepted = Figure(width=320, height=240).step(
        np.arange(10_001, dtype=np.float64), np.arange(10_001, dtype=np.float64)
    )
    accepted.axis_options["x"]["domain"] = (0.0, 10_001.0)
    accepted.axis_options["y"]["domain"] = (0.0, 10_001.0)
    assert scene_export_support_reason(accepted) is None
    assert accepted.to_scene()

    rejected = Figure(width=320, height=240).step(
        np.arange(10_002, dtype=np.float64), np.arange(10_002, dtype=np.float64)
    )
    rejected.axis_options["x"]["domain"] = (0.0, 10_002.0)
    rejected.axis_options["y"]["domain"] = (0.0, 10_002.0)
    assert scene_export_support_reason(rejected) == "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"


def test_public_stem_marker_must_immediately_follow_its_exact_stem_geometry() -> None:
    figure = _public_disconnected_segments()
    stem_marker = figure.traces.pop()
    figure.scatter([0.0], [0.0])
    figure.traces.append(stem_marker)
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE"


def test_fluid_viewport_uses_compatibility_until_static_dimensions_are_given() -> None:
    figure = Figure(width="100%", height="100%")
    figure.scatter([1], [2])
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_FLUID_VIEWPORT"
    assert scene_export_support_reason(figure, width=320, height=240) is None


def _axis_visibility_figure(axis_name: str, *, ticks: bool, text: bool) -> Figure:
    axis = (xyg.x_axis if axis_name == "x" else xyg.y_axis)(ticks=ticks, text=text)
    chart = xyg.scatter_chart(
        xyg.scatter([1, 2, 3], [1, 2, 3]),
        axis,
        width=420,
        height=260,
    )
    return chart.figure()


@pytest.mark.parametrize("axis_name", ["x", "y"])
@pytest.mark.parametrize(
    ("ticks", "text"), [(True, True), (False, True), (True, False), (False, False)]
)
def test_axis_visibility_switches_route_all_public_static_exports_through_scene(
    axis_name: str,
    ticks: bool,
    text: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The switches are independent canonical Scene chrome semantics."""
    figure = _axis_visibility_figure(axis_name, ticks=ticks, text=text)
    assert scene_export_support_reason(figure) is None

    from xyg import _native

    scene_static_export = _native.scene_static_export
    calls = {"n": 0}

    def observed_scene_static(*args: object, **kwargs: object) -> bytes:
        calls["n"] += 1
        return scene_static_export(*args, **kwargs)

    monkeypatch.setattr(_native, "scene_static_export", observed_scene_static)
    svg = figure.to_svg()
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")
    assert calls["n"] == 3

    # Both axis labels are present by default (three per axis). The switched
    # axis owns exactly three independently visible tick marks and labels.
    assert svg.count("<text ") == 6 - (0 if text else 3)
    assert svg.count("<line ") == 14 - (0 if ticks else 3)


@pytest.mark.parametrize("axis_name", ["x", "y"])
@pytest.mark.parametrize(
    ("ticks", "text"), [(True, True), (False, True), (True, False), (False, False)]
)
def test_axis_visibility_scene_public_route_matches_compatibility_structure_and_pixels(
    axis_name: str, ticks: bool, text: bool
) -> None:
    """Pin the migration against the established static-renderer contract."""
    from xyg import _raster, _svg

    Image = pytest.importorskip(
        "PIL.Image", reason="Pillow is required only for the raster pixel differential"
    )

    figure = _axis_visibility_figure(axis_name, ticks=ticks, text=text)
    compatibility_svg = _svg.to_svg(figure)
    public_svg = figure.to_svg()
    # Compatibility leaves invisible SVG elements in its structure. Scene
    # omits zero-paint primitives, so compare their visible contract instead.
    assert public_svg.count("<text ") == 6 - (0 if text else 3)
    assert public_svg.count("<line ") == 14 - (0 if ticks else 3)
    if not text:
        assert compatibility_svg.count('fill="#00000000"') == 3
    if not ticks:
        assert compatibility_svg.count('stroke-width="0"') == 3

    compatibility = np.asarray(
        Image.open(BytesIO(_raster.to_png(figure, scale=1))).convert("RGBA"), dtype=np.int16
    )
    public = np.asarray(Image.open(BytesIO(figure.to_png(scale=1))).convert("RGBA"), dtype=np.int16)
    delta = np.abs(compatibility - public)
    # The two raster consumers have distinct antialiasing, so this is a visual
    # differential rather than byte identity. Visibility-only variants are
    # exact today; the all-visible reference bounds their established paint
    # spelling difference without concealing a missing chrome element.
    assert float(delta.mean()) <= 0.11
    assert float(np.mean(delta.max(axis=2) > 24)) <= 0.0018


def test_axis_visibility_keeps_ticks_and_text_semantics_independent() -> None:
    ticks_off = _axis_visibility_figure("x", ticks=False, text=True).to_svg()
    text_off = _axis_visibility_figure("x", ticks=True, text=False).to_svg()
    assert re.findall(r"<text[^>]+>([123])</text>", ticks_off)
    assert '<line x1="56.36" y1="224" x2="56.36" y2="228"' not in ticks_off
    assert text_off.count("<text ") == 3  # y labels remain visible
    assert '<line x1="56.36" y1="224" x2="56.36" y2="228"' in text_off


def test_axis_visibility_python_fixture_and_browser_painter_are_exact() -> None:
    """The public switches stay one canonical Scene across Python and browser use."""
    from xyg import _native

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "public_axis_visibility_scene.json").read_text()
    )
    assert fixture["schema"] == "xyg-public-axis-visibility-scene-v1"
    for case in fixture["cases"]:
        figure = _axis_visibility_figure(
            str(case["axis"]), ticks=bool(case["ticks"]), text=bool(case["text"])
        )
        scene = figure.to_scene()
        assert hashlib.sha256(scene).hexdigest() == case["sha256"]
        painter = _native.scene_browser_painter(scene)
        assert painter.startswith(b"XYPB")
        assert len(painter) > 300


def test_axis_visibility_stays_bounded_before_the_public_scene_route() -> None:
    """Removing the visibility preflight must not weaken Scene resource limits."""
    figure = _axis_visibility_figure("x", ticks=False, text=True)
    figure.axis_options["x"]["tick_values"] = list(range(201))
    with pytest.raises(ValueError, match="axis tick lists are limited"):
        scene_export_support_reason(figure)


def _public_mark_figures() -> list[tuple[str, Figure]]:
    """In-scope Cartesian figures for every #272/#273 listed mark family."""
    return [
        ("scatter", _supported()),
        ("line_bar", _public_literal_geometry()),
        ("segments", _public_disconnected_segments()),
        ("hexbin", _public_hexbin()),
        ("ribbon", _public_ribbon("linear")),
        ("triangle_mesh", _public_triangle_mesh()),
        ("heatmap", _public_heatmap()),
        ("violin", _public_violin()),
        ("box", _public_box()),
    ]


def test_public_mark_figures_never_call_python_svg_mark_emitters(monkeypatch) -> None:
    """#272: Scene-eligible to_svg must not fall back to `_svg.py` mark paths."""
    from xyg import _svg

    def boom(*_args, **_kwargs):
        raise AssertionError("Python SVG mark emitter used for a Scene-eligible figure")

    for name in (
        "_segment_marks",
        "_scatter_marks",
        "_hexbin_marks",
        "_ribbon_marks",
        "_triangle_mesh_marks",
        "_bar_marks",
        "_rect_marks",
    ):
        monkeypatch.setattr(_svg, name, boom)
    monkeypatch.setattr(_svg, "to_svg", boom)

    for label, figure in _public_mark_figures():
        assert scene_export_support_reason(figure) is None, label
        svg = figure.to_svg()
        assert svg.startswith("<svg"), label
        assert "polyline" in svg or "path" in svg or "<rect" in svg, label


def test_public_mark_figures_never_call_python_raster_mark_emitters(monkeypatch) -> None:
    """#273: Scene-eligible PNG must not fall back to `_raster.py` mark emitters."""
    from xyg import _raster

    def boom(*_args, **_kwargs):
        raise AssertionError("Python raster mark emitter used for a Scene-eligible figure")

    for name in (
        "_emit_scatter",
        "_emit_authored_scatter",
        "_emit_segments",
        "_emit_hexbin",
        "_emit_ribbon",
        "_emit_triangle_mesh",
        "_emit_bars",
        "_emit_rects",
        "to_png",
        "to_rgba",
        "render_raster",
    ):
        monkeypatch.setattr(_raster, name, boom)

    for label, figure in _public_mark_figures():
        png = figure.to_png(scale=1)
        assert png.startswith(b"\x89PNG"), label


def test_public_mark_figures_encode_pdf_through_rust() -> None:
    """#274: Scene-eligible PDF uses the native closed-subset converter."""
    from xyg import _native

    for label, figure in _public_mark_figures():
        svg = figure.to_svg()
        pdf = figure.to_image(format="pdf")
        assert pdf.startswith(b"%PDF-"), label
        assert pdf == _native.svg_to_pdf(svg), label
        assert b"/FlateDecode" in pdf, label


def test_public_mark_figures_encode_jpeg_and_webp_through_rust(monkeypatch) -> None:
    """#274: Scene-eligible JPEG/WebP use native encode, not Python format modules."""
    from xyg import _jpeg, _webp

    def boom(*_args, **_kwargs):
        raise AssertionError("Python JPEG/WebP encoder used for a Scene-eligible figure")

    monkeypatch.setattr(_jpeg, "encode", boom)
    monkeypatch.setattr(_webp, "encode", boom)

    for label, figure in _public_mark_figures():
        jpeg = figure.to_image(format="jpeg", scale=1)
        webp = figure.to_image(format="webp", scale=1)
        assert jpeg[:3] == b"\xff\xd8\xff", label
        assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP", label
        assert public_static_export(figure, "jpeg") == jpeg, label
        assert public_static_export(figure, "webp") == webp, label
