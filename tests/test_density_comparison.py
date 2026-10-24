"""Equal-window/source proofs; large-row authority tests allocate no large source."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from benchmarks._ux_comparison_data import make_data
from benchmarks._ux_comparison_source import (
    allocation_guard,
    count_window,
    create_source,
    inventory,
    load_source,
    windows,
)


@pytest.mark.parametrize("validation", ["", "validateOutput:async()=>{},"])
def test_producer_cannot_accept_missing_or_failing_xyg_numerical_oracle(validation):
    pytest.importorskip("websocket")
    pytest.importorskip("tornado.web")
    from benchmarks.bench_density_comparison import engine_js

    script = r"""
let tick=0;
globalThis.performance={now:()=>++tick};
globalThis.requestAnimationFrame=callback=>setImmediate(callback);
globalThis.document={title:''};
const data=new Uint8Array(6*6*4);for(let i=3;i<data.length;i+=4)data[i]=255;
globalThis.window={__arm:{ready:()=>true,readbacks:()=>[{data,w:6,h:6}]},
 __comparison:{VALIDATION state:()=>({axes:[0,1,0,1],plot_shape:[512,512],
 output:{adopted:true,mode:'density',domain:[0,1,0,1],numerical_oracle:{passed:false}}})}};
setTimeout(()=>{process.stdout.write(document.title);process.exit(0);},100);
""".replace("VALIDATION", validation)
    script += engine_js(
        {"extents": [0, 1, 0, 1], "actual_rows": 1000, "windows": []}, 0.1, "xy-density"
    )
    completed = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=True, timeout=5
    )
    assert completed.stdout.startswith("UX_BENCH ")
    result = json.loads(completed.stdout.removeprefix("UX_BENCH "))
    assert result["comparison_status"] == "cold_failed"


def test_competitor_metrics_do_not_prepare_xyg_oracle(monkeypatch):
    pytest.importorskip("tornado.web")
    from benchmarks import _ux_comparison_host as host
    from benchmarks import _ux_comparison_oracle as numerical

    def forbidden(*args, **kwargs):
        raise AssertionError("XYG source oracle added to competitor preparation")

    monkeypatch.setattr(host, "_comparison_source", (None, None, None))
    monkeypatch.setattr(numerical, "SourceOracle", forbidden)
    assert host.metrics_handler({"canonical_admission": {}})


def test_same_24_pans_eight_adjacent_zooms_and_f32_source(tmp_path):
    meta = create_source(tmp_path / "source", 1000, "f32", chunk=127)
    x, y, loaded = load_source(tmp_path / "source/source.json", 1000)
    a, b = make_data(1000)
    np.testing.assert_array_equal(x, a)
    np.testing.assert_array_equal(y, b)
    assert meta == loaded
    assert meta["sha256_x_then_y"] == hashlib.sha256(a.tobytes() + b.tobytes()).hexdigest()
    steps = windows(meta["extents"])
    assert len(steps) == 32
    assert [s["kind"] for s in steps] == ["pan"] * 24 + ["zoom"] * 8
    zooms = steps[24:]
    assert (zooms[1]["window"][1] - zooms[1]["window"][0]) == pytest.approx(
        2 * (zooms[0]["window"][1] - zooms[0]["window"][0])
    )
    for step in meta["windows"]:
        assert step["expected_count"] == count_window(a, b, step["window"], chunk=13)
    assert count_window(x, y, [100, 101, 100, 101], chunk=64) == 0


def test_f64_map_is_chunk_invariant_real_and_retains_pointers(tmp_path):
    first = create_source(tmp_path / "a", 1000, "f64-memmap", chunk=19)
    second = create_source(tmp_path / "b", 1000, "f64-memmap", chunk=257)
    assert first["sha256_x_then_y"] == second["sha256_x_then_y"]
    assert sum(c["bytes"] for c in first["columns"].values()) == 16000
    x, y, _ = load_source(tmp_path / "a/source.json", 1000)
    assert isinstance(x, np.memmap) and isinstance(y, np.memmap)
    observed = inventory((x, y), (x.view(np.ndarray), y.view(np.ndarray)))
    assert all(
        v["pointer_equal"] and v["shares_memory"] and v["retained_mapped"]
        for v in observed.values()
    )
    assert count_window(x, y, first["extents"]) == 1000
    # Corruption is a source failure, never a row-count-only pass.
    with (tmp_path / "a/x.f64-memmap").open("r+b") as stream:
        stream.write(b"broken!!")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_source(tmp_path / "a/source.json", 1000)


def test_allocation_guard_precedes_files_and_does_not_confuse_mapped_size_with_rss(tmp_path):
    directory = tmp_path / "forbidden"
    with pytest.raises(ValueError, match="over 1M"):
        create_source(directory, 1_000_001, "f64-memmap", disk_gib=0.25)
    assert not directory.exists()
    with pytest.raises(ValueError, match="RSS guard"):
        allocation_guard(1000, "f32", rss_gib=3)
    with pytest.raises(ValueError, match="disk guard"):
        allocation_guard(1000, "f32", disk_gib=1)
    facts = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW": "Interactive ceiling benchmark",
        "RUNNER_OS": "macOS",
        "system": "Darwin",
        "machine": "arm64",
        "memory": 48 * 2**30,
    }
    authorized = allocation_guard(1_000_000_000, "f64-memmap", rss_gib=20, disk_gib=32, facts=facts)
    assert authorized["source_file_bytes"] == 16_000_000_000
    assert authorized["mapped_bytes_are_not_rss"] is True
    for key, value in [
        ("GITHUB_REF", "refs/heads/other"),
        ("system", "Linux"),
        ("GITHUB_EVENT_NAME", "push"),
    ]:
        with pytest.raises(ValueError, match="over 1M"):
            allocation_guard(
                1_000_000_000, "f64-memmap", rss_gib=20, disk_gib=32, facts={**facts, key: value}
            )


def test_original_archive_is_bound_to_historical_commit_not_current_harness():
    root = Path(__file__).resolve().parents[1]
    directory = root / "benchmarks/results/live-aggregation-2026-10-24"
    report = json.loads((directory / "bounded.json").read_text())
    assert (
        hashlib.sha256((directory / "bounded.json").read_bytes()).hexdigest()
        == "9917683d0175dd026fd3e9683bcadac498b9e34d1a761388e212303370e6a083"
    )
    assert report["environment"]["git"]["commit"] == "71e48b67827709ed251ae05b90d010a8cef824eb"
    # Its dirty-tree sources were committed as 51975d5d. Do not demand those
    # raw producer hashes match evolved code, and never rewrite the archive.
    old_hash = report["provenance_sha256"]["benchmarks/bench_ux.py"]
    assert len(old_hash) == 64


@pytest.mark.parametrize("child", [False, True])
def test_legacy_ux_rejects_large_source_before_generation_or_output(monkeypatch, tmp_path, child):
    pytest.importorskip("websocket")
    from benchmarks import bench_ux

    output = tmp_path / "not-created.json"
    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("unbounded controller or builder allocation")

    monkeypatch.setattr(bench_ux, "make_data", forbidden)
    monkeypatch.setattr(bench_ux, "plotly_artifact", forbidden)
    argv = (
        [
            "bench_ux.py",
            "--plotly-build-child",
            "--build-n",
            "1000001",
            "--build-artifact",
            str(output),
        ]
        if child
        else ["bench_ux.py", "--sizes", "1000001", "--memory-gib", "0.01", "--out", str(output)]
    )
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as rejected:
        bench_ux.main()
    assert rejected.value.code == 2
    assert called == []
    assert not output.exists()


def test_new_controller_rejects_large_local_source_before_launch_or_directory(
    monkeypatch, tmp_path
):
    pytest.importorskip("websocket")
    from benchmarks import bench_density_comparison as runner

    output = tmp_path / "not-created" / "result.json"

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "source child or temporary directory created before allocation authority"
        )

    monkeypatch.setattr(runner.subprocess, "Popen", forbidden)
    monkeypatch.setattr(runner.tempfile, "TemporaryDirectory", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        [
            "bench_density_comparison.py",
            "--sizes",
            "1000001",
            "--profile",
            "f64-memmap",
            "--memory-gib",
            "2",
            "--disk-gib",
            "0.25",
            "--chrome",
            "unused",
            "--out",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as rejected:
        runner.main()
    assert rejected.value.code == 2
    assert not output.parent.exists()


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--timeout", "nan"),
        ("--timeout", "inf"),
        ("--timeout", "301"),
        ("--timeout", "0"),
        ("--step-timeout", "nan"),
        ("--step-timeout", "inf"),
        ("--step-timeout", "16"),
        ("--step-timeout", "0"),
    ],
)
def test_comparison_rejects_invalid_deadlines_before_source_allocation(
    monkeypatch, tmp_path, flag, value
):
    pytest.importorskip("websocket")
    from benchmarks import bench_density_comparison as runner

    output = tmp_path / "not-created" / "result.json"

    def forbidden(*args, **kwargs):
        pytest.fail("invalid deadline reached source allocation")

    monkeypatch.setattr(runner.subprocess, "Popen", forbidden)
    monkeypatch.setattr(runner.tempfile, "TemporaryDirectory", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        [
            "bench_density_comparison.py",
            "--sizes",
            "1000",
            "--chrome",
            "unused",
            "--out",
            str(output),
            flag,
            value,
        ],
    )
    with pytest.raises(SystemExit) as rejected:
        runner.main()
    assert rejected.value.code == 2
    assert not output.parent.exists()


@pytest.mark.parametrize("hardware", [False, True])
@pytest.mark.parametrize("inherited", ["0", "1"])
def test_saved_renderer_mode_uses_cli_even_with_opposite_ambient_env(
    monkeypatch, tmp_path, hardware, inherited
):
    pytest.importorskip("websocket")
    from benchmarks import bench_density_comparison as runner

    monkeypatch.setenv("XY_BENCH_HARDWARE_GL", inherited)
    output = tmp_path / "report.json"
    # A real bounded source child times out before imports; no browser is launched.
    monkeypatch.setattr(
        "sys.argv",
        [
            "bench_density_comparison.py",
            "--sizes",
            "5",
            "--arms",
            "xy-density",
            "--chrome",
            "unused",
            "--timeout",
            "0.001",
            "--out",
            str(output),
            *(["--hardware"] if hardware else []),
        ],
    )
    runner.main()
    report = json.loads(output.read_text())
    expected = "hardware" if hardware else "software-gl"
    assert report["environment"]["browser_renderer"] == expected
    assert report["environment"]["browser_renderer_requested"] == expected
    assert report["environment"]["browser_renderer_observed"] is None
    assert report["environment"]["browser_renderer_scope"] == (
        "launch-request; actual renderer not measured"
    )
    assert {row["status"] for row in report["results"]} == {"source_timeout"}


def test_retained_equal_window_profiles_oracles_modes_and_historical_producers():
    """Offline integrity of actual browser observations; never a stubbed run."""
    root = Path(__file__).resolve().parents[1]
    directory = root / "benchmarks/results/live-aggregation-2026-10-24/equal-window-v2"
    reports = {
        name: json.loads(gzip.decompress((directory / (name + ".gz")).read_bytes()))
        for name in ("f32.json", "f32-xy-cache-followup.json", "f64-memmap.json")
    }
    initial = reports["f32.json"]
    historical = json.loads((directory.parent / "bounded.json").read_text())
    assert len(initial["results"]) == 18
    for n, source in initial["sources"].items():
        assert source["sha256_x_then_y"] == historical["sources"][n]["sha256_x_then_y"]
    # Retain both strict-pointer diagnostic failures, without turning them into successes.
    failures = [r for r in initial["results"] if r["status"] != "ok"]
    assert len(failures) == 2
    for row in failures:
        assert row["arm"] == "xy-density" and row["n"] == 1_000_000
        assert row["status"] == "step_failed"
        assert row["steps"][-1]["diag"]["snap"]["hash"] == row["steps"][3]["paint_hash32"]
    repairs = reports["f32-xy-cache-followup.json"]
    assert len(repairs["results"]) == 2
    for row in repairs["results"]:
        assert row["status"] == "ok" and len(row["steps"]) == 32
        cached = [
            s["state"]["output"]
            for s in row["steps"]
            if s["state"]["output"].get("equivalent_cached_raster")
        ]
        assert cached
        assert all(c["grid_value_equality_verified"] for c in cached)
        assert any(c["rendered_revision"] < c["revision"] for c in cached)
    assert len(reports["f64-memmap.json"]["results"]) == 18
    for name, report in reports.items():
        producer = directory / ("f32-producer" if name == "f32.json" else "current-producer")
        for path, digest in report["provenance_sha256"].items():
            if path.startswith("benchmarks/"):
                assert (
                    hashlib.sha256((producer / (path + ".txt")).read_bytes()).hexdigest() == digest
                )
        for row in report["results"]:
            if row["status"] != "ok":
                continue
            source = report["sources"][str(row["n"])]
            assert len(row["steps"]) == 32 and row["empty_control"]["ok"] is True
            assert row["empty_control"]["lit_pixels"] == 0
            assert row["host_meta"]["source"]["sha256_x_then_y"] == source["sha256_x_then_y"]
            assert row["host_meta"]["source"]["actual_rows"] == row["n"]
            assert sum(c["bytes"] for c in source["columns"].values()) == row["n"] * (
                16 if report["profile"] == "f64-memmap" else 8
            )
            for step, request in zip(row["steps"], source["windows"], strict=True):
                assert step["ok"] is True
                assert step["kind"] == request["kind"]
                assert step["requested_window"] == request["window"]
                assert step["expected_count"] == request["expected_count"]
                assert np.allclose(step["state"]["axes"], request["window"], rtol=0, atol=1e-9)
                assert step["state"]["plot_shape"] == [512, 512]
                out = step["state"]["output"]
                assert out["adopted"] is True
                if out["exact_fallback"]:
                    assert row["arm"] == "xy-density"
                    assert out["exact_count"] == request["expected_count"]
                    assert out["payload_count"] >= out["exact_count"]
                else:
                    assert np.allclose(out["domain"], request["window"], rtol=0, atol=1e-9)
                    assert all(0 < v <= 512 for v in out["raster_shape"])
                if out.get("oracle"):
                    assert (
                        out["oracle"]["passed"]
                        and out["oracle"]["count"] == request["expected_count"]
                    )
                observation = step["host_observation"]
                if row["arm"] == "datashader-aggregate":
                    assert observation["last_output"]["passed"] is True
                    assert observation["last_output"]["grid_mass"] == request["expected_count"]
                    assert np.allclose(
                        observation["last_output"]["domain"], request["window"], rtol=0, atol=1e-9
                    )
                for value in step["memory"].values():
                    assert value > 0
                assert step["memory"]["host_peak_rss_bytes"] >= step["memory"]["host_rss_bytes"]
                assert (
                    step["memory"]["browser_peak_rss_bytes"] >= step["memory"]["browser_rss_bytes"]
                )
                for col in observation["canonical_admission"].values():
                    for key in (
                        "pointer_equal",
                        "shares_memory",
                        "source_mapped",
                        "retained_mapped",
                    ):
                        assert isinstance(col[key], bool)
                    if report["profile"] == "f64-memmap":
                        assert col["source_mapped"] is True
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split("  ", 1)
        assert hashlib.sha256((directory / path).read_bytes()).hexdigest() == digest


def test_live_host_real_file_entry_prepares_and_posts_without_checkout_path(tmp_path):
    """Match the Actions file launch, with installed XYG but no checkout import path."""
    pytest.importorskip("tornado.web")
    import base64
    import os
    import sys
    import threading
    import urllib.request

    import xyg

    root = Path(__file__).resolve().parents[1]
    meta = create_source(tmp_path / "source", 1000, "f64-memmap")
    x, y, _ = load_source(tmp_path / "source/source.json", 1000)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    paths = subprocess.check_output(
        [sys.executable, "-c", "import json,sys;print(json.dumps(sys.path))"],
        cwd=tmp_path,
        env=env,
        text=True,
    )
    assert str(root) not in json.loads(paths)
    # The subprocess starts at the actual file entry, not runpy/importlib or -m.
    with (tmp_path / "stderr").open("w+") as errors:
        process = subprocess.Popen(
            [
                sys.executable,
                str(root / "benchmarks/_ux_live_host.py"),
                "--n",
                "1000",
                "--density",
                "on",
                "--comparison-source",
                str(tmp_path / "source/source.json"),
            ],
            cwd=tmp_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )
        lines = []

        def read():
            for line in process.stdout:
                if line.startswith("META "):
                    lines.append(line)
                    return

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            reader.join(30)
            errors.seek(0)
            assert lines, errors.read()
            host_meta = json.loads(lines[0][5:])
            assert host_meta["source"] == meta
            url = f"http://127.0.0.1:{host_meta['port']}/comparison_metrics"
            with urllib.request.urlopen(url, timeout=5) as response:
                metrics = json.load(response)
            assert metrics["numerical_oracle_preparation"]["version"] == "source-cell-compose-v1"
            fig = xyg.scatter_chart(
                xyg.scatter(x, y, density=True),
                xyg.x_axis(
                    domain=tuple(meta["extents"][:2]), show=False, tick_label_strategy="none"
                ),
                xyg.y_axis(
                    domain=tuple(meta["extents"][2:]), show=False, tick_label_strategy="none"
                ),
                width=512,
                height=512,
                padding=0,
            ).figure()
            spec, buffers = fig.build_payload_split()
            trace = spec["traces"][0]
            density = trace["density"]
            wire = bytes(buffers[density["buf"]])
            maximum = density["max"]
            decoded = (
                np.expm1(
                    np.frombuffer(wire, dtype=np.uint8).astype(float) / 255 * np.log1p(maximum)
                )
                .astype("<f4")
                .tobytes()
            )
            output = {
                "mode": "density",
                "tier": trace["tier"],
                "reduction": density["reduction"],
                "visible": trace["n_points"],
                "domain": [*density["x_range"], *density["y_range"]],
                "raster_shape": [density["h"], density["w"]],
                "binning": density["binning"],
                "encoding": density["enc"],
                "reply_max": maximum,
                "adopted_max": maximum,
            }
            body = {
                "output": output,
                "cold": True,
                "target": meta["extents"],
                "wire": base64.b64encode(wire).decode(),
                "decoded": base64.b64encode(decoded).decode(),
            }
            request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                proof = json.load(response)
            assert proof["passed"], proof
            assert proof["source_sha256"] == meta["sha256_x_then_y"]
            assert proof["validation_http_request_bytes"] == len(request.data)
        finally:
            process.terminate()
            process.wait(timeout=5)
            reader.join(5)


@pytest.mark.parametrize("fault", ["none", "image_hash", "backend_revision", "grid_hash", "extent"])
def test_bokeh_cold_admission_waits_for_bound_512_image(fault):
    """Ten stable bootstrap paints cannot stand in for a delayed real response."""
    pytest.importorskip("websocket")
    pytest.importorskip("tornado.web")
    from benchmarks._ux_comparison_host import BOKEH_JS
    from benchmarks.bench_density_comparison import engine_js

    script = r"""
