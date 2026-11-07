"""Public native checkpoint; no HTML/PNG/SVG or browser acceptance claim."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

import xyg
from xyg import _native
from xyg._graph_session import GraphSession
from xyg._graphforge_container import DTYPE as D
from xyg._graphforge_container import decode_container, encode_container

FIXTURE = json.loads((Path(__file__).parent / "fixtures/temporal/frozen-history.json").read_text())


def ids(values):
    return np.asarray([[v] * 16 for v in values], dtype=np.uint8).reshape(-1, 16)


def packed(values):
    return ids(values).tobytes()


def graph():
    f = FIXTURE
    return xyg.TemporalGraph(
        node_ids=ids(f["nodes"]),
        edge_ids=ids(f["edges"]),
        source_ids=ids(f["sources"]),
        target_ids=ids(f["targets"]),
        node_valid_from=(np.asarray(f["validFrom"], dtype=np.int64), np.ones(3, np.uint8)),
        node_valid_to=(np.asarray(f["validTo"], dtype=np.int64), np.ones(3, np.uint8)),
    )


def publish(g, frame):
    return g.frame(
        revision=frame["revision"], cursor=frame["cursor"], range=tuple(FIXTURE["range"])
    )


def freeze(g, revision, **kw):
    return g.freeze(
        revision=revision, timezone=FIXTURE["timezone"], window=tuple(FIXTURE["window"]), **kw
    )


def reencode(fields):
    # Independent standard-library checksum and existing framing codec oracle.
    dtypes = {
        "version": D.U32,
        "identity": D.U64,
        "time": D.I64,
        "window.kind": D.U32,
        "window": D.I64,
        "timezone": D.UTF8,
        "edge.source": D.U64,
        "edge.target": D.U64,
        "node.visibility": D.U8,
        "edge.visibility": D.U8,
        "focus.kind": D.U32,
        "render.identity": D.U64,
        "render.camera": D.F64,
        "render.document": D.BYTES,
        "render.publication": D.BYTES,
    }
    body = encode_container(
        "XYFG",
        [(name, index, dtypes.get(name, D.UUID), value) for (name, index), value in fields.items()],
    )
    return (
        body
        + hashlib.blake2s(
            b"xyg-frozen-temporal-v1" + body, digest_size=8, person=b"xykeyv1"
        ).digest()
    )


def test_public_freeze_history_exact_uuid_state_independent_lifetime():
    g = graph()
    snapshots = []
    try:
        g.set_selection(nodes=ids([3]), edges=ids([13])).set_focus(
            "node", bytes([3]) * 16
        ).set_pinned(ids([3]))
        for frame in FIXTURE["frames"]:
            publish(g, frame)
            f = freeze(g, frame["revision"])
            snapshots.append((f, f.to_bytes()))
            if os.environ.get("XYG_FROZEN_CAPTURE"):
                Path(
                    os.environ["XYG_FROZEN_CAPTURE"], f"frame-{frame['revision']}.xyfg"
                ).write_bytes(f.to_bytes())
            m = f.metadata
            assert m["visible.node.uuid"] == packed(frame["nodes"])
            assert m["visible.edge.uuid"] == packed(frame["edges"])
            assert m["selected.node.uuid"] == packed([3]) and m["selected.edge.uuid"] == packed(
                [13]
            )
            assert (
                m["pinned.node.uuid"] == packed([3])
                and m["focus.uuid"] == packed([3])
                and m["focus.kind"] == (1,)
            )
            assert m["time"] == (frame["cursor"], 0, 40) and m["window"] == (0, 40)
            assert m["timezone"] == FIXTURE["timezone"] and m["identity"][1] == frame["revision"]
            assert m["render.identity"] == (0, 0)
            with pytest.raises(TypeError):
                m["time"] = (0, 0, 0)
        g.set_selection(nodes=ids([1])).set_focus().set_pinned()
        g.close()
        for f, raw in snapshots:
            assert f.to_bytes() == raw
            assert reencode(decode_container(raw[:-8], "XYFG")) == raw
            with xyg.FrozenTemporalGraph.from_bytes(raw) as restored:
                assert restored.to_bytes() == raw
    finally:
        g.close()
        for f, _ in snapshots:
            f.close()
            f.close()


def test_stale_invalid_window_timezone_capacity_and_malformed_import():
    with graph() as g:
        with pytest.raises(xyg.TemporalGraphError):
            freeze(g, 1)
        publish(g, FIXTURE["frames"][0])
        with freeze(g, 1) as f:
            raw = f.to_bytes()
            peak = len(raw) * 16 + 65536
            with pytest.raises(xyg.TemporalGraphError) as e:
                xyg.FrozenTemporalGraph.from_bytes(raw, budget_bytes=peak - 1)
            assert e.value.status == -11
            with xyg.FrozenTemporalGraph.from_bytes(raw, budget_bytes=peak) as imported:
                assert imported.to_bytes() == raw
            for data in [raw[:-1], raw + b"\0", raw[:40] + bytes([raw[40] ^ 1]) + raw[41:]]:
                with pytest.raises(xyg.TemporalGraphError):
                    xyg.FrozenTemporalGraph.from_bytes(data)
            for field, value in [
                ("visible.node.uuid", packed([2, 1, 3])),
                ("node.uuid", packed([1, 1, 3])),
                ("edge.target", [0, 0, 99, 0]),
                ("selected.node.uuid", packed([99])),
                ("focus.uuid", packed([99])),
                ("window", [40, 0]),
                ("render.identity", [3, 1]),
                ("identity", [0, 1]),
            ]:
                fields = decode_container(raw[:-8], "XYFG")
                fields[field, 0] = value
                with pytest.raises(xyg.TemporalGraphError):
                    xyg.FrozenTemporalGraph.from_bytes(reencode(fields))
        for kw in [{"budget_bytes": 1}, {"budget_bytes": 384 * 1024 * 1024 + 1}]:
            with pytest.raises(xyg.TemporalGraphError):
                freeze(g, 1, **kw)
        for zone in ["", "UTC\0", "UTC\n", "x" * 129]:
            with pytest.raises(xyg.TemporalGraphError):
                g.freeze(revision=1, timezone=zone)
        for window in [(5, 5), (6, 8), (10, 0)]:
            with pytest.raises(xyg.TemporalGraphError):
                g.freeze(revision=1, timezone="UTC", window=window)
        publish(g, FIXTURE["frames"][1])
        with pytest.raises(xyg.TemporalGraphError) as e:
            freeze(g, 1)
        assert e.value.status == -14


def document():
    return encode_container(
        "XYGF",
        [
            ("status", 0, D.U32, [0]),
            ("kind", 0, D.UTF8, "graph"),
            ("composition.version", 0, D.U32, [2]),
            ("node.uuid", 0, D.UUID, packed(FIXTURE["nodes"])),
            ("edge.uuid", 0, D.UUID, packed(FIXTURE["edges"])),
            ("edge.derived", 0, D.U8, [0] * 4),
            ("edge.layer", 0, D.U32, [0xFFFFFFFF] * 4),
            ("edge.order", 0, D.I64, [-1] * 4),
            ("edge.path", 0, D.U64, [0xFFFFFFFFFFFFFFFF] * 4),
            ("edge.source", 0, D.U64, [0, 0, 1, 0]),
            ("edge.target", 0, D.U64, [1, 1, 2, 0]),
            ("node.status", 0, D.U8, [0, 1, 2]),
            ("edge.status", 0, D.U8, [0, 1, 2, 3]),
        ],
    )


def request(seq, op, rev=0, extra=()):
    return encode_container(
        "XYGI",
        [
            ("header.u64", 0, D.U64, [971123, 9, seq]),
            ("header.u32", 0, D.U32, [rev, op, 0, 0, 0, 0, 0, 0, 0]),
            *extra,
        ],
    )


def test_capture_actual_bound_publication_and_cross_instance_rejection():
    doc = document()
    opening = request(
        1,
        19,
        extra=[
            ("document.bytes", 0, D.BYTES, doc),
            ("load.x.f64", 0, D.F64, FIXTURE["positions"]["x"]),
            ("load.y.f64", 0, D.F64, FIXTURE["positions"]["y"]),
        ],
    )
    with (
        graph() as g,
        graph() as other,
        GraphSession(doc, opening, instance_id=971123, group_id=9) as session,
    ):
        publish(g, FIXTURE["frames"][0])
        publish(other, FIXTURE["frames"][0])
        bound = session.bind_temporal(
            request(2, 18, extra=[("temporal.u64", 0, D.U64, [g._open_handle()])])
        )
        rev = int(decode_container(bound, "XYGR")["header.u32", 0][0])
        reply = session.render(
            request(3, 21, rev, extra=[("camera.f64", 0, D.F64, FIXTURE["camera"])])
        )
        rev = int(decode_container(reply, "XYGR")["header.u32", 0][0])
        with freeze(g, 1, session=session, render_revision=rev) as f:
            raw = f.to_bytes()
            if os.environ.get("XYG_FROZEN_CAPTURE"):
                Path(os.environ["XYG_FROZEN_CAPTURE"], "retained.xyfg").write_bytes(raw)
            assert (
                f.metadata["render.publication"] == reply and f.metadata["render.document"] == doc
            )
            assert f.metadata["render.identity"] == (971123, rev)
            assert f.metadata["render.camera"] == tuple(FIXTURE["camera"])
            assert (
                len(decode_container(reply, "XYGR")["paint.piece.geometry.f64", 0]) > 0
            )  # loops/parallel pieces retained
            with pytest.raises(xyg.TemporalGraphError):
                freeze(other, 1, session=session, render_revision=rev)
            with pytest.raises(xyg.TemporalGraphError):
                freeze(g, 1, session=session, render_revision=rev + 1)
            # Later selection/pin/focus and camera publication cannot rewrite either snapshot.
            g.set_selection(nodes=ids([1]), edges=ids([11])).set_focus(
                "edge", bytes([11]) * 16
            ).set_pinned(ids([1]))
            camera = list(FIXTURE["camera"])
            camera[2] += 20
            later = session.render(request(4, 21, rev, extra=[("camera.f64", 0, D.F64, camera)]))
            later_rev = int(decode_container(later, "XYGR")["header.u32", 0][0])
            with freeze(g, 1, session=session, render_revision=later_rev) as changed:
                if os.environ.get("XYG_FROZEN_CAPTURE"):
                    Path(os.environ["XYG_FROZEN_CAPTURE"], "retained-later.xyfg").write_bytes(
                        changed.to_bytes()
                    )
                assert changed.metadata["render.publication"] == later and later != reply
                assert changed.metadata["render.camera"] == tuple(camera)
                assert (
                    changed.metadata["selected.node.uuid"] == b""
                )  # frame state stays at frame publication
            assert f.to_bytes() == raw
            malformed = decode_container(raw[:-8], "XYFG")
            malformed["render.document", 0] = malformed["render.document", 0].replace(
                packed([1, 2, 3]), packed([2, 1, 3])
            )
            with pytest.raises(xyg.TemporalGraphError):
                xyg.FrozenTemporalGraph.from_bytes(reencode(malformed))
            publish(g, FIXTURE["frames"][1])
            with pytest.raises(xyg.TemporalGraphError):
                freeze(g, 2, session=session, render_revision=later_rev)
            session.close()
            g.close()
            assert f.to_bytes() == raw
            with xyg.FrozenTemporalGraph.from_bytes(raw) as imported:
                assert imported.to_bytes() == raw


def test_native_short_copy_no_partial_write_and_registry_capacity():
    lib = _native._lib
    with graph() as g:
        publish(g, FIXTURE["frames"][0])
        zone = (ct.c_uint8 * 3).from_buffer_copy(b"UTC")
        handle = ct.c_uint64()
        assert (
            lib.xyg_temporal_graph_freeze(
                g._open_handle(), 1, 0, 0, 0, zone, 3, 0, 0, 1 << 20, ct.byref(handle)
            )
            == 0
        )
        try:
            n = ct.c_uint64()
            assert lib.xyg_temporal_graph_frozen_copy(handle.value, None, 0, ct.byref(n)) == -9
            out = (ct.c_uint8 * n.value)(*([0xA5] * n.value))
            assert (
                lib.xyg_temporal_graph_frozen_copy(handle.value, out, n.value - 1, ct.byref(n))
                == -9
            )
            assert bytes(out) == b"\xa5" * n.value
        finally:
            assert lib.xyg_temporal_graph_frozen_destroy(handle.value) == 0
        assert lib.xyg_temporal_graph_frozen_copy(handle.value, None, 0, ct.byref(n)) == -8
        snapshots = []
        try:
            for _ in range(256):
                snapshots.append(freeze(g, 1))
            with pytest.raises(xyg.TemporalGraphError) as e:
                freeze(g, 1)
            assert e.value.status == -2
            assert snapshots[0].metadata["identity"][1] == 1
        finally:
            for f in snapshots:
                f.close()
        with freeze(g, 1) as f:
            assert f.metadata["identity"][1] == 1
