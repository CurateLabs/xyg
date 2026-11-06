"""Public notebook path: existing composition, callback and native geometry seams."""

import asyncio
import threading

import pytest

import xyg
from test_graphforge import _base, _compose
from xyg._graph_widget import GraphWidget


def widget(**props):
    chart = xyg.graphforge_chart(xyg.compose_graphforge(base=_base("property")), **props)
    return chart, chart.widget()


async def wait_for(predicate):
    async with asyncio.timeout(10):
        while not predicate():
            await asyncio.sleep(0.005)


def message(w, kind, epoch="first", revision=None, **fields):
    w._on_custom_msg(
        w,
        {
            "type": kind,
            "graph_instance": w._instance,
            "graph_epoch": epoch,
            "graph_revision": w._revision if revision is None else revision,
            **fields,
        },
        [],
    )


@pytest.mark.parametrize(
    "props",
    [
        {},
        {"theme": "dark", "title": "Authored", "style": {"background": "#123456"}},
        {"width": "100%"},
    ],
)
def test_public_widget_defers_compile_and_preserves_presentation(props, monkeypatch):
    chart, w = widget(**props)
    assert isinstance(w, GraphWidget)
    assert chart._figure is None and w._figure is None
    assert w.view_state() == {"v": 1, "ranges": {}, "selection": None}
    w.close()


def test_native_frames_callbacks_identity_and_two_widget_isolation():
    async def journey():
        clicks, hovers, selections, views = [], [], [], []
        chart, a = widget(
            on_click=clicks.append,
            on_hover=hovers.append,
            on_select=selections.append,
            on_view_change=views.append,
            theme="dark",
            title="Authored",
            style={"background": "#123456"},
        )
        layered = _compose("louvain")
        b = xyg.graphforge_chart(layered).widget()
        messages = {a: [], b: []}
        for w in (a, b):
            w.send = lambda content, buffers=(), w=w: messages[w].append((content, buffers))
        try:
            for w in (a, b):
                message(w, "graph_mount")
            await wait_for(lambda: all(messages.values()))
            first = messages[a][0][0]
            assert first["type"] == "graph_frame" and first["step"] == 1
            assert first["spec"]["title"] == "Authored"
            assert first["spec"]["legend"] == chart.figure().build_payload_split()[0]["legend"]
            assert a._figure.style["background"] == "#123456"
            meta = a._figure._graph_meta[0]
            node, edge = meta["node_trace"], meta["edge_trace"]
            for kind in ("pick", "click"):
                message(a, kind, trace=node, index=0)
            assert (
                hovers
                and clicks
                and clicks[0]["id"] == chart._graphforge_mark.props["nodes"].ids[0]
            )
            # Every routed segment, including loops/parallel edges, resolves via
            # the original Rust route -> membership -> source UUID plane.
            data = chart._graphforge_mark.props["nodes"]
            identity = a._figure._graph_edge_identity[edge]
            assert len(data.edge_ids) > 0
            seen_edges = set()
            for segment, render in enumerate(identity.render_edge_index):
                members = identity.members_of(int(render))
                if len(members) == 1:
                    message(a, "click", trace=edge, index=segment)
                    assert clicks[-1]["edge_id"] == data.edge_ids[int(members[0])]
                    assert clicks[-1]["graphforge"] == [
                        {
                            "kind": "edge",
                            "uuid": data.edge_ids[int(members[0])],
                            "index": int(members[0]),
                            "layers": [],
                        }
                    ]
                    seen_edges.add(int(members[0]))
            assert seen_edges == set(range(len(data.edge_ids)))
            assert data.sources[0] == data.sources[1] and data.targets[0] == data.targets[1]
            assert data.sources[2] == data.targets[2]
            message(a, "select", x0=-1e9, x1=1e9, y0=-1e9, y1=1e9)
            assert selections and len(selections[-1])
            message(a, "graph_painted")
            a.select(rows={node: [0]})
            assert messages[a][-1][0]["type"] == "selection_rows"
            a.set_view({"x": [-10, 10]}, animate=False)
            assert messages[a][-1][0]["type"] == "state_patch"
            message(a, "view_change", ranges={"x": [-10, 10], "y": [-10, 10]})
            assert views
            old = a._revision
            message(a, "graph_painted")
            await wait_for(lambda: a._revision > old)
            assert [m[0]["step"] for m in messages[a] if m[0]["type"] == "graph_frame"] == [1, 9]
            n = len(clicks)
            message(a, "graph_painted")
            message(a, "click", revision=old, trace=node, index=0)
            assert len(clicks) == n
            assert b._revision == 1  # independent ACK/backpressure/lifetime
            message(a, "graph_dispose")
            message(a, "graph_mount", epoch="second")
            await wait_for(lambda: a._epoch == "second" and a._revision > old + 1)
            message(a, "click", epoch="first", trace=node, index=0)
            assert len(clicks) == n
        finally:
            a.close()
            b.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_kernel_responsive_during_compile_and_stable_worker_failure(monkeypatch):
    async def journey():
        _, w = widget()
        entered, release = threading.Event(), threading.Event()
        seen = []
        w.send = lambda content, buffers=(): seen.append(content)

        def blocked(checkpoint):
            entered.set()
            assert release.wait(5)
            raise RuntimeError("private worker details")

        monkeypatch.setattr(w, "_compile", blocked)
        try:
            message(w, "graph_mount")
            await wait_for(entered.is_set)
            await asyncio.sleep(0)  # loop executes while native/payload worker is occupied
            release.set()
            await wait_for(lambda: bool(seen))
            assert seen == [{"type": "graph_failed", "code": "XYG_GRAPH_WORKER_FAILED"}]
            assert not w._pending_api
            with pytest.raises(RuntimeError, match=r"^XYG_GRAPH_WORKER_FAILED$"):
                w.select(rows={0: [0]})
        finally:
            release.set()
            w.close()

    asyncio.run(journey())


