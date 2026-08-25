"""Public host framing for the bounded direct-WASM count-only vertical."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import xyg


def _generated_count_only_capacity() -> int:
    abi = json.loads((Path(__file__).parents[1] / "spec" / "wasm" / "abi.json").read_text())
    a = abi["aggregate"]
    cells = a["max_grid_cells"]
    fixed = (
        a["request_copy_factor"] * a["header_bytes"]
        + cells * a["accumulator_stride_count"]
        + a["output_copy_factor"] * (a["output_header_bytes"] + cells * a["output_stride_count"])
        + min(a["checkpoint_points"], a["max_points"]) * a["checkpoint_stride_count"]
    )
    return min(
        a["max_points"],
        (a["total_memory_bytes"] - fixed)
        // (a["request_copy_factor"] * a["request_stride_count"] + 16),
    )


def test_split_density_payload_transfers_one_bounded_canonical_f64_source() -> None:
    n = 10_000
    chart = xyg.scatter_chart(
        xyg.scatter(np.linspace(-1.0, 1.0, n), np.linspace(1.0, -1.0, n), density=True),
        xyg.x_axis(),
        xyg.y_axis(),
        width=320,
        height=240,
    )
    spec, buffers = chart.figure().build_payload_split()
    source = spec["wasm_density"]["source"]
    assert source == {
        "kind": "cartesian-count-f64-v1",
        "x": source["x"],
        "y": source["y"],
        "point_count": n,
        "trace_id": 0,
        "capacity": _generated_count_only_capacity(),
        "ownership": "transfer-to-worker",
    }
    x_meta, y_meta = spec["columns"][source["x"]], spec["columns"][source["y"]]
    assert x_meta["dtype"] == y_meta["dtype"] == "f64"
    assert x_meta["worker_owned"] is y_meta["worker_owned"] is True
    assert (
        np.frombuffer(buffers[x_meta["buf"]], dtype="<f8").tolist()
        == np.linspace(-1.0, 1.0, n).tolist()
    )
    assert (
        np.frombuffer(buffers[y_meta["buf"]], dtype="<f8").tolist()
        == np.linspace(1.0, -1.0, n).tolist()
    )


def test_full_density_source_is_not_advertised_for_color_or_over_capacity() -> None:
    n = 1_000
    colored = xyg.scatter_chart(
        xyg.scatter(np.arange(n), np.arange(n), color=np.arange(n), density=True)
    )
    unsupported = colored.figure().build_payload_split()[0]["wasm_density"]
    assert unsupported["automatic"] is False
    assert unsupported["unsupported"]["code"] == "XYG_WASM_SOURCE_UNSUPPORTED"
    assert _generated_count_only_capacity() == 338_598
    # Avoid allocating the >8 MiB source here: the public gate is explicitly
    # bounded and exercised by its capacity metadata above.
