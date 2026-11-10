"""Notebook regions use graph identity and the Rust induced-edge reducer."""

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import xyg
from test_graph_widget import message, widget


@contextmanager
def compiled_region_widget(*, x=None, y=None, extra=False, composition=None):
    selected, sent = [], []
    if composition is None:
        chart, view = widget(on_select=selected.append)
    else:
        chart = xyg.graphforge_chart(composition, on_select=selected.append)
        view = chart.widget()
    if extra:
        chart.children = (*chart.children, xyg.scatter([0.0, 3.0], [2.0, 3.0], name="extra"))
    view.send = lambda content, buffers=(): sent.append((content, buffers))
    try:
        count = chart._graphforge_composition.nodes.count
        figure, _ = view._compile(
            SimpleNamespace(
                x=np.arange(count, dtype=np.float64) * 4
                if x is None
                else np.asarray(x, dtype=np.float64),
                y=np.arange(count, dtype=np.float64) % 2
                if y is None
                else np.asarray(y, dtype=np.float64),
                step=1,
                alpha=1.0,
            )
        )
        view._figure = figure
        view._figures = {1: figure}
        view._revision = 1
        view._epoch = "first"
        view._figure_versions = {1: dict(view._state_versions)}
        view._ack = asyncio.Event()
        view._ack.set()
        yield view, figure, selected, sent
    finally:
        view.close()


def identities(composition, nodes=(), edges=()):
    return {
        *(("node", composition.nodes.uuid[i]) for i in nodes),
        *(("edge", composition.edges.uuid[i]) for i in edges),
    }


def resolved(selection):
    return {(row["kind"], row["uuid"]) for row in selection.graphforge}


def test_widget_box_selects_exact_nodes_parallel_edges_and_induced_self_loop():
    with compiled_region_widget() as (view, figure, selected, sent):
        message(view, "select", x0=-1, x1=4.5, y0=-1, y1=2)
        composition = view._chart._graphforge_composition
        assert resolved(selected[-1]) == identities(composition, [0, 1], [0, 1, 2])
        assert selected[-1].per_trace[figure._graph_meta[0]["node_trace"]].tolist() == [0, 1]
        assert selected[-1].per_trace[figure._graph_meta[0]["edge_trace"]].tolist() == [
            0,
            1,
            2,
            3,
            4,
        ]
        assert sent[-1][0]["type"] == "selection"


def test_region_keeps_layer_result_rows_and_derived_edge_identity():
    from test_graphforge import _compose

    composition = _compose("pagerank", "node_similarity")
    with compiled_region_widget(composition=composition) as (view, figure, selected, sent):
        message(view, "select", x0=-1, x1=1e9, y0=-1, y1=2)
        sources = set(range(composition.nodes.count))
        edges = [
            i
            for i, (a, b) in enumerate(
                zip(composition.edges.source, composition.edges.target, strict=True)
            )
            if a in sources and b in sources
        ]
        expected = [composition.identify("node", i) for i in sorted(sources)]
        expected += [composition.identify("edge", i) for i in edges]
        fields = ("kind", "uuid", "index", "layers")

        def normalize(row):
            return {key: row[key] for key in fields}

        assert sorted(
            selected[-1].graphforge, key=lambda row: (row["kind"], row["index"])
        ) == sorted(
            [normalize(row) for row in expected], key=lambda row: (row["kind"], row["index"])
        )
        assert any(row["layers"] for row in selected[-1].graphforge)
        assert any(row["kind"] == "edge" and row["uuid"] is None for row in selected[-1].graphforge)
        assert sent[-1][0]["type"] == "selection"


def test_row_space_stamp_survives_translation_and_reaches_ordinary_payload_refresh():
    with compiled_region_widget() as (_, figure, _, _):
        identity = figure._notebook_graph_identity
        stamp = identity.row_space()
        assert len(stamp) == 64
        assert figure.build_payload_split()[0]["_graph_row_space"] == stamp
        figure.traces[identity.meta["node_trace"]].style["color"] = "red"
        assert figure.build_payload_split()[0]["_graph_row_space"] == stamp
    with compiled_region_widget(x=[100, 104, 108, 112, 116], y=[50, 51, 50, 51, 50]) as (
        _,
        figure,
        _,
        _,
    ):
        assert figure._notebook_graph_identity.row_space() == stamp


@pytest.mark.parametrize(
    "plane", ["ids", "source_edge_ids", "member_of", "render_edge_index", "offsets", "members"]
)
def test_row_space_stamp_binds_every_ordered_identity_and_membership_plane(plane):
    with compiled_region_widget() as (_, figure, _, _):
        identity = figure._notebook_graph_identity
        before = identity.row_space()
        if plane in ("ids", "source_edge_ids", "member_of"):
            value = list(identity.meta[plane])
            value[0], value[1] = value[1], value[0]
            identity.meta[plane] = value
        else:
            trace = identity.meta["edge_trace"]
            edge = figure._graph_edge_identity[trace]
            value = np.array(getattr(edge, plane), copy=True)
            value[0] += 1
            figure._graph_edge_identity[trace] = replace(edge, **{plane: value})
        assert identity.row_space() != before