const cryptoNode=require('node:crypto');globalThis.crypto=cryptoNode.webcrypto;
let frame=0,now=0,changed=()=>{};
globalThis.performance={now:()=>now};
const domain=[0,1,0,1];
const makeImage=n=>{const a=new Uint32Array(n*n);a.fill(0xff000000);a.shape=[n,n];return a;};
const digest=a=>cryptoNode.createHash('sha256').update(new Uint8Array(a.buffer)).digest('hex');
const initial=makeImage(400),final=makeImage(512);
const host={domain,grid_shape:[512,512],backend_revision:2,grid_sha256:'a'.repeat(64),
 count:1000,grid_mass:1000,passed:true};
let binding={...host,grid_shape:[400,400],backend_revision:1,image_sha256:digest(initial)};
const cds={data:{image:[initial],comparison_backend:[binding]},
 properties:{data:{change:{connect:f=>changed=f}}}};
const pixels=new Uint8ClampedArray(final.buffer);
const pv={frame:{bbox:{width:512,height:512,x0:0,y0:0}},
 canvas_view:{primary:{el:{getContext:()=>({getImageData:()=>({data:pixels})})}}},
 renderer_views:new Map([[0,{model:{glyph:{type:'ImageRGBA'},data_source:cds}}]])};
globalThis.window={__arm:{_pv:()=>pv,ready:()=>true,currentRaster:()=>true,
 evidence:()=>({domain:{x0:0,x1:1,y0:0,y1:1},rasters:[{x:0,y:0,dw:1,dh:1,
 shape:cds.data.image[0].shape}]})}};
