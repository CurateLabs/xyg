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


def test_extrema_oracle_rejects_dropped_row_in_direct_tier(monkeypatch) -> None:
    n = 10_000
    x, y = bench_line._series(n)
    # Columns decode x first, then y; shorten both by one element (a dropped row).
    real = np.frombuffer

    def short(*args, **kwargs):
        if kwargs.get("count") == n:
            kwargs["count"] = n - 1
        return real(*args, **kwargs)

    monkeypatch.setattr(bench_line.np, "frombuffer", short)
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