def test_row_space_stamp_binds_trace_partition_and_shipped_subset_mapping():
    with compiled_region_widget() as (_, figure, _, _):
        identity = figure._notebook_graph_identity
        trace = figure.traces[identity.meta["node_trace"]]
        original = trace.shipped_sel
        before = identity.row_space()
        trace.shipped_sel = np.array([1, 0], dtype=np.uint64)
        subset = identity.row_space()
        assert subset != before
        trace.shipped_sel = np.array([0, 1], dtype=np.uint64)
        assert identity.row_space() not in (before, subset)
        trace.shipped_sel = original
        assert identity.row_space() == before
        figure.traces.append(trace)
        identity.meta["node_trace"] = len(figure.traces) - 1
        assert identity.row_space() != before


def test_concave_lasso_preserves_other_scatter_and_excludes_crossing_edges():
    with compiled_region_widget(x=[0, 4, 4, 0, 2], y=[0, 0, 4, 4, 2], extra=True) as (
        view,
        figure,
        selected,
        sent,
    ):
        polygon = [[-1, -1], [5, -1], [5, 1], [1, 1], [1, 5], [-1, 5]]
        message(view, "select_polygon", points=polygon)
        assert resolved(selected[-1]) == identities(
            view._chart._graphforge_composition, [0, 1, 3], [0, 1, 2]
        )
        extra = next(t.id for t in figure.traces if t.name == "extra")
        assert selected[-1].per_trace[extra].tolist() == [0]
        assert figure.view_state()["selection"] == {"polygon": polygon}
        assert sent[-1][0]["type"] == "selection"


@pytest.mark.parametrize("hidden", ["nodes", "edges"])
def test_legend_hidden_graph_traces_stay_outside_selection(hidden):
    with compiled_region_widget() as (view, figure, selected, _):
        meta = figure._graph_meta[0]
        figure.legend_toggle(meta["node_trace" if hidden == "nodes" else "edge_trace"], True)
        message(view, "select", x0=-1, x1=4.5, y0=-1, y1=2)
        expected = identities(
            view._chart._graphforge_composition, [] if hidden == "nodes" else [0, 1]
        )
        assert resolved(selected[-1]) == expected


def test_publication_mismatch_refuses_before_callbacks_masks_or_predicate_change():
    with compiled_region_widget() as (view, figure, selected, sent):
        message(view, "select", x0=-1, x1=4.5, y0=-1, y1=2)
        before = figure.view_state()
        old_count = len(selected)
        figure._graph_meta[0]["member_of"] = [1, 0, 2, 3, 4]
        message(view, "select", x0=-1, x1=20, y0=-1, y1=2)
        assert len(selected) == old_count
        assert figure.view_state() == before
        assert sent[-1][0] == {
            "type": "selection_refused",
            "code": "XYG_GRAPH_SELECTION_PUBLICATION_UNSUPPORTED",
            "selection": before["selection"],
            "graph_revision": 1,
        }


def test_stale_region_message_never_resolves_against_a_newer_frame():
    with compiled_region_widget() as (view, figure, selected, sent):
        message(view, "select", revision=0, x0=-1, x1=20, y0=-1, y1=2)
        assert not selected and not sent
        assert figure.view_state()["selection"] is None


def test_uuid_intent_cap_counts_nodes_and_edges_before_any_mask_is_sent():
    from xyg._graph_session import GraphSessionError, GraphSessionStatus

    count = 9_999
    ids = [(i + 1).to_bytes(16, "big") for i in range(count)]
    composition = xyg.compose_graphforge(
        base={
            "node_uuid": b"".join(ids),
            "edge_uuid": ids[0] + ids[1],
            "edge_source_uuid": ids[0] + ids[0],
            "edge_target_uuid": ids[1] + ids[2],
        }
    )
    view = xyg.graphforge_chart(composition).widget()
    sent = []
    view.send = lambda content, buffers=(): sent.append((content, buffers))
    try:
        figure, _ = view._compile(
            SimpleNamespace(x=np.arange(count, dtype=float), y=np.zeros(count), step=1, alpha=1.0)
        )
        view._figure = figure
        view._figures = {1: figure}
        view._revision = 1
        view._epoch = "first"
        view._figure_versions = {1: dict(view._state_versions)}
        view._ack = asyncio.Event()
        view._ack.set()
        view.select(uuids=[composition.nodes.uuid[0]])
        assert sent[-1][0]["type"] == "selection_rows"
        before, previous_count = view.view_state(), len(sent)
        with pytest.raises(GraphSessionError) as error:
            view.select(uuids=list(composition.nodes.uuid))
        assert error.value.status == GraphSessionStatus.SELECTION_TOO_LARGE
        assert len(sent) == previous_count and view.view_state() == before
    finally:
        view.close()


