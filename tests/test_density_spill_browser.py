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
    assert len(report["requests"]) == 66
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
