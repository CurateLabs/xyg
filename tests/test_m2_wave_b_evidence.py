"""Keep the M2 Wave B evidence ledger and public Scene goldens honest."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "spec" / "benchmarks" / "hosted-evidence-95adb9de.json"
FIXTURE = ROOT / "tests" / "fixtures" / "figure_scene_v3.json"
REFRESH = ROOT / "tests" / "fixtures" / "graphforge" / "scene32_refresh.json"


def _public_scene(route: str) -> bytes:
    from xyg._scene_v3 import figure_scene

    path = ROOT / "scripts" / "bench_public_scene_routes.py"
    spec = importlib.util.spec_from_file_location("bench_public_scene_routes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    author = next(author for name, author, _ in module.ROUTES if name == route)
    return figure_scene(author())


def _assert_current_and_historical_scene(route: str, expected: str) -> None:
    scene = _public_scene(route)
    assert scene[:4] == b"XYGS" and struct.unpack_from("<I", scene, 4)[0] == 32
    assert hashlib.sha256(scene).hexdigest() == expected
    # This fixture has no new primitive: its previous digest differs only in
    # the version word. Keep measured historical artifacts attached to their
    # original output rather than rewriting their digests as new measurements.
    previous = bytearray(scene)
    struct.pack_into("<I", previous, 4, 31)
    refresh = json.loads(REFRESH.read_text())
    assert hashlib.sha256(previous).hexdigest() == refresh["public_previous_scene_sha256"][route]


def test_hosted_evidence_extract_has_the_four_size_ladders() -> None:
    extract = json.loads(EXTRACT.read_text())
    assert extract["schema"] == "xyg-m2-wave-b-hosted-evidence-v1"
    assert extract["source"]["head_sha"] == "95adb9deef74a236ce3a5db30b1fd166025b7e8c"
    assert extract["post_hexbin_nightly"]["status"] == "absent"
    assert extract["post_hexbin_nightly"]["main_sha_at_record"] == (
        "14e91a36b24c2bb0447e983c698d2e15b4b03527"
    )
    for key, count_attr in (
        ("authored_scene_browser.typed_series", "count"),
        ("authored_scene_browser.authored_scene", "count"),
        ("hosted_density_browser.rows", "count"),
        ("hosted_stream_density_browser.rows", "count"),
    ):
        block = extract
        for part in key.split("."):
            block = block[part]
        assert [row[count_attr] for row in block] == [100, 10_000, 100_000, 1_000_000]
    assert extract["hosted_density_browser"]["payload_bytes_constant"] == 473_712
    assert extract["hosted_stream_density_browser"]["rows"][-1]["streamPushes"] == 31


def test_public_hexbin_goldens_are_checked_in_and_mean_shares_sum() -> None:
    fixture = json.loads(FIXTURE.read_text())
    hexbin = fixture["public_hexbin_sha256"]
    assert hexbin["count"] == "d3fba86cda3ea1460d5456ad118e6ac6b8aaca1c3bc8db8755affe3693349313"
    assert hexbin["mean"] == hexbin["sum"]
    assert hexbin["mean"] == "8576c9bc252b2ec474d4262c1d7281a3b01b4bb02b91b6e52929a42b9b5a2edb"
    for reduce in ("count", "mean", "sum"):
        _assert_current_and_historical_scene(f"hexbin_{reduce}", hexbin[reduce])


def test_public_heatmap_golden_is_checked_in() -> None:
    fixture = json.loads(FIXTURE.read_text())
    assert (
        fixture["public_heatmap_sha256"]
        == "b389be24e1c957b3fdcb7e12b7b00365ad46d41630d87111142cd777e9212c6a"
    )
    _assert_current_and_historical_scene("heatmap", fixture["public_heatmap_sha256"])
