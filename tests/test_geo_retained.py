"""Real native retained owner proofs, including notebook event-loop operation."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest

from test_geoscale import BUDGET, U64, query, source_fixture
from xyg import _geoscale as g
from xyg import _native
from xyg._geo_retained import RetainedGeoSource


def fixture_manifest():
    _, chunk = source_fixture()
    builder = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
    try:
        g.execute(g.encode_request(dict(command=2, handle=builder, payload=chunk)))
        g.execute(g.encode_request(dict(command=3, handle=builder, generation=U64)))
        return g.read(
            g.encode_request(dict(command=21, handle=builder)), BUDGET["processor_bytes"]
        ), chunk
    finally:
        g.execute(g.encode_request(dict(command=10, handle=builder)))


def style():
    return g.encode_style(
        dict(
            fill=b"\xff\0\0\xff",
            stroke=b"\0" * 4,
            stroke_width=0.0,
            diameter=6.0,
            opacity=1.0,
            symbol=0,
        )
    )


def test_sync_native_inside_running_notebook_loop_and_independent_old_frame():
    manifest, chunk = fixture_manifest()

    async def notebook():
        source = RetainedGeoSource(manifest, lambda ticket: chunk, budget=BUDGET)
        old = source.update(query(source.info), sequence=1, style=style())
        try:
            assert old.data.record(0)["feature_id"] == U64
            with pytest.raises(ValueError):
                source.update(query(source.info), sequence=2, style=b"bad")
            assert source.current is old
            newer = source.update(query(source.info), sequence=3, style=style())
            try:
                assert old.data.record(0)["feature_id"] == U64
                source.close()
                source.close()
                assert newer.data.record(1)["feature_id"] == (1 << 53) + 1
                assert old.data.identity["sequence"] == 1
            finally:
                newer.close()
        finally:
            old.close()
            source.close()

    asyncio.run(notebook())


def test_real_node_python_retained_scene_parity():
    root = Path(__file__).resolve().parents[1]
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    frame = source.update(query(source.info), sequence=1, style=style())
    try:
        expected = bytes(frame.data.packet)
        expected = expected[:16] + b"\0" * 8 + expected[24:]
        script = """import {RetainedGeoSource} from './packages/xy-node/src/geo-retained.js';
