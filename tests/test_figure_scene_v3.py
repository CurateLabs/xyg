from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import pytest

from xyg import _native, _scene_v3, kernels
from xyg._figure import Figure
from xyg._scene_v3 import UnsupportedSceneV3

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())


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
    figure.legend_options = {"loc": "best"}
    with pytest.raises(UnsupportedSceneV3, match="location"):
        figure.to_scene()
    figure.legend_options = {"loc": ""}
    with pytest.raises(UnsupportedSceneV3, match="location"):
        figure.to_scene()


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


def test_supported_public_exports_route_through_rust_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], color="#3987e5")

    scene_svg = _native.scene_svg
    scene_raster_commands = _native.scene_raster_commands
    calls = {"svg": 0, "raster": 0}

    def observed_scene_svg(*args: object, **kwargs: object) -> str:
        calls["svg"] += 1
        return scene_svg(*args, **kwargs)  # type: ignore[arg-type]

    def observed_scene_raster(*args: object, **kwargs: object) -> bytes:
        calls["raster"] += 1
        return scene_raster_commands(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_native, "scene_svg", observed_scene_svg)
    monkeypatch.setattr(_native, "scene_raster_commands", observed_scene_raster)
    svg = figure.to_svg()
    assert "XYGS" not in svg  # the public string is Rust's rendered SVG, not Scene bytes
    assert figure.to_scene()[:4] == b"XYGS"
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")
    assert calls["svg"] >= 2  # direct SVG plus PDF via Rust SVG
    assert calls["raster"] >= 1


def test_public_exporters_share_one_scene_selection_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Format routing belongs to Scene orchestration, not each Python exporter."""
    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], color="#3987e5")
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


def test_supported_file_exports_match_the_canonical_rust_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The single-file and batch public journeys share the Scene consumers.

    ``write_images`` does not call ``to_image`` because it amortizes browser
    setup, so this test must cover it separately. The supported native paths
    must nevertheless produce the exact bytes of the one encoded Rust Scene,
    rather than re-introducing an exporter-specific policy choice.
    """
    from xyg import _pdf, export

    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], color="#3987e5")
    scene = figure.to_scene()
    expected = {
        "svg": _native.scene_svg(scene).encode("utf-8"),
        "png": kernels.rasterize_png(_native.scene_raster_commands(scene), 320, 240),
    }
    expected["pdf"] = _pdf.svg_to_pdf(expected["svg"].decode("utf-8"))

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

    single_paths = {fmt: tmp_path / f"single.{fmt}" for fmt in expected}
    for fmt, path in single_paths.items():
        assert figure.write_image(path, scale=1) == expected[fmt]
        assert path.read_bytes() == expected[fmt]

    batch_paths = [tmp_path / f"batch.{fmt}" for fmt in expected]
    batch = export.write_images([figure] * len(batch_paths), batch_paths, scale=1)
    assert batch == [expected[path.suffix[1:]] for path in batch_paths]
    for path in batch_paths:
        assert path.read_bytes() == expected[path.suffix[1:]]

    # SVG and PDF both consume Rust SVG; PNG consumes Rust's display list.
    assert calls == {"svg": 4, "raster": 2}


def test_unsupported_public_exports_stay_on_compatibility_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    figure = Figure().heatmap([[0.0, 1.0], [1.0, 0.0]])

    def unexpected_scene_call(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError(
            "unsupported export must select compatibility before Scene compilation"
        )

    monkeypatch.setattr(_native, "scene_svg", unexpected_scene_call)
    monkeypatch.setattr(_native, "scene_raster_commands", unexpected_scene_call)
    assert figure.to_svg().startswith("<svg")
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda figure: setattr(figure, "title", "legacy text"), "PUBLIC_TEXT"),
        (
            lambda figure: figure.annotations.append({"kind": "marker", "x": 1, "y": 2}),
            "PUBLIC_ANNOTATION",
        ),
        (lambda figure: figure.set_axis("x", label="legacy axis"), "PUBLIC_AXIS"),
        (lambda figure: figure.line([0, 1], [0, 1], name="legacy legend"), "PUBLIC_LEGEND"),
        (lambda figure: figure.line(range(10_001), range(10_001)), "PUBLIC_LOD"),
    ],
)
def test_public_router_preflights_legacy_export_contracts(mutate, reason: str) -> None:
    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], color="#3987e5")
    mutate(figure)
    assert reason in (_scene_v3.scene_export_support_reason(figure) or "")


def test_non_circle_symbols_keep_the_legacy_rust_scatter_svg_contract() -> None:
    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], symbol="diamond")
    assert "PUBLIC_SYMBOL" in (_scene_v3.scene_export_support_reason(figure) or "")


def test_supported_public_exports_match_rust_consumers_and_are_repeatable() -> None:
    """The public journey must not merely produce valid files beside Scene."""
    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], color="#3987e5")
    svg = _scene_v3.figure_svg(figure)
    png = _scene_v3.try_public_png(figure, scale=1)
    pdf = _scene_v3.try_public_pdf(figure)

    assert figure.to_svg() == svg
    assert figure.to_svg() == figure.to_svg()
    assert figure.to_png(scale=1) == png
    assert figure.to_png(scale=1) == figure.to_png(scale=1)
    assert figure.to_image(format="pdf") == pdf
    assert figure.to_image(format="pdf") == figure.to_image(format="pdf")


