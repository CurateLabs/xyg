"""Support-predicate parity for the #117 public static-export Scene router.

`scene_export_support_reason` is the single seam the public exporter uses to
decide whether a figure routes through the canonical Rust Scene or the
compatibility renderers. It is intentionally narrower than `figure_scene`:
explicit Scene APIs may exercise a migrating record before the public output
contract is complete. These tests pin both compiler rejection and public
preflight so the router cannot silently select a partial consumer.
"""

from __future__ import annotations

import re
from collections.abc import Callable

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
    assert encoded[4:8] == (23).to_bytes(4, "little")
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


def test_bounded_cartesian_callout_remains_explicit_scene_only_until_public_parity() -> None:
    figure = _callout()
    assert "PUBLIC_ANNOTATION" in (scene_export_support_reason(figure) or "")
    assert b"here" in figure_scene(figure)


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
        (lambda: _supported().scatter([0, 1], [1, 2], symbol="diamond"), "PUBLIC_SYMBOL"),
        (lambda: _supported(), None),
    ],
)
def test_public_router_selects_only_the_proven_circle_scatter_subset(
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


@pytest.mark.parametrize("axis", [xyg.x_axis(ticks=False), xyg.x_axis(text=False)])
def test_axis_visibility_switches_preflight_to_compatibility(
    axis: xyg.Axis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy static raster owns independent ticks/text visibility today."""
    chart = xyg.scatter_chart(
        xyg.scatter([1, 2, 3], [1, 2, 3]),
        axis,
        width=420,
        height=260,
    )
    figure = chart.figure()
    assert scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS_VISIBILITY"

    from xyg import _native

    def unexpected_scene_call(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("axis visibility must select compatibility before Scene compilation")

    monkeypatch.setattr(_native, "scene_raster_commands", unexpected_scene_call)
    assert chart.to_png().startswith(b"\x89PNG\r\n\x1a\n")


def test_ticks_off_compatibility_svg_keeps_scene_route_label_paint() -> None:
    """A compatibility switch must not make the routed default labels disappear."""
    chart = xyg.scatter_chart(
        xyg.scatter([1, 2, 3], [1, 2, 3]),
        xyg.x_axis(ticks=False),
        width=420,
        height=260,
    )
    labels = re.findall(r'<text[^>]+fill="([^"]+)"[^>]*>([123])</text>', chart.to_svg())
    assert len(labels) == 6
    assert all(paint != "#00000000" for paint, _text in labels)
    assert {paint for paint, _text in labels} == {"rgba(32,32,32,0.85)"}
