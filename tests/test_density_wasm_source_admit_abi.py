"""ABI 269 density_wasm_source_admit parity."""

from __future__ import annotations

from xyg import kernels


def test_density_wasm_source_admit_both() -> None:
    assert kernels.density_wasm_source_admit(split_payload=True, wasm_eligible=True) is True


def test_density_wasm_source_admit_not_split() -> None:
    assert kernels.density_wasm_source_admit(split_payload=False, wasm_eligible=True) is False


def test_density_wasm_source_admit_not_eligible() -> None:
    assert kernels.density_wasm_source_admit(split_payload=True, wasm_eligible=False) is False
