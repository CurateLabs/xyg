"""ABI 260 scene_gradient_spec_pack parity."""

from __future__ import annotations

import struct

from xyg import kernels


def test_scene_gradient_spec_pack_mark_right() -> None:
    blob = kernels.scene_gradient_spec_pack(
        b"mark",
        b"right",
        [0.0, 1.0],
        b"#7c3aed#34d399",
        [7, 7],
    )
    assert blob is not None
    assert blob[:4] == bytes([0, 2, 2, 0])
    assert len(blob) == 4 + 2 * 10 + 14


def test_scene_gradient_spec_pack_unknown_space_dir() -> None:
    blob = kernels.scene_gradient_spec_pack(b"", b"", [], b"", [])
    assert blob is not None
    assert blob == bytes([255, 255, 0, 0])


def test_scene_gradient_spec_pack_invalid_layout() -> None:
    assert kernels.scene_gradient_spec_pack(b"mark", b"right", [0.0], b"x", [1, 2]) is None


def test_pack_gradient_spec_delegates_to_kernel() -> None:
    from xyg import _scene_v3 as scene

    blob = scene._pack_gradient_spec(
        {
            "space": "mark",
            "dir": "right",
            "stops": [[0.0, "#7c3aed"], [1.0, "#34d399"]],
        }
    )
    assert blob is not None
    assert blob[:4] == bytes([0, 2, 2, 0])
    t0 = struct.unpack("<d", blob[4:12])[0]
    len0 = struct.unpack("<H", blob[12:14])[0]
    assert t0 == 0.0
    assert len0 == 7
    assert blob[14:21] == b"#7c3aed"
