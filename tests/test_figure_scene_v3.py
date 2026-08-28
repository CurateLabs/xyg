from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import struct
from pathlib import Path

import numpy as np
import pytest

from xyg import _native, _scene_v3, kernels
from xyg._figure import Figure
from xyg._scene_v3 import UnsupportedSceneV3
from xyg.channels import ColorChannel

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())


def _xyad_from_figure(figure: Figure) -> bytes:
    compiled = _native.scene_pack_trace_compile(_scene_v3._pack_xytc(figure))
    attached = _native.scene_pack_trace_attach(compiled, _scene_v3._pack_xyta(figure))
    sidecars = _native.scene_pack_trace_sidecars(attached, _scene_v3._pack_xynm(figure))
    rows = _native.scene_pack_trace_row_bytes(attached, _scene_v3._pack_xycl(figure))
    facts = bytearray()
    for index, annotation in enumerate(list(getattr(figure, "annotations", None) or [])):
        facts.extend(_scene_v3._pack_xyaf(annotation, index))
    output = (
        _native.scene_pack_annotation_facts(
            bytes(facts),
            style_ref_base=len(figure.traces),
            x_domain=tuple(float(value) for value in figure._range("x")),
            y_domain=tuple(float(value) for value in figure._range("y")),
        )
        if facts
        else b""
    )
    return _scene_v3._unpack_xyas(_native.scene_splice_annotations(rows, sidecars, output))["xyad"]


def representative_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.scatter([1, 2], [2, 3], color="#3987e5", size=6, opacity=0.8, symbol="diamond")
    figure.line([1, 2, 3], [1, 4, 2], color="#ef4444", width=2)
    figure.bar([1, 2], [3, 2], color="#22c55e", opacity=0.85)
    return figure


def default_style_figure(kind: str) -> Figure:
    figure = Figure(width=200, height=120)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    if kind == "scatter":
        figure.scatter([0.25], [0.5])
        figure.traces[-1].id = 10
    else:
        figure.line([0.0, 1.0], [0.0, 1.0])
        figure.traces[-1].id = 11
    return figure


def cartesian_callout_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.scatter([0.0, 1.0], [0.0, 1.0])
    # Python's default trace identity differs from Node's. Pin the author
    # identity so this is a true cross-host transport fixture.
    figure.traces[-1].id = 0
    figure.callout(
        0.5,
        0.5,
        "Rust",
        dx=-12,
        dy=-18,
        style={"color": "#344054", "label_background": "#ffffff"},
    )
    return figure


def numeric_tick_format_figure() -> Figure:
    figure = Figure(width=420, height=260)
    figure.axis_options["x"].update(domain=(0.0, 1.0), format=".1%")
    figure.axis_options["y"].update(domain=(-15_000.0, 15_000.0), format="$,.0f USD")
    figure.scatter([0.0, 1.0], [-10_000.0, 10_000.0])
    figure.traces[-1].id = 0
    return figure


def nonlinear_axis_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.set_axis("x", type_="symlog", constant=2.0, domain=(-10.0, 10.0))
    figure.set_axis("y", type_="log", nonpositive="mask", domain=(0.1, 10.0))
    figure.scatter([-1.0, 1.0], [0.5, 2.0])
    figure.traces[-1].id = 0
    return figure


def public_callout_figure() -> Figure:
    """The one-callout public-routing contract, including the v23 label box."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.scatter([0.0, 1.0], [0.0, 1.0], color="#3987e5", size=6, opacity=0.8)
    figure.callout(
        0.5,
        0.5,
        "Public Rust",
        dx=-12,
        dy=-18,
        anchor="middle",
        style={
            "color": "#344054",
            "opacity": 0.9,
            "width": 1.5,
            "label_background": "#ffffff",
            "label_border_color": "#98a2b3",
            "label_border_width": 1.0,
        },
    )
    return figure


def public_two_callout_figure() -> Figure:
    """The bounded two-ordinary-callout public-routing contract."""
    figure = public_callout_figure()
    figure.callout(
        0.8,
        0.25,
        "Second public Rust callout",
        dx=-20,
        dy=20,
        anchor="end",
        style={"color": "#344054", "opacity": 0.9, "width": 1.5},
    )
    return figure


def public_authored_chrome_figure() -> Figure:
    """The complete bounded literal-chrome public-routing contract."""
    from scripts.generate_authored_scene_benchmark import authored_scene_figure

    return authored_scene_figure(100)


def test_python_figure_compiles_exact_scene_v3_fixture() -> None:
    scene = representative_figure().to_scene()
    assert hashlib.sha256(scene).hexdigest() == FIXTURE["expected_sha256"]
    assert scene[160 + 3 * 16 + 2] == 2  # canonical diamond symbol code
    svg = _native.scene_svg(scene)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert svg.count("<polyline ") == 1
    assert svg.count("<rect ") == 5  # plot clip, two backgrounds, and two bars
    assert 'clip-path="url(#xy-scene-plot)"' in svg
    assert 'data-xy-chrome="grid"' in svg
    assert 'data-xy-chrome="axes"' in svg
    assert svg.count("<text ") == 6
    assert ">0<" in svg and ">4<" in svg


def test_python_scene_defaults_have_shared_noncoincidental_bytes() -> None:
    assert FIXTURE["wasm_typed_series_v2"] == {
        "magic": "XYTS",
        "scatter_diameter": 8,
        "line_stroke_width": 1.5,
        "bar_half_width": 0.4,
        "bar_baseline": 0,
        "area_baseline": 0,
        "default_stable_id_base": 1,
        "arbitrary_stable_ids": [91, 7],
        "joined_series_share_stable_id": True,
        "default_fill_rgba": [37, 99, 235, 255],
        "default_line_stroke_rgba": [37, 99, 235, 255],
    }
    scatter = default_style_figure("scatter").to_scene()
    line = default_style_figure("line").to_scene()
    assert hashlib.sha256(scatter).hexdigest() == FIXTURE["default_scatter_sha256"]
    assert hashlib.sha256(line).hexdigest() == FIXTURE["default_line_sha256"]
    assert np.frombuffer(memoryview(scatter)[168:176], dtype="<f8")[0] == 0.0
    assert np.frombuffer(memoryview(scatter)[224:232], dtype="<f8")[0] == 4.0
    assert np.frombuffer(memoryview(line)[168:176], dtype="<f8")[0] == 1.5


def test_python_scene_v20_cartesian_callout_matches_node_bytes_and_consumers() -> None:
    scene = cartesian_callout_figure().to_scene()
    assert hashlib.sha256(scene).hexdigest() == FIXTURE["cartesian_callout_sha256"]
    svg = _native.scene_svg(scene)
    assert "Rust" in svg
    assert 'data-xy-stable-id="6366126145334673408"' in svg
    assert b"Rust" in _native.scene_raster_commands(scene)
    assert b"XYLB" in _native.scene_browser_painter(scene)


def test_python_numeric_tick_formats_match_node_bytes_and_all_consumers() -> None:
    scene = numeric_tick_format_figure().to_scene()
    assert hashlib.sha256(scene).hexdigest() == FIXTURE["numeric_tick_format_sha256"]
    labels = (b"0.0%", b"50.0%", b"100.0%", b"$-10,000 USD", b"$0 USD", b"$10,000 USD")
    consumers = (
        _native.scene_svg(scene).encode(),
        _native.scene_raster_commands(scene),
        _native.scene_browser_painter(scene),
    )
    for label in labels:
        assert all(label in consumer for consumer in consumers)


def test_python_nonlinear_axis_descriptor_matches_node_bytes() -> None:
    scene = nonlinear_axis_figure().to_scene()
    assert hashlib.sha256(scene).hexdigest() == FIXTURE["nonlinear_axis_forwarding_sha256"]
    assert (scene[96], scene[97], scene[104], scene[105]) == (2, 0, 1, 1)
    assert struct.unpack_from("<d", scene, 144)[0] == 2.0


def test_python_scene_v9_primary_legend_matches_node_bytes_and_consumers() -> None:
    figure = Figure(width=200, height=120)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.scatter([0.25], [0.5], name="observed", color="#3987e5")
    figure.legend_options = {"loc": "lower left", "title": "Series"}
    scene = figure.to_scene()
    legend = scene[scene.index(b"XYLG") :]
    assert hashlib.sha256(legend).hexdigest() == FIXTURE["primary_legend_sha256"]
    svg = _native.scene_svg(scene)
    assert 'data-xy-chrome="legend"' in svg
    assert 'role="listitem"' in svg
    assert "observed" in svg
    assert b"observed" in _native.scene_raster_commands(scene, 1.0)


def test_python_scene_v9_legend_bounds_and_unsupported_variants_fail_closed() -> None:
    figure = Figure()
    figure.scatter([0.25], [0.5], name="observed")
    figure.legend_options = {"ncols": 2}
    with pytest.raises(UnsupportedSceneV3, match="multiple columns"):
        figure.to_scene()
    figure.legend_options = {"anchor": [1.0, 1.0]}
    with pytest.raises(UnsupportedSceneV3, match="anchors"):
        figure.to_scene()
    figure.legend_options = {"toggle": True}
    with pytest.raises(UnsupportedSceneV3, match="static"):
        figure.to_scene()
    figure.legend_options = {"loc": ""}
    with pytest.raises(UnsupportedSceneV3, match="location"):
        figure.to_scene()


def test_python_scene_v9_legend_best_loc_settles_during_encode() -> None:
    figure = Figure()
    figure.scatter([0, 1], [0, 1], name="x")
    figure.legend_options = {"loc": "best"}
    scene = figure.to_scene()
    loc_byte = scene[scene.index(b"XYLG") + 4]
    assert loc_byte == 1


def test_python_scene_authored_ticks_filter_during_encode() -> None:
    figure = Figure()
    figure.scatter([0, 1], [0, 1])
    figure.axis_options["x"].update(
        domain=(0.0, 1.0),
        tick_values=[-1.0, 0.0],
        tick_labels=["off-domain-long-label", "zero"],
    )
    scene = figure.to_scene()
    assert b"zero" in scene
    assert b"off-domain-long-label" not in scene
    svg = _native.scene_svg(scene)
    assert "zero" in svg
    assert "off-domain-long-label" not in svg


@pytest.mark.parametrize(
    ("scale", "domain", "constant", "points", "majors", "minors"),
    [
        (
            "linear",
            (0.0, 1.0),
            None,
            ([0.0, 1.0], [0.0, 1.0]),
            [0.0, 1.0],
            [-0.25, 0.25, 0.75, 1.25],
        ),
        ("log", (1.0, 10.0), None, ([1.0, 10.0], [1.0, 2.0]), [1.0, 10.0], [0.5, 2.0, 5.0, 20.0]),
        (
            "symlog",
            (-10.0, 10.0),
            1.0,
            ([-1.0, 1.0], [-1.0, 1.0]),
            [-10.0, 10.0],
            [-20.0, -1.0, 1.0, 20.0],
        ),
    ],
)
def test_python_scene_authored_minors_filter_during_encode(
    scale: str,
    domain: tuple[float, float],
    constant: float | None,
    points: tuple[list[float], list[float]],
    majors: list[float],
    minors: list[float],
) -> None:
    figure = Figure()
    figure.scatter(points[0], points[1])
    options = {
        "type_": scale,
        "domain": domain,
        "tick_values": majors,
        "minor_tick_values": minors,
        "minor_style": {
            "grid_color": "#22c55e",
            "tick_color": "#22c55e",
            "tick_length": 3,
        },
    }
    if constant is not None:
        options["constant"] = constant
    figure.set_axis("x", **options)
    svg = _native.scene_svg(figure.to_scene())
    assert "rgba(34,197,94" in svg
    off_only = Figure()
    off_only.scatter(points[0], points[1])
    off_options = dict(options)
    off_options["minor_tick_values"] = [minors[0], minors[-1]]
    off_only.set_axis("x", **off_options)
    off_svg = _native.scene_svg(off_only.to_scene())
    assert "rgba(34,197,94" not in off_svg


def test_python_scene_polar_seam_authored_ticks_filter_during_encode() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.scatter([0.0], [0.5])
    figure.set_axis(
        "x",
        domain=(0.0, 360.0),
        theta_unit="degrees",
        sector=(300.0, 420.0),
        tick_values=[300.0, 330.0, 0.0, 30.0, 60.0, 180.0],
        tick_labels=["300", "330", "zero", "30", "60", "off-sector"],
    )
    figure.set_axis("y", domain=(0.0, 1.0))
    svg = _native.scene_svg(figure.to_scene())
    assert ">zero<" in svg
    assert "off-sector" not in svg
    assert ">180<" not in svg


def test_python_scene_polar_theta_uses_angular_labels() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.scatter([0.0, math.pi], [0.5, 0.8])
    figure.set_axis("x", domain=(0.0, math.tau), theta_unit="radians")
    figure.set_axis("y", domain=(0.0, 1.0))
    svg = _native.scene_svg(figure.to_scene())
    thetas = re.findall(r'data-xy-tick="theta"[^>]*>([^<]+)', svg)
    assert any("π" in label for label in thetas)
    assert "2" not in thetas
    assert "4" not in thetas
    assert "6" not in thetas


def test_python_scene_time_strftime_and_polar_numeric_format() -> None:
    figure = Figure(width=420, height=260)
    figure.scatter([0.0, 86_400_000.0], [0.0, 1.0])
    figure.set_axis("x", type_="time", domain=(0.0, 86_400_000.0), format="%Y-%m-%d")
    figure.set_axis("y", domain=(0.0, 1.0))
    svg = _native.scene_svg(figure.to_scene())
    assert "1970-01-01" in svg
    assert "5.0e7" not in svg
    assert _scene_v3.scene_export_support_reason(figure) == "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS"

    polar = Figure(width=400, height=400, coords="polar")
    polar.scatter([0.0], [0.5])
    polar.set_axis("x", domain=(0.0, 360.0), theta_unit="degrees", format=".0f")
    polar.set_axis("y", domain=(0.0, 1.0), format=".1f")
    polar_svg = _native.scene_svg(polar.to_scene())
    thetas = re.findall(r'data-xy-tick="theta"[^>]*>([^<]+)', polar_svg)
    assert thetas
    assert all("°" not in label for label in thetas)
    assert any(label in {"0", "90", "180", "270"} for label in thetas)

    fallback = Figure(width=320, height=240)
    fallback.scatter([0.0, 5.0], [0.0, 5.0])
    fallback.axis_options["x"].update(domain=(0.0, 5.0), format=".2e")
    fallback.axis_options["y"].update(domain=(0.0, 5.0))
    fallback_svg = _native.scene_svg(fallback.to_scene())
    assert ">0<" in fallback_svg
    assert ">4<" in fallback_svg
    assert ".2e" not in fallback_svg


def test_python_scene_secondary_axis_stays_fail_closed() -> None:
    figure = Figure()
    figure.scatter([0.0, 1.0], [0.0, 1.0])
    figure.set_axis("x2", side="top", domain=(0.0, 1.0), tick_values=[0.25])
    with pytest.raises(UnsupportedSceneV3, match="exactly x/y axes"):
        figure.to_scene()
    assert _scene_v3.scene_export_support_reason(figure) == (
        "Scene v12 figure compilation currently supports exactly x/y axes"
    )


@pytest.mark.parametrize(
    ("value", "encoded"), [(None, b""), ("", b""), (0, b"0"), (False, b"false")]
)
def test_python_scene_v9_legend_title_defaults_only_for_none(value: object, encoded: bytes) -> None:
    figure = Figure(width=240, height=160)
    figure.scatter([0.25], [0.5], name="observed")
    figure.legend_options = {"title": value}
    legend = figure.to_scene().split(b"XYLG", 1)[1]
    title_length = int.from_bytes(legend[8:12], "little")
    assert title_length == len(encoded)
    assert legend[68 : 68 + title_length] == encoded


def test_python_explicit_scene_raster_is_nonblank() -> None:
    figure = representative_figure()
    scene = figure.to_scene()
    commands = _native.scene_raster_commands(scene)
    pixels = kernels.rasterize(commands, 320, 240)
    assert np.count_nonzero(pixels[:, :, 3]) > 200


def test_python_scene_raster_rejects_nonrepresentable_f32_commands() -> None:
    scene = representative_figure().to_scene()
    with pytest.raises(ValueError, match="invalid canonical scene"):
        _native.scene_raster_commands(scene, np.finfo(np.float64).max)
    huge_viewport = _native.scene_batch_encode(
        viewport=(1e100, 1e100),
        margins=(0.0, 0.0, 0.0, 0.0),
        x_axis=(1, 0, 0.0, 1.0, 1.0, False),
        y_axis=(2, 0, 0.0, 1.0, 1.0, False),
        kinds=[],
        stable_ids=[],
        style_refs=[],
        fill_rgba=[],
        stroke_rgba=[],
        stroke_width=[],
        diameter=[],
        symbols=[],
        x0=[],
        y0=[],
        x1=[],
        y1=[],
    )
    with pytest.raises(ValueError, match="invalid canonical scene"):
        _native.scene_raster_commands(huge_viewport)
    huge_width = _native.scene_batch_encode(
        viewport=(100.0, 80.0),
        margins=(10.0, 10.0, 10.0, 10.0),
        x_axis=(1, 0, 0.0, 1.0, 1.0, False),
        y_axis=(2, 0, 0.0, 1.0, 1.0, False),
        kinds=[1, 1],
        stable_ids=[1, 1],
        style_refs=[0, 0],
        fill_rgba=[0, 0, 0, 0],
        stroke_rgba=[0, 0, 0, 255],
        stroke_width=[1e100],
        diameter=[0.0, 0.0],
        symbols=[0, 0],
        x0=[0.0, 1.0],
        y0=[0.0, 1.0],
        x1=[0.0, 0.0],
        y1=[0.0, 0.0],
    )
    with pytest.raises(ValueError, match="invalid canonical scene"):
        _native.scene_raster_commands(huge_width)


def test_python_expansion_mode_ingress_fails_closed_before_scene_encoding() -> None:
    base = {
        "viewport": (100.0, 80.0),
        "margins": (10.0, 10.0, 10.0, 10.0),
        "x_axis": (1, 0, 0.0, 1.0, 1.0, False),
        "y_axis": (2, 0, 0.0, 1.0, 1.0, False),
        "kinds": [1, 1],
        "stable_ids": [1, 1],
        "style_refs": [0, 0],
        "fill_rgba": [0, 0, 0, 0],
        "stroke_rgba": [0, 0, 0, 255],
        "stroke_width": [1.0],
        "diameter": [0.0, 0.0],
        "symbols": [0, 0],
        "x0": [0.0, 1.0],
        "y0": [0.0, 1.0],
        "x1": [0.0, 0.0],
        "y1": [0.0, 0.0],
    }
    with pytest.raises(ValueError, match="equal length"):
        _native.scene_batch_encode(**base, expansion_modes=[1])
    with pytest.raises(ValueError, match="unsigned integer range"):
        _native.scene_batch_encode(**base, expansion_modes=[13, 13])
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        _native.scene_batch_encode(**base, expansion_modes=[12, 12])
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        _native.scene_batch_encode(**{**base, "kinds": [0, 0]}, expansion_modes=[1, 1])
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        _native.scene_batch_encode(
            **{
                **base,
                "style_refs": [0, 1],
                "fill_rgba": [0, 0, 0, 0] * 2,
                "stroke_rgba": [0, 0, 0, 255] * 2,
                "stroke_width": [1.0, 1.0],
            },
            expansion_modes=[1, 1],
        )
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        _native.scene_batch_encode(**{**base, "x0": [0.0, np.nan]}, expansion_modes=[2, 2])
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        _native.scene_batch_encode(**{**base, "x1": [1.0, 0.0]}, expansion_modes=[1, 1])
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        _native.scene_batch_encode(**{**base, "y1": [0.0, 1.0]}, expansion_modes=[1, 1])

    compact_ribbon = {
        **base,
        "kinds": [3, 3],
        "stable_ids": [7, 7],
        "diameter": [0.0, 0.0],
        "symbols": [2, 2],
        "x0": [0.0, 0.0],
        "y0": [2.0, 1.0],
        "x1": [1.0, 1.0],
        "y1": [3.0, 2.0],
    }
    expanded = _native.scene_batch_encode(**compact_ribbon, expansion_modes=[4, 4])
    assert int.from_bytes(expanded[16:24], "little") == 97
    for malformed in (
        {"stable_ids": [7, 8]},
        {"symbols": [2, 1]},
        {"x0": [0.0, 0.1]},
        {"x1": [1.0, 0.9]},
    ):
        with pytest.raises(ValueError, match="invalid canonical scene batch"):
            _native.scene_batch_encode(**{**compact_ribbon, **malformed}, expansion_modes=[4, 4])


@pytest.mark.parametrize("factory", [public_callout_figure, public_authored_chrome_figure])
def test_supported_public_exports_route_through_rust_scene(
    monkeypatch: pytest.MonkeyPatch, factory
) -> None:
    figure = factory()

    scene_static_export = _native.scene_static_export
    calls = {"n": 0}

    def observed_scene_static(*args: object, **kwargs: object) -> bytes:
        calls["n"] += 1
        return scene_static_export(*args, **kwargs)

    monkeypatch.setattr(_native, "scene_static_export", observed_scene_static)
    svg = figure.to_svg()
    assert "XYGS" not in svg  # the public string is Rust's rendered SVG, not Scene bytes
    if factory is public_callout_figure:
        assert 'role="listitem"' in svg and "Public Rust" in svg
    else:
        assert "Authored Scene evidence" in svg and "representative callout" in svg
    assert figure.to_scene()[:4] == b"XYGS"
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")
    assert calls["n"] >= 3


def test_public_static_export_compiles_scene_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public router reuses the predicate Scene instead of encoding twice."""
    figure = public_callout_figure()
    real = _scene_v3.figure_scene
    calls = {"n": 0}

    def counted(*args: object, **kwargs: object) -> bytes:
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(_scene_v3, "figure_scene", counted)
    exported = _scene_v3.public_static_export(figure, "svg")
    assert exported is not None
    assert exported.decode("utf-8") == _native.scene_svg(real(figure))
    assert calls["n"] == 1
    calls["n"] = 0
    assert _scene_v3.public_static_export(figure, "png", scale=1) is not None
    assert calls["n"] == 1
    calls["n"] = 0
    assert _scene_v3.public_static_export(figure, "pdf") is not None
    assert calls["n"] == 1
    calls["n"] = 0
    assert _scene_v3.scene_export_support_reason(figure) is None
    assert calls["n"] == 1


