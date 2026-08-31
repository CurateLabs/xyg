"""ABI 261 scene_marker_blob_pack parity."""

from __future__ import annotations

import struct

from xyg import kernels

DIAMOND = {
    "filled": True,
    "contours": [[0.0, 0.5, 0.5, 0.0, 0.0, -0.5, -0.5, 0.0, 0.0, 0.5]],
}


def test_scene_marker_blob_pack_diamond() -> None:
    blob = kernels.scene_marker_blob_pack(1, DIAMOND["contours"][0], [10])
    assert blob is not None
    assert struct.unpack("<I", blob[:4])[0] == 1
    assert blob[4] == 1
    assert struct.unpack("<I", blob[8:12])[0] == 10
    assert len(blob) == 8 + 4 + 10 * 8


def test_scene_marker_blob_pack_invalid_layout() -> None:
    assert kernels.scene_marker_blob_pack(1, [0.0, 1.0], [3, 3]) is None
    assert kernels.scene_marker_blob_pack(2, [0.0], [1]) is None


def test_pack_marker_blob_delegates_to_kernel() -> None:
    from xyg import _scene_v3 as scene

    blob = scene._pack_marker_blob(DIAMOND)
    assert blob is not None
    assert struct.unpack("<I", blob[:4])[0] == 1