globalThis.fetch=async()=>({json:async()=>({last_output:host})});
globalThis.requestAnimationFrame=f=>setImmediate(()=>{
 frame++;now+=16;
 if(frame===35){
   binding={...host,image_sha256:digest(final)};
   if(FAULT==='image_hash')binding.image_sha256='f'.repeat(64);
   if(FAULT==='backend_revision')binding.backend_revision=1;
   if(FAULT==='grid_hash')binding.grid_sha256='b'.repeat(64);
   if(FAULT==='extent')binding.domain=[0,2,0,1];
   cds.data={image:[final],comparison_backend:[binding]};changed();
 }
 f();
});
globalThis.document={set title(t){
 if(t==='UX_SHOT visible-complete'){
  process.stdout.write(JSON.stringify({status:'admitted',frame,state:window.__comparison.state()}));process.exit(0);
 }
 if(t.startsWith('UX_BENCH ')){
  process.stdout.write(JSON.stringify({status:'rejected',frame,result:JSON.parse(t.slice(9))}));process.exit(0);
 }
}};
""".replace("FAULT", json.dumps(fault))
    script += BOKEH_JS + engine_js(
        {"extents": [0, 1, 0, 1], "actual_rows": 1000, "windows": []}, 2, "datashader-aggregate"
    )
    completed = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=True, timeout=10
    )
    result = json.loads(completed.stdout)
    assert result["frame"] >= 35
    if fault == "none":
        assert result["status"] == "admitted"
        out = result["state"]["output"]
        assert out["raster_shape"] == [512, 512]
        assert out["revision"] > 0 and out["backend_binding"]["backend_revision"] == 2
    else:
        assert result["status"] == "rejected"
        assert result["result"]["comparison_status"] == "cold_failed"


def test_bokeh_checkpoint_rejects_backend_ahead_of_adopted_image():
    pytest.importorskip("websocket")
    pytest.importorskip("tornado.web")
    from benchmarks.bench_density_comparison import datashader_checkpoint_matches

    out = {
        "domain": [0, 1, 0, 1],
        "grid_shape": [512, 512],
        "grid_sha256": "a" * 64,
        "count": 1000,
        "grid_mass": 1000,
        "passed": True,
        "backend_revision": 2,
    }
    browser = {
        "domain": out["domain"],
        "raster_shape": [512, 512],
        "backend_binding": dict(out),
    }
    paint = {"expected_count": 1000, "state": {"output": browser}}
    assert datashader_checkpoint_matches(paint, {"last_output": out})
    for key, bad in [
        ("grid_shape", [400, 400]),
        ("backend_revision", 1),
        ("grid_sha256", "b" * 64),
    ]:
        browser["backend_binding"] = dict(out, **{key: bad})
        assert not datashader_checkpoint_matches(paint, {"last_output": out})


def test_bokeh_image_binding_uses_matching_grid_not_latest_backend():
    pytest.importorskip("tornado.web")
    from benchmarks._ux_comparison_host import datashader_binding

    initial = {
        "domain": [0, 1, 0, 1],
        "grid_shape": [400, 400],
        "grid_sha256": "a" * 64,
        "count": 1000,
        "grid_mass": 1000,
        "passed": True,
        "backend_revision": 1,
    }
    final = dict(initial, grid_shape=[512, 512], grid_sha256="b" * 64, backend_revision=2)
    state = {"last_output": final, "backend_outputs": {"initial": initial, "final": final}}
    data = {
        "x": [0],
        "y": [0],
        "dw": [1],
        "dh": [1],
        "image": [np.zeros((400, 400), dtype=np.uint32)],
    }
    binding = datashader_binding(data, state)
    assert binding["backend_revision"] == 1
    assert binding["grid_sha256"] == initial["grid_sha256"]
    assert binding["image_sha256"] == hashlib.sha256(data["image"][0].tobytes()).hexdigest()
    data["image"] = [np.zeros((512, 512), dtype=np.uint32)]
    assert datashader_binding(data, state)["backend_revision"] == 2
    data["dw"] = [2]
    with pytest.raises(AssertionError, match="no observed source-grid binding"):
        datashader_binding(data, state)
