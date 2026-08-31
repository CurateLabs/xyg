"""ABI 272 scene_xytc_symbol_int_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_symbol_int_pack_string_path() -> None:
    assert kernels.scene_xytc_symbol_int_pack(0) == 0


def test_scene_xytc_symbol_int_pack_numeric_path() -> None:
    assert kernels.scene_xytc_symbol_int_pack(1) == 1 << 21


def test_pack_xytc_symbol_string_default() -> None:
    from xyg import _scene_v3 as scene

    flags, symbol_b, symbol_int = scene._pack_xytc_symbol({})
    assert flags == 0
    assert symbol_b == b"circle"
    assert symbol_int == 0


def test_pack_xytc_symbol_numeric() -> None:
    from xyg import _scene_v3 as scene

    flags, symbol_b, symbol_int = scene._pack_xytc_symbol({"symbol": 2})
    assert flags == 1 << 21
    assert symbol_b == b""
    assert symbol_int == 2
