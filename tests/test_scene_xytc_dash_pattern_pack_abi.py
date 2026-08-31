"""ABI 268 scene_xytc_dash_pattern_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_dash_pattern_pack_not_array() -> None:
    assert kernels.scene_xytc_dash_pattern_pack(0) == 0


def test_scene_xytc_dash_pattern_pack_array() -> None:
    assert kernels.scene_xytc_dash_pattern_pack(1) == 1 << 17


def test_pack_xytc_dash_string() -> None:
    from xyg import _scene_v3 as scene

    flags, dash_b, pattern = scene._pack_xytc_dash({"dash": "dashed"})
    assert flags == 0
    assert dash_b == b"dashed"
    assert pattern == []


def test_pack_xytc_dash_array() -> None:
    from xyg import _scene_v3 as scene

    flags, dash_b, pattern = scene._pack_xytc_dash({"dash": [6.0, 4.0]})
    assert flags == 1 << 17
    assert dash_b == b""
    assert pattern == [6.0, 4.0]


def test_pack_xytc_dash_array_bad_coercion() -> None:
    from xyg import _scene_v3 as scene

    flags, dash_b, pattern = scene._pack_xytc_dash({"dash": [6.0, "bad"]})
    assert flags == 1 << 17
    assert dash_b == b""
    assert pattern == []
