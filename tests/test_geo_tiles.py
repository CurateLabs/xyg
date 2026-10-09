"""Actual native tile authority, mixed attributed export and thin Node parity."""

import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

import pytest

import xyg
from xyg import _geo_tiles as tiles
from xyg import _geocatalog as catalog
from xyg import _native

ROOT = Path(__file__).resolve().parents[1]
MAX = (1 << 64) - 1


def fixture():
    camera = dict(
        crs=4326,
        world_wrap=False,
        center_x=0.0,
        center_y=0.0,
        zoom=0.0,
        width=800.0,
        height=600.0,
        bearing=0.0,
        pitch=0.0,
    )
    point = bytearray(96)
    struct.pack_into("<4s4I", point, 0, b"XYGD", 1, 1, 4326, 1)
    struct.pack_into("<2Q", point, 24, 1, 1)
    point[80] = 1
    struct.pack_into("<Q", point, 88, MAX)
    sources = [
        tiles.GeoTileSource(
            1,
            MAX,
            7,
            MAX,
            MAX,
            0,
            0,
            0,
            262144,
            1,
            1,
            "https://example.test/{z}/{x}/{y}",
            "Tile attribution",
            True,
            (-(1 << 63), (1 << 63) - 1),
        ),
        tiles.GeoTileSource(
            2,
            MAX,
            8,
            MAX,
            MAX,
            1,
            0,
            0,
            1024,
            1,
            1,
            "local/vector",
            "",
            False,
            (-(1 << 63), (1 << 63) - 1),
        ),
    ]
    foreground = catalog.encode_request(
        dict(
            camera=camera,
            layers=[
                dict(
                    layer_id=99,
                    kind=1,
                    source=bytes(point),
                    style=dict(fill=b"\0\0\xff\xff"),
                    labels=[
                        dict(
                            feature_index=0,
                            anchor=0,
                            font_size=14.0,
                            coordinate=[0.0, 0.0],
                            rgba=b"\0\0\0\xff",
                            text="Tile attribution",
                        )
                    ],
                )
            ],
        ),
        128 << 20,
    )
    style = dict(
        fill=b"\xff\0\0\xff",
        stroke=b"\0" * 4,
        stroke_width=0.0,
        diameter=6.0,
        opacity=1.0,
        symbol=0,
    )
    return camera, sources, bytes(point), foreground, [dict(layer_id=8, kind=1, style=style)]


def digest(b):
    return hashlib.sha256(b).hexdigest()


def canonical_receipt(receipt):
    receipt = bytearray(receipt)

    def checksum():
        return hashlib.blake2s(
            b"xyg-tile-scene-receipt-v1" + receipt[:136] + receipt[256:],
            digest_size=8,
            person=b"xykeyv1",
        ).digest()

    assert receipt[136:144] == checksum()
    receipt[16:24] = bytes(8)  # sole ephemeral cache handle
    receipt[136:144] = checksum()  # dependent receipt digest, not omitted metadata
    return receipt.hex()


def tile_semantics(snapshot):
    size = struct.unpack_from("<I", snapshot, 188)[0]
    scene_size = struct.unpack_from("<Q", snapshot, 24)[0]
    blob = snapshot[len(snapshot) - scene_size - size : len(snapshot) - scene_size]
    assert struct.unpack_from("<3I", blob) == (1, 1, 3)  # external time, absent global revisions
    sources, keys = struct.unpack_from("<2I", blob, 12)
    at = 64
    for _ in range(sources):
        locator, attr = struct.unpack_from("<2I", blob, at + 96)
        at += 128 + locator + attr
    at += keys * 96
    receipt = blob[at:]
    assert receipt[:4] == b"XYGU"
    # Compare the complete receipt, normalizing only cache handle and its checksum.
    return digest(blob[:at]), digest(snapshot[-scene_size:]), canonical_receipt(receipt)


