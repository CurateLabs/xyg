"""ABI 270 density_wasm_density_wire_kind parity."""

from __future__ import annotations

from xyg import kernels


def test_density_wasm_density_wire_kind_not_split() -> None:
    assert (
        kernels.density_wasm_density_wire_kind(
            split_payload=False,
            wasm_source_count=1,
            has_density_tier=True,
        )
        == kernels.DENSITY_WASM_DENSITY_NONE
    )


def test_density_wasm_density_wire_kind_automatic() -> None:
    assert (
        kernels.density_wasm_density_wire_kind(
            split_payload=True,
            wasm_source_count=1,
            has_density_tier=False,
        )
        == kernels.DENSITY_WASM_DENSITY_AUTOMATIC
    )


def test_density_wasm_density_wire_kind_unsupported() -> None:
    assert (
        kernels.density_wasm_density_wire_kind(
            split_payload=True,
            wasm_source_count=0,
            has_density_tier=True,
        )
        == kernels.DENSITY_WASM_DENSITY_UNSUPPORTED
    )