def test_supported_public_export_failure_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    figure = Figure(width=320, height=240).scatter([1, 2], [2, 3], color="#3987e5")

    def broken_scene(*_args: object, **_kwargs: object) -> str:
        raise ValueError("broken Scene consumer")

    def unexpected_compatibility(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("a Scene consumer error must not select compatibility")

    from xyg import _svg

    monkeypatch.setattr(_native, "scene_svg", broken_scene)
    monkeypatch.setattr(_svg, "to_svg", unexpected_compatibility)
    with pytest.raises(ValueError, match="broken Scene consumer"):
        figure.to_svg()
    with pytest.raises(ValueError, match="broken Scene consumer"):
        figure.to_image(format="pdf")


def test_try_public_scene_helpers_select_migrated_subset() -> None:
    from xyg import _scene_v3

    figure = representative_figure()
    svg = _scene_v3.try_public_svg(figure)
    assert svg is not None
    assert 'clip-path="url(#xy-scene-plot)"' in svg
    png = _scene_v3.try_public_png(figure, scale=1)
    assert png is not None and png.startswith(b"\x89PNG\r\n\x1a\n")
    pdf = _scene_v3.try_public_pdf(figure)
    assert pdf is not None and pdf.startswith(b"%PDF-")
    styled = representative_figure()
    styled.set_axis("x", style={"grid_color": "#123456"})
    styled_svg = _scene_v3.try_public_svg(styled)
    assert styled_svg is not None and "rgba(18,52,86,1.000000)" in styled_svg


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
    assert int.from_bytes(encoded[4:8], "little") == 23
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
    with pytest.raises(UnsupportedSceneV3, match="supports Cartesian coordinates only"):
        figure.to_scene()


def test_python_scene_rejects_malformed_and_falls_back_for_unsupported_marks() -> None:
    with pytest.raises(ValueError, match="invalid canonical scene"):
        _native.scene_svg(b"not-a-scene")
    unsupported = Figure().heatmap([[0.0, 1.0], [1.0, 0.0]])
    with pytest.raises(UnsupportedSceneV3, match="heatmap"):
        unsupported.to_scene()
    assert "<svg" in unsupported.to_svg()


def test_python_scene_compiles_ribbon_and_triangle_mesh() -> None:
    ribbon = Figure(width=320, height=200)
    ribbon.axis_options["x"]["domain"] = (0.0, 1.0)
    ribbon.axis_options["y"]["domain"] = (0.0, 1.0)
    ribbon.ribbon([0.1], [0.9], [0.2], [0.5], [0.3], [0.7], color="#7c3aed")
    scene = ribbon.to_scene()
    assert scene[4:8] == (23).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert '<path d="M ' in svg
    assert ' Z"' in svg

    mesh = Figure(width=240, height=160)
    mesh.axis_options["x"]["domain"] = (0.0, 1.0)
    mesh.axis_options["y"]["domain"] = (0.0, 1.0)
    mesh.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0], color="#22c55e")
    mesh_svg = _native.scene_svg(mesh.to_scene())
    assert '<path d="M ' in mesh_svg

    gradient = Figure()
    gradient.ribbon(
        [0.0], [1.0], [0.0], [0.3], [0.2], [0.5], color="#7c3aed", color_target="#34d399"
    )
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_GRADIENT"):
        gradient.to_scene()


def test_python_scene_compiles_area_and_error_band() -> None:
    area = Figure(width=240, height=160)
    area.axis_options["x"]["domain"] = (0.0, 2.0)
    area.axis_options["y"]["domain"] = (0.0, 3.0)
    area.area([0.0, 1.0, 2.0], [1.0, 2.0, 1.5], base=0.0, color="#3987e5", opacity=0.5)
    scene = area.to_scene()
    assert scene[4:8] == (23).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert '<path d="M ' in svg
    assert ' Z"' in svg

    band = Figure(width=240, height=160)
    band.axis_options["x"]["domain"] = (0.0, 2.0)
    band.axis_options["y"]["domain"] = (0.0, 3.0)
    band.error_band([0.0, 1.0, 2.0], [0.7, 1.2, 0.9], [1.3, 1.8, 1.5], color="#22c55e")
    assert '<path d="M ' in _native.scene_svg(band.to_scene())


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

    def capture_scene_batch_encode(**kwargs: object) -> bytes:
        captured["annotations"] = kwargs["authored_text_annotations"]  # type: ignore[assignment]
        return b"captured-scene"

    monkeypatch.setattr(_scene_v3._native, "scene_batch_encode", capture_scene_batch_encode)
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
    assert scene[:8] == b"XYGS\x17\x00\x00\x00"
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
    assert scene[4:8] == (23).to_bytes(4, "little")  # SCENE_VERSION
    svg = _native.scene_svg(scene)
    assert svg.count("<rect ") >= 2  # plot clip plus at least one bar
    assert 'clip-path="url(#xy-scene-plot)"' in svg


def test_python_scene_rejects_rect_corner_radius_and_density() -> None:
    rounded = Figure()
    rounded.bar([0, 1], [1, 2], corner_radius=4.0)
    with pytest.raises(UnsupportedSceneV3, match="corner_radius"):
        rounded.to_scene()
    density = Figure()
    density.scatter([0.0] * 200_000, [0.0] * 200_000, density=True)
    with pytest.raises(UnsupportedSceneV3, match="density-tier"):
        density.to_scene()
    assert "<svg" in density.to_svg()


def test_python_scene_rejects_unequal_rect_columns() -> None:
    figure = Figure(width=200, height=120)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.bar([0, 1], [1, 2])
    figure.traces[0].x1 = figure.store.ingest([0.5])  # length mismatch vs x0
    with pytest.raises(UnsupportedSceneV3, match="equal length"):
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
