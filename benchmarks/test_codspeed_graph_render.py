"""CodSpeed attribution for the graph render pipeline.

Simulation mode measures deterministic CPU/native work: canonical identity
ingest, layout, bounded render-graph geometry, payload construction, and the
inherited static exporters. Browser upload, GPU paint, and frame pacing remain
wall-clock measurements in ``bench_interaction.py``; these rows do not claim
request-to-pixels latency.
"""

from __future__ import annotations

import numpy as np
import pytest

import xyg
from xyg import _graph, _native
from xyg import kernels as k

SMALL_N = 1_000
MEDIUM_N = 10_000
LARGE_N = 100_000
NODE_BUDGET = 5_000
EDGE_BUDGET = 10_000
N_BUCKETS = 2_048


@pytest.fixture(scope="session", autouse=True)
def require_native_backend() -> None:
    assert k.BACKEND == "native", f"CodSpeed requires native backend, got {k.BACKEND!r}"


def _ring(n: int) -> tuple[np.ndarray, np.ndarray]:
    sources = np.arange(n, dtype=np.uint64)
    targets = np.roll(sources, -1)
    return sources, targets


@pytest.fixture(scope="module")
def graph_data() -> dict[str, object]:
    small_sources, small_targets = _ring(SMALL_N)
    medium_sources, medium_targets = _ring(MEDIUM_N)
    large_sources, large_targets = _ring(LARGE_N)
    theta = np.linspace(0.0, 2.0 * np.pi, LARGE_N, endpoint=False)
    return {
        "small": _graph.normalize_graph_inputs(
            list(range(SMALL_N)),
            list(zip(small_sources.tolist(), small_targets.tolist(), strict=True)),
        ),
        "medium_sources": medium_sources,
        "medium_targets": medium_targets,
        "large_sources": large_sources,
        "large_targets": large_targets,
        "large_x": np.cos(theta),
        "large_y": np.sin(theta),
    }


@pytest.fixture(scope="module")
def graphforge_tables() -> tuple[dict[str, object], dict[str, object]]:
    node_ids = [index.to_bytes(16, "big") for index in range(1, MEDIUM_N + 1)]
    edge_ids = [(MEDIUM_N + index + 1).to_bytes(16, "big") for index in range(MEDIUM_N)]
    return (
        {
            "node_uuid": node_ids,
            "label": np.asarray(["Node"] * MEDIUM_N, dtype="U4"),
            "provenance_row": np.arange(MEDIUM_N, dtype=np.uint64),
        },
        {
            "edge_uuid": edge_ids,
            "src_uuid": node_ids,
            "dst_uuid": node_ids[1:] + node_ids[:1],
            "relationship_type": np.asarray(["NEXT"] * MEDIUM_N, dtype="U4"),
            "provenance_row": np.arange(MEDIUM_N, dtype=np.uint64),
        },
    )


@pytest.fixture(scope="session", autouse=True)
def warm_graph_stack() -> None:
    figure = xyg.graph_chart(
        xyg.graph(["a", "b", "c"], [("a", "b"), ("b", "c")], layout="circle"),
        width=160,
        height=120,
    ).figure()
    figure.build_payload_split(64)
    figure.to_svg(width=160, height=120)
    figure.to_png(engine=xyg.Engine.default, scale=1.0)


def test_graphforge_projection_ingest_medium(benchmark, graphforge_tables):
    nodes, edges = graphforge_tables
    graph = benchmark(xyg.from_graphforge_tables, nodes, edges)
    assert graph.n_nodes == MEDIUM_N
    assert graph.n_edges == MEDIUM_N
    assert graph.node_uuid_bytes.nbytes == MEDIUM_N * 16
    assert graph.edge_uuid_bytes.nbytes == MEDIUM_N * 16


def test_graph_force_ticks_small(benchmark, graph_data):
    data = graph_data["small"]
    x0, y0 = _native.graph_layout("circle", SMALL_N, data.sources, data.targets)
    handle = _native.graph_force_create(SMALL_N, data.sources, data.targets, x=x0, y=y0, seed=7)
    try:
        x, y, alpha = benchmark(_native.graph_force_tick, handle, SMALL_N, 5)
    finally:
        _native.graph_force_destroy(handle)
    assert len(x) == SMALL_N and len(y) == SMALL_N
    assert 0.0 <= alpha <= 1.0


