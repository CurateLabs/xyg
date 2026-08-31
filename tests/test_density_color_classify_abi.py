"""ABI 260 density_color_classify parity."""

from __future__ import annotations

from xyg import _native, kernels


def test_density_color_classify_none() -> None:
    color_mode, categorical, compact, stratified = kernels.density_color_classify(
        channel_mode=_native.DENSITY_CHANNEL_MODE_NONE,
    )
    assert color_mode == _native.DENSITY_COLOR_MODE_NONE
    assert categorical is False
    assert compact is False
    assert stratified is False


def test_density_color_classify_constant() -> None:
    color_mode, categorical, compact, stratified = kernels.density_color_classify(
        channel_mode=_native.DENSITY_CHANNEL_MODE_CONSTANT,
    )
    assert color_mode == _native.DENSITY_COLOR_MODE_CONSTANT
    assert categorical is False


def test_density_color_classify_stratified_categorical() -> None:
    color_mode, categorical, compact, stratified = kernels.density_color_classify(
        channel_mode=_native.DENSITY_CHANNEL_MODE_CATEGORICAL,
        codes_present=True,
        codes_u8=True,
        has_counts=True,
    )
    assert color_mode == _native.DENSITY_COLOR_MODE_OTHER
    assert categorical is True
    assert compact is True
    assert stratified is True


def test_density_color_classify_compact_without_counts() -> None:
    _color_mode, _categorical, compact, stratified = kernels.density_color_classify(
        channel_mode=_native.DENSITY_CHANNEL_MODE_CATEGORICAL,
        codes_present=True,
        codes_u8=True,
        has_counts=False,
    )
    assert compact is True
    assert stratified is False
