"""Native quantiles / Tukey box stats parity with the prior NumPy path."""

from __future__ import annotations

import numpy as np
import pytest

from xy import kernels
from xy.marks import _distribution_stats


def _legacy_distribution_stats(group: np.ndarray):
    finite = group[np.isfinite(group)]
    if len(finite) == 0:
        empty = np.empty(0, dtype=np.float64)
        return (np.nan, np.nan, np.nan, np.nan, np.nan, empty)
    q1, median, q3 = np.percentile(finite, [25.0, 50.0, 75.0])
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    low = float(np.min(finite[finite >= lo_fence]))
    high = float(np.max(finite[finite <= hi_fence]))
    outliers = finite[(finite < low) | (finite > high)]
    return float(q1), float(median), float(q3), low, high, outliers


@pytest.mark.parametrize(
    "vals",
    [
        np.array([0.0, 10.0, 11.0, 12.0, 13.0, 14.0, 40.0]),
        np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        np.linspace(-3.0, 3.0, 101),
        np.array([np.nan, 1.0, 2.0, np.inf, 3.0, 100.0]),
        np.array([], dtype=np.float64),
        np.array([np.nan, np.inf], dtype=np.float64),
    ],
)
def test_box_stats_match_legacy_percentiles(vals: np.ndarray) -> None:
    got = _distribution_stats(vals)
    exp = _legacy_distribution_stats(vals)
    for a, b in zip(got[:5], exp[:5], strict=True):
        if np.isnan(b):
            assert np.isnan(a)
        else:
            assert a == pytest.approx(b, rel=0, abs=1e-12)
    np.testing.assert_allclose(np.sort(got[5]), np.sort(exp[5]), atol=1e-12)


def test_quantiles_match_numpy_linear() -> None:
    rng = np.random.default_rng(0)
    data = rng.normal(size=257)
    probs = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    got = kernels.quantiles(data, probs)
    exp = np.quantile(data, probs, method="linear")
    np.testing.assert_allclose(got, exp, atol=1e-12)


def test_quantiles_reject_bad_probs() -> None:
    with pytest.raises(ValueError, match="probabilities"):
        kernels.quantiles(np.array([1.0, 2.0]), np.array([1.5]))