def test_figure_scene_does_not_call_figure_support_predicate_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    figure = public_callout_figure()

    def boom(_payload: bytes) -> str:
        raise AssertionError("product path must not probe XYFS separately")

    monkeypatch.setattr(_scene_v3._native, "scene_figure_support_reason", boom)
    encoded = _scene_v3.figure_scene(figure)
    assert encoded[:4] == b"XYGS"


def test_public_exporters_share_one_scene_selection_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Format routing belongs to Scene orchestration, not each Python exporter."""
    figure = public_callout_figure()
    public_static_export = _scene_v3.public_static_export
    formats: list[str] = []

    def observed_public_static_export(*args: object, **kwargs: object) -> bytes | None:
        formats.append(str(args[1]))
        return public_static_export(*args, **kwargs)

    monkeypatch.setattr(_scene_v3, "public_static_export", observed_public_static_export)

    assert figure.to_svg().startswith("<svg")
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")
    assert formats == ["svg", "png", "pdf"]


def test_two_ordinary_callouts_route_all_public_static_exports_through_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two-callout bound is proven through every public static consumer."""
    figure = public_two_callout_figure()
    scene_static_export = _native.scene_static_export
    calls = {"n": 0}

    def observed_scene_static(*args: object, **kwargs: object) -> bytes:
        calls["n"] += 1
        return scene_static_export(*args, **kwargs)

    monkeypatch.setattr(_native, "scene_static_export", observed_scene_static)
    svg = figure.to_svg()
    assert "Public Rust" in svg
    assert "Second public Rust callout" in svg
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")
    assert calls["n"] >= 3


@pytest.mark.parametrize("factory", [public_callout_figure, public_authored_chrome_figure])
def test_supported_file_exports_match_the_canonical_rust_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory
) -> None:
    """The single-file and batch public journeys share the Scene consumers.

    ``write_images`` does not call ``to_image`` because it amortizes browser
    setup, so this test must cover it separately. The supported native paths
    must nevertheless produce the exact bytes of the one encoded Rust Scene,
    rather than re-introducing an exporter-specific policy choice.
    """
    from xyg import _pdf, export

    figure = factory()
    scene = figure.to_scene()
    expected = {
        "svg": _native.scene_svg(scene).encode("utf-8"),
        "png": kernels.rasterize_png(
            _native.scene_raster_commands(scene), figure.width, figure.height
        ),
    }
    expected["pdf"] = _pdf.svg_to_pdf(expected["svg"].decode("utf-8"))

    scene_static_export = _native.scene_static_export
    calls = {"n": 0}

    def observed_scene_static(*args: object, **kwargs: object) -> bytes:
        calls["n"] += 1
        return scene_static_export(*args, **kwargs)

    monkeypatch.setattr(_native, "scene_static_export", observed_scene_static)

    single_paths = {fmt: tmp_path / f"single.{fmt}" for fmt in expected}
    for fmt, path in single_paths.items():
        assert figure.write_image(path, scale=1) == expected[fmt]
        assert path.read_bytes() == expected[fmt]

    batch_paths = [tmp_path / f"batch.{fmt}" for fmt in expected]
    batch = export.write_images([figure] * len(batch_paths), batch_paths, scale=1)
    assert batch == [expected[path.suffix[1:]] for path in batch_paths]
    for path in batch_paths:
        assert path.read_bytes() == expected[path.suffix[1:]]

    assert calls["n"] == 6


