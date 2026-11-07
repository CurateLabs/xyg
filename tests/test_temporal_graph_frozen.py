"""Public native checkpoint; no HTML/PNG/SVG or browser acceptance claim."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import os
import struct
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


PUBLICATION_MUTATIONS = [
    ("render.node_y.f64", [1.0, 0.0, 20.0]),
    ("render.node_x.f64", [1.0, 40.0, 80.0]),
    ("render.camera", [1.0, 1.0, 61.0, 60.0, 240.0, 180.0, 1.0]),
    ("render.camera", [2.0, 1.0, 60.0, 60.0, 240.0, 180.0, 1.0]),
    ("render.edge_target.u64", [999999, 1, 2, 0]),
    ("render.edge_source.u64", [999999, 0, 1, 0]),
    ("render.member_of.u64", [999999, 1, 2]),
    ("render.node_member_offsets.u64", [999999, 1, 2, 3]),
    ("render.node_y.f64", [float("nan"), 160, 160]),
    ("render.node_x.f64", [float("inf"), 300, 500]),
    ("render.node_y.f64", [160]),
    ("render.edge_target.u64", []),
    ("render.node_member_offsets.u64", [0, 1, 2, 999999]),
    ("render.node_member_offsets.u64", [0, 2, 1, 3]),
    ("render.node_members.u64", [0, 0, 2]),
    ("render.member_of.u64", [1, 1, 2]),
    ("render.edge_source.u64", [1, 0, 1, 0]),
    ("render.edge_member_offsets.u64", [1, 1, 2, 3, 4]),
    ("render.edge_member_offsets.u64", [0, 0, 2, 3, 4]),
    ("render.edge_member_offsets.u64", [0, 2, 1, 3, 4]),
    ("render.edge_member_offsets.u64", [0, 1, 2, 3, 999999]),
    ("render.edge_members.u64", [0, 0, 2, 3]),
    ("render.edge_visual_states.u8", []),
    ("render.emphasis.u8", []),
]


def malformed_retained_publication(name, values):
    """Reframe with authoritative original dtypes and an independent valid checksum."""
    raw = (
        Path(__file__).resolve().parents[1]
        / "spec/performance/temporal-graph-freeze-2026-11-07/retained.xyfg"
    ).read_bytes()
    outer = decode_container(raw[:-8], "XYFG")
    if name == "render.camera":
        outer[name, 0] = values
        return reencode(outer)
    publication = outer["render.publication", 0]
    fields = decode_container(publication, "XYGR")
    fields[name, 0] = values
    count = struct.unpack_from("<I", publication, 8)[0]
    names = 32 + count * 40
    descriptors = []
    for i in range(count):
        offset, size, dtype, index = struct.unpack_from("<IIII", publication, 32 + i * 40)
        field = publication[names + offset : names + offset + size].decode("ascii")
        descriptors.append((field, index, dtype, fields[field, index]))
    outer["render.publication", 0] = encode_container("XYGR", descriptors)
    return reencode(outer)


@pytest.mark.parametrize("name,values", PUBLICATION_MUTATIONS)
def test_rechecksummed_retained_publication_rejects_invalid_topology(name, values):
    with pytest.raises(xyg.TemporalGraphError):
        xyg.FrozenTemporalGraph.from_bytes(malformed_retained_publication(name, values))


def test_frozen_projection_uses_css_coordinates_independent_of_dpr():
    raw = malformed_retained_publication("render.camera", [1.0, 1.0, 60.0, 60.0, 240.0, 180.0, 2.0])
    with xyg.FrozenTemporalGraph.from_bytes(raw) as frozen:
        assert frozen.to_bytes() == raw
        assert frozen.metadata["render.camera"][-1] == 2.0


@pytest.mark.parametrize("dpr", [1, 2])
def test_rendered_exports_survive_disposal_and_reject_body_tampering(tmp_path, dpr):
    import io

    from PIL import Image

    doc = document()
    camera = list(FIXTURE["camera"])
    camera[6] = dpr
    opening = request(
        1,
        19,
        extra=[
            ("document.bytes", 0, D.BYTES, doc),
            ("load.x.f64", 0, D.F64, FIXTURE["positions"]["x"]),
            ("load.y.f64", 0, D.F64, FIXTURE["positions"]["y"]),
        ],
    )
    with graph() as g, GraphSession(doc, opening, instance_id=971123, group_id=9) as session:
        g.set_selection(nodes=ids([1]), edges=ids([11])).set_focus(
            "node", bytes([1]) * 16
        ).set_pinned(ids([1]))
        publish(g, FIXTURE["frames"][0])
        bound = session.bind_temporal(
            request(2, 18, extra=[("temporal.u64", 0, D.U64, [g._open_handle()])])
        )
        rev = int(decode_container(bound, "XYGR")["header.u32", 0][0])
        reply = session.render(request(3, 21, rev, extra=[("camera.f64", 0, D.F64, camera)]))
        rev = int(decode_container(reply, "XYGR")["header.u32", 0][0])
        frozen = freeze(g, 1, session=session, render_revision=rev)
        raw = frozen.to_bytes()
        buf = (ct.c_uint8 * len(raw)).from_buffer_copy(raw)
        sentinel = (ct.c_uint8 * 1)(0xA5)
        required = ct.c_uint64()
        status = _native._lib.xyg_temporal_graph_frozen_export(
            buf,
            len(raw),
            0,
            1.0,
            0xFFEC99AA,
            384 * 1024 * 1024,
            sentinel,
            1,
            ct.byref(required),
        )
        assert status == -9 and required.value > 1 and sentinel[0] == 0xA5
        before = {
            fmt: frozen.export(fmt, focus_rgba=(170, 153, 236, 255))
            for fmt in ("svg", "png", "html")
        }
        publish(g, FIXTURE["frames"][1])
    try:
        assert frozen.to_bytes() == raw
        for fmt, artifact in before.items():
            assert frozen.export(fmt, focus_rgba=(170, 153, 236, 255)) == artifact
            (tmp_path / f"frozen.{fmt}").write_bytes(artifact)
            if os.environ.get("XYG_FROZEN_CAPTURE"):
                Path(os.environ["XYG_FROZEN_CAPTURE"], f"render-dpr{dpr}.{fmt}").write_bytes(
                    artifact
                )
            with xyg.FrozenTemporalGraph.from_artifact(artifact) as recovered:
                assert recovered.to_bytes() == raw
                assert recovered.metadata["selected.node.uuid"] == packed([1])
                assert recovered.metadata["pinned.node.uuid"] == packed([1])
                assert recovered.metadata["focus.uuid"] == packed([1])
                assert recovered.export(fmt, focus_rgba=(170, 153, 236, 255)) == artifact
            for invalid in [artifact[:-1], artifact + b"x", artifact[:20] + b"!" + artifact[21:]]:
                with pytest.raises(xyg.TemporalGraphError):
                    xyg.FrozenTemporalGraph.from_artifact(invalid)
        svg = before["svg"].decode()
        assert "<svg" in svg and "<path" in svg
        im = Image.open(io.BytesIO(before["png"])).convert("RGBA")
        assert im.size == (240 * dpr, 180 * dpr)
        assert im.getpixel((60 * dpr, 60 * dpr)) != im.getpixel((220 * dpr, 160 * dpr))
        doubled = Image.open(
            io.BytesIO(frozen.export("png", scale=2, focus_rgba=(170, 153, 236, 255)))
        )
        assert doubled.size == (480 * dpr, 360 * dpr)
        import subprocess

        from xyg.export import find_chromium

        chrome = find_chromium(os.environ.get("XYG_FROZEN_CHROMIUM"))
        assert chrome is not None, "frozen offline HTML proof requires Chromium"
        result = subprocess.run(
            [
                chrome,
                "--headless",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-proxy-server",
                "--host-resolver-rules=MAP * ~NOTFOUND",
                f"--user-data-dir={tmp_path / 'profile'}",
                "--window-size=300,250",
                f"--screenshot={tmp_path / 'offline.png'}",
                (tmp_path / "frozen.html").as_uri(),
            ],
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        browser = Image.open(tmp_path / "offline.png").convert("RGB")
        assert browser.getpixel((68, 68)) != browser.getpixel((228, 168))
        assert frozen.export("scene", focus_rgba=(170, 153, 236, 255))[:4] == b"XYGS"
        assert frozen.export("painter", focus_rgba=(170, 153, 236, 255))[:4] == b"XYPB"
        with pytest.raises(xyg.TemporalGraphError):
            frozen.export("png", focus_rgba=(170, 153, 236, 255), budget_bytes=1)
    finally:
        frozen.close()
