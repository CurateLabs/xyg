"""The line extrema oracle must hold at every admitted size (#1027)."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

import benchmarks.bench_line as bench_line  # noqa: E402

from xyg import chart, line  # noqa: E402


def _tier(x, y) -> str:
    spec, _ = chart(line(x=x, y=y), width=900, height=420).figure().build_payload(bench_line.N_OUT)
    return spec["traces"][0]["tier"]


@pytest.mark.parametrize(
    ("n", "tier"),
    [(2_000, "direct"), (10_000, "direct"), (100_000, "decimated")],
)
def test_extrema_oracle_passes_in_direct_and_decimated_tiers(n: int, tier: str) -> None:
    x, y = bench_line._series(n)
    assert _tier(x, y) == tier
    assert bench_line._extrema_ok(x, y)


def _patch_frombuffer(monkeypatch, n: int, transform) -> None:
    real = np.frombuffer
    calls = {"i": 0}

    def patched(*args, **kwargs):
        out = real(*args, **kwargs)
        if kwargs.get("count") == n:
            calls["i"] += 1
            out = transform(calls["i"], out.copy())
        return out

    monkeypatch.setattr(bench_line.np, "frombuffer", patched)


def _interior_non_extreme_row(x, y) -> int:
    """A row strictly between same-bucket neighbours: dropping it keeps every
    per-column min/max intact, so only the row-count check can reject it."""
    x0, x1 = sorted(chart(line(x=x, y=y), width=900, height=420).figure().x_range())
    n_out = bench_line.N_OUT
    bucket = np.clip(((x - x0) / (x1 - x0) * n_out).astype(np.int64), 0, n_out - 1)
    for i in range(len(x) // 2, len(x) - 1):
        if bucket[i - 1] == bucket[i] == bucket[i + 1] and y[i - 1] < y[i] < y[i + 1]:
            return i
    raise AssertionError("no interior non-extreme row found")


def test_extrema_oracle_rejects_dropped_row_in_direct_tier(monkeypatch) -> None:
    n = 10_000
    x, y = bench_line._series(n)
    drop = _interior_non_extreme_row(x, y)
    # Control: the row's bucket min/max is unchanged without it (strictly
    # between same-bucket neighbours), so only the row count can fail.
    left, right = y[drop - 1], y[drop + 1]
    assert left < y[drop] < right
    assert bench_line._extrema_ok(x, y)
    real = np.frombuffer

    def drop_row(*args, **kwargs):
        out = real(*args, **kwargs)
        return np.delete(out, drop) if kwargs.get("count") == n else out

    monkeypatch.setattr(bench_line.np, "frombuffer", drop_row)
    assert not bench_line._extrema_ok(x, y)


def test_extrema_oracle_rejects_value_tamper_in_y_only(monkeypatch) -> None:
    n = 10_000
    x, y = bench_line._series(n)

    def flatten_peak(call: int, out):
        if call == 2:  # y column
            out[int(np.argmax(out))] = out.min()
        return out

    _patch_frombuffer(monkeypatch, n, flatten_peak)
    assert not bench_line._extrema_ok(x, y)