def test_mixed_six_exports_attribution_pixels_old_frame_and_actual_node_semantic_parity():
    camera, sources, point, foreground, styles = fixture()
    reads = []

    def reader(receipt):
        reads.append(receipt["ticket"])
        assert receipt["key"]["generation"] == MAX
        return bytes([30, 60, 90, 255]) * (256 * 256) if receipt["key"]["kind"] == 0 else point

    session = tiles.GeoTileSession(sources, reader, view_id=1, budget=128 << 20)
    frame = session.prepare(camera, catalog=foreground, vector_styles=styles, image_id=42)
    frame.commit()
    session.close()
    semantic = None
    try:
        assert len(reads) == 2
        assert frame.data["attributions"] == ["Tile attribution"]
        assert len(frame.data["catalog"]["layers"]) == 2
        for format in ("svg", "png", "pdf", "jpeg", "webp", "html"):
            first = frame.export(format)
            try:
                data_hash, snapshot_hash = digest(first.bytes), digest(first.snapshot)
                semantic = tile_semantics(first.snapshot)
                assert (
                    struct.unpack_from("<I", first.snapshot, 32)[0] == 0
                )  # no fabricated ordinary layer generations
                if format in ("svg", "html"):
                    assert b"Tile attribution" in first.bytes
                if format == "html":
                    assert b"default-src 'none'" in first.bytes and b"<script" not in first.bytes
                if format == "png":
                    from io import BytesIO

                    from PIL import Image

                    image = Image.open(BytesIO(first.bytes)).convert("RGBA")
                    assert image.getpixel((400, 400)) == (30, 60, 90, 255)
                    assert image.getpixel((400, 300))[:3] == (0, 0, 255)
                    image.close()
            finally:
                first.close()
            second = frame.export(format)
            try:
                assert (digest(second.bytes), digest(second.snapshot)) == (data_hash, snapshot_hash)
            finally:
                second.close()
        script = """
import {GeoTileSource,GeoTileSession} from './packages/xy-node/src/geo-tiles.js';
import {createHash} from 'node:crypto';
import {geoChart,geoLayer} from './packages/xy-node/src/charts.js';
const f=JSON.parse(process.env.XYG_TILE_FIXTURE),camera={crs:4326,worldWrap:false,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},max=18446744073709551615n;
const source=(kind)=>new GeoTileSource({sourceId:BigInt(kind+1),generation:max,layerId:BigInt(kind+7),layerRevision:max,styleRevision:max,kind,minZoom:0,maxZoom:0,maxBytes:kind?1024n:262144n,maxFeatures:1n,maxVertices:1n,locator:kind?'local/vector':'https://example.test/{z}/{x}/{y}',attribution:kind?'':'Tile attribution',network:!kind,time:{start:-9223372036854775808n,end:9223372036854775807n}});
const bytes=x=>Uint8Array.from(Buffer.from(x,'hex')),styles=[{layerId:8n,kind:1,style:{fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0}}];
const session=await GeoTileSession.create([source(0),source(1)],async r=>r.key.kind?bytes(f.point):Uint8Array.from({length:262144},(_,i)=>[30,60,90,255][i%4]),{viewId:1n,budget:128<<20});
const chart=geoChart(geoLayer('points',{source:bytes(f.point).buffer,layerId:99n,style:{fill:new Uint8Array([0,0,255,255])},labels:[{featureIndex:0,anchor:0,fontSize:14,coordinate:[0,0],rgba:new Uint8Array([0,0,0,255]),text:'Tile attribution'}]}),{camera,tileSession:session,tileVectorStyles:styles,tileImageId:42n});const frame=await chart.compileTiles();await session.dispose();const hash=b=>createHash('sha256').update(new Uint8Array(b)).digest('hex');let semantic;
for(const format of ['svg','png','pdf','jpeg','webp','html']){const a=await chart.toImage(format,{frame}),bytesHash=hash(a.bytes),snapshotHash=hash(a.snapshot),b=new Uint8Array(a.snapshot),v=new DataView(a.snapshot),scene=Number(v.getBigUint64(24,true)),size=v.getUint32(188,true),blob=b.subarray(b.length-scene-size,b.length-scene),bv=new DataView(blob.buffer,blob.byteOffset,blob.length);let at=64;for(let i=0;i<bv.getUint32(12,true);i++)at+=128+bv.getUint32(at+96,true)+bv.getUint32(at+100,true);at+=bv.getUint32(16,true)*96;semantic=[hash(blob.subarray(0,at)),hash(b.subarray(b.length-scene)),Buffer.from(blob.subarray(at)).toString('hex')];await a.dispose();const z=await frame.export(format);if(hash(z.bytes)!==bytesHash||hash(z.snapshot)!==snapshotHash)throw new Error('same-frame export nondeterminism');await z.dispose();}
await frame.dispose();console.log(JSON.stringify(semantic));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            env={
                **os.environ,
                "XYG_NATIVE_LIB": str(Path(_native._lib._name).resolve()),
                "XYG_TILE_FIXTURE": json.dumps(
                    dict(point=point.hex(), foreground=foreground.hex())
                ),
            },
            text=True,
            capture_output=True,
            check=True,
        )
        node_semantic = json.loads(result.stdout)
        node_semantic[2] = canonical_receipt(bytes.fromhex(node_semantic[2]))
        assert node_semantic == list(semantic)
    finally:
        frame.close()
        session.close()


def test_native_stage_failure_style_stale_and_disposed_session_preserve_old_receipt():
    camera, sources, point, foreground, styles = fixture()
    session = tiles.GeoTileSession(
        sources,
        lambda r: b"\xff" * 262144 if r["key"]["kind"] == 0 else point,
        view_id=1,
        budget=128 << 20,
    )

    def stage(frame):
        owner = frame.export("svg")
        owner.close()

    old = session.update(camera, catalog=foreground, vector_styles=styles, image_id=42, stage=stage)
    original = digest(old.data["scene"])
    try:
        with pytest.raises(RuntimeError, match="target rejected"):
            session.update(
                camera,
                catalog=foreground,
                vector_styles=styles,
                image_id=42,
                stage=lambda frame: (_ for _ in ()).throw(RuntimeError("target rejected")),
            )
        assert session.current is old and digest(old.data["scene"]) == original
        changed = [dict(styles[0], style=dict(styles[0]["style"], diameter=7.0))]
        with pytest.raises(_native.GeoNativeError):
            session.prepare(camera, catalog=foreground, vector_styles=changed, image_id=42)
        assert session.current is old

        def stage_reentry(candidate):
            with pytest.raises(RuntimeError, match="operation is active"):
                session.close()
            with pytest.raises(RuntimeError, match="unavailable"):
                session.prepare(camera, catalog=foreground, vector_styles=styles, image_id=42)
            assert not session._closed

        newer = session.update(
            camera, catalog=foreground, vector_styles=styles, image_id=42, stage=stage_reentry
        )
        assert session.current is newer
        newer.close()
        session.close()
        owner = old.export("png")
        owner.close()
        assert digest(old.data["scene"]) == original
    finally:
        old.close()
        session.close()


def test_public_native_tile_chart_stages_before_commit_and_requires_its_frozen_frame():
    camera, sources, point, foreground, styles = fixture()
    assert xyg.GeoTileSource is tiles.GeoTileSource
    assert xyg.GeoTileSession is tiles.GeoTileSession
    session = xyg.GeoTileSession(
        sources,
        lambda r: b"\xff" * 262144 if r["key"]["kind"] == 0 else point,
        view_id=1,
        budget=128 << 20,
    )
    layer = xyg.geo_layer(
        "points",
        source=point,
        layer_id=99,
        style=dict(fill=b"\0\0\xff\xff"),
        labels=[
            dict(
                feature_index=0,
                anchor=0,
                font_size=14.0,
                coordinate=[0.0, 0.0],
                rgba=b"\0\0\0\xff",
                text="Tile attribution",
            )
        ],
    )
    chart = xyg.geo_chart(
        layer, camera=camera, tile_session=session, tile_vector_styles=styles, tile_image_id=42
    )
    frame = chart.compile()
    try:
        assert session.current is frame
        with pytest.raises(ValueError, match="pass frame"):
            chart.to_image()
        session.close()
        owner = chart.to_image("png", frame=frame)
        owner.close()
        other = xyg.geo_chart(
            layer,
            camera={**camera, "zoom": 1.0},
            tile_session=session,
            tile_vector_styles=styles,
            tile_image_id=42,
        )
        with pytest.raises(ValueError, match="match this"):
            other.to_image(frame=frame)
    finally:
        frame.close()
        session.close()


def test_authorized_backing_capacity_rejects_before_publish_and_native_node_cancel_settles_read():
    camera, sources, point, foreground, styles = fixture()
    oversized = bytearray(262145)
    session = tiles.GeoTileSession(
        sources,
        lambda _: memoryview(oversized)[:1],
        view_id=1,
        budget=128 << 20,
    )
    try:
        with pytest.raises(ValueError, match="capacity"):
            session.prepare(camera, catalog=foreground, vector_styles=styles, image_id=42)
        assert session.current is None
        session._reader = lambda r: b"\xff" * 262144 if r["key"]["kind"] == 0 else point
        frame = session.prepare(camera, catalog=foreground, vector_styles=styles, image_id=42)
        frame.close()
    finally:
        session.close()
    script = r"""
