#!/usr/bin/env python3
"""Write Python-authoritative payload cross-host golden fixtures.

Produces ``tests/fixtures/payload_cross_host.json`` consumed by
``tests/test_payload_cross_host.py`` and ``packages/xy-node/test/payload-cross-host.test.mjs``.

Run from repo root::

    uv run python packages/xy-node/test/fixtures/write_payload_cross_host_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "python"))

from xyg import _native, channels  # noqa: E402
from xyg._figure import Figure  # noqa: E402
from xyg.config import PROTOCOL_VERSION  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "payload_cross_host.json"


def _case(name: str, figure: Figure) -> dict[str, object]:
    spec, blob = figure.build_payload()
    trace = spec["traces"][0]
    entry: dict[str, object] = {
        "name": name,
        "width": spec["width"],
        "height": spec["height"],
        "trace_id": trace["id"],
        "kind": trace["kind"],
        "tier": trace.get("tier"),
        "n_marks": trace.get("n_marks"),
        "payload_blob_len": len(blob),
        "payload_blob_sha256": hashlib.sha256(blob).hexdigest(),
        "payload_blob_hex": blob.hex(),
        "trace_keys": trace.get("keys"),
    }
    if trace.get("keys") is not None:
        lo = int(trace["keys"]["lo"])
        hi = int(trace["keys"]["hi"])
        entry["keys_lo_hex"] = blob[spec["columns"][lo]["byte_offset"] :].hex()[
            : spec["columns"][lo]["len"] * 8
        ]
        entry["keys_hi_hex"] = blob[spec["columns"][hi]["byte_offset"] :].hex()[
            : spec["columns"][hi]["len"] * 8
        ]
    return entry


def main() -> None:
    cases: list[dict[str, object]] = []

    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    fig.traces[0].id = 7
    cases.append(_case("scatter_direct", fig))

    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], color=["a", "b", "a"])
    fig.traces[0].id = 15
    cases.append(_case("scatter_categorical_color", fig))

    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.traces[0].style_channels = {"stroke_width": channels.StyleChannel([2.0, 3.0])}
    fig.traces[0].id = 34
    cases.append(_case("scatter_style_channels", fig))

    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0], color="#112233")
    fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#445566")
    fig.traces[0].id = 36
    cases.append(_case("scatter_color_ch", fig))

    fig = Figure(width=240, height=160)
    fig.line([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    fig.traces[0].id = 8
    fig.traces[0].transition_keys = np.array([[1, 2], [3, 4], [5, 6]], dtype=np.uint32)
    cases.append(_case("line_transition_keys", fig))

    fig = Figure(width=240, height=160)
    fig.set_axis("x", type_="log")
    fig.line([1.0, 10.0], [1.0, 10.0])
    fig.traces[0].id = 40
    cases.append(_case("line_log_ship_scale", fig))

    fig = Figure(width=240, height=160)
    fig.histogram([0.0, 1.0, 1.0, 2.0, 3.0], bins=3, range=(0.0, 3.0))
    fig.traces[0].id = 10
    cases.append(_case("histogram_fixed_bins", fig))

    fig = Figure(width=240, height=160)
    fig._append_rect_trace(
        "histogram",
        np.array([0.0, 1.0]),
        np.array([1.0, 2.0]),
        np.array([0.0, 0.0]),
        np.array([1.0, np.nan]),
        name=None,
        color="#3987e5",
        opacity=0.85,
        role="histogram",
        count=4,
    )
    fig.traces[0].id = 17
    cases.append(_case("histogram_finite_sel", fig))

    fig = Figure(width=240, height=160)
    fig.histogram([0.0, 1.0, 1.0, 2.0], bins=2, range=(0.0, 2.0))
    n = len(fig.traces[0].x0.values)

    fig.traces[0].style_channels = {
        "stroke_width": channels.StyleChannel(np.full(n, 2.0, dtype=np.float64))
    }
    fig.traces[0].id = 21
    cases.append(_case("histogram_style_channels", fig))

    fig = Figure(width=240, height=160)
    fig.histogram([0.0, 1.0, 1.0, 2.0], bins=2, range=(0.0, 2.0))
    rgba = np.array([[1, 0, 0, 1], [0, 1, 0, 1]], dtype=np.float64)
    fig.traces[0].stroke_ch = channels.resolve_color(rgba, 2, default_constant="transparent")
    fig.traces[0].id = 31
    cases.append(_case("histogram_stroke_ch", fig))

    fig = Figure(width=240, height=160)
    fig.histogram([0.0, 1.0, 1.0, 2.0], bins=2, range=(0.0, 2.0))
    fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#112233")
    fig.traces[0].id = 35
    cases.append(_case("histogram_color_ch", fig))

    fig = Figure(width=240, height=160)
    fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 0.0])
    fig.traces[0].id = 12
    cases.append(_case("segments_pass_through", fig))

    fig = Figure(width=240, height=160)
    fig.segments([0.0], [0.0], [1.0], [1.0], color="#112233")
    fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#445566")
    fig.traces[0].id = 22
    cases.append(_case("segments_color_ch", fig))

    fig = Figure(width=240, height=160)
    fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 0.0])
    n = len(fig.traces[0].x0.values)
    fig.traces[0].style_channels = {
        "stroke_width": channels.StyleChannel(np.full(n, 2.0, dtype=np.float64))
    }
    fig.traces[0].id = 33
    cases.append(_case("segments_style_channels", fig))

    fig = Figure(width=240, height=160)
    fig.bar([0, 1], [1, 2], color="#112233")
    fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#445566")
    fig.traces[0].id = 23
    cases.append(_case("rect_color_ch", fig))

    fig = Figure(width=240, height=160)
    fig.bar([0, 1], [1, 2])
    n = len(fig.traces[0].x0.values)
    fig.traces[0].style_channels = {
        "stroke_width": channels.StyleChannel(np.full(n, 2.0, dtype=np.float64))
    }
    fig.traces[0].id = 32
    cases.append(_case("rect_style_channels", fig))

    fig = Figure(width=240, height=160)
    fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
    fig.traces[0].style_channels = {
        "stroke_width": channels.StyleChannel(np.full(1, 2.0, dtype=np.float64))
    }
    fig.traces[0].id = 24
    cases.append(_case("mesh_style_channels", fig))

    fig = Figure(width=240, height=160)
    fig.ribbon([0.0], [1.0], [0.0], [1.0], [0.0], [1.0], color="#112233")
    fig.traces[0].style_channels = {
        "stroke_width": channels.StyleChannel(np.full(1, 2.0, dtype=np.float64))
    }
    fig.traces[0].id = 25
    cases.append(_case("ribbon_style_channels", fig))

    fig = Figure(width=240, height=160)
    fig.bar([0, 1], [1, 2])
    rgba = np.array([[1, 0, 0, 1], [0, 1, 0, 1]], dtype=np.float64)
    fig.traces[0].stroke_ch = channels.resolve_color(rgba, 2, default_constant="transparent")
    fig.traces[0].id = 26
    cases.append(_case("rect_stroke_ch", fig))

    fig = Figure(width=240, height=160)
    fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
    rgba = np.array([[1, 0, 0, 1]], dtype=np.float64)
    fig.traces[0].stroke_ch = channels.resolve_color(rgba, 1, default_constant="transparent")
    fig.traces[0].id = 27
    cases.append(_case("mesh_stroke_ch", fig))

    fig = Figure(width=240, height=160)
    fig.ribbon([0.0], [1.0], [0.0], [1.0], [0.0], [1.0], color="#112233")
    fig.traces[0].stroke_ch = channels.ColorChannel(mode="constant", constant="#445566")
    fig.traces[0].id = 28
    cases.append(_case("ribbon_stroke_ch", fig))

    fig = Figure(width=240, height=160)
    fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 0.0])
    rgba = np.array([[1, 0, 0, 1], [0, 1, 0, 1]], dtype=np.float64)
    fig.traces[0].stroke_ch = channels.resolve_color(rgba, 2, default_constant="transparent")
    fig.traces[0].id = 29
    cases.append(_case("segments_stroke_ch", fig))

    fig = Figure(width=240, height=160)
    fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0], color="#112233")
    fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#445566")
    fig.traces[0].id = 30
    cases.append(_case("mesh_color_ch", fig))

    fig = Figure(width=240, height=160)
    fig.axis_options["x"]["domain"] = (0.0, 4.0)
    fig.axis_options["y"]["domain"] = (0.0, 5.0)
    fig.hexbin(
        [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0],
        [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0],
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        name="hex",
    )
    fig.traces[0].id = 14
    cases.append(_case("hexbin_colormap", fig))

    fig = Figure(width=240, height=160)
    fig.bar([0, 1], [1, 2])
    fig.traces[0].id = 9
    cases.append(_case("bar_compact", fig))

    fig = Figure(width=240, height=160)
    fig.heatmap([[0, 1], [1, 0]], colormap="viridis")
    fig.traces[0].id = 11
    cases.append(_case("heatmap_colormap", fig))

    fig = Figure(width=240, height=160)
    fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
    fig.traces[0].id = 20
    cases.append(_case("triangle_mesh_single", fig))

    payload = {
        "schema": "xyg.payload-cross-host/v1",
        "authority": "python/xyg/_figure.py build_payload",
        "protocol": PROTOCOL_VERSION,
        "abi_version": int(_native.ABI_VERSION),
        "cases": cases,
        "gaps": {},
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
