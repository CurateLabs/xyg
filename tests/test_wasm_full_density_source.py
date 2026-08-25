"""Public host framing for the bounded direct-WASM count-only vertical."""

from __future__ import annotations

import numpy as np

import xyg
from xyg._wasm_aggregate_generated import WASM_AGGREGATE_MAX_POINTS


def test_split_density_payload_retains_one_replayable_canonical_f64_source() -> None:
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
        "kind": "cartesian-count-f64-stream-v1",
        "x": source["x"],
        "y": source["y"],
        "point_count": n,
        "trace_id": 0,
        "capacity": WASM_AGGREGATE_MAX_POINTS,
        "ownership": "retain-host-replay",
    }
    x_meta, y_meta = spec["columns"][source["x"]], spec["columns"][source["y"]]
    assert x_meta["dtype"] == y_meta["dtype"] == "f64"
    assert "worker_owned" not in x_meta and "worker_owned" not in y_meta
    assert (
        np.frombuffer(buffers[x_meta["buf"]], dtype="<f8").tolist()
        == np.linspace(-1.0, 1.0, n).tolist()
    )
    assert (
        np.frombuffer(buffers[y_meta["buf"]], dtype="<f8").tolist()
        == np.linspace(1.0, -1.0, n).tolist()
    )


def test_packed_density_payload_keeps_the_screen_bounded_export_contract() -> None:
    """The Worker-only source is an out-of-band split transport exception."""
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

    # A packed payload is used by HTML/notebook/export routes.  It carries
    # only painter geometry, never the full canonical f64 source required by
    # the live browser Worker.
    assert "wasm_density" not in packed
    assert all(column.get("dtype", "f32") != "f64" for column in packed["columns"])
    assert len(blob) < n * 16

    # This is the sole intentional exception to normal packed/split byte
    # parity: the live split route adds two replayable f64 spans and names
    # them in a browser-only top-level contract.
    source = split["wasm_density"]["source"]
    source_bytes = sum(buffers[split["columns"][source[key]]["buf"]].nbytes for key in ("x", "y"))
    assert source_bytes == n * 16
    assert len(split["columns"]) == len(packed["columns"]) + 2
    assert all("worker_owned" not in split["columns"][source[key]] for key in ("x", "y"))


def test_full_density_source_is_not_advertised_for_color_or_over_capacity() -> None:
    n = 1_000
    colored = xyg.scatter_chart(
        xyg.scatter(np.arange(n), np.arange(n), color=np.arange(n), density=True)
    )
    unsupported = colored.figure().build_payload_split()[0]["wasm_density"]
    assert unsupported["automatic"] is False
    assert unsupported["unsupported"]["code"] == "XYG_WASM_SOURCE_UNSUPPORTED"
    assert WASM_AGGREGATE_MAX_POINTS == 8_000_000
    # Avoid allocating the >8 MiB source here: the public gate is explicitly
    # bounded and exercised by its capacity metadata above.