def test_graph_cose_configured_ticks_small(benchmark, graph_data):
    data = graph_data["small"]
    x0, y0 = _native.graph_layout("circle", SMALL_N, data.sources, data.targets)
    pinned = np.zeros(SMALL_N, dtype=np.uint8)
    pinned[0] = 1
    handle = _native.graph_force_create(
        SMALL_N,
        data.sources,
        data.targets,
        x=x0,
        y=y0,
        seed=7,
        algorithm="cose",
        pinned=pinned,
        cose={"ideal_edge_length": 1.0, "bounds": (-2_000.0, -2_000.0, 2_000.0, 2_000.0)},
    )
    try:
        x, y, alpha = benchmark(_native.graph_force_tick, handle, SMALL_N, 5)
    finally:
        _native.graph_force_destroy(handle)
    assert (x[0], y[0]) == (x0[0], y0[0])
    assert len(x) == SMALL_N and len(y) == SMALL_N
    assert 0.0 <= alpha <= 1.0


def test_graph_render_direct_medium(benchmark, graph_data):
    sources = graph_data["medium_sources"]
    targets = graph_data["medium_targets"]
    theta = np.linspace(0.0, 2.0 * np.pi, MEDIUM_N, endpoint=False)
    result = benchmark(
        _native.graph_build_render,
        np.cos(theta),
        np.sin(theta),
        sources,
        targets,
        node_budget=MEDIUM_N,
        edge_budget=MEDIUM_N,
    )
    out_x, _out_y, _members, out_sources, _out_targets, tier, kept = result
    assert tier == 0
    assert len(out_x) == MEDIUM_N and len(out_sources) == kept == MEDIUM_N


def test_graph_render_aggregate_large(benchmark, graph_data):
    result = benchmark(
        _native.graph_build_render,
        graph_data["large_x"],
        graph_data["large_y"],
        graph_data["large_sources"],
        graph_data["large_targets"],
        node_budget=NODE_BUDGET,
        edge_budget=EDGE_BUDGET,
    )
    out_x, _out_y, members, out_sources, _out_targets, tier, kept = result
    assert tier == 2
    assert len(out_x) == 278
    assert len(out_sources) == kept == 278
    assert len(members) == LARGE_N
    assert len(np.unique(members)) == 278


def test_graph_lod_massive_policy(benchmark):
    results = benchmark(
        lambda: tuple(
            _native.graph_lod_decision(n, n * 2, node_budget=NODE_BUDGET, edge_budget=EDGE_BUDGET)
            for n in (10_000_000, 100_000_000, 1_000_000_000)
        )
    )
    assert all(tier >= 1 and kept <= EDGE_BUDGET for tier, kept in results)


def test_graph_payload_medium(benchmark):
    nodes = list(range(MEDIUM_N))
    edges = list(zip(nodes, nodes[1:] + nodes[:1], strict=True))

    def build() -> tuple[dict[str, object], list[np.ndarray]]:
        figure = xyg.graph_chart(xyg.graph(nodes, edges, layout="circle")).figure()
        return figure.build_payload_split(N_BUCKETS)

    spec, buffers = benchmark(build)
    payload_bytes = sum(buffer.nbytes for buffer in buffers)
    assert len(spec["graph"]) == 1
    assert spec["graph"][0]["n_nodes"] == MEDIUM_N
    assert spec["graph"][0]["n_edges"] == MEDIUM_N
    assert [(trace["kind"], trace["n_marks"]) for trace in spec["traces"]] == [
        # Directed routing expands each edge into shaft + two arrow wings.
        ("segments", MEDIUM_N * 3),
        ("scatter", MEDIUM_N),
    ]
    assert 0 < payload_bytes < MEDIUM_N * 160


@pytest.mark.parametrize("kind", ["svg", "png"])
def test_graph_static_export_small(benchmark, graph_data, kind):
    data = graph_data["small"]
    edges = list(zip(data.sources.tolist(), data.targets.tolist(), strict=True))
    figure = xyg.graph_chart(
        xyg.graph(data.ids, edges, layout="circle"), width=640, height=480
    ).figure()
    if kind == "svg":
        output = benchmark(figure.to_svg, width=640, height=480)
        assert output.startswith("<svg")
        assert 'width="640" height="480"' in output
        assert output.count("<circle") == SMALL_N
        # The graph shell is outside #856's bounded ordinary autorange slice,
        # so public SVG deliberately keeps the compatibility exporter.  Its
        # directed routing lowers every edge to a shaft and two arrow wings;
        # grid/chrome lines may add more, but the three-per-edge floor must hold.
        assert output.count("<line") >= SMALL_N * 3
    else:
        output = benchmark(figure.to_png, engine=xyg.Engine.default, scale=1.0)
        assert output.startswith(b"\x89PNG")
        from io import BytesIO

        from PIL import Image

        image = np.asarray(Image.open(BytesIO(output)).convert("RGB"))
        assert image.shape == (480, 640, 3)
        non_background = np.count_nonzero(np.any(image != image[0, 0], axis=2))
        assert non_background > SMALL_N
