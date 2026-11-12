"""Exact semantic ingress representation before Rust owns paint policy (§7.1)."""

from __future__ import annotations

import struct

import numpy as np
import pytest

from xyg import _native

INTEGER_DTYPES = [
    f"{endian}{kind}{width}" for endian in "<>" for kind in "iu" for width in (1, 2, 4, 8)
]


@pytest.mark.parametrize(
    "classes,metric,flags,edge,theme,error,message",
    [
        ([8], ["invalid"], [-1], 1, "other", TypeError, "edge must be a bool"),
        ([0.5], [0.0], [0], False, "other", ValueError, "theme must be"),
        ([8], ["invalid"], [-1], False, "light", ValueError, r"closed range 0\.\.7"),
        ([0], ["invalid"], [2**32], False, "light", ValueError, "float"),
        ([0], [[0.0]], [2**32], False, "light", ValueError, "uint32 values"),
        ([0], [0.0, 1.0], [0.5], False, "light", ValueError, "exact integer"),
    ],
)
def test_semantic_ingress_keeps_refusal_precedence(
    classes, metric, flags, edge, theme, error, message
):
    with pytest.raises(error, match=message):
        _native._graph_semantic_inputs(classes, [0], [0], metric, flags, edge, theme)


@pytest.mark.parametrize("dtype", INTEGER_DTYPES)
@pytest.mark.parametrize("count", [0, 1, 8, 9, 16, 4097])
def test_exact_codes_flags_and_metric_bits_survive_strided_ingress(dtype, count):
    values = [i % 8 for i in reversed(range(count))]
    source = np.repeat(np.asarray(values, dtype=dtype), 2)[::2]
    metric_bits = [0x8000000000000000 if i % 2 else 0x7FF8000000000ABC for i in range(count)]
    metric = np.frombuffer(
        b"".join(struct.pack("=Q", value) for value in metric_bits), dtype=np.float64
    )
    flag_values = [0xFFFF_FFFF if i % 2 else 0 for i in range(count)]
    flags = np.repeat(np.asarray(flag_values, dtype=">u8"), 2)[::2]
    before = source.tobytes(), metric.tobytes(), flags.tobytes()
    n, codes, retained_metric, retained_flags, theme = _native._graph_semantic_inputs(
        source, source, source, metric, flags, np.bool_(True), "dark"
    )
    assert (n, theme) == (count, 1)
    for plane in codes:
        assert plane.dtype == np.uint8 and plane.flags.c_contiguous
        assert plane.tobytes() == bytes(values)
    assert retained_metric.tobytes() == before[1]
    assert retained_flags.dtype == np.uint32 and retained_flags.flags.c_contiguous
    assert retained_flags.tobytes() == b"".join(struct.pack("=I", value) for value in flag_values)
    assert before == (source.tobytes(), metric.tobytes(), flags.tobytes())


@pytest.mark.parametrize(
    "resolver", [_native.graph_semantic_styles, _native.graph_semantic_paint_layers]
)
@pytest.mark.parametrize("field", [0, 1, 2])
@pytest.mark.parametrize("bad,dtype", [(-1, ">i8"), (8, "u8"), (256, ">u8"), (2**64 - 1, "u8")])
def test_late_invalid_code_refuses_before_narrowing(resolver, field, bad, dtype):
    count = 4097
    args = [np.zeros(count, dtype=np.uint8) for _ in range(3)]
    args[field] = np.zeros(count, dtype=dtype)
    args[field][-1] = bad
    with pytest.raises(ValueError, match=r"closed range 0\.\.7"):
        resolver(*args, np.zeros(count), np.zeros(count, dtype=np.uint32))


@pytest.mark.parametrize(
    "resolver", [_native.graph_semantic_styles, _native.graph_semantic_paint_layers]
)
@pytest.mark.parametrize("bad,dtype", [(-1, ">i8"), (2**32, "u8"), (2**64 - 1, ">u8")])
def test_late_invalid_flag_refuses_before_narrowing(resolver, bad, dtype):
    count = 4097
    zero = np.zeros(count, dtype=np.uint8)
    flags = np.zeros(count, dtype=dtype)
    flags[-1] = bad
    with pytest.raises(ValueError, match="flags must contain uint32 values"):
        resolver(zero, zero, zero, np.zeros(count), flags)


@pytest.mark.parametrize(
    "resolver", [_native.graph_semantic_styles, _native.graph_semantic_paint_layers]
)
@pytest.mark.parametrize("edge", [False, True])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_complete_public_rust_planes_preserve_large_source_permutation(resolver, edge, theme):
    base_codes = [
        np.arange(8, dtype=np.uint8),
        np.roll(np.arange(8, dtype=np.uint8), 1),
        np.roll(np.arange(8, dtype=np.uint8), 2),
    ]
    metric = np.arange(8, dtype=np.float64)
    flags = np.array([0, 1, 2, 4, 8, 16, 32, 64], dtype=np.uint32)
    expected = resolver(*base_codes, metric, flags, edge=edge, theme=theme)
    order = (np.arange(4097) * 7) % 8
    codes = [np.repeat(value[order], 2).astype(">u8")[::2] for value in base_codes]
    actual = resolver(*codes, metric[order], flags[order].astype(">u4"), edge=edge, theme=theme)
    assert actual.keys() == expected.keys()
    for key, value in expected.items():
        if isinstance(value, np.ndarray):
            assert actual[key].dtype == value.dtype and actual[key].shape == value[order].shape
            assert actual[key].tobytes() == value[order].tobytes(), key
        else:
            assert actual[key] == value