const input=JSON.parse(process.env.XYG_RETAINED_FIXTURE), bytes=x=>Uint8Array.from(Buffer.from(x,'hex'));
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:134217728n,maxChunks:65536,pageRows:4096};
const source=await RetainedGeoSource.create(bytes(input.manifest),async()=>bytes(input.chunk),{budget});
const max=18446744073709551615n,q={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:source.info.digest,generation:source.info.generation,layerId:max,cameraRevision:max,timeRevision:max,layerRevision:max,styleRevision:max,stateRevision:max,time:{kind:1,instant:-9223372036854775808n},maxProjectedVertices:1000000n};
const frame=await source.update(q,{sequence:1n,style:bytes(input.style)});await source.dispose();const hits=await frame.pick({style:bytes(input.style),x:400,y:300,tolerance:0,mode:1,maxHits:10});if(!Array.from({length:Number(hits.data.count)},(_,i)=>hits.data.record(i).featureId).includes(max))throw new Error('full-ID old-frame pick');await hits.dispose();const packet=new Uint8Array(frame.data.packet);packet.fill(0,16,24);console.log(Buffer.from(packet).toString('hex'));await frame.dispose();"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=root,
            env={
                **os.environ,
                "XYG_NATIVE_LIB": str(Path(_native._lib._name).resolve()),
                "XYG_RETAINED_FIXTURE": json.dumps(
                    dict(manifest=manifest.hex(), chunk=chunk.hex(), style=style().hex())
                ),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert bytes.fromhex(result.stdout.strip()) == expected
    finally:
        frame.close()
        source.close()


def aggregate_fixture():
    import struct

    import numpy as np

    n = 32769
    descriptor = bytearray(64 + n * 16 + ((n + 7) // 8) * 8 + n * 8)
    struct.pack_into("<4s5I5Q", descriptor, 0, b"XYGD", 1, 1, 4326, 1, 0, n, n, 0, 0, 0)
    descriptor[64 : 64 + n * 16] = np.zeros(n * 2, dtype="<f8").tobytes()
    descriptor[64 + n * 16 : 64 + n * 17] = b"\1" * n
    ids_at = 64 + n * 16 + ((n + 7) // 8) * 8
    descriptor[ids_at:] = np.arange(n, dtype="<u8").tobytes()
    struct.pack_into("<Q", descriptor, ids_at, U64)
    chunk_request = g.encode_chunk_request(
        dict(descriptor=bytes(descriptor), rows=n), BUDGET["processor_bytes"]
    )
    chunk = g.read(chunk_request, BUDGET["processor_bytes"])
    builder = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
    try:
        g.execute(g.encode_request(dict(command=2, handle=builder, payload=chunk)))
        g.execute(g.encode_request(dict(command=3, handle=builder, generation=U64)))
        manifest = g.read(
            g.encode_request(dict(command=21, handle=builder)), BUDGET["processor_bytes"]
        )
    finally:
        g.execute(g.encode_request(dict(command=10, handle=builder)))
    return manifest, chunk


def test_exact_paged_membership_keeps_ids_and_cursor_opaque():
    import struct

    manifest, chunk = aggregate_fixture()
    budget = {**BUDGET, "page_rows": 1}
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=budget)
    q = query(source.info)
    q["time"] = {"kind": 0}
    q["max_cells"] = 1
    q["previous_direct"] = False
    frame = source.update(q, sequence=1, style=style())
    page = nextpage = None
    try:
        assert frame.data.aggregate
        source.close()
        page = frame.membership(0, max_projected_vertices=1000000)
        assert page.data["count"] == 1
        assert struct.unpack_from("<Q", page.data["records"])[0] == U64
        cursor = page.data["cursor"]
        assert len(cursor) == 208
        nextpage = source.membership(0, sequence=1, max_projected_vertices=1000000, cursor=cursor)
        assert struct.unpack_from("<Q", nextpage.data["records"])[0] == 1
        source.close()
        assert len(page.data["cursor"]) == 208
    finally:
        if nextpage:
            nextpage.close()
        if page:
            page.close()
        frame.close()
        source.close()


def test_async_dispose_waits_for_unsettled_read_and_releases_ticket():
    manifest, chunk = fixture_manifest()

    async def proof():
        started, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def reader(ticket):
            nonlocal calls
            calls += 1
            if calls > 1:
                started.set()
                await release.wait()
            return chunk

        source = await RetainedGeoSource.create_async(manifest, reader, budget=BUDGET)
        update = asyncio.create_task(source.aupdate(query(source.info), sequence=1, style=style()))
        await started.wait()
        disposal = asyncio.create_task(source.aclose())
        await asyncio.sleep(0)
        assert not disposal.done()
        release.set()
        await disposal
        with pytest.raises(asyncio.CancelledError):
            await update
        assert source._closed

    asyncio.run(proof())


def test_old_frame_exact_pick_survives_new_publication_and_source_disposal():
    import struct

    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    old = source.update(query(source.info), sequence=1, style=style())
    newer = source.update(query(source.info), sequence=2, style=style())
    source.close()
    hits = None
    try:
        hits = old.pick(style=style(), x=400.0, y=300.0, tolerance=0.0, mode=1, max_hits=10)
        assert hits.data["count"] >= 1
        ids = [
            struct.unpack_from("<Q", hits.data["records"], at + 8)[0]
            for at in range(0, len(hits.data["records"]), 48)
        ]
        assert U64 in ids
        with pytest.raises(TypeError):
            old.pick(style=style(), x="400", y=300.0, tolerance=0.0, mode=1, max_hits=10)
    finally:
        if hits:
            hits.close()
        old.close()
        newer.close()


def test_async_membership_cancel_during_member_disposal_releases_unreturned_page():
    manifest, chunk = aggregate_fixture()

    async def proof():
        started, release = asyncio.Event(), asyncio.Event()

        class Bridge(g.NativeGeoScaleBridge):
            member = None
            data = None

            def __init__(self, budget):
                super().__init__(budget)
                self.disposals = []

            async def execute(self, request):
                import struct

                command = struct.unpack_from("<I", request, 8)[0]
                handle = struct.unpack_from("<Q", request, 16)[0]
                result = g.execute(request)
                if command == 12:
                    self.member = g.decode_reply(result)["handle"]
                if command == 13:
                    self.data = g.decode_reply(result)["handle"]
                if command == 10:
                    self.disposals.append(handle)
                    if handle == self.member:
                        started.set()
                        await release.wait()
                return result

        bridge = Bridge(BUDGET["processor_bytes"])

        async def reader(_):
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget={**BUDGET, "page_rows": 1}, bridge=bridge
        )
        q = query(source.info)
        q.update(time={"kind": 0}, max_cells=1, previous_direct=False)
        frame = await source.aupdate(q, sequence=1, style=style())
        task = asyncio.create_task(frame.membership_async(0, max_projected_vertices=1000000))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert bridge.data in bridge.disposals
        await frame.dispose()
        await source.aclose()

    asyncio.run(proof())
