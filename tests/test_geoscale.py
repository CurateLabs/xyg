"""Real ABI382 source/Scene ownership and independent thin-adapter edge proofs."""

from __future__ import annotations

import asyncio
import ctypes
import gc
import json
import os
import struct
import subprocess
import weakref
from pathlib import Path

import numpy as np
import pytest

from xyg import _geoscale as g

ROOT = Path(__file__).resolve().parents[1]
BUDGET = dict(
    processor_bytes=128 << 20,
    max_rows_examined=1_000_000,
    max_read_bytes=128 << 20,
    max_chunks=65536,
    page_rows=4096,
)
U64 = (1 << 64) - 1
I64 = -(1 << 63)


def source_fixture() -> tuple[bytes, bytes]:
    # Independent canonical XYGD authoring: two exact full-ID point rows.
    descriptor = bytearray(120)
    struct.pack_into("<4s5I5Q", descriptor, 0, b"XYGD", 1, 1, 4326, 1, 0, 2, 2, 0, 0, 0)
    struct.pack_into("<4d", descriptor, 64, 0.0, 0.0, 1.0, 1.0)
    descriptor[96:98] = b"\x01\x01"
    struct.pack_into("<2Q", descriptor, 104, U64, (1 << 53) + 1)
    request = g.encode_chunk_request(
        dict(
            descriptor=bytes(descriptor),
            rows=2,
            intervals=dict(
                starts=np.array([I64, I64], dtype="<i8"),
                ends=np.array([(1 << 63) - 1] * 2, dtype="<i8"),
                start_validity=np.ones(2, dtype="u1"),
                end_validity=np.ones(2, dtype="u1"),
            ),
            values=np.array([0.0, 1.0], dtype="<f8"),
        ),
        BUDGET["processor_bytes"],
    )
    return request, g.read(request, BUDGET["processor_bytes"])


def query(source: dict) -> dict:
    return dict(
        camera=dict(
            crs=4326,
            world_wrap=True,
            center_x=0.0,
            center_y=0.0,
            zoom=0.0,
            width=800.0,
            height=600.0,
            bearing=0.0,
            pitch=0.0,
        ),
        reduced_kind=0,
        max_cells=32768,
        previous_direct=True,
        source_digest=source["digest"],
        generation=source["generation"],
        layer_id=U64,
        camera_revision=U64,
        time_revision=U64,
        layer_revision=U64,
        style_revision=U64,
        state_revision=U64,
        time=dict(kind=1, instant=I64),
        max_projected_vertices=1_000_000,
    )


async def native_fixture() -> dict:
    request, chunk = source_fixture()
    bridge = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
    builder = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
    session = lease = None
    try:
        g.execute(g.encode_request(dict(command=2, handle=builder, payload=chunk)))
        g.execute(g.encode_request(dict(command=3, handle=builder, generation=U64)))
        manifest = g.read(
            g.encode_request(dict(command=21, handle=builder)), BUDGET["processor_bytes"]
        )
        session = g.decode_reply(
            g.execute(g.encode_request(dict(command=4, budget=BUDGET, payload=manifest)))
        )["handle"]

        async def read_chunk(ticket):
            assert ticket["encoded_bytes"] == len(chunk)
            return chunk

        source = (
            await g.drive_session(
                bridge, handle=session, sequence=0, budget=BUDGET, read_chunk=read_chunk
            )
        )["source"]
        begin = g.encode_request(
            dict(command=5, handle=session, sequence=1, budget=BUDGET, query=query(source))
        )
        g.execute(begin)
        assert (
            await g.drive_session(
                bridge, handle=session, sequence=1, budget=BUDGET, read_chunk=read_chunk
            )
        )["code"] == 4
        lease = await g.prepare_scene_data(
            bridge,
            handle=session,
            sequence=1,
            budget=BUDGET,
            style=g.encode_style(
                dict(
                    fill=b"\xff\x00\x00\xff",
                    stroke=b"\x00" * 4,
                    stroke_width=0.0,
                    diameter=6.0,
                    opacity=1.0,
                    symbol=0,
                )
            ),
        )
        assert lease.data.record(0)["feature_id"] == U64
        assert lease.data.record(1)["feature_id"] == (1 << 53) + 1
        assert lease.data.identity["time"]["instant"] == I64
        # Pure output probes must not consume a Data slot. Two real reads admitted.
        assert g.read(
            g.encode_request(dict(command=23, handle=lease.handle)), BUDGET["processor_bytes"]
        )
        with pytest.raises(ValueError) as error:
            g.read(
                g.encode_request(dict(command=23, handle=lease.handle)), BUDGET["processor_bytes"]
            )
        assert error.value.status == -9
        packet = bytearray(lease.data.packet)
        packet[16:24] = b"\0" * 8  # Registry handle is intentionally process-local.
        begin = bytearray(begin)
        begin[16:24] = b"\0" * 8
        return dict(
            chunk_request=request.hex(),
            chunk=chunk.hex(),
            manifest=manifest.hex(),
            begin=begin.hex(),
            packet=packet.hex(),
        )
    finally:
        if lease is not None:
            await lease.dispose()
            with pytest.raises(RuntimeError, match="disposed"):
                _ = lease.data
        if session is not None:
            g.execute(g.encode_request(dict(command=10, handle=session)))
        g.execute(g.encode_request(dict(command=10, handle=builder)))


