"""ABI 262 density_trace_color_classify parity."""

from __future__ import annotations

from xyg import _native, kernels


def test_density_trace_color_classify_no_channel() -> None:
    color_mode, categorical, compact, stratified = kernels.density_trace_color_classify(
        has_channel=False,
    )
    assert color_mode == _native.DENSITY_COLOR_MODE_NONE
    assert categorical is False
    assert compact is False
    assert stratified is False


def test_density_trace_color_classify_constant_mode() -> None:
    color_mode, categorical, compact, stratified = kernels.density_trace_color_classify(
        has_channel=True,
        mode="constant",
    )
    assert color_mode == _native.DENSITY_COLOR_MODE_CONSTANT
    assert categorical is False
    assert compact is False
    assert stratified is False


def test_density_trace_color_classify_stratified_categorical() -> None:
    color_mode, categorical, compact, stratified = kernels.density_trace_color_classify(
        has_channel=True,
        mode="categorical",
        codes_present=True,
        codes_u8=True,
        has_counts=True,
    )
    assert color_mode == _native.DENSITY_COLOR_MODE_OTHER
    assert categorical is True
    assert compact is True
    assert stratified is True


def test_density_trace_color_classify_other_mode() -> None:
    color_mode, _categorical, _compact, _stratified = kernels.density_trace_color_classify(
        has_channel=True,
        mode="direct_rgba",
    )
    assert color_mode == _native.DENSITY_COLOR_MODE_OTHER