import assert from 'node:assert/strict';
import {nativeGeoSnapshotBridge} from './packages/xy-node/src/geo-snapshot.js';
import {GeoTileSource,GeoTileSession,nativeGeoTileBridge} from './packages/xy-node/src/geo-tiles.js';
const f=JSON.parse(process.env.XYG_TILE_FIXTURE),max=18446744073709551615n;
const camera={crs:4326,worldWrap:false,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0};
const source=new GeoTileSource({sourceId:2n,generation:max,layerId:8n,layerRevision:max,styleRevision:max,kind:1,minZoom:0,maxZoom:0,maxBytes:1024n,maxFeatures:1n,maxVertices:1n,locator:'local/vector',attribution:'',network:false});
const bytes=x=>Uint8Array.from(Buffer.from(x,'hex')),native=nativeGeoTileBridge(128<<20),commands=[];
const bridge={execute:p=>{commands.push(new DataView(p).getUint32(8,true));return native.execute(p)},read:p=>native.read(p)};
let resolveRead,notify;const entered=new Promise(r=>notify=r);let pause=true;
const session=await GeoTileSession.create([source],async(_receipt,signal)=>{if(pause){notify(signal);await new Promise(r=>resolveRead=r)}return bytes(f.point)}, {viewId:1n,budget:128<<20,bridge});
const options={catalog:bytes(f.foreground),vectorStyles:[{layerId:8n,kind:1,style:{fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0}}],imageId:42n};
const pending=session.prepare(camera,options);pending.catch(()=>{});const signal=await entered;
let settled=false;const cancel=session.cancel().then(()=>settled=true);
await new Promise(r=>setImmediate(r));assert.equal(signal.aborted,true);assert.equal(settled,false);assert.equal(commands.includes(5),false);
resolveRead();await cancel;await assert.rejects(pending);assert.equal(commands.filter(c=>c===5).length,1);assert.equal(session.current,undefined);
pause=false;const frame=await session.prepare(camera,options);await frame.commit();await session.dispose();
const artifact=await frame.export('png',{bridge:nativeGeoSnapshotBridge(384<<20)});assert(artifact.bytes.byteLength>0);await artifact.dispose();await frame.dispose();
let releaseDispose,enteredDispose;const disposing=new Promise(r=>enteredDispose=r);
const delayed={execute:async p=>{if(new DataView(p).getUint32(8,true)===10){enteredDispose();await new Promise(r=>releaseDispose=r)}return native.execute(p)},read:p=>native.read(p)};
const closing=await GeoTileSession.create([source],async()=>bytes(f.point),{viewId:2n,budget:128<<20,bridge:delayed});
const retired=closing.dispose();await disposing;assert.throws(()=>closing.prepare(camera,options),/unavailable/);
assert.equal(closing.closed,true);releaseDispose();await retired;
"""
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        env={
            **os.environ,
            "XYG_NATIVE_LIB": str(Path(_native._lib._name).resolve()),
            "XYG_TILE_FIXTURE": json.dumps(dict(point=point.hex(), foreground=foreground.hex())),
        },
        text=True,
        capture_output=True,
        check=True,
    )
