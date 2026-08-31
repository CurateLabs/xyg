"""ABI 258 scene_xyta_colormap_pack parity."""

from __future__ import annotations

import pytest

from xyg import kernels


def test_scene_xyta_colormap_pack_named() -> None:
    flags, cmap, stops = kernels.scene_xyta_colormap_pack(1, b"viridis", b"")
    assert flags == 1 << 6
    assert cmap == b"viridis"
    assert stops == b""


def test_scene_xyta_colormap_pack_rgb_stops() -> None:
    flags, cmap, stops = kernels.scene_xyta_colormap_pack(2, b"", bytes([255, 0, 0, 0, 255, 0]))
    assert flags == 1 << 7
    assert cmap == b""
    assert stops == bytes([255, 0, 0, 0, 255, 0])


def test_scene_xyta_colormap_pack_invalid_stops_swallow() -> None:
    flags, cmap, stops = kernels.scene_xyta_colormap_pack(2, b"", b"\xff\x00")
    assert flags == 1 << 7
    assert cmap == b""
    assert stops == b""


def test_pack_xyta_colormap_delegates_to_kernel() -> None:
    from xyg import _scene_v3 as scene

    flags, cmap, stops = scene._pack_xyta_colormap({"colormap": "plasma"})
    assert flags == 1 << 6
    assert cmap == b"plasma"
    assert stops == b""

    flags, cmap, stops = scene._pack_xyta_colormap({"colormap": [[1, 2, 3]]})
    assert flags == 1 << 7
    assert cmap == b""
    assert stops == bytes([1, 2, 3])

    flags, cmap, stops = scene._pack_xyta_colormap({"colormap": [1, 2, 3]})
    assert flags == 1 << 7
    assert stops == b""


@pytest.mark.parametrize("mode", [0, 99])
def test_scene_xyta_colormap_pack_absent(mode: int) -> None:
    flags, cmap, stops = kernels.scene_xyta_colormap_pack(mode, b"x", b"\x01\x02\x03")
    assert flags == 0
    assert cmap == b""
    assert stops == b""


def test_scene_xyhf_colormap_pack_named() -> None:
    flags, cmap, stops = kernels.scene_xyhf_colormap_pack(1, b"plasma", b"")
    assert flags == 1 << 5
    assert cmap == b"plasma"
    assert stops == b""


def test_scene_xyhf_colormap_pack_rgb_stops() -> None:
    flags, cmap, stops = kernels.scene_xyhf_colormap_pack(2, b"", bytes([0, 128, 255, 255, 128, 0]))
    assert flags == 1 << 6
    assert cmap == b""
    assert stops == bytes([0, 128, 255, 255, 128, 0])
