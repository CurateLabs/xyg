"""Exact active native diagnostics for the deferred historical polar journeys."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests import test_polar_charts as polar

from xyg._static_document import UnsupportedStaticExport

CASES = json.loads((Path(__file__).parent / "fixtures/issue_889_polar_rejections.json").read_text())


@pytest.mark.parametrize(
    "case", CASES, ids=lambda case: case["test"] + str(case.get("param_index", ""))
)
def test_deferred_polar_journey_has_exact_native_reason(case):
    function = getattr(polar, case["test"])
    args = ()
    if "param_index" in case:
        mark = next(mark for mark in function.pytestmark if mark.name == "parametrize")
        parameter = mark.args[1][case["param_index"]]
        args = parameter.values if hasattr(parameter, "values") else parameter
    with pytest.raises(UnsupportedStaticExport) as error:
        function(*args)
    assert str(error.value) == case["reason"]


@pytest.mark.parametrize("index,axis", [(0, "y2"), (1, "x2")])
def test_secondary_polar_axis_has_exact_reason(index, axis):
    function = polar.test_polar_refuses_a_secondary_axis
    mark = next(mark for mark in function.pytestmark if mark.name == "parametrize")
    _label, build = mark.args[1][index]
    with pytest.raises(ValueError) as error:
        build().figure().build_payload_split()
    assert str(error.value) == (
        "XYG_POLAR_UNSUPPORTED_SECONDARY_AXIS: coords='polar' supports a single angular ('x') and radial ('y') "
        f"axis; found ['{axis}']. See spec/design/polar-axes.md."
    )