def test_real_native_and_cross_host_exact_bytes() -> None:
    from xyg import _native

    python = asyncio.run(native_fixture())
    env = dict(os.environ, XYG_NATIVE_LIB=str(Path(_native._lib._name).resolve()))
    node = subprocess.run(
        ["node", "packages/xy-node/test/geoscale-fixture.mjs"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(node.stdout) == python


def test_native_mutation_never_size_probes() -> None:
    from xyg import _native

    source = ctypes.create_string_buffer(g.encode_request(dict(command=1)))
    function = _native._lib.xyg_geo_scale_execute
    for _ in range(16):
        assert function(source, 256, None, 0) == -1
    out = ctypes.create_string_buffer(b"z" * 256, 256)
    assert function(source, 256, out, 255) == -13
    assert out.raw == b"z" * 256
    handle = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
    g.execute(g.encode_request(dict(command=10, handle=handle)))


def step_reply(code=1) -> bytes:
    b = bytearray(256)
    struct.pack_into("<4sII", b, 0, b"XYGZ", 1, code)
    struct.pack_into("<QQ", b, 16, 1, 0)
    if code == 1:
        struct.pack_into("<QQQI", b, 64, 9, 1, 0, 0)
        struct.pack_into("<Q", b, 120, 4)
    return bytes(b)


class Storage(bytearray):
    pass


@pytest.mark.parametrize("mode", ["event", "task", "giant", "failure", "success"])
def test_read_ack_after_settlement_and_storage_drop(mode: str) -> None:
    async def run():
        entered, unblock, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        event = asyncio.Event()
        calls, refs = [], []

        class Bridge:
            async def execute(self, request):
                command = struct.unpack_from("<I", request, 8)[0]
                calls.append(command)
                if command == 9:
                    cancelled.set()
                if command == 8:
                    assert unblock.is_set()
                    gc.collect()
                    assert all(ref() is None for ref in refs)
                return step_reply(1 if calls.count(6) == 1 else 3)

        async def read_chunk(ticket):
            entered.set()
            await unblock.wait()
            storage = Storage(b"1234" if mode != "giant" else b"12345678")
            refs.append(weakref.ref(storage))
            if mode == "failure":
                raise OSError("reader failed")
            return memoryview(storage)[:4]

        task = asyncio.create_task(
            g.drive_session(
                Bridge(),
                handle=1,
                sequence=0,
                budget=BUDGET,
                read_chunk=read_chunk,
                cancel_event=event,
            )
        )
        await entered.wait()
        if mode in ("event", "task"):
            if mode == "event":
                event.set()
            else:
                task.cancel()
            await asyncio.wait_for(cancelled.wait(), 1)
            assert 8 not in calls
            if mode == "task":
                task.cancel()  # Repeated outer cancellation must not cancel mutation9.
        unblock.set()
        if mode in ("event", "task"):
            with pytest.raises(asyncio.CancelledError):
                await task
        elif mode == "failure":
            with pytest.raises(OSError, match="reader failed"):
                await task
        elif mode == "giant":
            with pytest.raises(ValueError, match="exact bounded"):
                await task
        else:
            assert (await task)["code"] == 3
        assert calls.count(8) == 1
        assert (7 in calls) == (mode == "success")

    asyncio.run(run())


def test_malformed_metadata_and_exact_typed_admission() -> None:
    packet = bytearray(bytes.fromhex(asyncio.run(native_fixture())["packet"]))
    scene_len = struct.unpack_from("<Q", packet, 32)[0]
    packet[256 + scene_len + 28] = 1
    with pytest.raises(ValueError, match="reserved"):
        g.parse_scene_data(packet)
    request, _ = source_fixture()
    assert struct.unpack_from("<q", request, 256 + 32 + 120)[0] == I64
    with pytest.raises(TypeError, match="contiguous typed"):
        g.encode_chunk_request(
            dict(descriptor=b"", rows=1, values=np.array([1.0], dtype="<f4")), 1 << 20
        )
    with pytest.raises(ValueError, match="peak"):
        g.encode_chunk_request(dict(descriptor=b"x" * 1024, rows=0), 1024)
    with pytest.raises(TypeError, match="u64"):
        g.encode_request(dict(command=6, handle=1.5, sequence=1))


def test_task_cancel_during_pending_read_ack_stops_next_step() -> None:
    async def run():
        entered, unblock, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls = []

        class Bridge:
            async def execute(self, request):
                command = struct.unpack_from("<I", request, 8)[0]
                calls.append(command)
                if command == 8:
                    entered.set()
                    await unblock.wait()
                if command == 9:
                    cancelled.set()
                return step_reply()

        async def read_chunk(ticket):
            return b"1234"

        task = asyncio.create_task(
            g.drive_session(Bridge(), handle=1, sequence=0, budget=BUDGET, read_chunk=read_chunk)
        )
        await entered.wait()
        task.cancel()
        await asyncio.wait_for(cancelled.wait(), 1)
        assert not task.done()
        unblock.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls == [6, 7, 8, 9]

    asyncio.run(run())


def test_cancelled_prepare_waits_handle_reply_then_disposes() -> None:
    async def run():
        entered, unblock = asyncio.Event(), asyncio.Event()
        calls = []

        class Bridge:
            async def execute(self, request):
                command = struct.unpack_from("<I", request, 8)[0]
                calls.append(command)
                if command == 11:
                    entered.set()
                    await unblock.wait()
                reply = bytearray(step_reply(0))
                struct.pack_into("<Q", reply, 16, 99)
                return bytes(reply)

        task = asyncio.create_task(
            g.prepare_scene_data(Bridge(), handle=1, sequence=1, budget=BUDGET, style=b"\0" * 48)
        )
        await entered.wait()
        task.cancel()
        assert not task.done()
        unblock.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls == [11, 10]

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["identity", "metadata"])
def test_prepare_failure_drops_decoder_and_packet_before_disposal(failure: str) -> None:
    fixture = asyncio.run(native_fixture())["packet"]

    async def run():
        refs, calls = [], []

        class Bridge:
            async def execute(self, request):
                command = struct.unpack_from("<I", request, 8)[0]
                calls.append(command)
                if command == 10:
                    gc.collect()
                    assert all(ref() is None for ref in refs)
                b = bytearray(step_reply(0))
                struct.pack_into("<4Q", b, 16, 99, 1, len(fixture) // 2, 1)
                return bytes(b)

            async def read(self, request):
                packet = Storage(bytes.fromhex(fixture))
                refs.append(weakref.ref(packet))
                if failure == "metadata":
                    scene_len = struct.unpack_from("<Q", packet, 32)[0]
                    packet[256 + scene_len + 28] = 1
                return packet

        with pytest.raises(ValueError, match="identity" if failure == "identity" else "reserved"):
            await g.prepare_scene_data(
                Bridge(), handle=1, sequence=1, budget=BUDGET, style=b"\0" * 48
            )
        assert calls == [11, 10]

    asyncio.run(run())
