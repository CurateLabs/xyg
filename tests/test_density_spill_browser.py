"""Real-browser control and negative oracles, never authority allocations."""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest
from scripts import density_spill_browser_smoke as smoke


@pytest.fixture(scope="module")
def chromium():
    path = os.environ.get("XYG_TEST_CHROMIUM")
    if not path:
        pytest.skip("set XYG_TEST_CHROMIUM to an explicit Chrome/Chromium executable")
    assert Path(path).is_file(), path
    return path


@pytest.mark.parametrize("points", [0, -1, True, 1_000_001, 100_000_000])
def test_control_rejects_scale_before_generating(points, monkeypatch, tmp_path):
    def forbidden(*_args):
        pytest.fail("invalid scale reached source allocation")

    monkeypatch.setattr(smoke.spill, "generate", forbidden)
    with pytest.raises(ValueError):
        smoke.run_control(points, 4096, "unused", tmp_path, 120)


def test_control_guard_bounds():
    smoke.guard(1_000_000, 1_000_000, 3600)
    for chunk, timeout in [(0, 120), (1_000_001, 120), (4096, float("nan")), (4096, 3601)]:
        with pytest.raises(ValueError):
            smoke.guard(16384, chunk, timeout)


def test_actual_mapped_browser_journey(chromium):
    # Short owned parent avoids Chromium's Unix-domain socket path limit.
    root = smoke.ROOT / "target" / "t"
    report = smoke.run_control(16384, 4096, chromium, root, 180)
    assert report["status"] == "ok" and report["authority"] is False
    assert report["source"]["generator"] == "diagonal-band-two-color-v1"
    assert report["windows"] == smoke.spill.windows(report["domain"])
    assert len(report["requests"]) == 99
    cached = report["browser"]["runs"]["cached"]
    fresh = report["browser"]["runs"]["fetch-all"]
    assert len(cached["samples"]) == len(fresh["samples"]) == 33
    for a, b in zip(cached["samples"], fresh["samples"], strict=True):
        assert b["cachedPixelEquality"] and a["pixelSha256"] == b["pixelSha256"]
        assert a["densityPixels"] > 100 and a["seam"]["densityPixels"] > 20
        assert a["seam"]["maxError"] <= 2
    fades = [s["fade"] for s in cached["samples"] if s["kind"] == "zoom"]
    assert len(fades) == 8 and all(f["sourceSurvived"] and f["retired"] for f in fades)
    assert sum(s["stats"]["received"] for s in cached["samples"]) < sum(
        s["stats"]["received"] for s in fresh["samples"]
    )
    assert cached["gpu"]["createdTextures"] > 0 and cached["gpu"]["remainingTextures"] == 0
    assert cached["destroyed"] and fresh["lateReplyIgnored"]
    assert report["browser"]["process_reaped"] and report["browser"]["profile_removed"]
    assert all(v is True or v == [] for v in report["cleanup"].values())
    assert not list(root.glob("density-spill-browser-*"))


@pytest.mark.parametrize("corruption", ["blank", "gutter"])
def test_browser_oracles_reject_corrupted_native_paint(chromium, monkeypatch, corruption):
    from xyg import interaction, kernels

    original = kernels.tile_store_paint
    budget = interaction.PYRAMID_RESIDENT_BYTES

    def corrupt(*args, **kwargs):
        packet = bytearray(original(*args, **kwargs))
        for index in range(struct.unpack_from("<I", packet, 16)[0]):
            at = 128 + index * 96
            width, height, offset, length = struct.unpack_from("<4I", packet, at + 12)
            if not length:
                continue
            if corruption == "blank":
                packet[offset : offset + length] = bytes(length)
            else:
                # Corrupt just the first gutter column, preserving image ink.
                for y in range(height):
                    pos = offset + y * width * 4
                    packet[pos : pos + 4] = bytes([0, 255, 0, 255])
        return bytes(packet)

    monkeypatch.setattr(kernels, "tile_store_paint", corrupt)
    root = smoke.ROOT / "target" / "t"
    with pytest.raises(
        RuntimeError, match=r"blank or missing endpoint colors|gutter mismatch|seam discontinuity"
    ):
        smoke.run_control(16384, 4096, chromium, root, 180)
    assert budget == interaction.PYRAMID_RESIDENT_BYTES
    assert not list(root.glob("density-spill-browser-*"))


