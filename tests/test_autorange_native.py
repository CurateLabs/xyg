"""Rust-owned Figure autorange / domain (ABI 106, M2 #280)."""

from __future__ import annotations

import math

import pytest

from xyg._figure import Figure
from xyg._native import auto_domain as native_auto_domain


def test_auto_domain_matches_rust() -> None:
    assert Figure._auto_domain(None) == (0.0, 1.0)
    assert Figure._auto_domain((2.0, 5.0)) == (2.0, 5.0)
    assert Figure._auto_domain((10.0, 10.0)) == pytest.approx((9.5, 10.5))
    assert Figure._auto_domain((0.0, 0.0)) == (-0.5, 0.5)
    assert native_auto_domain(None) == (0.0, 1.0)


def test_cartesian_scatter_uses_three_percent_margin() -> None:
    figure = Figure().scatter([-5.0, 5.0], [-5.0, 5.0])
    assert figure.x_range() == pytest.approx((-5.3, 5.3))
    assert figure.y_range() == pytest.approx((-5.3, 5.3))


def test_authored_domain_short_circuits_autorange() -> None:
    figure = Figure().scatter([0.0, 1.0], [0.0, 1.0])
    figure.set_axis("x", domain=(2.0, 8.0))
    figure.set_axis("y", domain=(2.0, 8.0), reverse=True)
    assert figure.x_range() == (2.0, 8.0)
    assert figure.y_range() == (8.0, 2.0)


def test_positive_bars_pin_zero_baseline() -> None:
    figure = Figure().bar(["A", "B"], [2.0, 4.0])
    lo, hi = figure.y_range()
    assert lo == 0.0
    assert hi == pytest.approx(4.0 * 1.03)


def test_log_autorange_rejects_non_positive_data() -> None:
    figure = Figure().scatter([0.0, 1.0], [-2.0, -1.0])
    figure.set_axis("y", type_="log")
    with pytest.raises(ValueError, match="y log axis requires at least one positive value"):
        figure.y_range()


def test_polar_theta_range_is_a_full_turn() -> None:
    figure = Figure(coords="polar").scatter([0.2, 1.1], [1.0, 2.0])
    lo, hi = figure.x_range()
    assert lo == 0.0
    assert hi == pytest.approx(2.0 * math.pi)
    figure.set_axis("x", theta_unit="degrees")
    assert figure.x_range() == (0.0, 360.0)
    r_lo, r_hi = figure.y_range()
    assert r_lo == 0.0
    assert r_hi == pytest.approx(2.0)