def test_unsupported_public_exports_stay_on_compatibility_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    figure = Figure().line([0.0, 1.0], [0.5, 1.0])
    figure.traces[-1].style["marker_path"] = "M0 0"

    def unexpected_scene_call(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError(
            "unsupported export must select compatibility before Scene compilation"
        )

    monkeypatch.setattr(_native, "scene_static_export", unexpected_scene_call)
    assert figure.to_svg().startswith("<svg")
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (
            lambda figure: setattr(figure, "style", {"background": "#fff", "theme": "dark"}),
            "PUBLIC_STYLE",
        ),
        (
            lambda figure: figure.chrome_styles.update({"title": {"font_family": "Custom"}}),
            "PUBLIC_STYLE",
        ),
        (lambda figure: setattr(figure, "class_name", "legacy-css"), "UNSUPPORTED_BROWSER_CSS"),
        # A literal primary marker is now part of the bounded public Scene
        # annotation family; the remaining rows continue to prove the legacy
        # preflight boundaries.
        (lambda figure: figure.error_band([0, 1], [0, 0], [1, 1]), "PUBLIC_AXIS"),
        (lambda figure: figure.scatter(range(10_001), range(10_001)), "PUBLIC_LOD"),
    ],
)
def test_public_router_preflights_legacy_export_contracts(mutate, reason: str) -> None:
    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], color="#3987e5")
    mutate(figure)
    assert reason in (_scene_v3.scene_export_support_reason(figure) or "")


def test_all_builtin_symbols_use_the_public_rust_scatter_contract() -> None:
    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], symbol="square")
    assert _scene_v3.scene_export_support_reason(figure) is None
    assert figure.to_svg() == _scene_v3.figure_svg(figure)


def test_constant_scatter_stroke_uses_the_public_rust_scene_contract() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.scatter(
        [0.25, 1.75],
        [0.5, 1.5],
        color="#336699",
        opacity=0.75,
        size=12,
        symbol="diamond",
        stroke="#ff8800",
        stroke_width=3.5,
        name="outlined",
    )
    figure.traces[-1].id = 41
    scene = figure.to_scene()
    assert hashlib.sha256(scene).hexdigest() == FIXTURE["public_scatter_stroke_sha256"]
    assert _scene_v3.scene_export_support_reason(figure) is None
    svg = _native.scene_svg(scene)
    assert 'stroke="rgb(255,136,0)" stroke-opacity="0.75"' in svg
    assert 'stroke-width="3.5"' in svg
    assert "outlined" in svg
    assert figure.to_svg() == svg
    assert figure.to_png(scale=1) == _scene_v3.public_static_export(figure, "png", scale=1)
    assert figure.to_image(format="pdf") == _scene_v3.public_static_export(figure, "pdf")
    assert _native.scene_raster_commands(scene)
    assert _native.scene_browser_painter(scene)


def test_constant_scatter_stroke_defaults_and_compatibility_boundaries() -> None:
    stroke_only = Figure(width=320, height=240).scatter(
        [0.5], [0.5], color="#336699", stroke="#ff8800"
    )
    assert stroke_only.traces[-1].style["stroke_width"] == 1.0
    assert _scene_v3.scene_export_support_reason(stroke_only) is None

    width_only = Figure(width=320, height=240).scatter(
        [0.5], [0.5], color="#336699", stroke_width=2.0
    )
    assert _scene_v3.scene_export_support_reason(width_only) is None
    width_svg = _native.scene_svg(width_only.to_scene())
    assert 'stroke="rgb(51,102,153)"' in width_svg
    assert 'stroke-width="2"' in width_svg
    assert width_only.to_svg() == width_svg

    plain_line_symbol = Figure(width=320, height=240).scatter(
        [0.5], [0.5], color="#336699", symbol="plus_line"
    )
    plain_svg = _scene_v3.figure_svg(plain_line_symbol)
    assert 'stroke="rgb(51,102,153)" stroke-opacity="0.8"' in plain_svg
    assert 'stroke-width="1"' in plain_svg

    for kwargs in (
        {"stroke": ["#111111", "#222222"]},
        {"stroke_width": [1.0, 2.0]},
    ):
        figure = Figure(width=320, height=240).scatter([0.5, 1.0], [0.5, 1.0], **kwargs)
        assert _scene_v3.scene_export_support_reason(figure) is None
        svg = _native.scene_svg(figure.to_scene())
        assert figure.to_svg() == svg

    sized = Figure(width=320, height=240).scatter([0.5, 1.0], [0.5, 1.0], size=[4.0, 12.0])
    assert _scene_v3.scene_export_support_reason(sized) is not None

    for opacity_key in ("fill_opacity", "stroke_opacity"):
        figure = Figure(width=320, height=240).scatter([0.5], [0.5], color="#336699")
        if opacity_key == "stroke_opacity":
            figure.traces[-1].style["stroke"] = "#111111"
            figure.traces[-1].style["stroke_width"] = 2.0
        figure.traces[-1].style[opacity_key] = 0.5
        assert _scene_v3.scene_export_support_reason(figure) is None

    for invalid_width in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="scatter stroke_width"):
            Figure().scatter([0.5], [0.5], stroke_width=invalid_width)


@pytest.mark.parametrize("factory", [public_callout_figure, public_authored_chrome_figure])
def test_supported_public_exports_match_rust_consumers_and_are_repeatable(factory) -> None:
    """The public journey must not merely produce valid files beside Scene."""
    figure = factory()
    svg = _scene_v3.figure_svg(figure)
    png = _scene_v3.public_static_export(figure, "png", scale=1)
    pdf = _scene_v3.public_static_export(figure, "pdf")

    assert figure.to_svg() == svg
    assert figure.to_svg() == figure.to_svg()
    assert figure.to_png(scale=1) == png
    assert figure.to_png(scale=1) == figure.to_png(scale=1)
    assert figure.to_image(format="pdf") == pdf
    assert figure.to_image(format="pdf") == figure.to_image(format="pdf")