def test_run_existing_cannot_bypass_local_scale_guard(tmp_path):
    class UnallocatedAuthoritySize:
        def __len__(self):
            return 100_000_000

    with pytest.raises(ValueError, match="1M"):
        smoke.run_existing(
            fig=None,
            sources=(UnallocatedAuthoritySize(),),
            source=None,
            spec=None,
            buffers=None,
            domain=None,
            journey=None,
            spill_file=None,
            chromium="unused",
            timeout=120,
            socket_parent=tmp_path,
        )


@pytest.mark.parametrize(
    "injection,match",
    [
        ("gl.createTexture();", "explicit deletion missing"),
        (
            "const leak=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,leak);gl.bufferData(gl.ARRAY_BUFFER,4096,gl.STATIC_DRAW);",
            "explicit deletion missing",
        ),
    ],
)
def test_initial_unreferenced_resource_leak_fails_before_context_loss(
    chromium, monkeypatch, injection, match
):
    marker = "  audit.label(v.pickTex,'pick');"
    assert marker in smoke.BROWSER_PROOF
    monkeypatch.setattr(
        smoke, "BROWSER_PROOF", smoke.BROWSER_PROOF.replace(marker, injection + marker, 1)
    )
    with pytest.raises(RuntimeError, match=match):
        smoke.run_control(16384, 4096, chromium, smoke.ROOT / "target/t", 180)


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("outgoing", "fade source destroyed|WebGL error|owned GL error"),
        ("stale", "owned GL error|owned creation failed|stale reply allocated"),
    ],
)
def test_real_browser_rejects_outgoing_deletion_and_stale_allocation(
    chromium, monkeypatch, mutation, match
):
    if mutation == "outgoing":
        marker = (
            "    assert(source.every(t=>gl.isTexture(t.tex)),'fade source destroyed during draw');"
        )
        replacement = "gl.deleteTexture(source[0].tex);" + marker
    else:
        marker = "  v._onKernelMsg(lastMessage,[lastRaw]);await sleep(30);"
        replacement = "  v._onKernelMsg(lastMessage,[lastRaw]);gl.createTexture();await sleep(30);"
    assert marker in smoke.BROWSER_PROOF
    monkeypatch.setattr(smoke, "BROWSER_PROOF", smoke.BROWSER_PROOF.replace(marker, replacement, 1))
    with pytest.raises(RuntimeError, match=match):
        smoke.run_control(16384, 4096, chromium, smoke.ROOT / "target/t", 180)


def test_actual_owned_storage_reallocation_uses_capacity_not_cumulative_uploads(chromium):
    # Exercise mutable/immutable images, subresources, buffer growth and shrink
    # on a real WebGL context, independent of the product's current allocation mix.
    expression = r"""
(async()=>{
 const gl=document.createElement('canvas').getContext('webgl2'),audit=ownedGL(gl);
 const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);
 gl.bufferData(gl.ARRAY_BUFFER,1024,gl.STATIC_DRAW);gl.bufferData(gl.ARRAY_BUFFER,4096,gl.STATIC_DRAW);gl.bufferData(gl.ARRAY_BUFFER,64,gl.STATIC_DRAW);
 const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
 gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,16,16,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
 gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,32,32,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
 gl.texImage2D(gl.TEXTURE_2D,0,gl.R8,4,4,0,gl.RED,gl.UNSIGNED_BYTE,null);
 const immutable=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,immutable);gl.texStorage2D(gl.TEXTURE_2D,2,gl.R8,8,8);
 const sizes=[audit.objects.get(b).bytes,audit.objects.get(t).bytes,audit.objects.get(immutable).bytes];
 gl.deleteBuffer(b);gl.deleteTexture(t);gl.deleteTexture(immutable);
 const gpu=audit.finish({gl:null,gpuTraces:[],_lutCache:new Map()},{});
 return {...await PROBE,gpu,sizes};})()
""".replace("PROBE", smoke.RENDERER_PROBE)
    page = "<script>" + smoke.GL_AUDIT + "window.proof=" + expression + ";</script>"
    result = smoke.run_browser(page, chromium, 30)
    assert result["sizes"] == [256, 16, 80]
    assert result["gpu"]["peakInstrumentedBytes"] == 4352


