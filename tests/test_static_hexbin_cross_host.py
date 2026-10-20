"""Python/Node identity for native static hexbin exports beyond 1,024 groups (#887).

A hexbin cell is one Scene PolyFill group. The former shared 1,024-group
ceiling no longer applies to hexbin; cells have their own documented ceiling
(`MAX_PUBLIC_HEXBIN_CELLS`, 50,000) and fail closed above it with the stable
``XYG_SCENE_UNSUPPORTED_PUBLIC_LOD`` reason in both hosts.

Run::

    cargo build --release && npm ci --prefix packages/xy-node
    uv run pytest tests/test_static_hexbin_cross_host.py -q
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import xyg
from xyg._scene_v3 import public_static_export, scene_export_support_reason

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "static_hexbin_cross_host.mjs"
LIB = (
    ROOT
    / "target"
    / "release"
    / (
        "xyg_core.dll"
        if sys.platform == "win32"
        else "libxyg_core.dylib"
        if sys.platform == "darwin"
        else "libxyg_core.so"
    )
)

N = 20000
X = [((i * 7919) % 10007) / 10007 for i in range(N)]
Y = [((i * 104729) % 10009) / 10009 for i in range(N)]
# name -> (gridsize, constant color or None, extra scatter points)
CASES: dict[str, tuple[tuple[int, int], str | None, int]] = {
    "above_former_group_ceiling": ((40, 30), None, 0),
    "default_gridsize_lattice": ((100, 100), None, 0),
    "near_cell_ceiling": ((155, 155), None, 0),
    # Constant paint has no per-cell paint plane, so its encode input is tiny
    # while its Scene output (6 records per cell) is not: output sizing must
    # not be inferred from input size (#887 review).
    "near_cell_ceiling_constant_color": ((155, 155), "#3987e5", 0),
    "near_cell_ceiling_mixed": ((155, 155), "#3987e5", 5000),
    "above_cell_ceiling": ((330, 330), None, 0),
}
CEILING = 50_000
GROUP_CEILING = 1_024


def _figure(name: str) -> Any:
    gridsize, color, extra = CASES[name]
    marks = [xyg.hexbin(X, Y, gridsize=gridsize, **({"color": color} if color else {}))]
    if extra:
        # Mixed documents need authored domains for the Scene route.
        marks += [
            xyg.scatter(X[:extra], Y[:extra], color="#ef4444", size=3),
            xyg.x_axis(domain=(-0.2, 1.2)),
            xyg.y_axis(domain=(-0.2, 1.2)),
        ]
    return xyg.hexbin_chart(*marks, width=640, height=480).figure()


@pytest.fixture(scope="module")
def node_cases() -> dict[str, dict[str, Any]]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found on PATH")
    if not LIB.is_file():
        pytest.skip(f"missing native core {LIB}")
    env = {**os.environ, "XYG_NATIVE_LIB": os.environ.get("XYG_NATIVE_LIB", str(LIB))}
    proc = subprocess.run(
        [node, str(NODE_SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        pytest.fail(f"Node hexbin proof failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "xyg.static-hexbin-cross-host/v1"
    return {case["name"]: case for case in payload["cases"]}


ADMITTED = [name for name in CASES if name != "above_cell_ceiling"]


@pytest.mark.parametrize("name", ADMITTED)
def test_oversized_hexbin_exports_every_cell_identically_in_both_hosts(
    name: str, node_cases: dict[str, dict[str, Any]]
) -> None:
    figure = _figure(name)
    cells = len(figure.traces[0].x.values)
    assert GROUP_CEILING < cells <= CEILING
    assert scene_export_support_reason(figure) is None
    svg = public_static_export(figure, "svg")
    png = public_static_export(figure, "png")
    assert svg is not None and png is not None and png.startswith(b"\x89PNG\r\n\x1a\n")
    # Full fidelity: one SVG cell path per lattice cell, none dropped or merged.
    assert len(re.findall(rb'<path d="M ', svg)) == cells

    node = node_cases[name]
    assert node["cells"] == cells
    assert node["reason"] is None
    assert base64.b64decode(node["scene_svg_b64"]) == svg
    assert base64.b64decode(node["svg_b64"]) == figure.to_svg().encode()
    assert base64.b64decode(node["png_b64"]) == figure.to_png(scale=1)


def test_hexbin_above_cell_ceiling_fails_closed_identically_in_both_hosts(
    node_cases: dict[str, dict[str, Any]],
) -> None:
    figure = _figure("above_cell_ceiling")
    assert len(figure.traces[0].x.values) > CEILING
    reason = scene_export_support_reason(figure)
    assert reason is not None and reason.startswith("XYG_SCENE_UNSUPPORTED_PUBLIC_LOD")
    assert public_static_export(figure, "svg") is None
    node = node_cases["above_cell_ceiling"]
    assert node["cells"] > CEILING
    assert node["reason"] == reason


def test_unrepresentable_product_output_surfaces_the_stable_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rust rejects >i32::MAX outputs with `-3` + a 0xFFFFFFFF marker (#887)."""
    import ctypes

    from xyg import _native
    from xyg._scene_v3 import UnsupportedSceneV3, figure_scene

    real = _native._lib

    def reject(marker: int):
        def call(*args: Any) -> int:
            ctypes.memmove(args[-2], marker.to_bytes(4, "little"), 4)
            return -3

        return call

    class Lib:
        xyg_scene_encode_product = staticmethod(reject(0xFFFFFFFF))

        def __getattr__(self, name: str) -> Any:
            return getattr(real, name)

    figure = _figure("above_former_group_ceiling")
    monkeypatch.setattr(_native, "_lib", Lib())
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"):
        figure_scene(figure)

    # A genuine encode-sidecar Limit (small failing index) keeps its meaning.
    Lib.xyg_scene_encode_product = staticmethod(reject(3))
    with pytest.raises(ValueError, match="invalid scene chrome packing"):
        figure_scene(figure)
