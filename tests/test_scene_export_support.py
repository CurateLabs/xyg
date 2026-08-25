"""Support-predicate parity for the #117 public static-export Scene router.

`scene_export_support_reason` is the single seam the public exporter uses to
decide whether a figure routes through the canonical Rust Scene or the
compatibility renderers. It is intentionally narrower than `figure_scene`:
explicit Scene APIs may exercise a migrating record before the public output
contract is complete. These tests pin both compiler rejection and public
preflight so the router cannot silently select a partial consumer.
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
    scene_export_support_reason,
)
from xyg.marks import _SYMBOL_CODES

BUILTIN_SYMBOLS = tuple(_SYMBOL_CODES)


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


def _polar() -> Figure:
    figure = _supported()
    figure.coords = "polar"
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
    assert encoded[4:8] == (25).to_bytes(4, "little")
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
    assert scene[4:8] == (25).to_bytes(4, "little")
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
    "polar": (_polar, "XYG_SCENE_UNSUPPORTED_POLAR"),
    "custom_font": (_custom_font, "XYG_SCENE_UNSUPPORTED_CUSTOM_FONT"),
    "browser_css": (_browser_css, "XYG_SCENE_UNSUPPORTED_BROWSER_CSS"),
    "colorbar": (_colorbar, "XYG_SCENE_UNSUPPORTED_COLORBAR"),
    "extra_legend": (_extra_legend, "XYG_SCENE_UNSUPPORTED_EXTRA_LEGEND"),
    "dashed_line": (_dashed_line, "dashed"),
}


def test_supported_figure_has_no_reason() -> None:
    figure = _supported()
    # Compiler accepts it, so the predicate must report None (route via Scene).
    figure_scene(figure)
    assert scene_export_support_reason(figure) is None


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


@pytest.mark.parametrize(
    ("style_key", "style_value"),
    [("stroke", "transparent"), ("stroke", "#ff0000"), ("stroke_width", 2.0)],
)
def test_authored_scatter_stroke_stays_on_compatibility_route(
    style_key: str, style_value: str | float
) -> None:
    """The all-symbol increment does not widen authored scatter paint policy."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.scatter([1.0], [1.0], symbol="plus_line", color="#3987e5")
    figure.traces[-1].style[style_key] = style_value
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE"


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
        lambda figure: figure.traces[0].style.__setitem__("marker_glyph", "A"),
        lambda figure: figure.scatter([2.5, 3.5], [2.5, 3.5], symbol=["circle", "square"]),
        lambda figure: figure.scatter([2.5, 3.5], [2.5, 3.5], color=[0.0, 1.0]),
        lambda figure: setattr(figure, "coords", "polar"),
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
        lambda figure: setattr(figure.traces[0], "color2_ch", figure.traces[0].color_ch),
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
    assert "expansion_modes=expansion_modes" in python_packer
    assert "expansionModes, x0, y0" in node_packer
    assert "_ribbon_band_samples" not in python_packer
    assert "ribbon_edge" not in python_packer
    assert "function ribbonEdge" not in node_packer
    assert "RIBBON_STEPS" not in node_packer


@pytest.mark.parametrize(
    "annotation",
    [
        {"kind": "text", "x": 0.5, "y": 0.5, "text": "rotated", "rotation": 30},
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
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "offset", "dy": -8},
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "anchor", "anchor": "end"},
    ],
)
def test_public_annotation_router_rejects_unencoded_text_and_marker_label_layout(
    annotation: dict[str, object],
) -> None:
    figure = _supported()
    figure.annotations = [annotation]
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_ANNOTATION"


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
        (lambda: _supported().bar([0, 1], [1, 2]), None),
        (lambda: _supported().column([0, 1], [1, 2]), None),
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
        lambda: _supported().bar(
            [0, 1], [1, 2], fill="linear-gradient(to bottom, #000000, #ffffff)"
        ),
        lambda: _supported().column([0, 1], [1, 2], corner_radius=2),
        lambda: _supported().area([0, 1], [1, 2], curve="smooth"),
        lambda: _supported().area(
            [0, 1], [1, 2], fill="linear-gradient(to bottom, #000000, #ffffff)"
        ),
        lambda: _supported().scatter(range(10_001), range(10_001)),
    ],
)
def test_public_literal_geometry_boundary_fails_closed_for_unmodeled_behavior(factory) -> None:
    """A successful internal record must not silently widen static routing."""
    reason = scene_export_support_reason(factory()) or ""
    assert reason


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
        (lambda figure: figure.traces[0].style.__setitem__("dash", "4,2"), "PUBLIC_STYLE"),
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

    scene_svg = _native.scene_svg
    scene_raster_commands = _native.scene_raster_commands
    calls = {"svg": 0, "raster": 0}

    def observed_scene_svg(*args: object, **kwargs: object) -> str:
        calls["svg"] += 1
        return scene_svg(*args, **kwargs)  # type: ignore[arg-type]

    def observed_scene_raster_commands(*args: object, **kwargs: object) -> bytes:
        calls["raster"] += 1
        return scene_raster_commands(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_native, "scene_svg", observed_scene_svg)
    monkeypatch.setattr(_native, "scene_raster_commands", observed_scene_raster_commands)
    svg = figure.to_svg()
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")
    assert calls == {"svg": 2, "raster": 1}

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
