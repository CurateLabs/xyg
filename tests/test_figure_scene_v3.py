from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from xy import _native, kernels
from xy._figure import Figure
from xy._scene_v3 import UnsupportedSceneV3

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


def test_python_figure_compiles_exact_scene_v3_fixture() -> None:
    scene = representative_figure().to_scene()
    assert hashlib.sha256(scene).hexdigest() == FIXTURE["expected_sha256"]
    assert scene[160 + 3 * 16 + 2] == 2  # canonical diamond symbol code
    svg = _native.scene_svg(scene)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert svg.count("<polyline ") == 1
    assert svg.count("<rect ") == 3  # plot clip plus two bars
    assert 'clip-path="url(#xy-scene-plot)"' in svg
    assert 'data-xy-chrome="grid"' in svg
    assert 'data-xy-chrome="axes"' in svg
    assert svg.count("<text ") == 6
    assert ">0<" in svg and ">4<" in svg


def test_python_scene_defaults_have_shared_noncoincidental_bytes() -> None:
    scatter = default_style_figure("scatter").to_scene()
    line = default_style_figure("line").to_scene()
    assert hashlib.sha256(scatter).hexdigest() == FIXTURE["default_scatter_sha256"]
    assert hashlib.sha256(line).hexdigest() == FIXTURE["default_line_sha256"]
    assert np.frombuffer(memoryview(scatter)[168:176], dtype="<f8")[0] == 0.0
    assert np.frombuffer(memoryview(scatter)[224:232], dtype="<f8")[0] == 4.0
    assert np.frombuffer(memoryview(line)[168:176], dtype="<f8")[0] == 1.5


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


def test_public_exports_preserve_compatibility_chrome(monkeypatch: pytest.MonkeyPatch) -> None:
    figure = representative_figure()
    figure.title = "Compatibility title"
    figure.set_axis(
        "x",
        label="Horizontal",
        domain=(0, 4),
        tick_values=[0, 2, 4],
        tick_labels=["zero", "two", "four"],
        style={"grid_color": "#123456"},
    )
    figure.set_axis("y", label="Vertical", domain=(0, 5))

    def unexpected_scene_call(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("public export must not select incomplete Scene chrome")

    monkeypatch.setattr(_native, "scene_svg", unexpected_scene_call)
    monkeypatch.setattr(_native, "scene_raster_commands", unexpected_scene_call)
    svg = figure.to_svg()
    assert "Compatibility title" in svg
    assert "Horizontal" in svg
    assert "Vertical" in svg
    assert "two" in svg
    assert "#123456" in svg
    with pytest.raises(UnsupportedSceneV3, match="tick, grid, or axis styling"):
        figure.to_scene()
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image(format="pdf").startswith(b"%PDF-")


def test_python_scene_rejects_malformed_and_falls_back_for_unsupported_marks() -> None:
    with pytest.raises(ValueError, match="invalid canonical scene"):
        _native.scene_svg(b"not-a-scene")
    unsupported = Figure().area([0, 1], [1, 2])
    with pytest.raises(UnsupportedSceneV3, match="area"):
        unsupported.to_scene()
    assert "<svg" in unsupported.to_svg()


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


def test_python_scene_still_rejects_annotations() -> None:
    figure = representative_figure()
    figure.annotations.append({"kind": "text", "x": 1, "y": 2, "text": "note"})
    with pytest.raises(UnsupportedSceneV3, match="annotations"):
        figure.to_scene()


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
    assert scene[4:8] == (5).to_bytes(4, "little")  # SCENE_VERSION
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