@pytest.mark.parametrize("factory", [public_callout_figure, public_authored_chrome_figure])
def test_supported_public_export_failure_never_falls_back(
    monkeypatch: pytest.MonkeyPatch, factory
) -> None:
    figure = factory()

    def broken_scene(*_args: object, **_kwargs: object) -> bytes:
        raise ValueError("broken Scene consumer")

    def unexpected_compatibility(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("a Scene consumer error must not select compatibility")

    from xyg import _raster, _svg

    monkeypatch.setattr(_native, "scene_static_export", broken_scene)
    monkeypatch.setattr(_svg, "to_svg", unexpected_compatibility)
    monkeypatch.setattr(_raster, "to_png", unexpected_compatibility)
    with pytest.raises(ValueError, match="broken Scene consumer"):
        figure.to_svg()
    with pytest.raises(ValueError, match="broken Scene consumer"):
        figure.to_image(format="pdf")
    with pytest.raises(ValueError, match="broken Scene consumer"):
        figure.to_png(scale=1)


def test_malformed_public_literal_propagates_without_compatibility_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid canonical literal is an input failure, not a fallback cue."""
    figure = public_authored_chrome_figure()

    def malformed_scene(*_args: object, **_kwargs: object) -> bytes:
        raise ValueError("malformed canonical literal")

    def unexpected_compatibility(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("malformed canonical input must not select compatibility")

    from xyg import _svg

    monkeypatch.setattr(_native, "scene_encode_product", malformed_scene)
    monkeypatch.setattr(_svg, "to_svg", unexpected_compatibility)
    with pytest.raises(ValueError, match="malformed canonical literal"):
        figure.to_svg()


def test_public_static_export_selects_migrated_subset() -> None:
    from xyg import _scene_v3

    figure = representative_figure()
    svg_data = _scene_v3.public_static_export(figure, "svg")
    assert svg_data is not None
    svg = svg_data.decode("utf-8")
    assert 'clip-path="url(#xy-scene-plot)"' in svg
    png = _scene_v3.public_static_export(figure, "png", scale=1)
    assert png is not None and png.startswith(b"\x89PNG\r\n\x1a\n")
    pdf = _scene_v3.public_static_export(figure, "pdf")
    assert pdf is not None and pdf.startswith(b"%PDF-")
    styled = representative_figure()
    styled.set_axis("x", style={"grid_color": "#123456"})
    styled_data = _scene_v3.public_static_export(styled, "svg")
    assert styled_data is None
    assert "rgba(18,52,86,1.000000)" in _scene_v3.figure_svg(styled)


def test_python_scene_v8_authors_backgrounds_axis_side_and_major_minor_ticks() -> None:
    figure = default_style_figure("scatter")
    figure.style = {"background": "#102030", "--chart-bg": "#f1f5f9"}
    figure.set_axis(
        "x",
        domain=(0, 1),
        side="top",
        tick_sides=["bottom", "top"],
        tick_label_sides=["top"],
        tick_values=[0, 0.5, 1],
        minor_tick_values=[0.25, 0.75],
        style={
            "axis_color": "#ef4444",
            "axis_width": 2,
            "tick_length": 8,
            "tick_direction": "inout",
        },
        minor_style={
            "grid_color": "#22c55e",
            "tick_color": "#3b82f6",
            "tick_length": 3,
            "tick_direction": "in",
        },
    )
    figure.set_axis(
        "y",
        domain=(0, 1),
        style={
            "axis_width": 0,
            "tick_width": 0,
            "tick_length": 0,
            "grid_opacity": 0,
            "tick_label_color": "#00000000",
            "label_color": "#00000000",
        },
    )
    encoded = figure.to_scene()
    assert int.from_bytes(encoded[4:8], "little") == 31
    svg = _native.scene_svg(encoded)
    assert 'fill="rgba(16,32,48,1.000000)"' in svg
    assert 'fill="rgba(241,245,249,1.000000)"' in svg
    assert 'stroke="rgba(34,197,94,1.000000)"' in svg
    assert 'stroke="rgba(59,130,246,1.000000)"' in svg
    assert 'stroke="rgba(239,68,68,1.000000)" stroke-width="2"' in svg


def test_scene_v8_axis_line_visibility_does_not_hide_independent_ticks() -> None:
    from xyg import _scene_v3

    figure = default_style_figure("scatter")
    figure.set_axis("x", style={"axis_width": 0, "axis_color": "#00000000"})
    chrome = _scene_v3._scene_chrome_style(figure)
    assert struct.unpack_from("<d", chrome, 24 + 32)[0] == 0
    assert chrome[24 + 16 : 24 + 20] == bytes((32, 32, 32, 140))


def test_scene_v10_explicit_hidden_cartesian_chrome_stays_cartesian() -> None:
    figure = default_style_figure("scatter")
    hidden = {
        "axis_width": 0,
        "tick_width": 0,
        "tick_length": 0,
        "grid_width": 0,
        "axis_color": "#00000000",
        "grid_color": "#00000000",
        "tick_color": "#00000000",
        "tick_label_color": "#00000000",
        "label_color": "#00000000",
    }
    hidden_minor = {
        "grid_width": 0,
        "tick_width": 0,
        "tick_length": 0,
        "grid_color": "#00000000",
        "tick_color": "#00000000",
    }
    figure.set_axis("x", style=hidden, minor_style=hidden_minor, tick_sides=[], tick_label_sides=[])
    figure.set_axis("y", style=hidden, minor_style=hidden_minor, tick_sides=[], tick_label_sides=[])
    figure.title = "Cartesian title"
    svg = _native.scene_svg(figure.to_scene())
    assert 'data-xy-chrome="grid"' not in svg
    assert 'data-xy-chrome="axes"' not in svg
    assert 'data-xy-chrome="title"' in svg
    assert "Cartesian title" in svg

    figure.coords = "polar"
    polar = figure.to_scene()
    assert polar[4:8] == (31).to_bytes(4, "little")
    assert polar[-92:-88] == b"XYPL"


def test_python_scene_rejects_malformed_and_falls_back_for_unsupported_marks() -> None:
    with pytest.raises(ValueError, match="invalid canonical scene"):
        _native.scene_svg(b"not-a-scene")
    colormap = Figure().heatmap([[0.0, 1.0], [1.0, 0.0]])
    colormap_svg = _native.scene_svg(colormap.to_scene())
    assert "<rect" in colormap_svg
    assert "<svg" in colormap.to_svg()


def test_python_scene_compiles_ribbon_and_triangle_mesh() -> None:
    ribbon = Figure(width=320, height=200)
    ribbon.axis_options["x"]["domain"] = (0.0, 1.0)
    ribbon.axis_options["y"]["domain"] = (0.0, 1.0)
    ribbon.ribbon([0.1], [0.9], [0.2], [0.5], [0.3], [0.7], color="#7c3aed")
    scene = ribbon.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert '<path d="M ' in svg
    assert ' Z"' in svg

    mesh = Figure(width=240, height=160)
    mesh.axis_options["x"]["domain"] = (0.0, 1.0)
    mesh.axis_options["y"]["domain"] = (0.0, 1.0)
    mesh.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0], color="#22c55e")
    mesh_svg = _native.scene_svg(mesh.to_scene())
    assert '<path d="M ' in mesh_svg

    hexbin = Figure(width=320, height=240)
    hexbin.axis_options["x"]["domain"] = (0.0, 4.0)
    hexbin.axis_options["y"]["domain"] = (0.0, 5.0)
    hexbin.hexbin(
        [0.5, 1.5, 2.5],
        [0.5, 0.5, 2.0],
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        color="#3987e5",
    )
    hex_svg = _native.scene_svg(hexbin.to_scene())
    assert hex_svg.count('<path d="M ') == len(hexbin.traces[0].x.values)

    heatmap = Figure(width=320, height=240)
    heatmap.axis_options["x"]["domain"] = (0.0, 4.0)
    heatmap.axis_options["y"]["domain"] = (0.0, 5.0)
    heatmap.heatmap(
        [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]],
        x=[1.0, 2.0, 3.0],
        y=[1.0, 3.0],
        color="#3987e5",
    )
    heat_svg = _native.scene_svg(heatmap.to_scene())
    rows, cols = heatmap.traces[0].grid_shape or (0, 0)
    clip_start = heat_svg.find('<g clip-path="url(#xy-scene-plot)">')
    clip_end = heat_svg.find("</g>", clip_start)
    assert heat_svg[clip_start:clip_end].count("<rect ") == rows * cols

    colormap = Figure(width=320, height=240)
    colormap.axis_options["x"]["domain"] = (0.0, 4.0)
    colormap.axis_options["y"]["domain"] = (0.0, 5.0)
    colormap.heatmap([[0.0, 1.0], [1.0, 0.0]])
    colormap_svg = _native.scene_svg(colormap.to_scene())
    cmap_start = colormap_svg.find('<g clip-path="url(#xy-scene-plot)">')
    cmap_end = colormap_svg.find("</g>", cmap_start)
    assert colormap_svg[cmap_start:cmap_end].count("<rect ") == 4

    custom = Figure(width=320, height=240)
    custom.axis_options["x"]["domain"] = (0.0, 4.0)
    custom.axis_options["y"]["domain"] = (0.0, 5.0)
    custom.hexbin(
        [0.5, 1.5],
        [0.5, 0.5],
        C=[1.0, 2.0],
        reduce_C_function=np.median,
        color="#3987e5",
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
    )
    custom_svg = _native.scene_svg(custom.to_scene())
    assert custom_svg.count('<path d="M ') == len(custom.traces[0].x.values)
    assert custom.to_svg() == custom_svg
    assert _scene_v3.scene_export_support_reason(custom) is None


def test_python_scene_compiles_constant_ribbon_color2() -> None:
    gradient = Figure(width=240, height=160)
    gradient.axis_options["x"]["domain"] = (0.0, 1.0)
    gradient.axis_options["y"]["domain"] = (0.0, 1.0)
    gradient.ribbon(
        [0.0], [1.0], [0.0], [0.3], [0.2], [0.5], color="#7c3aed", color_target="#34d399"
    )
    scene = gradient.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYGR" in scene
    svg = _native.scene_svg(scene)
    assert '<linearGradient id="xy-scene-g0"' in svg
    assert 'fill="url(#xy-scene-g0)"' in svg
    assert gradient.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(gradient) is None
    solid = Figure(width=240, height=160)
    solid.axis_options["x"]["domain"] = (0.0, 1.0)
    solid.axis_options["y"]["domain"] = (0.0, 1.0)
    solid.ribbon([0.0], [1.0], [0.0], [0.3], [0.2], [0.5], color="#7c3aed", color_target="#7c3aed")
    solid_svg = _native.scene_svg(solid.to_scene())
    assert "<linearGradient" not in solid_svg
    assert solid.to_svg() == solid_svg
    assert _scene_v3.scene_export_support_reason(solid) is None
    per_item = Figure(width=240, height=160)
    per_item.axis_options["x"]["domain"] = (0.0, 1.0)
    per_item.axis_options["y"]["domain"] = (0.0, 1.0)
    per_item.ribbon(
        [0.0, 0.2],
        [0.4, 0.8],
        [0.0, 0.1],
        [0.2, 0.3],
        [0.15, 0.25],
        [0.35, 0.45],
        color=["#7c3aed", "#2563eb"],
        color_target=["#34d399", "#f59e0b"],
    )
    scene = per_item.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYGR" in scene
    svg = _native.scene_svg(scene)
    assert svg.count("<linearGradient") == 2
    assert per_item.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(per_item) is None


def test_python_scene_compiles_unwrapped_text_layout() -> None:
    figure = representative_figure()
    figure.annotations.append({"kind": "text", "x": 0.5, "y": 0.5, "text": "offset", "dx": 6})
    xyad = _xyad_from_figure(figure)
    assert b"XYAW" in xyad
    scene = figure.to_scene()
    assert b"offset" in scene
    svg = _native.scene_svg(scene)
    assert ">offset<" in svg
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None
    plain = representative_figure()
    plain.annotations.append({"kind": "text", "x": 0.5, "y": 0.5, "text": "offset"})
    plain_svg = _native.scene_svg(plain.to_scene())
    plain_x = float(re.search(r'x="([^"]+)"[^>]*>offset<', plain_svg).group(1))
    offset_x = float(re.search(r'x="([^"]+)"[^>]*>offset<', svg).group(1))
    assert offset_x == pytest.approx(plain_x + 6.0)
    anchored = representative_figure()
    anchored.annotations.append(
        {"kind": "text", "x": 0.5, "y": 0.5, "text": "anchor", "anchor": "end"}
    )
    anchored_svg = _native.scene_svg(anchored.to_scene())
    assert ">anchor<" in anchored_svg
    assert 'text-anchor="end"' in anchored_svg
    assert anchored.to_svg() == anchored_svg
    assert _scene_v3.scene_export_support_reason(anchored) is None
    rotated = representative_figure()
    rotated.annotations.append(
        {"kind": "text", "x": 0.5, "y": 0.5, "text": "rotated", "rotation": 30}
    )
    rotated_xyad = _xyad_from_figure(rotated)
    assert b"XYAW" in rotated_xyad
    rotated_svg = _native.scene_svg(rotated.to_scene())
    assert ">rotated<" in rotated_svg
    assert 'transform="rotate(-30 ' in rotated_svg
    assert rotated.to_svg() == rotated_svg
    assert _scene_v3.scene_export_support_reason(rotated) is None
    styled = representative_figure()
    styled.annotations.append(
        {"kind": "text", "x": 0.5, "y": 0.5, "text": "rotated", "style": {"rotation": 30}}
    )
    styled_svg = _native.scene_svg(styled.to_scene())
    assert 'transform="rotate(-30 ' in styled_svg
    assert _scene_v3.scene_export_support_reason(styled) is None
    authored = representative_figure()
    authored.text(2.0, 2.5, "note", rotation=30)
    assert _scene_v3.scene_export_support_reason(authored) is None
    assert 'transform="rotate(-30 ' in authored.to_svg()


def test_python_scene_compiles_labelled_marker_layout() -> None:
    figure = representative_figure()
    figure.annotations.append({"kind": "marker", "x": 0.5, "y": 0.5, "text": "pin", "dy": -8})
    xyad = _xyad_from_figure(figure)
    assert b"XYAW" in xyad
    scene = figure.to_scene()
    assert b"pin" in scene
    svg = _native.scene_svg(scene)
    assert ">pin<" in svg
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None
    plain = representative_figure()
    plain.annotations.append({"kind": "marker", "x": 0.5, "y": 0.5, "text": "pin"})
    plain_svg = _native.scene_svg(plain.to_scene())
    plain_y = float(re.search(r'y="([^"]+)"[^>]*>pin<', plain_svg).group(1))
    offset_y = float(re.search(r'y="([^"]+)"[^>]*>pin<', svg).group(1))
    assert offset_y == pytest.approx(plain_y - 8.0)
    anchored = representative_figure()
    anchored.annotations.append(
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "anchor", "anchor": "end"}
    )
    anchored_svg = _native.scene_svg(anchored.to_scene())
    assert ">anchor<" in anchored_svg
    assert 'text-anchor="end"' in anchored_svg
    assert anchored.to_svg() == anchored_svg
    assert _scene_v3.scene_export_support_reason(anchored) is None
    rotated = representative_figure()
    rotated.annotations.append(
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "rotated", "rotation": 30}
    )
    rotated_xyad = _xyad_from_figure(rotated)
    assert b"XYAW" in rotated_xyad
    rotated_svg = _native.scene_svg(rotated.to_scene())
    assert ">rotated<" in rotated_svg
    assert 'transform="rotate(-30 ' in rotated_svg
    assert rotated.to_svg() == rotated_svg
    assert _scene_v3.scene_export_support_reason(rotated) is None
    styled = representative_figure()
    styled.annotations.append(
        {"kind": "marker", "x": 0.5, "y": 0.5, "text": "rotated", "style": {"rotation": 30}}
    )
    styled_svg = _native.scene_svg(styled.to_scene())
    assert 'transform="rotate(-30 ' in styled_svg
    assert _scene_v3.scene_export_support_reason(styled) is None
    authored = representative_figure()
    authored.marker(2.0, 2.5, text="note", rotation=30)
    assert _scene_v3.scene_export_support_reason(authored) is None
    assert 'transform="rotate(-30 ' in authored.to_svg()
    unlabelled = representative_figure()
    unlabelled.annotations.append({"kind": "marker", "x": 0.5, "y": 0.5, "dx": 8, "dy": -8})
    assert _scene_v3.scene_export_support_reason(unlabelled) is None


def test_python_scene_compiles_area_and_error_band() -> None:
    for mode, options, symbol in (
        ("top", {}, 1),
        ("perimeter", {"stroke_perimeter": True}, 2),
        ("none", {"line_width": 0.0}, 0),
    ):
        area = Figure(width=240, height=160)
        area.axis_options["x"]["domain"] = (0.0, 2.0)
        area.axis_options["y"]["domain"] = (0.0, 3.0)
        area.area(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 1.5],
            base=0.0,
            color="#3987e5",
            opacity=0.5,
            line_color="#112233",
            line_width=options.get("line_width", 2.0),
            line_opacity=0.4,
            stroke_perimeter=options.get("stroke_perimeter", False),
            style={"fill-opacity": 0.8, "stroke-opacity": 0.5},
        )
        area.traces[0].id = 7
        scene = area.to_scene()
        expected = FIXTURE["band_outlines"][mode]
        assert scene == base64.b64decode(expected["scene_base64"])
        assert hashlib.sha256(scene).hexdigest() == expected["sha256"]
        assert scene[4:8] == (31).to_bytes(4, "little")
        assert scene[160:168] == bytes((57, 135, 229, 102, 17, 34, 51, 26))
        assert scene[160 + 16 + 2] == symbol
        svg = _native.scene_svg(scene)
        assert svg.count('<path d="') == (2 if mode == "top" else 1)
        assert bool('fill="none"' in svg) is (mode == "top")
        assert bool('stroke="none"' in svg) is (mode != "perimeter")
        assert _native.scene_raster_commands(scene, 1.0)
        painter = _native.scene_browser_painter(scene)
        assert painter[300 + 1] == symbol

    band = Figure(width=240, height=160)
    band.axis_options["x"]["domain"] = (0.0, 2.0)
    band.axis_options["y"]["domain"] = (0.0, 3.0)
    band.error_band([0.0, 1.0, 2.0], [0.7, 1.2, 0.9], [1.3, 1.8, 1.5], color="#22c55e")
    band_scene = band.to_scene()
    assert band_scene[160 + 16 + 2] == 0
    assert '<path d="M ' in _native.scene_svg(band_scene)

    invalid = Figure(width=240, height=160)
    invalid.axis_options["x"]["domain"] = (0.0, 1.0)
    invalid.axis_options["y"]["domain"] = (0.0, 1.0)
    invalid.area([0.0, 1.0], [0.25, 0.75], base=0.0)
    for invalid_value in ("true", 1, None):
        invalid.traces[0].style["stroke_perimeter"] = invalid_value
        with pytest.raises(UnsupportedSceneV3, match="stroke_perimeter must be a boolean"):
            invalid.to_scene()


def test_python_scene_compiles_box_and_contour() -> None:
    box = Figure(width=240, height=160)
    box.axis_options["x"]["domain"] = (-0.5, 1.5)
    box.axis_options["y"]["domain"] = (0.0, 5.0)
    box.box([[1.0, 2.0, 2.5, 3.0, 4.0], [0.5, 1.5, 2.0, 2.5, 3.5]], show_outliers=False)
    svg = _native.scene_svg(box.to_scene())
    assert svg.count("<rect ") >= 3  # clip + two boxes
    assert svg.count("<polyline ") >= 2

    contour = Figure(width=240, height=160)
    z = np.array([[0.0, 1.0, 0.5], [1.0, 2.0, 1.0], [0.5, 1.0, 0.0]], dtype=np.float64)
    contour.contour(z, levels=[0.5, 1.0, 1.5], color="#ef4444")
    assert "<polyline " in _native.scene_svg(contour.to_scene())


@pytest.mark.parametrize("kind", ["line", "scatter"])
def test_python_scene_rejects_missing_coordinates_until_break_records_exist(kind: str) -> None:
    figure = Figure()
    getattr(figure, kind)([0.0, 1.0, 2.0], [1.0, np.nan, 2.0])
    with pytest.raises(UnsupportedSceneV3, match="missing-data breaks"):
        figure.to_scene()
    assert "<svg" in figure.to_svg()


def test_python_scene_encodes_title_and_axis_labels() -> None:
    figure = representative_figure()
    figure.title = "Peak days"
    figure.x_label = "day"
    figure.y_label = "count"
    scene = figure.to_scene()
    assert scene.endswith(b"Peak daysdaycount") or b"Peak days" in scene
    svg = _native.scene_svg(scene)
    assert 'data-xy-chrome="title"' in svg
    assert 'data-xy-chrome="x-label"' in svg
    assert 'data-xy-chrome="y-label"' in svg
    assert "Peak days" in svg and ">day<" in svg and ">count<" in svg


def test_python_scene_compiles_rule_and_band_annotations() -> None:
    figure = representative_figure()
    figure.vline(2.0, color="#ef4444", width=2.0)
    figure.hline(1.0, color="#22c55e")
    figure.x_band(0.5, 1.5, color="#3987e5", opacity=0.25)
    svg = _native.scene_svg(figure.to_scene())
    assert "rgb(239,68,68)" in svg
    assert "rgb(34,197,94)" in svg
    assert "rgb(57,135,229)" in svg


def test_python_scene_admits_plain_and_attached_text_but_rejects_rich_annotations() -> None:
    labeled = representative_figure()
    labeled.vline(1.0, text="threshold")
    assert b"threshold" in labeled.to_scene()
    figure = representative_figure()
    figure.annotations.append(
        {"kind": "text", "x": 1, "y": 2, "text": "note", "style": {"label_background": "#fff"}}
    )
    svg = _native.scene_svg(figure.to_scene())
    assert ">note<" in svg
    assert 'fill="rgba(255,255,255,1.000000)"' in svg


def test_python_scene_frames_attached_label_rgba_in_xyal_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    figure = representative_figure()
    figure.vline(1.0, text="default")
    figure.x_band(
        1.0,
        2.0,
        text="custom",
        style={"label_color": "#102030", "label_opacity": 0.5},
    )
    captured: dict[str, bytes] = {}

    def capture_scene_encode_product(**kwargs: object) -> bytes:
        captured["annotations"] = _xyad_from_figure(figure)
        return b"captured-scene"

    monkeypatch.setattr(_scene_v3._native, "scene_encode_product", capture_scene_encode_product)
    assert figure.to_scene() == b"captured-scene"

    envelope = captured["annotations"]
    assert envelope[:8] == b"XYAD\x02\x00\x00\x00"
    xyat_len = int.from_bytes(envelope[8:12], "little")
    xyal_len = int.from_bytes(envelope[12:16], "little")
    xyal = envelope[24 + xyat_len : 24 + xyat_len + xyal_len]
    assert xyal[:12] == b"XYAL\x02\x00\x00\x00\x02\x00\x00\x00"
    first_id, first_rgba, first_len = struct.unpack_from("<Q4sI", xyal, 12)
    first_text_at = 28
    assert first_id == 0x5859010000000000
    assert first_rgba == bytes((102, 112, 133, 255))
    assert xyal[first_text_at : first_text_at + first_len] == b"default"
    second_at = first_text_at + first_len
    second_id, second_rgba, second_len = struct.unpack_from("<Q4sI", xyal, second_at)
    second_text_at = second_at + 16
    assert second_id == 0x5859020000000001
    assert second_rgba == bytes((16, 32, 48, 128))
    assert xyal[second_text_at : second_text_at + second_len] == b"custom"


def test_python_scene_rejects_attached_label_style_without_a_label() -> None:
    figure = representative_figure()
    figure.vline(1.0, style={"label_color": "#102030"})
    with pytest.raises(UnsupportedSceneV3, match="label_color"):
        figure.to_scene()

    figure = representative_figure()
    figure.vline(1.0, text="threshold", style={"label_opacity": 1.1})
    with pytest.raises(ValueError, match="label opacity"):
        figure.to_scene()


def test_python_scene_attached_label_background_uses_xyal_v3_and_rust_box() -> None:
    figure = representative_figure()
    figure.marker(2.0, 2.0, text="threshold", style={"label_background": "#ffffff"})
    scene = figure.to_scene()
    assert scene[:8] == b"XYGS\x1f\x00\x00\x00"
    assert b"XYLB\x03\x00\x00\x00" in scene
    svg = _native.scene_svg(scene)
    assert "threshold" in svg
    assert 'fill="rgba(255,255,255,1.000000)"' in svg


@pytest.mark.parametrize("kind", ["column", "histogram"])
def test_python_scene_compiles_rect_family_aliases(kind: str) -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    if kind == "column":
        figure.column([1, 2], [3, 2], color="#22c55e", opacity=0.85)
    else:
        figure.histogram([1.0, 1.5, 2.0, 2.5, 3.0], bins=4, range=(0.0, 4.0), color="#22c55e")
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")  # SCENE_VERSION
    svg = _native.scene_svg(scene)
    assert svg.count("<rect ") >= 2  # plot clip plus at least one bar
    assert 'clip-path="url(#xy-scene-plot)"' in svg


def test_python_scene_compiles_rect_corner_radius() -> None:
    rounded = Figure(width=240, height=160)
    rounded.axis_options["x"]["domain"] = (0.0, 2.0)
    rounded.axis_options["y"]["domain"] = (0.0, 3.0)
    rounded.bar([0, 1], [1, 2], corner_radius=4.0)
    scene = rounded.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert svg.count('<path d="M') == 2
    assert rounded.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(rounded) is None
    polar = Figure(width=400, height=400, coords="polar")
    polar.axis_options["x"]["domain"] = (0.0, 6.283185307179586)
    polar.axis_options["y"]["domain"] = (0.0, 1.0)
    polar.bar([0.0], [1.0], corner_radius=4.0)
    pie = polar.to_scene()
    assert pie[4:8] == (31).to_bytes(4, "little")
    pie_svg = _native.scene_svg(pie)
    assert pie_svg.count('<path d="M') == 1
    assert polar.to_svg() == pie_svg
    assert _scene_v3.scene_export_support_reason(polar) is None
    cells = Figure(width=240, height=160)
    cells.axis_options["x"]["domain"] = (0.0, 2.0)
    cells.axis_options["y"]["domain"] = (0.0, 2.0)
    cells.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#3987e5")
    cells.traces[-1].style["corner_radius"] = 6.0
    cell_svg = _native.scene_svg(cells.to_scene())
    assert cell_svg.count('<path d="M') == 4
    assert cells.to_svg() == cell_svg
    assert _scene_v3.scene_export_support_reason(cells) is None
    square_cells = Figure(width=240, height=160)
    square_cells.axis_options["x"]["domain"] = (0.0, 2.0)
    square_cells.axis_options["y"]["domain"] = (0.0, 2.0)
    square_cells.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#3987e5")
    assert cell_svg != _native.scene_svg(square_cells.to_scene())


def test_python_scene_compiles_violin_box_corner_radius() -> None:
    violin = Figure(width=320, height=240)
    violin.axis_options["x"]["domain"] = (-1.0, 5.0)
    violin.axis_options["y"]["domain"] = (-1.0, 5.0)
    violin.violin(
        [[1, 2, 2, 3, 4], [2, 2.5, 3.5]],
        bins=8,
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        style={"fill": "#22c55e"},
    )
    violin.traces[-1].style["corner_radius"] = 6.0
    violin_scene = violin.to_scene()
    assert violin_scene[4:8] == (31).to_bytes(4, "little")
    violin_svg = _native.scene_svg(violin_scene)
    assert '<path d="M' in violin_svg
    assert violin.to_svg() == violin_svg
    assert _scene_v3.scene_export_support_reason(violin) is None
    square_violin = Figure(width=320, height=240)
    square_violin.axis_options["x"]["domain"] = (-1.0, 5.0)
    square_violin.axis_options["y"]["domain"] = (-1.0, 5.0)
    square_violin.violin(
        [[1, 2, 2, 3, 4], [2, 2.5, 3.5]],
        bins=8,
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        style={"fill": "#22c55e"},
    )
    assert violin_svg != _native.scene_svg(square_violin.to_scene())
    rounded_box = Figure(width=320, height=240)
    rounded_box.axis_options["x"]["domain"] = (-2.0, 102.0)
    rounded_box.axis_options["y"]["domain"] = (-2.0, 102.0)
    rounded_box.box(
        [[1, 2, 3, 100], [2, 3, 4, 5]],
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        name="dist",
    )
    next(trace for trace in rounded_box.traces if trace.kind == "box").style["corner_radius"] = 6.0
    box_svg = _native.scene_svg(rounded_box.to_scene())
    assert '<path d="M' in box_svg
    assert rounded_box.to_svg() == box_svg
    assert _scene_v3.scene_export_support_reason(rounded_box) is None
    square_box = Figure(width=320, height=240)
    square_box.axis_options["x"]["domain"] = (-2.0, 102.0)
    square_box.axis_options["y"]["domain"] = (-2.0, 102.0)
    square_box.box(
        [[1, 2, 3, 100], [2, 3, 4, 5]],
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        name="dist",
    )
    assert box_svg != _native.scene_svg(square_box.to_scene())


def test_python_scene_compiles_violin_box_opacity_channels() -> None:
    violin = Figure(width=320, height=240)
    violin.axis_options["x"]["domain"] = (-1.0, 5.0)
    violin.axis_options["y"]["domain"] = (-1.0, 5.0)
    violin.violin(
        [[1, 2, 2, 3, 4], [2, 2.5, 3.5]],
        bins=8,
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        style={"fill": "#22c55e"},
    )
    violin.traces[-1].style["fill_opacity"] = 0.5
    violin_svg = _native.scene_svg(violin.to_scene())
    assert 'fill-opacity="' in violin_svg
    assert violin.to_svg() == violin_svg
    assert _scene_v3.scene_export_support_reason(violin) is None
    square_violin = Figure(width=320, height=240)
    square_violin.axis_options["x"]["domain"] = (-1.0, 5.0)
    square_violin.axis_options["y"]["domain"] = (-1.0, 5.0)
    square_violin.violin(
        [[1, 2, 2, 3, 4], [2, 2.5, 3.5]],
        bins=8,
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        style={"fill": "#22c55e"},
    )
    assert violin_svg != _native.scene_svg(square_violin.to_scene())
    rounded_box = Figure(width=320, height=240)
    rounded_box.axis_options["x"]["domain"] = (-2.0, 102.0)
    rounded_box.axis_options["y"]["domain"] = (-2.0, 102.0)
    rounded_box.box(
        [[1, 2, 3, 100], [2, 3, 4, 5]],
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        name="dist",
    )
    next(trace for trace in rounded_box.traces if trace.kind == "box").style["fill_opacity"] = 0.5
    box_svg = _native.scene_svg(rounded_box.to_scene())
    assert 'fill-opacity="' in box_svg
    assert rounded_box.to_svg() == box_svg
    assert _scene_v3.scene_export_support_reason(rounded_box) is None
    square_box = Figure(width=320, height=240)
    square_box.axis_options["x"]["domain"] = (-2.0, 102.0)
    square_box.axis_options["y"]["domain"] = (-2.0, 102.0)
    square_box.box(
        [[1, 2, 3, 100], [2, 3, 4, 5]],
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        name="dist",
    )
    assert box_svg != _native.scene_svg(square_box.to_scene())


def test_python_scene_compiles_bar_fill_opacity() -> None:
    faded = Figure(width=240, height=160)
    faded.axis_options["x"]["domain"] = (0.0, 2.0)
    faded.axis_options["y"]["domain"] = (0.0, 3.0)
    faded.bar([0, 1], [1, 2], color="#22c55e")
    faded.traces[-1].style["fill_opacity"] = 0.5
    svg = _native.scene_svg(faded.to_scene())
    assert 'fill-opacity="' in svg
    assert faded.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(faded) is None
    solid = Figure(width=240, height=160)
    solid.axis_options["x"]["domain"] = (0.0, 2.0)
    solid.axis_options["y"]["domain"] = (0.0, 3.0)
    solid.bar([0, 1], [1, 2], color="#22c55e")
    assert svg != _native.scene_svg(solid.to_scene())


def test_python_scene_compiles_heatmap_fill_opacity() -> None:
    faded = Figure(width=320, height=240)
    faded.axis_options["x"]["domain"] = (0.0, 4.0)
    faded.axis_options["y"]["domain"] = (0.0, 5.0)
    faded.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#22c55e", opacity=0.75)
    faded.traces[-1].style["fill_opacity"] = 0.5
    svg = _native.scene_svg(faded.to_scene())
    assert 'fill-opacity="' in svg
    assert faded.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(faded) is None
    solid = Figure(width=320, height=240)
    solid.axis_options["x"]["domain"] = (0.0, 4.0)
    solid.axis_options["y"]["domain"] = (0.0, 5.0)
    solid.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#22c55e", opacity=0.75)
    assert svg != _native.scene_svg(solid.to_scene())


def test_python_scene_compiles_heatmap_stroke_opacity() -> None:
    stroked = Figure(width=320, height=240)
    stroked.axis_options["x"]["domain"] = (0.0, 4.0)
    stroked.axis_options["y"]["domain"] = (0.0, 5.0)
    stroked.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#22c55e", opacity=0.75)
    stroked.traces[-1].style["stroke"] = "#111111"
    stroked.traces[-1].style["stroke_width"] = 2.0
    stroked.traces[-1].style["stroke_opacity"] = 0.5
    svg = _native.scene_svg(stroked.to_scene())
    assert 'stroke-opacity="' in svg
    assert stroked.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(stroked) is None
    solid = Figure(width=320, height=240)
    solid.axis_options["x"]["domain"] = (0.0, 4.0)
    solid.axis_options["y"]["domain"] = (0.0, 5.0)
    solid.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#22c55e", opacity=0.75)
    solid.traces[-1].style["stroke"] = "#111111"
    solid.traces[-1].style["stroke_width"] = 2.0
    assert svg != _native.scene_svg(solid.to_scene())


def test_python_scene_compiles_scatter_fill_opacity() -> None:
    faded = Figure(width=240, height=160)
    faded.axis_options["x"]["domain"] = (0.0, 2.0)
    faded.axis_options["y"]["domain"] = (0.0, 2.0)
    faded.scatter([0.5, 1.5], [0.5, 1.5], color="#22c55e", size=18, opacity=0.8)
    faded.traces[-1].style["fill_opacity"] = 0.5
    svg = _native.scene_svg(faded.to_scene())
    assert 'fill-opacity="' in svg
    assert faded.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(faded) is None
    solid = Figure(width=240, height=160)
    solid.axis_options["x"]["domain"] = (0.0, 2.0)
    solid.axis_options["y"]["domain"] = (0.0, 2.0)
    solid.scatter([0.5, 1.5], [0.5, 1.5], color="#22c55e", size=18, opacity=0.8)
    assert svg != _native.scene_svg(solid.to_scene())
    stroked = Figure(width=240, height=160)
    stroked.axis_options["x"]["domain"] = (0.0, 2.0)
    stroked.axis_options["y"]["domain"] = (0.0, 2.0)
    stroked.scatter(
        [0.5, 1.5],
        [0.5, 1.5],
        color="#22c55e",
        size=18,
        opacity=0.8,
        stroke="#111111",
        stroke_width=2.0,
    )
    stroked.traces[-1].style["stroke_opacity"] = 0.5
    stroke_svg = _native.scene_svg(stroked.to_scene())
    assert 'stroke-opacity="' in stroke_svg
    assert stroked.to_svg() == stroke_svg
    assert _scene_v3.scene_export_support_reason(stroked) is None


def test_python_scene_compiles_hexbin_fill_opacity() -> None:
    faded = Figure(width=320, height=240)
    faded.axis_options["x"]["domain"] = (0.0, 4.0)
    faded.axis_options["y"]["domain"] = (0.0, 5.0)
    faded.hexbin(
        [0.5, 1.5, 2.5],
        [0.5, 0.5, 2.0],
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        color="#22c55e",
        opacity=0.75,
    )
    faded.traces[-1].style["fill_opacity"] = 0.5
    svg = _native.scene_svg(faded.to_scene())
    assert 'fill-opacity="' in svg
    assert faded.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(faded) is None
    solid = Figure(width=320, height=240)
    solid.axis_options["x"]["domain"] = (0.0, 4.0)
    solid.axis_options["y"]["domain"] = (0.0, 5.0)
    solid.hexbin(
        [0.5, 1.5, 2.5],
        [0.5, 0.5, 2.0],
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        color="#22c55e",
        opacity=0.75,
    )
    assert svg != _native.scene_svg(solid.to_scene())


def test_python_scene_compiles_hexbin_stroke_opacity() -> None:
    stroked = Figure(width=320, height=240)
    stroked.axis_options["x"]["domain"] = (0.0, 4.0)
    stroked.axis_options["y"]["domain"] = (0.0, 5.0)
    stroked.hexbin(
        [0.5, 1.5, 2.5],
        [0.5, 0.5, 2.0],
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        color="#22c55e",
        opacity=0.75,
    )
    stroked.traces[-1].style["stroke"] = "#111111"
    stroked.traces[-1].style["stroke_width"] = 2.0
    stroked.traces[-1].style["stroke_opacity"] = 0.5
    svg = _native.scene_svg(stroked.to_scene())
    assert 'stroke-opacity="' in svg
    assert stroked.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(stroked) is None
    solid = Figure(width=320, height=240)
    solid.axis_options["x"]["domain"] = (0.0, 4.0)
    solid.axis_options["y"]["domain"] = (0.0, 5.0)
    solid.hexbin(
        [0.5, 1.5, 2.5],
        [0.5, 0.5, 2.0],
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        color="#22c55e",
        opacity=0.75,
    )
    solid.traces[-1].style["stroke"] = "#111111"
    solid.traces[-1].style["stroke_width"] = 2.0
    assert svg != _native.scene_svg(solid.to_scene())


def test_python_scene_compiles_polar_hexbin() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, math.tau)
    figure.axis_options["y"]["domain"] = (0.0, 4.0)
    figure.hexbin(
        [0.5, 1.5, 2.5],
        [1.0, 2.0, 3.0],
        gridsize=(4, 4),
        range=((0.0, math.tau), (0.0, 4.0)),
        color="#3987e5",
        mincnt=1,
    )
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert svg.count('<path d="M ') == len(figure.traces[0].x.values)
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None
    painted = Figure(width=400, height=400, coords="polar")
    painted.axis_options["x"]["domain"] = (0.0, math.tau)
    painted.axis_options["y"]["domain"] = (0.0, 4.0)
    painted.hexbin(
        [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0],
        [1.0, 1.0, 1.0, 1.0, 3.0, 3.0, 3.0],
        gridsize=(4, 4),
        range=((0.0, math.tau), (0.0, 4.0)),
        colormap="viridis",
        mincnt=1,
    )
    painted_svg = _native.scene_svg(painted.to_scene())
    assert painted_svg.count('<path d="M ') == len(painted.traces[0].x.values)
    fills = {
        part.split('fill="', 1)[1].split('"', 1)[0]
        for part in painted_svg.split("<path ")[1:]
        if 'fill="' in part
    }
    assert len(fills) > 1
    assert painted.to_svg() == painted_svg
    assert _scene_v3.scene_export_support_reason(painted) is None


def test_python_scene_compiles_hexbin_direct_rgba_and_categorical() -> None:
    direct = Figure(width=320, height=240)
    direct.axis_options["x"]["domain"] = (0.0, 4.0)
    direct.axis_options["y"]["domain"] = (0.0, 5.0)
    direct.hexbin(
        [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0],
        [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0],
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        color="#3987e5",
    )
    n = len(direct.traces[0].x.values)
    assert n >= 2
    rgba = np.zeros((n, 4), dtype=np.float64)
    rgba[:, 3] = 1.0
    rgba[0] = (1.0, 0.0, 0.0, 1.0)
    rgba[1] = (0.0, 1.0, 0.0, 1.0)
    direct.traces[0].color_ch = ColorChannel(mode="direct_rgba", rgba=rgba)
    direct_svg = _native.scene_svg(direct.to_scene())
    assert direct_svg.count('<path d="M ') == n
    fills = {
        part.split('fill="', 1)[1].split('"', 1)[0]
        for part in direct_svg.split("<path ")[1:]
        if 'fill="' in part
    }
    assert len(fills) > 1
    assert direct.to_svg() == direct_svg
    assert _scene_v3.scene_export_support_reason(direct) is None
    categorical = Figure(width=320, height=240)
    categorical.axis_options["x"]["domain"] = (0.0, 4.0)
    categorical.axis_options["y"]["domain"] = (0.0, 5.0)
    categorical.hexbin(
        [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0],
        [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0],
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        color="#3987e5",
    )
    n = len(categorical.traces[0].x.values)
    categorical.traces[0].color_ch = ColorChannel(
        mode="categorical",
        codes=np.arange(n, dtype=np.int64) % 2,
        categories=["a", "b"],
        palette=["#ef4444", "#22c55e"],
    )
    cat_svg = _native.scene_svg(categorical.to_scene())
    assert cat_svg.count('<path d="M ') == n
    cat_fills = {
        part.split('fill="', 1)[1].split('"', 1)[0]
        for part in cat_svg.split("<path ")[1:]
        if 'fill="' in part
    }
    assert len(cat_fills) > 1
    assert categorical.to_svg() == cat_svg
    assert _scene_v3.scene_export_support_reason(categorical) is None


def test_python_scene_compiles_triangle_mesh_fill_opacity() -> None:
    faded = Figure(width=240, height=160)
    faded.axis_options["x"]["domain"] = (0.0, 1.0)
    faded.axis_options["y"]["domain"] = (0.0, 1.0)
    faded.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0], color="#22c55e", opacity=0.75)
    faded.traces[-1].style["fill_opacity"] = 0.5
    svg = _native.scene_svg(faded.to_scene())
    assert 'fill-opacity="' in svg
    assert faded.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(faded) is None
    solid = Figure(width=240, height=160)
    solid.axis_options["x"]["domain"] = (0.0, 1.0)
    solid.axis_options["y"]["domain"] = (0.0, 1.0)
    solid.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0], color="#22c55e", opacity=0.75)
    assert svg != _native.scene_svg(solid.to_scene())
    stroked = Figure(width=240, height=160)
    stroked.axis_options["x"]["domain"] = (0.0, 1.0)
    stroked.axis_options["y"]["domain"] = (0.0, 1.0)
    stroked.triangle_mesh(
        [0.0],
        [0.0],
        [1.0],
        [0.0],
        [0.5],
        [1.0],
        color="#22c55e",
        opacity=0.75,
        stroke="#111111",
        stroke_width=2.0,
    )
    stroked.traces[-1].style["stroke_opacity"] = 0.5
    stroke_svg = _native.scene_svg(stroked.to_scene())
    assert 'stroke-opacity="' in stroke_svg
    assert stroked.to_svg() == stroke_svg
    assert _scene_v3.scene_export_support_reason(stroked) is None


def test_python_scene_compiles_triangle_mesh_joined_fill() -> None:
    joined = Figure(width=240, height=160)
    joined.axis_options["x"]["domain"] = (0.0, 1.0)
    joined.axis_options["y"]["domain"] = (0.0, 1.0)
    joined.triangle_mesh(
        [0.0, 1.0],
        [0.0, 0.0],
        [1.0, 1.0],
        [0.0, 1.0],
        [0.0, 0.0],
        [1.0, 1.0],
        color="#22c55e",
    )
    joined.traces[-1].style["joined_fill"] = True
    svg = _native.scene_svg(joined.to_scene())
    assert svg.count('<path d="M') == 1
    assert joined.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(joined) is None
    unjoined = Figure(width=240, height=160)
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
    unjoined_svg = _native.scene_svg(unjoined.to_scene())
    assert unjoined_svg.count('<path d="M') == 2
    assert svg != unjoined_svg
    disconnected = Figure(width=240, height=160)
    disconnected.axis_options["x"]["domain"] = (0.0, 2.0)
    disconnected.axis_options["y"]["domain"] = (0.0, 2.0)
    disconnected.triangle_mesh(
        [0.0, 1.5],
        [0.0, 1.0],
        [1.0, 2.0],
        [0.0, 1.0],
        [0.5, 1.75],
        [1.0, 1.75],
        color="#22c55e",
    )
    disconnected.traces[-1].style["joined_fill"] = True
    disconnected_svg = _native.scene_svg(disconnected.to_scene())
    assert disconnected_svg.count('<path d="M') == 2
    assert disconnected.to_svg() == disconnected_svg
    assert _scene_v3.scene_export_support_reason(disconnected) is None


def test_python_scene_compiles_polar_corner_radius() -> None:
    donut = Figure(width=400, height=400, coords="polar")
    donut.axis_options["x"]["domain"] = (0.0, 6.283185307179586)
    donut.axis_options["y"]["domain"] = (0.0, 1.0)
    donut.bar([0.0, 1.5], [1.0, 0.8], base=0.25, corner_radius=14.0, color="#2563eb")
    scene = donut.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert svg.count('<path d="M') == 2
    assert donut.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(donut) is None
    heatmap = Figure(width=400, height=400, coords="polar")
    heatmap.axis_options["x"]["domain"] = (0.0, 6.283185307179586)
    heatmap.axis_options["y"]["domain"] = (0.0, 1.0)
    heatmap.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#3987e5")
    heatmap.traces[-1].style["corner_radius"] = 4.0
    scene = heatmap.to_scene()
    svg = _native.scene_svg(scene)
    assert svg.count('<path d="M') == 4
    assert heatmap.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(heatmap) is None
    square = Figure(width=400, height=400, coords="polar")
    square.axis_options["x"]["domain"] = (0.0, 6.283185307179586)
    square.axis_options["y"]["domain"] = (0.0, 1.0)
    square.heatmap([[1.0, 2.0], [3.0, 4.0]], color="#3987e5")
    assert svg != _native.scene_svg(square.to_scene())


def test_python_scene_compiles_polar_wedge_gap() -> None:
    gapped = Figure(width=400, height=400, coords="polar")
    gapped.axis_options["x"]["domain"] = (0.0, 6.283185307179586)
    gapped.axis_options["y"]["domain"] = (0.0, 1.0)
    gapped.bar([0.0, 1.5], [1.0, 0.8], wedge_gap=12.0, color="#2563eb")
    scene = gapped.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert svg.count('<path d="M') == 2
    assert gapped.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(gapped) is None
    cartesian = Figure(width=240, height=160)
    cartesian.axis_options["x"]["domain"] = (0.0, 2.0)
    cartesian.axis_options["y"]["domain"] = (0.0, 3.0)
    cartesian.bar([0, 1], [1, 2], wedge_gap=12.0)
    with pytest.raises(UnsupportedSceneV3, match="wedge_gap"):
        cartesian.to_scene()


def test_python_scene_compiles_polar_density_tessellation() -> None:
    figure = Figure(width=400, height=400, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, math.tau)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.scatter([0.0, math.pi / 2], [0.5, 1.0], density=True, color="#3987e5")
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert scene[-92:-88] == b"XYPL"
    assert b"XYIM" not in scene
    svg = _native.scene_svg(scene)
    assert "<path" in svg and 'd="M' in svg
    assert "<image" not in svg
    assert "<rect x=" not in svg
    assert 'data-xy-grid="ring"' in svg or 'data-xy-frame="polar"' in svg
    assert figure.to_svg() == svg


def test_python_scene_compiles_cartesian_density_blit() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (-1.0, 1.0)
    figure.axis_options["y"]["domain"] = (-1.0, 1.0)
    figure.scatter([0.0] * 200_000, [0.0] * 200_000, density=True, color="#3987e5")
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYIM" in scene
    svg = _native.scene_svg(scene)
    assert svg.count("<image") == 1
    assert "data:image/png;base64," in svg
    assert figure.to_svg() == svg


def test_python_scene_compiles_cartesian_mean_color_density() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    x = [0.25] * 80 + [0.75] * 80
    y = [0.5] * 160
    color = [0.0] * 80 + [1.0] * 80
    figure.scatter(x, y, color=color, density=True)
    assert _scene_v3.scene_export_support_reason(figure) is None
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYIM" in scene
    svg = _native.scene_svg(scene)
    assert svg.count("<image") == 1
    assert "data:image/png;base64," in svg
    assert figure.to_svg() == svg

    sized = Figure(width=240, height=160)
    sized.axis_options["x"]["domain"] = (0.0, 1.0)
    sized.axis_options["y"]["domain"] = (0.0, 1.0)
    sized.scatter(x, y, color=color, size=[4.0] * 80 + [8.0] * 80, density=True)
    with pytest.raises(UnsupportedSceneV3, match="hidden or per-item"):
        sized.to_scene()

    polar = Figure(width=240, height=160, coords="polar")
    polar.axis_options["x"]["domain"] = (0.0, 1.0)
    polar.axis_options["y"]["domain"] = (0.0, 1.0)
    polar.scatter(x, y, color=color, density=True)
    polar_scene = polar.to_scene()
    assert polar_scene[-92:-88] == b"XYPL"
    assert b"XYIM" not in polar_scene
    polar_svg = _native.scene_svg(polar_scene)
    assert "<path" in polar_svg
    assert "<image" not in polar_svg
    assert polar.to_svg() == polar_svg


def test_python_scene_rejects_hidden_and_unknown_kind() -> None:
    hidden = Figure().line([0.0, 1.0], [0.0, 1.0])
    hidden.traces[0].hidden = True
    with pytest.raises(UnsupportedSceneV3, match="hidden or per-item"):
        hidden.to_scene()
    unknown = Figure().line([0.0, 1.0], [0.0, 1.0])
    unknown.traces[0].kind = "text"
    with pytest.raises(UnsupportedSceneV3, match="does not yet support text"):
        unknown.to_scene()


def test_python_scene_rejects_unequal_rect_columns() -> None:
    figure = Figure(width=200, height=120)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.bar([0, 1], [1, 2])
    figure.traces[0].x1 = figure.store.ingest([0.5])  # length mismatch vs x0
    with pytest.raises(UnsupportedSceneV3, match="invalid scene trace packing"):
        figure.to_scene()


def test_python_scene_compiles_segments_and_step_lines() -> None:
    segments = Figure(width=240, height=160)
    segments.axis_options["x"]["domain"] = (0.0, 2.0)
    segments.axis_options["y"]["domain"] = (0.0, 2.0)
    segments.segments([0.0, 1.0], [0.0, 0.0], [1.0, 2.0], [1.0, 1.0], color="#ef4444", width=2.0)
    svg = _native.scene_svg(segments.to_scene())
    assert svg.count("<polyline ") == 2

    stepped = Figure(width=240, height=160)
    stepped.axis_options["x"]["domain"] = (0.0, 2.0)
    stepped.axis_options["y"]["domain"] = (0.0, 3.0)
    stepped.step([0.0, 1.0, 2.0], [1.0, 2.0, 1.0], where="post", color="#3987e5")
    svg_step = _native.scene_svg(stepped.to_scene())
    assert svg_step.count("<polyline ") == 1


def test_python_scene_compiles_stem_errorbar_and_violin() -> None:
    stem = Figure(width=240, height=160)
    stem.axis_options["x"]["domain"] = (-0.5, 1.5)
    stem.axis_options["y"]["domain"] = (0.0, 3.0)
    stem.stem([0.0, 1.0], [1.0, 2.0], color="#22c55e")
    svg = _native.scene_svg(stem.to_scene())
    assert svg.count("<polyline ") == 2
    assert "<circle " in svg or "<path " in svg  # stem markers

    errors = Figure(width=240, height=160)
    errors.axis_options["x"]["domain"] = (-0.5, 1.5)
    errors.axis_options["y"]["domain"] = (0.0, 3.0)
    errors.errorbar([0.0, 1.0], [1.0, 2.0], yerr=0.2, color="#ef4444")
    assert "<polyline " in _native.scene_svg(errors.to_scene())

    violin = Figure(width=240, height=160)
    violin.axis_options["x"]["domain"] = (-1.0, 2.0)
    violin.axis_options["y"]["domain"] = (0.0, 5.0)
    violin.violin([[1.0, 2.0, 2.5, 3.0, 2.0]])
    assert _native.scene_svg(violin.to_scene()).count("<rect ") >= 2


def test_python_scene_compiles_constant_dash_polylines() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.line([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], color="#ef4444", width=2.0, dash="dashed")
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYDS" in scene
    svg = _native.scene_svg(scene)
    assert 'stroke-dasharray="6,4"' in svg
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None
    marked = Figure().line([0.0, 1.0], [0.0, 1.0], dash="dashed")
    marked.traces[-1].style["marker_path"] = "M0 0"
    with pytest.raises(UnsupportedSceneV3, match="authored markers"):
        marked.to_scene()


def test_python_scene_compiles_constant_linecap_polylines() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.line(
        [0.0, 1.0, 2.0],
        [0.0, 1.0, 0.5],
        color="#ef4444",
        width=2.0,
        style={"stroke-linecap": "butt"},
    )
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYLC" in scene
    svg = _native.scene_svg(scene)
    assert 'stroke-linecap="butt"' in svg
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None
    unknown = Figure().line([0.0, 1.0], [0.0, 1.0])
    unknown.traces[-1].style["linecap"] = "flat"
    with pytest.raises(UnsupportedSceneV3, match="authored markers"):
        unknown.to_scene()
    marked = Figure().line([0.0, 1.0], [0.0, 1.0], style={"stroke-linecap": "butt"})
    marked.traces[-1].style["marker_path"] = "M0 0"
    with pytest.raises(UnsupportedSceneV3, match="authored markers"):
        marked.to_scene()


_DIAMOND_MARKER_PATH = {
    "contours": [[-0.5, 0.0, 0.0, 0.5, 0.5, 0.0, 0.0, -0.5]],
    "filled": True,
}
_PLUS_MARKER_PATH = {
    "contours": [[-0.5, 0.0, 0.5, 0.0], [0.0, -0.5, 0.0, 0.5]],
    "filled": False,
}


def test_python_scene_compiles_constant_marker_paths() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.scatter(
        [0.5, 1.5],
        [0.5, 1.5],
        color="#336699",
        size=12,
        _marker_path=_DIAMOND_MARKER_PATH,
    )
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYMP" not in scene
    svg = _native.scene_svg(scene)
    assert '<path d="M ' in svg
    assert ' Z"' in svg
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None

    plus = Figure(width=240, height=160)
    plus.axis_options["x"]["domain"] = (0.0, 2.0)
    plus.axis_options["y"]["domain"] = (0.0, 2.0)
    plus.scatter([1.0], [1.0], color="#336699", size=12, _marker_path=_PLUS_MARKER_PATH)
    plus_svg = _native.scene_svg(plus.to_scene())
    assert plus_svg.count("<polyline ") == 2
    assert 'stroke-width="1"' in plus_svg
    assert plus.to_svg() == plus_svg
    assert _scene_v3.scene_export_support_reason(plus) is None

    polar = Figure(width=400, height=400, coords="polar")
    polar.axis_options["x"]["domain"] = (0.0, math.tau)
    polar.axis_options["y"]["domain"] = (0.0, 1.0)
    polar.scatter([0.0], [0.5], color="#336699", size=12, _marker_path=_DIAMOND_MARKER_PATH)
    polar_svg = _native.scene_svg(polar.to_scene())
    assert '<path d="M ' in polar_svg
    assert polar.to_svg() == polar_svg
    assert _scene_v3.scene_export_support_reason(polar) is None

    invalid = Figure().scatter([1.0], [1.0])
    invalid.traces[-1].style["marker_path"] = "M0 0"
    with pytest.raises(UnsupportedSceneV3, match="authored markers"):
        invalid.to_scene()


def test_python_scene_compiles_constant_marker_glyphs() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.scatter([1.0], [1.0], color="#336699", size=12, _marker_glyph="A")
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYMG" in scene
    svg = _native.scene_svg(scene)
    assert 'font-family="DejaVu Sans"' in svg
    assert 'dominant-baseline="central"' in svg
    assert 'text-anchor="middle"' in svg
    assert ">A</text>" in svg
    assert "<circle " not in svg
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None

    club = Figure(width=240, height=160)
    club.axis_options["x"]["domain"] = (0.0, 2.0)
    club.axis_options["y"]["domain"] = (0.0, 2.0)
    club.scatter([1.0], [1.0], color="#336699", size=12, _marker_glyph="♣")
    club_svg = _native.scene_svg(club.to_scene())
    assert ">♣</text>" in club_svg
    assert club.to_svg() == club_svg

    multi = Figure(width=240, height=160)
    multi.axis_options["x"]["domain"] = (0.0, 2.0)
    multi.axis_options["y"]["domain"] = (0.0, 2.0)
    multi.scatter([1.0], [1.0], color="#336699", size=12, _marker_glyph="AB")
    multi_svg = _native.scene_svg(multi.to_scene())
    assert ">AB</text>" in multi_svg
    assert multi.to_svg() == multi_svg
    assert _scene_v3.scene_export_support_reason(multi) is None

    polar = Figure(width=400, height=400, coords="polar")
    polar.axis_options["x"]["domain"] = (0.0, math.tau)
    polar.axis_options["y"]["domain"] = (0.0, 1.0)
    polar.scatter([0.0], [0.5], color="#336699", size=12, _marker_glyph="A")
    polar_svg = _native.scene_svg(polar.to_scene())
    assert ">A</text>" in polar_svg
    assert polar.to_svg() == polar_svg
    assert _scene_v3.scene_export_support_reason(polar) is None

    both = Figure().scatter([1.0], [1.0], _marker_glyph="A")
    both.traces[-1].style["marker_path"] = _DIAMOND_MARKER_PATH
    with pytest.raises(UnsupportedSceneV3, match="authored markers"):
        both.to_scene()
    invalid = Figure().scatter([1.0], [1.0])
    invalid.traces[-1].style["marker_glyph"] = "A" * 65
    with pytest.raises(UnsupportedSceneV3, match="authored markers"):
        invalid.to_scene()


def test_python_scene_compiles_constant_linear_gradient_fills() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 3.0)
    figure.bar([0.0, 1.0], [1.0, 2.0], fill="linear-gradient(to bottom, #000000, #ffffff)")
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    assert b"XYGR" in scene
    svg = _native.scene_svg(scene)
    assert '<linearGradient id="xy-scene-g0"' in svg
    assert 'fill="url(#xy-scene-g0)"' in svg
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None

    area = Figure(width=240, height=160)
    area.axis_options["x"]["domain"] = (0.0, 2.0)
    area.axis_options["y"]["domain"] = (0.0, 2.0)
    area.area(
        [0.0, 1.0, 2.0], [0.5, 1.5, 0.75], fill="linear-gradient(to bottom, #000000, #ffffff)"
    )
    area_svg = _native.scene_svg(area.to_scene())
    assert '<linearGradient id="xy-scene-g0"' in area_svg
    assert area.to_svg() == area_svg
    assert _scene_v3.scene_export_support_reason(area) is None

    transparent = Figure(width=240, height=160)
    transparent.axis_options["x"]["domain"] = (0.0, 2.0)
    transparent.axis_options["y"]["domain"] = (0.0, 3.0)
    transparent.bar([0.0, 1.0], [1.0, 2.0], fill="linear-gradient(#ff0000, transparent)")
    transparent_svg = _native.scene_svg(transparent.to_scene())
    assert 'stop-color="rgb(255,0,0)" stop-opacity="0"' in transparent_svg
    assert 'stop-color="rgb(0,0,0)" stop-opacity="0"' not in transparent_svg
    assert transparent.to_svg() == transparent_svg

    plot_space = Figure(width=240, height=160)
    plot_space.axis_options["x"]["domain"] = (0.0, 2.0)
    plot_space.axis_options["y"]["domain"] = (0.0, 3.0)
    plot_space.bar(
        [0.0, 1.0],
        [1.0, 2.0],
        fill={"gradient": "linear-gradient(to right, #000000, #ffffff)", "space": "plot"},
    )
    plot_svg = _native.scene_svg(plot_space.to_scene())
    assert 'gradientUnits="userSpaceOnUse"' in plot_svg
    assert plot_space.to_svg() == plot_svg

    ribbon = Figure(width=240, height=160)
    ribbon.axis_options["x"]["domain"] = (0.0, 1.0)
    ribbon.axis_options["y"]["domain"] = (0.0, 1.0)
    ribbon.area([0.0, 1.0], [0.2, 0.8], fill="linear-gradient(to bottom, var(--a), #ffffff)")
    with pytest.raises(UnsupportedSceneV3, match=r"solid literal paints|gradient fills|non-CSS"):
        ribbon.to_scene()


def _polyline_vertex_count(svg: str) -> int:
    counts = [len(points.split()) for points in re.findall(r"<polyline points=\"([^\"]+)\"", svg)]
    assert counts
    return max(counts)


def test_python_scene_compiles_smooth_polylines() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.line(
        [0.0, 1.0, 2.0],
        [0.0, 1.0, 0.5],
        color="#ef4444",
        width=2.0,
        curve="smooth",
    )
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    linear = Figure(width=240, height=160)
    linear.axis_options["x"]["domain"] = (0.0, 2.0)
    linear.axis_options["y"]["domain"] = (0.0, 2.0)
    linear.line([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], color="#ef4444", width=2.0)
    linear_svg = _native.scene_svg(linear.to_scene())
    assert _polyline_vertex_count(svg) == 1 + (3 - 1) * 16
    assert _polyline_vertex_count(linear_svg) == 3
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None

    combined = Figure(width=240, height=160)
    combined.axis_options["x"]["domain"] = (0.0, 2.0)
    combined.axis_options["y"]["domain"] = (0.0, 2.0)
    combined.line(
        [0.0, 1.0, 2.0],
        [0.0, 1.0, 0.5],
        color="#ef4444",
        width=2.0,
        curve="smooth",
        dash="dashed",
        style={"stroke-linecap": "butt"},
    )
    combined_scene = combined.to_scene()
    assert b"XYDS" in combined_scene
    assert b"XYLC" in combined_scene
    combined_svg = _native.scene_svg(combined_scene)
    assert 'stroke-dasharray="6,4"' in combined_svg
    assert 'stroke-linecap="butt"' in combined_svg
    assert combined.to_svg() == combined_svg
    assert _polyline_vertex_count(combined_svg) == 1 + (3 - 1) * 16

    short = Figure(width=240, height=160)
    short.axis_options["x"]["domain"] = (0.0, 1.0)
    short.axis_options["y"]["domain"] = (0.0, 1.0)
    short.line([0.0, 1.0], [0.0, 1.0], curve="smooth")
    assert _scene_v3.scene_export_support_reason(short) is None
    short.to_scene()

    polar = Figure(width=400, height=400, coords="polar")
    polar.axis_options["x"]["domain"] = (0.0, math.tau)
    polar.axis_options["y"]["domain"] = (0.0, 1.0)
    polar.line([0.0, math.pi / 2, math.pi], [0.5, 1.0, 0.5], curve="smooth", color="#ef4444")
    polar_linear = Figure(width=400, height=400, coords="polar")
    polar_linear.axis_options["x"]["domain"] = (0.0, math.tau)
    polar_linear.axis_options["y"]["domain"] = (0.0, 1.0)
    polar_linear.line([0.0, math.pi / 2, math.pi], [0.5, 1.0, 0.5], color="#ef4444")
    polar_svg = _native.scene_svg(polar.to_scene())
    assert polar_svg == _native.scene_svg(polar_linear.to_scene())
    assert polar.to_svg() == polar_svg
    assert _scene_v3.scene_export_support_reason(polar) is None
    stepped = Figure(width=400, height=400, coords="polar")
    stepped.axis_options["x"]["domain"] = (0.0, math.tau)
    stepped.axis_options["y"]["domain"] = (0.0, 1.0)
    stepped.line([0.0, math.pi / 2, math.pi], [0.5, 1.0, 0.5], color="#ef4444")
    stepped.traces[-1].style["step"] = "mid"
    stepped_smooth = Figure(width=400, height=400, coords="polar")
    stepped_smooth.axis_options["x"]["domain"] = (0.0, math.tau)
    stepped_smooth.axis_options["y"]["domain"] = (0.0, 1.0)
    stepped_smooth.line(
        [0.0, math.pi / 2, math.pi], [0.5, 1.0, 0.5], curve="smooth", color="#ef4444"
    )
    stepped_smooth.traces[-1].style["step"] = "mid"
    stepped_svg = _native.scene_svg(stepped.to_scene())
    stepped_smooth_svg = _native.scene_svg(stepped_smooth.to_scene())
    assert stepped_smooth_svg == stepped_svg
    assert stepped_smooth_svg != polar_svg
    assert stepped_smooth.to_svg() == stepped_smooth_svg
    assert _scene_v3.scene_export_support_reason(stepped_smooth) is None
    cartesian_both = Figure(width=240, height=160)
    cartesian_both.axis_options["x"]["domain"] = (0.0, 2.0)
    cartesian_both.axis_options["y"]["domain"] = (0.0, 2.0)
    cartesian_both.line([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], curve="smooth")
    cartesian_both.traces[-1].style["step"] = "mid"
    cartesian_step = Figure(width=240, height=160)
    cartesian_step.axis_options["x"]["domain"] = (0.0, 2.0)
    cartesian_step.axis_options["y"]["domain"] = (0.0, 2.0)
    cartesian_step.line([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    cartesian_step.traces[-1].style["step"] = "mid"
    cartesian_both_svg = _native.scene_svg(cartesian_both.to_scene())
    cartesian_step_svg = _native.scene_svg(cartesian_step.to_scene())
    assert cartesian_both_svg == cartesian_step_svg
    assert cartesian_both_svg != svg
    assert cartesian_both.to_svg() == cartesian_both_svg
    assert _scene_v3.scene_export_support_reason(cartesian_both) is None
    cartesian_area_both = Figure(width=240, height=160)
    cartesian_area_both.axis_options["x"]["domain"] = (0.0, 2.0)
    cartesian_area_both.axis_options["y"]["domain"] = (0.0, 2.0)
    cartesian_area_both.area([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], curve="smooth")
    cartesian_area_both.traces[-1].style["step"] = "mid"
    cartesian_area_step = Figure(width=240, height=160)
    cartesian_area_step.axis_options["x"]["domain"] = (0.0, 2.0)
    cartesian_area_step.axis_options["y"]["domain"] = (0.0, 2.0)
    cartesian_area_step.area([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    cartesian_area_step.traces[-1].style["step"] = "mid"
    cartesian_area_both_svg = _native.scene_svg(cartesian_area_both.to_scene())
    cartesian_area_step_svg = _native.scene_svg(cartesian_area_step.to_scene())
    cartesian_area_linear = Figure(width=240, height=160)
    cartesian_area_linear.axis_options["x"]["domain"] = (0.0, 2.0)
    cartesian_area_linear.axis_options["y"]["domain"] = (0.0, 2.0)
    cartesian_area_linear.area([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    cartesian_area_linear_svg = _native.scene_svg(cartesian_area_linear.to_scene())
    assert cartesian_area_both_svg == cartesian_area_step_svg
    assert cartesian_area_both_svg != cartesian_area_linear_svg
    assert cartesian_area_both.to_svg() == cartesian_area_both_svg
    assert _scene_v3.scene_export_support_reason(cartesian_area_both) is None
    cartesian_band_both = Figure(width=240, height=160)
    cartesian_band_both.axis_options["x"]["domain"] = (0.0, 2.0)
    cartesian_band_both.axis_options["y"]["domain"] = (0.0, 2.0)
    cartesian_band_both.error_band([0.0, 1.0, 2.0], [0.0, 0.5, 0.2], [0.5, 1.0, 0.8])
    cartesian_band_both.traces[-1].style["curve"] = "smooth"
    cartesian_band_both.traces[-1].style["step"] = "mid"
    cartesian_band_step = Figure(width=240, height=160)
    cartesian_band_step.axis_options["x"]["domain"] = (0.0, 2.0)
    cartesian_band_step.axis_options["y"]["domain"] = (0.0, 2.0)
    cartesian_band_step.error_band([0.0, 1.0, 2.0], [0.0, 0.5, 0.2], [0.5, 1.0, 0.8])
    cartesian_band_step.traces[-1].style["step"] = "mid"
    cartesian_band_both_svg = _native.scene_svg(cartesian_band_both.to_scene())
    cartesian_band_step_svg = _native.scene_svg(cartesian_band_step.to_scene())
    assert cartesian_band_both_svg == cartesian_band_step_svg
    assert cartesian_band_both.to_svg() == cartesian_band_both_svg
    assert _scene_v3.scene_export_support_reason(cartesian_band_both) is None
    marked = Figure().line([0.0, 1.0], [0.0, 1.0])
    marked.traces[-1].style["marker_path"] = "M0 0"
    with pytest.raises(UnsupportedSceneV3, match="authored markers"):
        marked.to_scene()


def _closed_path_point_count(svg: str) -> int:
    counts = []
    for path in re.findall(r'<path d="([^"]+)"', svg):
        if "Z" not in path:
            continue
        tokens = path.replace("Z", " ").replace("M", " ").replace("L", " ").split()
        counts.append(len(tokens) // 2)
    assert counts
    return max(counts)


def test_python_scene_compiles_smooth_areas() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.area(
        [0.0, 1.0, 2.0],
        [0.0, 1.0, 0.5],
        color="#ef4444",
        curve="smooth",
    )
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    linear = Figure(width=240, height=160)
    linear.axis_options["x"]["domain"] = (0.0, 2.0)
    linear.axis_options["y"]["domain"] = (0.0, 2.0)
    linear.area([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], color="#ef4444")
    linear_svg = _native.scene_svg(linear.to_scene())
    expected = 1 + (3 - 1) * 16
    assert _closed_path_point_count(svg) == expected * 2
    assert _closed_path_point_count(linear_svg) == 3 * 2
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None

    short = Figure(width=240, height=160)
    short.axis_options["x"]["domain"] = (0.0, 1.0)
    short.axis_options["y"]["domain"] = (0.0, 1.0)
    short.area([0.0, 1.0], [0.0, 1.0], curve="smooth")
    assert _scene_v3.scene_export_support_reason(short) is None
    short.to_scene()

    polar = Figure(width=400, height=400, coords="polar")
    polar.axis_options["x"]["domain"] = (0.0, math.tau)
    polar.axis_options["y"]["domain"] = (0.0, 1.0)
    polar.area([0.0, math.pi / 2, math.pi], [0.4, 0.8, 0.6], curve="smooth", color="#22c55e")
    polar_linear = Figure(width=400, height=400, coords="polar")
    polar_linear.axis_options["x"]["domain"] = (0.0, math.tau)
    polar_linear.axis_options["y"]["domain"] = (0.0, 1.0)
    polar_linear.area([0.0, math.pi / 2, math.pi], [0.4, 0.8, 0.6], color="#22c55e")
    polar_svg = _native.scene_svg(polar.to_scene())
    assert polar_svg == _native.scene_svg(polar_linear.to_scene())
    assert polar.to_svg() == polar_svg
    assert _scene_v3.scene_export_support_reason(polar) is None


def test_python_scene_compiles_smooth_error_bands() -> None:
    figure = Figure(width=240, height=160)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.error_band([0.0, 1.0, 2.0], [0.0, 0.5, 0.2], [0.5, 1.0, 0.8], color="#22c55e")
    figure.traces[0].style["curve"] = "smooth"
    scene = figure.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    linear = Figure(width=240, height=160)
    linear.axis_options["x"]["domain"] = (0.0, 2.0)
    linear.axis_options["y"]["domain"] = (0.0, 2.0)
    linear.error_band([0.0, 1.0, 2.0], [0.0, 0.5, 0.2], [0.5, 1.0, 0.8], color="#22c55e")
    linear_svg = _native.scene_svg(linear.to_scene())
    expected = 1 + (3 - 1) * 16
    assert _closed_path_point_count(svg) == expected * 2
    assert _closed_path_point_count(linear_svg) == 3 * 2
    assert figure.to_svg() == svg
    assert _scene_v3.scene_export_support_reason(figure) is None
