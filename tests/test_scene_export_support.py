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


def _supported() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.scatter([1, 2], [2, 3], color="#3987e5", size=6, opacity=0.8)
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
    assert encoded[4:8] == (24).to_bytes(4, "little")
    assert b"XYTL" in encoded


def _labeled_annotation() -> Figure:
    figure = _supported()
    figure.annotations = [{"kind": "marker", "x": 1.0, "y": 2.0, "text": "peak"}]
    return figure


def _callout() -> Figure:
    figure = _supported()
    figure.annotations = [{"kind": "callout", "x": 1.0, "y": 2.0, "text": "here"}]
    return figure


def _dashed_line() -> Figure:
    figure = _supported().line([1, 2, 3], [1, 4, 2], color="#ef4444", width=2)
    figure.traces[-1].style["dash"] = "4,2"
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


def test_up_to_two_ordinary_bounded_cartesian_callouts_are_a_supported_public_scene_slice() -> None:
    figure = _callout()
    assert scene_export_support_reason(figure) is None
    assert b"here" in figure_scene(figure)
    figure.annotations.append({"kind": "callout", "x": 2.0, "y": 3.0, "text": "there", "dx": -24.0})
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    assert b"here" in scene and b"there" in scene


def test_proven_ordinary_and_wrapped_callout_fixture_is_a_supported_public_slice() -> None:
    """The v24 public evidence fixture must not fall back before Rust sees XYAW."""
    from scripts.generate_authored_scene_benchmark import authored_scene_figure

    figure = authored_scene_figure(100)
    assert scene_export_support_reason(figure) is None
    assert b"XYLB" in figure_scene(figure)


@pytest.mark.parametrize(
    "annotations",
    [
        [{"kind": "marker", "x": 1.0, "y": 2.0, "text": "peak"}],
        [
            {"kind": "callout", "x": 1.0, "y": 2.0, "text": "first"},
            {"kind": "callout", "x": 2.0, "y": 3.0, "text": "second"},
            {"kind": "callout", "x": 3.0, "y": 4.0, "text": "third"},
        ],
        [{"kind": "callout", "x": 1.0, "y": 2.0, "text": "wrapped", "wrap": 96.0}],
    ],
)
def test_only_two_ordinary_bounded_callouts_enter_the_public_annotation_slice(
    annotations: list[dict[str, object]],
) -> None:
    figure = _supported()
    figure.annotations = annotations
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
        (lambda: _supported().line([0, 1], [0, 1]), "PUBLIC_MARK"),
        (lambda: _supported().bar([0, 1], [1, 2]), "PUBLIC_MARK"),
        (lambda: _supported().scatter([0, 1], [1, 2], symbol="square"), "PUBLIC_SYMBOL"),
        (lambda: _supported().scatter([0, 1], [1, 2], symbol="diamond"), None),
        (lambda: _supported(), None),
    ],
)
def test_public_router_selects_only_the_proven_circle_diamond_scatter_subset(
    factory, reason: str | None
) -> None:
    assert scene_export_support_reason(factory()) == (
        None if reason is None else f"XYG_SCENE_UNSUPPORTED_{reason}"
    )


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
