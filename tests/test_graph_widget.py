"""Exercise the public default property graph widget and its native lifetime."""

import asyncio
import threading

import numpy as np
import pytest

import xyg
from test_graphforge import _base
from xyg._graph_widget import GraphWidget
from xyg._graphforge_container import DTYPE as D
from xyg._graphforge_container import decode_container, encode_container


def widget():
    return xyg.graphforge_chart(xyg.compose_graphforge(base=_base("property"))).widget()


def request(w, seq, op, revision=0):
    words = [revision, op, 0, 0, 0, 0, 0, 8 if op == 15 else 0, 0]
    sections = [
        ("header.u64", 0, D.U64, np.array([w._instance, 0, seq], dtype="<u8")),
        ("header.u32", 0, D.U32, words),
    ]
    if op == 21:
        sections.append(("camera.f64", 0, D.F64, [1, 1, 450, 210, 900, 420, 1]))
    return encode_container("XYGI", sections)


async def wait_for(predicate):
    async with asyncio.timeout(10):
        while not predicate():
            await asyncio.sleep(0.005)


def test_public_widget_defers_layout_and_static_path_stays_batch(monkeypatch):
    from xyg import _graph

    monkeypatch.setattr(_graph, "run_layout", lambda *a, **kw: pytest.fail("kernel layout"))
    w = widget()
    assert isinstance(w, GraphWidget)
    assert w._session is None
    w.close()


def test_native_progress_stale_refusal_and_two_widget_isolation():
    async def journey():
        a, b = widget(), widget()
        messages = {a: [], b: []}
        for w in (a, b):
            w.send = lambda content, buffers=(), w=w: messages[w].append((content, buffers))
        try:
            for w in (a, b):
                w._message(w, {"operation": "mount", "epoch": "first"}, [])
            await wait_for(lambda: all(messages.values()))
            assert a._instance != b._instance
            for w in (a, b):
                w._message(w, {"operation": "render", "epoch": "first"}, [request(w, 2, 21)])
            await wait_for(lambda: all(len(v) == 2 for v in messages.values()))
            initial = decode_container(messages[a][-1][1][0], "XYGR")
            assert initial["relayout.steps.u64", 0][0] == 1
            assert initial["relayout.done.u8", 0][0] == 0
            revision = int(initial["header.u32", 0][0])
            a._message(a, {"operation": "step", "epoch": "first"}, [request(a, 3, 15, revision)])
            await wait_for(lambda: len(messages[a]) == 3)
            progress = decode_container(messages[a][-1][1][0], "XYGR")
            assert progress["relayout.steps.u64", 0][0] == 9
            assert len(messages[b]) == 2
            a._message(a, {"operation": "step", "epoch": "stale"}, [request(a, 4, 15)])
            await asyncio.sleep(0.02)
            assert len(messages[a]) == 3
            a._message(a, {"operation": "step", "epoch": "first"}, [request(b, 4, 15)])
            await wait_for(lambda: len(messages[a]) == 4)
            assert messages[a][-1][0]["code"] == "XYG_GRAPH_WORKER_FAILED"
            assert len(messages[b]) == 2
        finally:
            a.close()
            b.close()

    asyncio.run(journey())


def test_kernel_responsive_and_rerender_rejects_inflight_reply(monkeypatch):
    async def journey():
        w = widget()
        entered, release = threading.Event(), threading.Event()
        original = w._execute
        seen = []
        w.send = lambda content, buffers=(): seen.append(content)

        def blocked(operation, packet):
            entered.set()
            assert release.wait(5)
            return original(operation, packet)

        monkeypatch.setattr(w, "_execute", blocked)
        try:
            w._message(w, {"operation": "mount", "epoch": "old"}, [])
            await wait_for(entered.is_set)
            # Kernel loop executes while the native worker is occupied.
            heartbeat = asyncio.create_task(asyncio.sleep(0))
            await heartbeat
            w._message(w, {"operation": "dispose", "epoch": "old"}, [])
            w._message(w, {"operation": "mount", "epoch": "new"}, [])
            release.set()
            await wait_for(lambda: bool(seen))
            assert [m["epoch"] for m in seen] == ["new"]
        finally:
            release.set()
            w.close()

    asyncio.run(journey())
