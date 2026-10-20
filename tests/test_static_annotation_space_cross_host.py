"""Annotation coordinate spaces, byte-identical across hosts (#1006 case 53).

``text`` annotations may be placed in ``axes_fraction``, ``xaxis_transform``
(x data, y axes fraction) or ``yaxis_transform`` (x axes fraction, y data).
Hosts marshal only the ``coordinate_space`` string; Rust maps it to a code,
projects the data components through the Scene's own axis scale (here a log x
axis) and rejects ``figure_fraction`` because a panel Scene does not own the
figure rectangle.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import xyg
from xyg import _native
from xyg._scene_annotations import pack_xyaf_bulk
from xyg._static_document import UnsupportedStaticExport

ROOT = Path(__file__).resolve().parents[1]
FORMATS = ("svg", "png", "pdf", "jpeg", "webp")
SPACES = ("data", "axes_fraction", "xaxis_transform", "yaxis_transform")


def _text(x: float, y: float, value: str, **style: Any) -> xyg.Annotation:
    return xyg.text(x, y, value, dx=0, dy=0, anchor="middle", style=style)


def _row(x: float, y: float, value: str, **style: Any) -> dict[str, Any]:
    return {
        "kind": "text",
        "x": x,
        "y": y,
        "text": value,
        "dx": 0,
        "dy": 0,
        "anchor": "middle",
        "style": style,
    }


def _chart(*annotations: xyg.Annotation) -> xyg.Chart:
    return xyg.chart(
        xyg.line([1, 10, 1000], [1, 3, 2], color="#ef4444", width=2),
        *annotations,
        xyg.x_axis(type_="log", domain=(1, 1000), label="X"),
        xyg.y_axis(domain=(0, 4), label="Y"),
        xyg.legend(show=False),
        width=320,
        height=240,
    )


CASES = {
    "axes_fraction": _chart(
        _text(0.5, 0.5, "Center", coordinate_space="axes_fraction"),
        _text(0.02, 0.95, "Corner", coordinate_space="axes_fraction", font_size=9),
        _text(
            0.5,
            -0.1,
            "Below",
            coordinate_space="axes_fraction",
            background="#dbeafe",
            padding="4px 8px",
        ),
    ),
    "mixed": _chart(
        _text(10, 0.5, "x data", coordinate_space="xaxis_transform"),
        _text(0.25, 3, "y data", coordinate_space="yaxis_transform"),
    ),
    "data_reference": _chart(
        _text(1000**0.5, 2, "Center"),
        _text(10, 2, "x data"),
        _text(1000**0.25, 3, "y data"),
    ),
}

REJECTED = {
    "figure_fraction": [_text(0.5, 0.5, "Fig", coordinate_space="figure_fraction")],
    "unknown_space": [_text(0.5, 0.5, "Odd", coordinate_space="polar")],
    "callout_space": [
        xyg.callout(0.5, 0.5, "No", dx=10, dy=-10, style={"coordinate_space": "axes_fraction"})
    ],
}


@pytest.fixture(scope="module")
def node_results() -> dict[str, Any]:
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    process = subprocess.run(
        ["node", str(ROOT / "packages/xy-node/scripts/static_annotation_space_cross_host.mjs")],
        text=True,
        capture_output=True,
        timeout=300,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize("name", sorted(CASES))
@pytest.mark.parametrize("fmt", FORMATS)
def test_hosts_export_identical_bytes(name: str, fmt: str, node_results: dict[str, Any]) -> None:
    expected = node_results["cases"][name][fmt]
    options = {"quality": 90} if fmt == "jpeg" else {}
    data = CASES[name].to_image(fmt, scale=1, **options)
    if fmt == "svg":
        assert data.decode() == expected["text"]
    else:
        assert hashlib.sha256(data).hexdigest() == expected["sha256"]


@pytest.mark.parametrize("space", SPACES)
def test_hosts_pack_identical_xyaf_bytes(space: str, node_results: dict[str, Any]) -> None:
    packed = pack_xyaf_bulk([_row(0.25, 0.75, "Pack", coordinate_space=space)])
    assert packed.hex() == node_results["bulk"][space]


def test_xyaf_record_carries_the_space_code_and_data_is_the_default() -> None:
    codes = {}
    for space in SPACES:
        packed = pack_xyaf_bulk([_row(0.25, 0.75, "Pack", coordinate_space=space)])
        codes[space] = packed[26]
    assert codes == {"data": 0, "axes_fraction": 1, "xaxis_transform": 2, "yaxis_transform": 3}
    plain = pack_xyaf_bulk([_row(0.25, 0.75, "Pack")])
    assert plain[26] == 0


def _position(svg: str, label: str) -> tuple[float, float]:
    match = re.search(rf"<text([^>]*)>{re.escape(label)}</text>", svg)
    assert match, f"{label!r} missing from the SVG"
    return tuple(
        float(re.search(rf' {axis}="([-\d.]+)"', match.group(1)).group(1)) for axis in "xy"
    )


def test_spaces_project_to_the_same_pixels_as_equivalent_data_coordinates() -> None:
    """Axes fractions land where the matching data coordinate lands (log x)."""
    reference = CASES["data_reference"].to_svg()
    axes = CASES["axes_fraction"].to_svg()
    mixed = CASES["mixed"].to_svg()
    assert _position(axes, "Center") == _position(reference, "Center")
    assert _position(mixed, "x data") == _position(reference, "x data")
    assert _position(mixed, "y data") == _position(reference, "y data")


def test_axes_fraction_text_may_sit_outside_the_plot_rectangle() -> None:
    _x, below = _position(CASES["axes_fraction"].to_svg(), "Below")
    _x, center = _position(CASES["axes_fraction"].to_svg(), "Center")
    assert below > center


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_unsupported_spaces_fail_closed_identically(
    name: str, node_results: dict[str, Any]
) -> None:
    with pytest.raises(UnsupportedStaticExport) as raised:
        _chart(*REJECTED[name]).to_svg()
    node_message = node_results["failures"][name]
    assert node_message is not None
    assert str(raised.value).endswith(node_message) or node_message in str(raised.value)


def test_figure_fraction_has_a_stable_reason() -> None:
    with pytest.raises(
        UnsupportedStaticExport, match="XYG_SCENE_UNSUPPORTED_ANNOTATION_COORDINATE_SPACE"
    ):
        _chart(*REJECTED["figure_fraction"]).to_svg()