def test_real_native_owner_capacity_refusal_can_retry_after_another_owner_releases():
    from test_graphforge import _base
    from xyg._graph_session import GraphSession, GraphSessionError, GraphSessionStatus
    from xyg._graphforge_container import DTYPE as D
    from xyg._graphforge_container import encode_container

    composition = xyg.compose_graphforge(base=_base("property"))
    owners = []
    try:
        for instance in range(1, 258):
            opening = encode_container(
                "XYGI",
                [
                    ("header.u64", 0, D.U64, [instance, 0, 1]),
                    ("header.u32", 0, D.U32, [0, 19, 0, 0, 0, 0, 0, 0, 0]),
                    ("document.bytes", 0, D.BYTES, composition.bytes),
                ],
            )
            try:
                owners.append(
                    GraphSession(composition.bytes, opening, instance_id=instance, group_id=0)
                )
            except GraphSessionError as error:
                assert error.status == GraphSessionStatus.CAPACITY
                break
        else:
            raise AssertionError("native registry did not enforce its unchanged owner cap")
        assert owners
        with compiled_region_widget() as (view, figure, selected, sent):
            adapter = figure._notebook_graph_identity
            assert adapter.session is None and adapter._error is None
            message(view, "select", x0=-1, x1=4.5, y0=-1, y1=2)
            assert not selected
            assert sent[-1][0]["type"] == "selection_refused"
            assert sent[-1][0]["code"] == "XYG_GRAPH_SELECTION_RESOURCE_LIMIT"
            assert figure.view_state()["selection"] is None
            assert adapter.session is None and adapter._error is None
            owners.pop().close()
            message(view, "select", x0=-1, x1=4.5, y0=-1, y1=2)
            assert sent[-1][0]["type"] == "selection"
            assert resolved(selected[-1]) == identities(
                view._chart._graphforge_composition, [0, 1], [0, 1, 2]
            )
    finally:
        for owner in owners:
            owner.close()


@pytest.mark.parametrize("side", ["nodes", "edges"])
def test_source_identity_mismatch_refuses_even_with_equal_geometry(side):
    with compiled_region_widget() as (view, figure, selected, sent):
        meta = figure._graph_meta[0]
        name = "ids" if side == "nodes" else "source_edge_ids"
        values = list(meta[name])
        values[0], values[1] = values[1], values[0]
        meta[name] = values
        message(view, "select", x0=-1, x1=20, y0=-1, y1=2)
        assert not selected
        assert sent[-1][0]["type"] == "selection_refused"
        assert sent[-1][0]["code"] == "XYG_GRAPH_SELECTION_PUBLICATION_UNSUPPORTED"
        assert figure.view_state()["selection"] is None


def test_region_reply_freezes_accepted_predicate_before_reentrant_callback():
    with compiled_region_widget() as (view, figure, selected, sent):
        original = view._callbacks.on_select
        # The public callback can issue a newer API row selection before the
        # geometric query returns. Its pushed rows must remain distinguishable.
        view._callbacks = replace(
            view._callbacks,
            on_select=lambda selection: (
                original(selection),
                view.select(rows={figure._graph_meta[0]["node_trace"]: [4]}),
            ),
        )
        message(view, "select", x0=-1, x1=4.5, y0=-1, y1=2, seq=31)
        response = sent[-1][0]
        assert sent[-2][0]["type"] == "selection_rows"
        assert response["seq"] == 31
        assert response["selection"] == {"range": {"x0": -1, "x1": 4.5, "y0": -1, "y1": 2}}
        assert figure.view_state()["selection"] == {"rows": True}


def test_refusal_echoes_sequence_without_mutating_accepted_predicate_or_intent():
    with compiled_region_widget() as (view, figure, selected, sent):
        message(view, "select", x0=-1, x1=4.5, y0=-1, y1=2, seq=1, mode="x")
        previous = figure.view_state()["selection"]
        assert previous["range"]["mode"] == "x"
        figure._graph_meta[0]["member_of"][0] = 4
        message(view, "select_polygon", points=[[0, 0], [4, 0], [0, 4]], seq=2)
        assert sent[-1][0]["type"] == "selection_refused"
        assert sent[-1][0]["seq"] == 2
        assert sent[-1][0]["selection"] == previous
        assert figure.view_state()["selection"] == previous


@pytest.mark.parametrize(
    "replacement",
    [
        "# node scripts/graph_notebook_regions_smoke.mjs",
        "node scripts/graph_notebook_regions_smoke.mjs || true",
        "XYG_GRAPH_REGION_DPR=2 node scripts/graph_notebook_regions_smoke.mjs",
    ],
)
def test_required_notebook_regions_command_cannot_be_removed_or_masked(tmp_path, replacement):
    from scripts.classify_release_surface import classify
    from scripts.verify_ci_workflow import validate_workflow

    for name in ("tests/notebook_graph_regions.ipynb", "scripts/graph_notebook_regions_smoke.mjs"):
        assert classify([name])
    workflow = Path(".github/workflows/ci.yml").read_text()
    before = "          node scripts/graph_notebook_regions_smoke.mjs\n"
    assert before in workflow
    broken = tmp_path / "ci.yml"
    broken.write_text(workflow.replace(before, "          " + replacement + "\n", 1))
    assert any("Native graph notebook regions" in error for error in validate_workflow(broken))