def actual_renderer(name="ANGLE (Apple, ANGLE Metal Renderer: Apple M4, Unspecified Version)"):
    return {
        "vendor": "Google Inc. (Apple)",
        "renderer": "WebKit WebGL",
        "version": "WebGL 2.0",
        "unmaskedVendor": "Apple",
        "unmaskedRenderer": name,
    }


@pytest.mark.parametrize(
    "mode,renderer,features",
    [
        ("hardware", "ANGLE SwiftShader software", {"webgl": "enabled", "webgl2": "enabled"}),
        ("hardware", "ANGLE Metal Renderer: Apple M4", {}),
        (
            "hardware",
            "ANGLE Metal Renderer: Apple M4",
            {"webgl": "unavailable_software", "webgl2": "enabled"},
        ),
        ("hardware", "ANGLE Metal Renderer: Apple M3", {"webgl": "enabled", "webgl2": "enabled"}),
        ("software", "ANGLE Metal Renderer: Apple M4", {}),
        ("software", None, {}),
    ],
)
def test_renderer_admission_uses_actual_gpu_not_request(mode, renderer, features):
    with pytest.raises(ValueError):
        smoke.renderer_guard(actual_renderer(renderer), {"gpu": {"featureStatus": features}}, mode)


def test_positive_hardware_renderer_requires_accelerated_webgl2():
    smoke.renderer_guard(
        actual_renderer(),
        {"gpu": {"featureStatus": {"webgl": "enabled", "webgl2": "enabled"}}},
        "hardware",
    )


def test_failed_hardware_preflight_retains_actual_renderer_and_feature_status(
    chromium, tmp_path, monkeypatch
):
    # Even an accelerated developer workstation cannot satisfy this deliberate
    # negative admission, and no chart/source generation is involved.
    original = smoke.renderer_guard

    def refuse(renderer, gpu, mode):
        original(renderer, gpu, "software")
        raise ValueError("deliberate negative hardware admission")

    monkeypatch.setattr(smoke, "renderer_guard", refuse)
    with pytest.raises(smoke.RendererAdmissionError) as exc:
        smoke.renderer_preflight(chromium, "software", smoke.ROOT / "target/t", 30)
    evidence = exc.value.evidence
    assert evidence["status"] == "failed"
    assert evidence["renderer"]["unmaskedRenderer"]
    assert evidence["gpu_info"]["gpu"]["featureStatus"]
    assert evidence["process_reaped"] and evidence["profile_removed"]


def test_hardware_admits_chromium_single_webgl_feature_with_actual_webgl2_context():
    smoke.renderer_guard(
        actual_renderer(), {"gpu": {"featureStatus": {"webgl": "enabled"}}}, "hardware"
    )
    with pytest.raises(ValueError, match="WebGL feature status"):
        smoke.renderer_guard(
            actual_renderer(),
            {"gpu": {"featureStatus": {"webgl": "enabled", "webgl2": "unavailable_software"}}},
            "hardware",
        )
    with pytest.raises(ValueError, match="WebGL2 context/version"):
        smoke.renderer_guard(
            {**actual_renderer(), "version": "WebGL 1.0"},
            {"gpu": {"featureStatus": {"webgl": "enabled"}}},
            "hardware",
        )


def test_destroy_rejects_deleted_buffer_reference_in_any_view_field(chromium, monkeypatch):
    marker = "  v.destroy();const gpu=audit.finish(v,g),before=audit.events.length;"
    assert marker in smoke.BROWSER_PROOF
    replacement = "  const saved=v.quad;v.destroy();v.retainedDeletedBuffer=saved;const gpu=audit.finish(v,g),before=audit.events.length;"
    monkeypatch.setattr(smoke, "BROWSER_PROOF", smoke.BROWSER_PROOF.replace(marker, replacement, 1))
    with pytest.raises(RuntimeError, match="retained owned resource references"):
        smoke.run_control(16384, 4096, chromium, smoke.ROOT / "target/t", 180)
