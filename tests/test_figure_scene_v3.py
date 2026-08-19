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
    figure.scatter([1, 2], [2, 3], color="#3987e5", size=6, opacity=0.8)
    figure.line([1, 2, 3], [1, 4, 2], color="#ef4444", width=2)
    figure.bar([1, 2], [3, 2], color="#22c55e", opacity=0.85)
    return figure


def test_python_figure_compiles_exact_scene_v3_fixture() -> None:
    scene = representative_figure().to_scene()
    assert hashlib.sha256(scene).hexdigest() == FIXTURE["expected_sha256"]
    svg = _native.scene_svg(scene)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert svg.count("<polyline ") == 1
    assert svg.count("<rect ") == 3  # plot clip plus two bars
    assert 'clip-path="url(#xy-scene-plot)"' in svg


def test_python_scene_raster_is_nonblank_and_matches_export_route() -> None:
    figure = representative_figure()
    scene = figure.to_scene()
    commands = _native.scene_raster_commands(scene)
    pixels = kernels.rasterize(commands, 320, 240)
    assert np.count_nonzero(pixels[:, :, 3]) > 200
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")


def test_python_scene_rejects_malformed_and_falls_back_for_unsupported_marks() -> None:
    with pytest.raises(ValueError, match="invalid canonical scene"):
        _native.scene_svg(b"not-a-scene")
    unsupported = Figure().area([0, 1], [1, 2])
    with pytest.raises(UnsupportedSceneV3, match="area"):
        unsupported.to_scene()
    assert "<svg" in unsupported.to_svg()
