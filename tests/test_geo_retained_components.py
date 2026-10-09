"""Public composition against actual native retained sources and Node bindings."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest

import xyg
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _native

ROOT = Path(__file__).resolve().parents[1]


def chart_for(source, **properties):
    q = query(source.info)
    return xyg.geo_chart(
        xyg.geo_layer(
            "points", source=source, layer_id=U64, query=q, sequence=1, style=style(), **properties
        ),
        camera=q["camera"],
    )


def test_public_sync_notebook_loop_returns_owned_frame_and_density_is_only_a_preference():
    manifest, chunk = fixture_manifest()
    assert xyg.RetainedGeoSource.__module__ == "xyg._geo_retained"

    async def notebook():
        source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
        q = query(source.info)
        q["reduced_kind"] = 1
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=1, style=style()
            ),
            camera=q["camera"],
        )
        frame = chart.compile()
        try:
            assert not frame.data.aggregate
            assert frame.data.record(0)["feature_id"] == U64
            with pytest.raises(ValueError, match="compile the retained"):
                chart.to_image()
            source.close()
            assert frame.data.record(0)["feature_id"] == U64
        finally:
            frame.close()
            source.close()

    asyncio.run(notebook())


@pytest.mark.parametrize(
    "property_name", ["feature_styles", "values", "state_flags", "event", "labels", "legend_label"]
)
def test_retained_unsupported_properties_fail_before_publication(property_name):
    manifest, chunk = fixture_manifest()
    source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    try:
        chart = chart_for(source, **{property_name: []})
        with pytest.raises(ValueError, match="exactly query"):
            chart.compile()
        assert source.current is None
    finally:
        source.close()


def test_retained_camera_layer_budget_legend_events_and_mixed_layers_are_explicit():
    manifest, chunk = fixture_manifest()
    source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = query(source.info)
    layer = xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=1, style=style())
    try:
        for camera in (
            {**q["camera"], "center_x": -0.0},
            {k: v for k, v in q["camera"].items() if k != "world_wrap"},
        ):
            with pytest.raises(ValueError, match="camera"):
                xyg.geo_chart(layer, camera=camera).compile()
        with pytest.raises(ValueError, match="budget"):
            xyg.geo_chart(layer, camera=q["camera"], budget=64 << 20).compile()
        with pytest.raises(ValueError, match="layer_id"):
            xyg.geo_chart(
                xyg.geo_layer(
                    "points", source=source, layer_id=1, query=q, sequence=1, style=style()
                ),
                camera=q["camera"],
            ).compile()
        with pytest.raises(ValueError, match="one layer"):
            xyg.geo_chart(layer, layer, camera=q["camera"]).compile()
        with pytest.raises(ValueError, match="no legend"):
            xyg.geo_chart(layer, camera=q["camera"], legend={}).compile()
        with pytest.raises(ValueError, match="events"):
            xyg.geo_chart(layer, camera=q["camera"]).compile(event={"kind": 4})
        with pytest.raises(ValueError, match="only points"):
            xyg.geo_chart(
                xyg.geo_layer(
                    "density", source=source, layer_id=U64, query=q, sequence=1, style=style()
                ),
                camera=q["camera"],
            ).compile()
        with pytest.raises(ValueError, match="every field"):
            xyg.geo_chart(
                xyg.geo_layer(
                    "points",
                    source=source,
                    layer_id=U64,
                    query=q,
                    sequence=1,
                    style={"fill": b"\xff" * 4},
                ),
                camera=q["camera"],
            ).compile()
        assert source.current is None
    finally:
        source.close()


def test_public_async_same_composition_with_complete_uniform_style():
    manifest, chunk = fixture_manifest()

    async def proof():
        async def reader(_):
            return chunk

        source = await xyg.RetainedGeoSource.create_async(manifest, reader, budget=BUDGET)
        q = query(source.info)
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points",
                source=source,
                layer_id=U64,
                query=q,
                sequence=1,
                style=dict(
                    fill=b"\xff\0\0\xff",
                    stroke=b"\0" * 4,
                    stroke_width=0.0,
                    diameter=6.0,
                    opacity=1.0,
                    symbol=0,
                ),
            ),
            camera=q["camera"],
        )
        frame = await chart.compile_async()
        try:
            assert frame.data.record(0)["feature_id"] == U64
        finally:
            await frame.aclose()
            await source.aclose()

    asyncio.run(proof())


def test_new_source_export_remains_lazy_for_ordinary_composition():
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-c",
            "import sys,xyg; assert 'xyg._geo_retained' not in sys.modules; _=xyg.GeoChart; _=xyg.geo_layer; assert 'xyg._geoscale' not in sys.modules; assert 'xyg._geo_retained' not in sys.modules",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_node_public_retained_composition_matches_python_packet_and_static_catalog():
    manifest, chunk = fixture_manifest()
    source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    frame = chart_for(source).compile()
    try:
        expected = bytearray(frame.data.packet)
        expected[16:24] = b"\0" * 8
        script = """import {RetainedGeoSource,geoLayer,geoChart,GeoChart} from './packages/xy-node/src/index.js';
const p=JSON.parse(process.env.XYG_PUBLIC_RETAINED),b=x=>Uint8Array.from(Buffer.from(x,'hex'));
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:134217728n,maxChunks:65536,pageRows:4096};
const source=await RetainedGeoSource.create(b(p.manifest),async()=>b(p.chunk),{budget}),max=18446744073709551615n;
const camera={crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0};
const query={camera,reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:source.info.digest,generation:source.info.generation,layerId:max,cameraRevision:max,timeRevision:max,layerRevision:max,styleRevision:max,stateRevision:max,time:{kind:1,instant:-9223372036854775808n},maxProjectedVertices:1000000n};
const chart=geoChart(geoLayer('points',{source,layerId:max,query,sequence:1n,style:b(p.style)}),{camera});
if(!(chart instanceof GeoChart))throw new Error('public chart class');
try{chart.compile();throw new Error('acceptedwrongcompile');}catch(e){if(!e.message.includes('compileRetained'))throw e;}
const frame=await chart.compileRetained();await source.dispose();const packet=new Uint8Array(frame.data.packet);packet.fill(0,16,24);console.log(Buffer.from(packet).toString('hex'));await frame.dispose();
const staticChart=geoChart(geoLayer('points',{source:{geometry:1,crs:4326,xy:new Float64Array([0,0]),validity:new Uint8Array([1]),featureIds:new BigUint64Array([max])},layerId:max,style:{fill:new Uint8Array([255,0,0,255]),diameter:10}}),{camera});
const compiled=staticChart.compile();if(compiled.layers[0].featureIds[0]!==max)throw new Error('staticfullid');if(!staticChart.toSvg().includes('<svg'))throw new Error('staticsvg');"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            env={
                **os.environ,
                "XYG_NATIVE_LIB": str(Path(_native._lib._name).resolve()),
                "XYG_PUBLIC_RETAINED": json.dumps(
                    dict(manifest=manifest.hex(), chunk=chunk.hex(), style=style().hex())
                ),
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert bytes.fromhex(result.stdout.strip()) == expected
    finally:
        frame.close()
        source.close()
