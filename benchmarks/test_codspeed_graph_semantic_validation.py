"""Real semantic ingress validation; setup/oracles are outside CodSpeed measurement."""

from __future__ import annotations

import numpy as np
import pytest

from xyg import _native


@pytest.fixture(
    scope="module", params=[0, 1, 8, 16, 1_000, 100_000, 200_000], ids=lambda n: f"rows-{n}"
)
def planes(request):
    n = request.param
    codes = [np.arange(n, dtype=np.uint64) % 8 for _ in range(3)]
    metric = np.linspace(-1.0, 1.0, n)
    metric[::11] = np.nan
    metric[1::13] = -0.0
    flags = (np.arange(n, dtype=np.uint64) % 4).astype(np.uint32)
    return codes, metric, flags


@pytest.fixture(scope="module")
def validator():
    return _native._graph_semantic_inputs


def _assert_result(result, inputs):
    n, codes, metric, flags, theme = result
    original_codes, original_metric, original_flags = inputs
    assert n == len(original_metric) and theme == 0
    for value, original in zip(codes, original_codes, strict=True):
        assert value.dtype == np.uint8 and value.flags.c_contiguous
        assert value.tobytes() == original.astype(np.uint8).tobytes()
    assert metric.dtype == np.float64 and metric.flags.c_contiguous
    assert metric.tobytes() == original_metric.tobytes()
    assert flags.dtype == np.uint32 and flags.flags.c_contiguous
    assert flags.tobytes() == original_flags.astype(np.uint32).tobytes()


def test_contiguous_validation(benchmark, validator, planes):
    codes, metric, flags = planes
    result = benchmark(validator, *codes, metric, flags, False, "light")
    _assert_result(result, planes)


def test_strided_big_endian_validation(benchmark, validator, planes):
    codes, metric, flags = planes
    source = [np.repeat(value, 2)[::2].astype(">u8")[::-1] for value in codes]
    source_metric = np.repeat(metric, 2)[::2][::-1]
    source_flags = np.repeat(flags, 2).astype(">u4")[::2][::-1]
    result = benchmark(validator, *source, source_metric, source_flags, True, "light")
    _assert_result(result, (source, source_metric, source_flags))
