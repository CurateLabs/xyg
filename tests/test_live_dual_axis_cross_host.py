"""Python/Node live-wire parity for the secondary right-hand y axis (#1006).

The same public dual-axis chart is built through both hosts; the live payload
(``build_payload``) must carry the y2 axis, per-trace view ranges, and
y2-bound annotations identically — or refuse identically. A y2 trace drawn on
the primary scale (Node previously collapsed every trace onto the primary y
range and omitted the y2 axis) or a silently dropped annotation binding is the
wrong-picture failure this locks out. Static-export identity lives in
``tests/test_static_dual_axis_cross_host.py``; the static y2-annotation
boundary (``XYG_SCENE_UNSUPPORTED_Y2_ANNOTATION``) is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import xyg.components as c
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "live_dual_axis_cross_host.mjs"
WIDTH = 480
HEIGHT = 320


@pytest.fixture(scope="module")
def node_payload() -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found on PATH")
    name = {"win32": "xyg_core.dll", "darwin": "libxyg_core.dylib"}.get(
        sys.platform, "libxyg_core.so"
    )
    native = ROOT / "target" / "release" / name
    if not native.is_file():
        pytest.skip(f"missing native core {native}")
    env = {**os.environ, "XYG_NATIVE_LIB": os.environ.get("XYG_NATIVE_LIB", str(native))}
    proc = subprocess.run(
        [node, str(NODE_SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        pytest.fail(f"Node live payload proof failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout)


def _dual(*, annotations: tuple[Any, ...] = ()) -> Any:
    return c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.line(x=[1, 2, 3], y=[100, 200, 300], y_axis="y2"),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4), label="L"),
        c.y_axis(id="y2", side="right", label="R", domain=(0, 400)),
        *annotations,
        width=WIDTH,
        height=HEIGHT,
    ).figure()


def _annotated() -> Any:
    figure = _dual(
        annotations=(
            c.text(2, 200, "secondary", y_axis="y2"),
            c.text(2, 2, "primary"),
        )
    )
    for index, trace in enumerate(figure.traces):
        trace.id = index
    return figure


def test_live_payload_marshals_y2_axes_ranges_and_annotation_bindings(
    node_payload: dict[str, Any],
) -> None:
    spec, blob = _annotated().build_payload()

    # Unequal y/y2 domains must survive to the wire on both hosts.
    assert sorted(spec["axes"]) == ["x", "y", "y2"]
    assert spec["view"]["ranges"]["y"] == [0.0, 4.0]
    assert spec["view"]["ranges"]["y2"] == [0.0, 400.0]
    assert [(t["id"], t["x_axis"], t["y_axis"]) for t in spec["traces"]] == [
        (0, "x", "y"),
        (1, "x", "y2"),
    ]
    bindings = {a["text"]: a.get("y_axis") for a in spec["annotations"]}
    assert bindings == {"secondary": "y2", "primary": None}

    # Host identity: axes, ranges, trace bindings, annotations, and the packed
    # §29 payload blob (the y2 trace encodes against its own scale) all match.
    assert spec["axes"] == node_payload["axes"]
    assert spec["view"]["ranges"] == node_payload["view_ranges"]
    assert [(t["id"], t["kind"], t["x_axis"], t["y_axis"]) for t in spec["traces"]] == [
        (t["id"], t["kind"], t["x_axis"], t["y_axis"]) for t in node_payload["traces"]
    ]
    assert spec["annotations"] == node_payload["annotations"]
    assert hashlib.sha256(blob).hexdigest() == node_payload["payload_blob_sha256"]
    assert len(blob) == node_payload["payload_blob_len"]


def test_reversed_axes_keep_their_direction_on_the_live_wire_in_both_hosts(
    node_payload: dict[str, Any],
) -> None:
    """Rust autorange applies `reverse`; the directed range ([hi, lo]) must
    reach `axes`/`view.ranges` untouched — sorting it flips the rendered
    orientation versus Python (review round 5)."""
    figure = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.line(x=[1, 2, 3], y=[100, 200, 300], y_axis="y2"),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4), reverse=True),
        c.y_axis(id="y2", side="right", domain=(0, 400), reverse=True),
        c.text(2, 100, "secondary", y_axis="y2"),
        width=WIDTH,
        height=HEIGHT,
    ).figure()
    for index, trace in enumerate(figure.traces):
        trace.id = index
    spec, blob = figure.build_payload()
    assert spec["view"]["ranges"] == {"x": [0.0, 4.0], "y": [4.0, 0.0], "y2": [400.0, 0.0]}
    assert spec["axes"]["y2"]["reverse"] is True
    assert spec["view"]["ranges"] == node_payload["reversed"]["view_ranges"]
    assert spec["axes"]["y2"]["reverse"] == node_payload["reversed"]["axes_y2_reverse"]
    assert spec["annotations"] == node_payload["reversed"]["annotations"]
    assert hashlib.sha256(blob).hexdigest() == node_payload["reversed"]["payload_blob_sha256"]


def test_an_omitted_y2_side_flows_to_rust_and_the_live_wire_matches_static(
    node_payload: dict[str, Any],
) -> None:
    """Rust owns the omitted-y2-side policy (right). The public setters keep
    the authored absence — so `side_authored` is False and the static chrome
    observation is unobserved, exactly like the raw deleted-key case — while
    the live/HTML wire mirrors Rust's resolution identically in both hosts
    (review round 6)."""

    def build(*, annotated: bool):
        children = [
            c.line(x=[1, 2, 3], y=[1, 2, 3]),
            c.line(x=[1, 2, 3], y=[100, 200, 300], y_axis="y2"),
            c.x_axis(domain=(0, 4)),
            c.y_axis(domain=(0, 4), label="L"),
            c.y_axis(id="y2", domain=(0, 400), label="R"),
        ]
        if annotated:
            children.append(c.text(2, 200, "secondary", y_axis="y2"))
        figure = c.line_chart(*children, width=WIDTH, height=HEIGHT).figure()
        for index, trace in enumerate(figure.traces):
            trace.id = index
        return figure

    figure = build(annotated=True)
    # The setter preserved the authored absence (no host default anywhere).
    assert figure.axis_options["y2"]["side"] is None
    assert node_payload["omitted_side"]["stored_side"] is None

    spec, blob = figure.build_payload()
    assert spec["axes"]["y2"]["side"] == "right"
    assert spec["axes"]["y2"] == node_payload["omitted_side"]["axes_y2"]
    assert hashlib.sha256(blob).hexdigest() == node_payload["omitted_side"]["payload_blob_sha256"]

    # HTML inherits the same live spec in both hosts.
    html = build(annotated=True).to_html()
    start = html.index("const spec = ") + len("const spec = ")
    end = html.index(";\n  const buf = ")
    assert html[start:end].startswith("{")
    embedded = json.loads(html[start:end])
    assert embedded["axes"]["y2"]["side"] == "right"
    assert node_payload["omitted_side"]["html_axes_y2_side"] == "right"

    # And the static path (Rust's decision) equals the explicit-right chart.
    # (No y2-bound annotation here: static export refuses those by design.)
    from xyg._static_document import export_figure

    explicit = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.line(x=[1, 2, 3], y=[100, 200, 300], y_axis="y2"),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4), label="L"),
        c.y_axis(id="y2", side="right", domain=(0, 400), label="R"),
        width=WIDTH,
        height=HEIGHT,
    ).figure()
    assert export_figure(build(annotated=False), "svg", width=WIDTH, height=HEIGHT) == (
        export_figure(explicit, "svg", width=WIDTH, height=HEIGHT)
    )


def test_a_y2_density_trace_bins_against_its_own_domain_in_both_hosts(
    node_payload: dict[str, Any],
) -> None:
    """A direct line column is data-relative, so blob identity alone would not
    distinguish primary from y2 ranges. The tier-2 density grid is binned
    against the trace's own domain — its bytes prove the per-trace range flows
    identically in both hosts."""
    figure = c.scatter_chart(
        c.scatter(x=[1, 2, 3], y=[1, 2, 3]),
        c.scatter(x=[1, 2, 3], y=[100, 200, 300], y_axis="y2", density=True),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4)),
        c.y_axis(id="y2", side="right", domain=(0, 400)),
        width=120,
        height=90,
    ).figure()
    for index, trace in enumerate(figure.traces):
        trace.id = index
    spec, buffers = figure.build_payload_split()
    assert spec["traces"][1]["density"]["y_range"] == [0.0, 400.0]
    assert spec["traces"][1]["density"]["y_range"] == node_payload["density_y2"]["y_range"]
    shas = [hashlib.sha256(bytes(b)).hexdigest() for b in buffers]
    assert shas == node_payload["density_y2"]["buffer_sha256s"]


def test_live_protocol_carries_the_y2_wire_contract(node_payload: dict[str, Any]) -> None:
    # v14: `annotations[].y_axis: "y2"` would be silently projected through the
    # primary scale by a cached v13 client, so the handshake must reject it.
    assert PROTOCOL_VERSION == 14
    assert node_payload["protocol"] == 14


def test_charts_without_y2_carry_no_y2_axis_or_range(node_payload: dict[str, Any]) -> None:
    figure = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4)),
        width=WIDTH,
        height=HEIGHT,
    ).figure()
    for index, trace in enumerate(figure.traces):
        trace.id = index
    spec, _ = figure.build_payload()
    assert sorted(spec["axes"]) == ["x", "y"]
    assert sorted(spec["view"]["ranges"]) == ["x", "y"]
    assert node_payload["plain_axes"] == ["x", "y"]
    assert node_payload["plain_view_ranges"] == spec["view"]["ranges"]


def test_y2_bound_annotations_fail_closed_identically_without_a_y2_axis(
    node_payload: dict[str, Any],
) -> None:
    # The public path (no declared y2) refuses at chart compile time, exactly
    # like a mark bound to an undeclared axis.
    def python_error() -> str | None:
        try:
            c.line_chart(
                c.line(x=[1, 2, 3], y=[1, 2, 3]),
                c.x_axis(domain=(0, 4)),
                c.y_axis(domain=(0, 4)),
                c.text(2, 200, "secondary", y_axis="y2"),
                width=WIDTH,
                height=HEIGHT,
            ).figure()
        except ValueError as error:
            return f"ValueError: {error}"
        return None

    def python_bad_id_error() -> str:
        try:
            c.text(2, 200, "secondary", y_axis="y3")
        except ValueError as error:
            return f"ValueError: {error}"
        raise AssertionError("invalid annotation y_axis accepted")

    python_missing = python_error()
    node_missing = node_payload["rejections"]["y2_annotation_without_axis"]
    node_bad = node_payload["rejections"]["y2_annotation_bad_id"]
    assert python_missing is not None and node_missing is not None
    assert node_bad is not None
    # Same stable diagnosis in both hosts: the binding names the missing
    # declaration (message core identical, error type is the host's own).
    core = "y_axis 'y2' has no matching xyg.y_axis(id='y2')"
    assert core in python_missing
    assert core in node_missing
    assert "y_axis must be 'y' or 'y2'" in python_bad_id_error()
    assert "y_axis must be 'y' or 'y2'" in node_bad