def test_comm_on_another_notebook_loop_dispatches_callbacks_on_owner():
    async def journey():
        owner = threading.get_ident()
        callbacks = []
        _, w = widget(on_click=lambda row: callbacks.append(threading.get_ident()))
        frames = []
        w.send = lambda content, buffers=(): frames.append(content)
        try:
            w.select(rows={1: [0]})
            message(w, "graph_mount")
            await wait_for(lambda: bool(frames))
            node = w._figure._graph_meta[0]["node_trace"]

            def another_loop():
                async def comm():
                    message(w, "click", trace=node, index=0)
                    message(w, "graph_painted")

                asyncio.run(comm())

            await asyncio.get_running_loop().run_in_executor(None, another_loop)
            await wait_for(lambda: w._revision == 2)
            assert callbacks == [owner]
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_final_native_checkpoint_matches_batch_and_preserves_cached_view():
    async def journey():
        chart, w = widget()
        final = asyncio.Event()
        frames = []

        def receive(content, buffers=()):
            if content["type"] != "graph_frame":
                return
            frames.append(content["step"])
            if content["step"] == 1:
                message(w, "view_change", ranges={"x": [-20, 20], "y": [-20, 20]})
            if content["phase"] == "complete":
                final.set()
            message(w, "graph_painted")

        w.send = receive
        try:
            message(w, "graph_mount")
            await asyncio.wait_for(final.wait(), 10)
            assert frames[0] == 1 and frames[-1] == 300
            assert w.view_state()["ranges"]["x"] == [-20.0, 20.0]
            batch = chart.figure()
            import numpy as np

            node = w._figure._graph_meta[0]["node_trace"]
            np.testing.assert_array_equal(
                w._figure.traces[node].x.values, batch.traces[node].x.values
            )
            np.testing.assert_array_equal(
                w._figure.traces[node].y.values, batch.traces[node].y.values
            )
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_saved_widget_state_keeps_latest_picture_without_duplicate_buffer_sync():
    async def journey():
        _, w = widget()
        states, frames = [], []
        w.send_state = lambda key=None: states.append(key)
        w.send = lambda content, buffers=(): frames.append((content, buffers))
        try:
            message(w, "graph_mount")
            await wait_for(lambda: bool(frames))
            assert w.spec["graph_snapshot"]["step"] == 1
            assert w.spec["graph_snapshot"]["spec"] == frames[0][0]["spec"]
            assert w.buffers is frames[0][1]
            assert not states  # actual ipywidgets property lock, no duplicate trait payload
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_axes_and_css_dimensions_use_the_same_declarative_compiler():
    async def journey():
        chart = xyg.graphforge_chart(
            xyg.compose_graphforge(base=_base("property")),
            theme="dark",
            title="Styled graph",
            width="100%",
            style={"background": "#123456"},
        )
        chart.children = (
            *chart.children,
            xyg.x_axis(label="Authored X", show=True, domain=(-20, 20)),
        )
        w = chart.widget()
        frames = []
        w.send = lambda content, buffers=(): frames.append(content)
        try:
            message(w, "graph_mount")
            await wait_for(lambda: bool(frames))
            spec = frames[0]["spec"]
            assert spec["width"] == "100%" and spec["title"] == "Styled graph"
            assert spec["x_axis"]["label"] == "Authored X"
            assert spec["x_axis"]["range"] == [-20.0, 20.0]
            assert w._figure.style["background"] == "#123456"
            assert w._figure._graph_meta[0]["style_contract"]["theme"] == "dark"
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_python_commands_wait_for_their_painted_frame(monkeypatch):
    from xyg.widget import FigureWidget

    async def journey():
        sent = []
        monkeypatch.setattr(
            FigureWidget, "send", lambda self, content, buffers=None: sent.append(content)
        )
        _, w = widget()
        try:
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            message(w, "graph_painted")
            await wait_for(lambda: w._revision == 2)
            node = w._figure._graph_meta[0]["node_trace"]
            before = len(sent)
            w.select(rows={node: [0]})
            assert len(sent) == before  # revision 2 is not yet displayed
            message(w, "click", revision=1, trace=node, index=0)
            message(w, "graph_painted", revision=2)
            assert sent[-1]["type"] == "selection_rows"
            assert sent[-1]["graph_revision"] == 2
            assert w.view_state()["selection"] == {"rows": True}
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_old_readout_does_not_copy_unmodified_selection_or_ranges():
    async def journey():
        _, w = widget()
        w.send = lambda *args, **kwargs: None
        try:
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            message(w, "graph_painted")
            await wait_for(lambda: w._revision == 2)
            w._figure._record_selection({"rows": True})
            w._figure._record_view_ranges({"x": [-20, 20]})
            expected = w.view_state()
            node = w._figure._graph_meta[0]["node_trace"]
            message(w, "click", revision=1, trace=node, index=0)
            assert w.view_state() == expected
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_append_before_mount_survives_checkpoints_and_preserves_graph_envelope():
    async def journey():
        chart, w = widget()
        chart.children = (*chart.children, xyg.scatter([0.0, 1.0], [2.0, 3.0], name="extra"))
        trace = chart.figure().traces[-1].id
        w.send = lambda *args, **kwargs: None
        try:
            w.append(trace, [2.0], [4.0])
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            message(w, "graph_painted")
            assert len(w._figure.traces[trace].x) == 3
            assert w.spec["graph_host"] is True
            appended = w._figure.traces[trace]
            appended._spatial_index = object()  # derived cache belongs to that frame
            await wait_for(lambda: w._revision == 2)
            message(w, "graph_painted")
            assert w._figure.traces[trace].x is appended.x  # one canonical column
            assert w._figure.traces[trace]._spatial_index is not appended._spatial_index
            assert list(w._figure.traces[trace].x.values) == [0.0, 1.0, 2.0]
            w.append(trace, [3.0], [5.0])
            assert w.spec["graph_host"] is True
            await wait_for(lambda: w._revision == 3)
            assert list(w._figure.traces[trace].x.values) == [0.0, 1.0, 2.0, 3.0]
            assert len(w._figure.traces[trace].y) == 4
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_remount_restores_committed_view_in_first_frame():
    async def journey():
        _, w = widget()
        frames = []
        w.send = lambda content, buffers=(): frames.append(content)
        try:
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            message(w, "graph_painted")
            message(w, "view_change", ranges={"x": [-20, 20], "y": [-20, 20]})
            expected = w.view_state()["ranges"]
            message(w, "graph_mount", epoch="replacement")
            await wait_for(lambda: w._epoch == "replacement" and w._revision > 1)
            assert w.view_state()["ranges"] == expected
            first = next(f for f in reversed(frames) if f["type"] == "graph_frame")
            assert first["restore_state"]["ranges"] == expected
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_remount_cancels_commands_queued_for_the_old_mount(monkeypatch):
    from xyg.widget import FigureWidget

    async def journey():
        sent = []
        monkeypatch.setattr(
            FigureWidget, "send", lambda self, content, buffers=None: sent.append(content)
        )
        _, w = widget()
        try:
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            node = w._figure._graph_meta[0]["node_trace"]
            w.select(rows={node: [0]})
            message(w, "graph_mount", epoch="replacement")
            await wait_for(lambda: w._revision == 2)
            message(w, "graph_painted", epoch="replacement")
            assert not [m for m in sent if m["type"] == "selection_rows"]
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_remount_keeps_hidden_traces_and_categories_before_first_paint():
    async def journey():
        chart, w = widget()
        chart.children = (
            *chart.children,
            xyg.scatter([0.0, 1.0], [0.0, 1.0], color=["a", "b"], name="extra"),
        )
        frames = []
        w.send = lambda content, buffers=(): frames.append(content)
        try:
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            message(w, "graph_painted")
            extra = w._figure.traces[-1].id
            message(w, "legend_toggle", trace=0, hidden=True)
            message(w, "legend_toggle", trace=extra, category=1, hidden=True)
            message(w, "graph_mount", epoch="replacement")
            await wait_for(lambda: w._epoch == "replacement" and w._revision > 1)
            assert w._figure.traces[0].hidden
            assert w._figure.traces[extra].hidden_categories == {1}
            visibility = frames[-1]["spec"]["_graph_legend_visibility"]
            assert visibility[0]["hidden"] is True
            assert visibility[extra]["categories"] == [1]
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_typed_identity_uuid_roundtrip_layer_rows_and_retired_picture():
    async def journey():
        clicks, selections = [], []
        composition = _compose("louvain")
        chart = xyg.graphforge_chart(
            composition, on_click=clicks.append, on_select=selections.append
        )
        w = chart.widget()
        sent = []
        w.send = lambda content, buffers=(): sent.append((content, buffers))
        try:
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            meta = w._figure._graph_meta[0]
            node, edge = meta["node_trace"], meta["edge_trace"]
            message(w, "click", trace=node, index=0)
            source = meta["member_of"].index(0)
            expected = composition.identify("node", source)
            assert clicks[-1]["graphforge"] == [expected]
            assert expected["layers"]  # result id and row, not just UUID
            message(w, "select", x0=-1e9, x1=1e9, y0=-1e9, y1=1e9)
            assert {
                row["uuid"] for row in selections[-1].graphforge if row["kind"] == "node"
            } == set(composition.nodes.uuid)
            message(w, "graph_painted")
            chosen = [composition.nodes.uuid[0], composition.edges.uuid[0]]
            w.select(uuids=chosen)
            assert sent[-1][0]["type"] == "selection_rows"
            resolved = w._figure._notebook_graph_identity.select(chosen)
            assert {(row["kind"], row["uuid"]) for row in resolved} == {
                ("node", chosen[0]),
                ("edge", chosen[1]),
            }
            rows = w._figure._notebook_graph_identity.render_rows(resolved)
            assert rows[node].tolist() == [meta["member_of"][0]]
            identity = w._figure._graph_edge_identity[edge]
            assert rows[edge].tolist() == [
                i
                for i, r in enumerate(identity.render_edge_index)
                if identity.members_of(int(r)).tolist() == [0]
            ]
            retained_session = w._figure._notebook_graph_identity.session
            old = w._revision
            await wait_for(lambda: w._revision > old)
            before = len(clicks)
            message(w, "click", revision=old, trace=node, index=0)
            assert len(clicks) == before + 1  # retained displayed checkpoint
            assert clicks[-1]["graphforge"] == [expected]
            message(w, "graph_painted")
            assert retained_session._handle is None
            message(w, "click", revision=old, trace=node, index=0)
            assert len(clicks) == before + 1  # retired after new paint
            with pytest.raises(ValueError, match="cannot be combined"):
                w.select(uuids=chosen, rows={node: [0]})
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_uuid_commands_and_typed_callbacks_remain_isolated_across_mounts():
    async def journey():
        clicks = []
        chart, w = widget(on_click=clicks.append)
        _, other = widget()
        sent = []
        w.send = lambda content, buffers=(): sent.append(content)
        composition = chart._graphforge_composition
        try:
            w.select(uuids=[composition.nodes.uuid[0]])
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            node = w._figure._graph_meta[0]["node_trace"]
            message(w, "graph_painted")
            assert sent[-1]["type"] == "selection_rows"
            message(w, "click", trace=node, index=0, graph_instance=other._instance)
            assert not clicks
            message(w, "legend_toggle", trace=node, hidden=True)
            message(w, "graph_mount", epoch="replacement")
            await wait_for(lambda: w._revision > 1)
            assert w._figure.traces[node].hidden
            before = len(sent)
            w.select(uuids=[composition.nodes.uuid[1]])
            assert len(sent) == before
            message(w, "click", epoch="first", revision=1, trace=node, index=0)
            assert not clicks
            message(w, "graph_painted", epoch="replacement")
            assert sent[-1]["type"] == "selection_rows"
        finally:
            w.close()
            other.close()
            await asyncio.sleep(0)

    asyncio.run(journey())


def test_derived_edge_callback_uses_native_exact_result_reference():
    async def journey():
        composition = _compose("pagerank", "node_similarity")
        w = xyg.graphforge_chart(composition).widget()
        w.send = lambda *args, **kwargs: None
        try:
            message(w, "graph_mount")
            await wait_for(lambda: w._revision == 1)
            adapter = w._figure._notebook_graph_identity
            edge = adapter.meta["edge_trace"]
            identity = w._figure._graph_edge_identity[edge]
            seen = set()
            for segment, render in enumerate(identity.render_edge_index):
                members = identity.members_of(int(render))
                if len(members) == 1 and composition.edges.derived[int(members[0])]:
                    source = int(members[0])
                    expected = composition.identify("edge", source)
                    actual = adapter.project({edge: [segment]})
                    assert actual == [
                        {key: expected[key] for key in ("kind", "uuid", "index", "layers")}
                    ]
                    seen.add(source)
            assert seen == {
                i for i in range(composition.edges.count) if composition.edges.derived[i]
            }
        finally:
            w.close()
            await asyncio.sleep(0)

    asyncio.run(journey())
