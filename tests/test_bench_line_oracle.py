"""The line extrema oracle must hold at every admitted size (#1027)."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

import benchmarks.bench_line as bench_line  # noqa: E402


@pytest.mark.parametrize("n", [2_000, 10_000, 100_000])
def test_extrema_oracle_passes_in_direct_and_decimated_tiers(n: int) -> None:
    # 2e3/1e4 are under the LOD budget (direct tier, lossless); 1e5 is decimated.
    x, y = bench_line._series(n)
    assert bench_line._extrema_ok(x, y)


def test_extrema_oracle_rejects_dropped_rows_in_direct_tier(monkeypatch) -> None:
    x, y = bench_line._series(10_000)
    real = bench_line.np.frombuffer

    def drop_peak(*args, **kwargs):
        out = real(*args, **kwargs)
        if kwargs.get("count") == len(y):
            out = out.copy()
            out[int(np.argmax(out))] = out.min()
        return out

    monkeypatch.setattr(bench_line.np, "frombuffer", drop_peak)
    assert not bench_line._extrema_ok(x, y)
