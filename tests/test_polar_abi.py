"""Native polar projection vs the shared polar_transform fixtures (ABI 131)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xyg import _native

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "polar_transform.json").read_text(encoding="utf-8")
)
TOL = FIXTURES["tolerance_px"]
CASES = FIXTURES["cases"]


def _metrics(case: dict) -> list[float]:
    cfg = case["config"]
    theta_axis = {
        "theta_unit": cfg["unit"],
        "theta_zero": cfg["zero"],
        "theta_direction": cfg["direction"],
    }
    r_axis = {"range": cfg["r_range"]}
    return _native.polar_layout(theta_axis, r_axis, case["plot"]).tolist()


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_native_projection_matches_fixture(case: dict) -> None:
    metrics = _metrics(case)
    for point in case["points"]:
        px, py = _native.polar_project(metrics, point["theta"], point["r"])
        assert float(px) == pytest.approx(point["px"], abs=TOL), case["name"]
        assert float(py) == pytest.approx(point["py"], abs=TOL), case["name"]


def test_default_cardinals_native() -> None:
    case = next(item for item in CASES if item["name"] == "default-cardinals")
    metrics = _metrics(case)
    px, py = _native.polar_project(metrics, 0.0, 1.0)
    assert (float(px), float(py)) == pytest.approx((400.0, 200.0), abs=TOL)
    px, py = _native.polar_project(metrics, 1.5707963267948966, 1.0)
    assert (float(px), float(py)) == pytest.approx((200.0, 0.0), abs=TOL)
