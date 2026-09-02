"""ABI 272 scene_xytc_symbol_int_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_symbol_int_pack_string_path() -> None:
    assert kernels.scene_xytc_symbol_int_pack(0) == 0


def test_scene_xytc_symbol_int_pack_numeric_path() -> None:
    assert kernels.scene_xytc_symbol_int_pack(1) == 1 << 21
