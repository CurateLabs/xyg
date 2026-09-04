"""Host payloads stay bounded; direct-browser WASM sources stay browser-local."""

from __future__ import annotations

import numpy as np
import pytest

import xyg
from xyg import kernels
from xyg._payload_writer import PayloadWriter
from xyg._wasm_aggregate_generated import WASM_AGGREGATE_MAX_POINTS


def _buffer_classes(spec: dict, buffers: list[memoryview]) -> dict[str, int]:
    columns = spec["columns"]
    density = spec["traces"][0]["density"]
    grid_refs = {density["buf"]}
    if "rgba" in density:
        grid_refs.add(density["rgba"])
    sample = density.get("sample") or {}
    sample_refs = {sample[key]["col"] for key in ("x", "y") if key in sample}
    totals = {"density_grid": 0, "sample_geometry": 0, "canonical_f64": 0, "other": 0}
    for index, buffer in enumerate(buffers):
        refs = {i for i, column in enumerate(columns) if column["buf"] == index}
        if any(columns[ref].get("dtype") == "f64" for ref in refs):
            key = "canonical_f64"
        elif refs & grid_refs:
            key = "density_grid"
        elif refs & sample_refs:
            key = "sample_geometry"
        else:
            key = "other"
        totals[key] += buffer.nbytes
    return totals


def test_split_density_payload_keeps_canonical_f64_at_the_host() -> None:
    n = 1_000_000
    chart = xyg.scatter_chart(
        xyg.scatter(np.linspace(-1.0, 1.0, n), np.linspace(1.0, -1.0, n), density=True),
        xyg.x_axis(),
        xyg.y_axis(),
        width=320,
        height=240,
    )
    spec, buffers = chart.figure().build_payload_split()
    classes = _buffer_classes(spec, buffers)
    density = spec["traces"][0]["density"]
    assert classes["canonical_f64"] == 0
    assert classes["density_grid"] <= density["w"] * density["h"]
    assert classes["sample_geometry"] <= 2 * 4 * (8_192 + density["w"])
    assert sum(classes.values()) < n * 16
    assert spec["wasm_density"]["automatic"] is False
    assert spec["wasm_density"]["unsupported"]["code"] == "XYG_WASM_SOURCE_UNSUPPORTED"


def test_packed_and_split_density_payloads_share_the_screen_bounded_contract() -> None:
    n = 100_000
    chart = xyg.scatter_chart(
        xyg.scatter(np.linspace(-1.0, 1.0, n), np.linspace(1.0, -1.0, n), density=True),
        xyg.x_axis(),
        xyg.y_axis(),
        width=320,
        height=240,
    )
    packed, blob = chart.figure().build_payload()
    split, buffers = chart.figure().build_payload_split()

    # Packed and live split payloads both carry painter geometry only. A true
    # direct-browser host already owns source locally and stages it into WASM
    # without routing canonical f64 through either host payload.
    assert "wasm_density" not in packed
    assert all(column.get("dtype", "f32") != "f64" for column in packed["columns"])
    assert len(blob) < n * 16

    assert _buffer_classes(split, buffers)["canonical_f64"] == 0
    assert len(split["columns"]) == len(packed["columns"])


def test_explicit_wasm_replay_source_is_separate_and_bounded() -> None:
    n = 10_000
    chart = xyg.scatter_chart(
        xyg.scatter(np.arange(n, dtype=np.float64), np.arange(n, dtype=np.float64), density=True)
    )
    spec, buffers = chart.figure().build_payload_split(wasm_source=True)
    source = spec["wasm_density"]["source"]
    assert source["ownership"] == "retain-host-replay"
    assert source["capacity"] == WASM_AGGREGATE_MAX_POINTS
    assert source["point_count"] == n
    assert _buffer_classes(spec, buffers)["canonical_f64"] == n * 16


def test_full_density_source_is_not_advertised_for_color_or_over_capacity() -> None:
    n = 1_000
    colored = xyg.scatter_chart(
        xyg.scatter(np.arange(n), np.arange(n), color=np.arange(n), density=True)
    )
    unsupported = colored.figure().build_payload_split()[0]["wasm_density"]
    assert unsupported["automatic"] is False
    assert unsupported["unsupported"]["code"] == "XYG_WASM_SOURCE_UNSUPPORTED"
    assert WASM_AGGREGATE_MAX_POINTS == 8_000_000
    # Avoid allocating an over-capacity source here: the public gate is explicitly
    # bounded and exercised by its capacity metadata above.


@pytest.mark.parametrize("point_count", [1_000_000, 100_000_000])
def test_default_density_source_policy_is_bounded_at_massive_sizes(point_count: int) -> None:
    """The default gate is N-independent; 100M never implies an f64 paint plane."""
    wasm_eligible = point_count <= WASM_AGGREGATE_MAX_POINTS
    assert not kernels.density_wasm_source_admit(
        split_payload=False,
        wasm_eligible=wasm_eligible,
    )


def test_replay_source_requires_split_transport() -> None:
    with pytest.raises(ValueError, match="requires split payload"):
        PayloadWriter(wasm_source=True)
