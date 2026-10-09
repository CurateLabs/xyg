"""Actual native immutable frame export, public composition and Node parity."""

import asyncio
import json
import os
import struct
import subprocess
from pathlib import Path

import pytest

import xyg
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geo_snapshot as s
from xyg import _native

ROOT = Path(__file__).resolve().parents[1]


def frozen_header(packet, format):
    assert packet[:4] == b"XYGX"
    assert struct.unpack_from("<I", packet, 4)[0] == 2
    assert struct.unpack_from("<Q", packet, 16)[0] == len(packet)
    assert struct.unpack_from("<I", packet, 12)[0] == 1
    assert struct.unpack_from("<I", packet, 144)[0] == s.FORMATS[format]
    assert struct.unpack_from("<Q", packet, 136)[0] == U64
    assert struct.unpack_from("<Q", packet, 176)[0] == U64
    assert struct.unpack_from("<q", packet, 56)[0] == -(1 << 63)
    assert struct.unpack_from("<Q", packet, 192)[0] == U64  # layer ID
    assert struct.unpack_from("<Q", packet, 200)[0] == 0  # locator-neutral source ID
    assert struct.unpack_from("<Q", packet, 208)[0] == U64  # source generation
    assert struct.unpack_from("<Q", packet, 288)[0] == U64  # direct literal feature ID
    assert struct.unpack_from("<I", packet, 184)[0] == 1  # full-key descriptor, even direct


def test_six_native_formats_old_frame_public_export_inside_notebook_loop_and_node_parity():
    manifest, chunk = fixture_manifest()

    async def notebook():
        source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
        q = query(source.info)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        frame = chart.compile()
        source.close()
        outputs = {}
        try:
            for format in s.FORMATS:
                owner = chart.to_image(format, frame=frame)
                try:
                    data, companion = owner.bytes, owner.snapshot
                    frozen_header(companion, format)
                    assert struct.unpack_from("<Q", companion, 160)[0] == len(data)
                    signatures = dict(
                        svg=b"<svg",
                        png=b"\x89PNG",
                        pdf=b"%PDF",
                        jpeg=b"\xff\xd8",
                        webp=b"RIFF",
                        html=b"<!doctype html>",
                    )
                    assert signatures[format] in data[:256]
                    if format == "html":
                        assert (
                            b"default-src 'none'" in data
                            and b"<script" not in data
                            and b"xyg-frozen-snapshot" in data
                        )
                    outputs[format] = dict(data=data.hex(), snapshot=companion.hex())
                    del data, companion
                finally:
                    owner.close()
                with pytest.raises(RuntimeError, match="disposed"):
                    _ = owner.bytes
            bad = xyg.geo_chart(
                xyg.geo_layer(
                    "points", source=source, layer_id=U64, query=q, sequence=2, style=style()
                ),
                camera=q["camera"],
            )
            with pytest.raises(ValueError, match="match this"):
                bad.to_image(frame=frame)
            with pytest.raises(s.GeoSnapshotError, match="LIMIT"):
                frame.export("png", budget=256)
            assert frame.data.record(0)["feature_id"] == U64
            return outputs
        finally:
            frame.close()
            source.close()

    expected = asyncio.run(notebook())
    script = """
import {RetainedGeoSource} from './packages/xy-node/src/geo-retained.js';
import {geoChart,geoLayer} from './packages/xy-node/src/charts.js';
const fixture=JSON.parse(process.env.XYG_EXPORT_FIXTURE),bytes=x=>Uint8Array.from(Buffer.from(x,'hex'));
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:134217728n,maxChunks:65536,pageRows:4096};
const source=await RetainedGeoSource.create(bytes(fixture.manifest),async()=>bytes(fixture.chunk),{budget});
const max=18446744073709551615n,q={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:source.info.digest,generation:source.info.generation,layerId:max,cameraRevision:max,timeRevision:max,layerRevision:max,styleRevision:max,stateRevision:max,time:{kind:1,instant:-9223372036854775808n},maxProjectedVertices:1000000n};
const chart=geoChart(geoLayer('points',{source,layerId:max,query:q,sequence:1n,style:bytes(fixture.style)}),{camera:q.camera});const frame=await chart.compileRetained();await source.dispose();const result={};
for(const format of ['svg','png','pdf','jpeg','webp','html']){const owner=await chart.toImage(format,{frame});result[format]={data:Buffer.from(owner.bytes).toString('hex'),snapshot:Buffer.from(owner.snapshot).toString('hex')};await owner.dispose();try{owner.bytes;throw new Error('disposed access');}catch(e){if(e.message==='disposed access')throw e;}}
await frame.dispose();console.log(JSON.stringify(result));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        env={
            **os.environ,
            "XYG_NATIVE_LIB": str(Path(_native._lib._name).resolve()),
            "XYG_EXPORT_FIXTURE": json.dumps(
                dict(manifest=manifest.hex(), chunk=chunk.hex(), style=style().hex())
            ),
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == expected


def test_async_export_cancellation_during_read_settles_then_retires_all_candidate_handles():
    manifest, chunk = fixture_manifest()

    async def run():
        source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
        frame = source.update(query(source.info), sequence=1, style=style())
        ready, release = asyncio.Event(), asyncio.Event()

        class Bridge(s.NativeSnapshotBridge):
            def __init__(self):
                super().__init__(384 << 20)
                self.handles, self.disposed = [], []

            async def execute(self, packet):
                command = struct.unpack_from("<I", packet, 8)[0]
                handle = struct.unpack_from("<Q", packet, 16)[0]
                result = await super().execute(packet)
                if command in (1, 2):
                    self.handles.append(s.reply(result)["handle"])
                if command == 3:
                    self.disposed.append(handle)
                return result

            async def read(self, packet):
                result = await super().read(packet)
                ready.set()
                await release.wait()
                return result

        bridge = Bridge()
        task = asyncio.create_task(frame.export_async("png", bridge=bridge))
        try:
            await ready.wait()
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and not bridge.disposed
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert sorted(bridge.handles) == sorted(bridge.disposed)
            for handle in bridge.handles:
                with pytest.raises(s.GeoSnapshotError, match="STALE"):
                    s.read(s.request(22, handle), 384 << 20)
            assert frame.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            frame.close()
            source.close()

    asyncio.run(run())
