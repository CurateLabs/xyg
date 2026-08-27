"""Keep the M2 Wave B evidence ledger and public Scene goldens honest."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "spec" / "benchmarks" / "hosted-evidence-95adb9de.json"
FIXTURE = ROOT / "tests" / "fixtures" / "figure_scene_v3.json"


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
    assert hexbin["count"] == "e13ea9a03480bb9c578774bc041e9fe85c7c4761ab292eb8c23c7d330ea77266"
    assert hexbin["mean"] == hexbin["sum"]
    assert hexbin["mean"] == "c6eb4e309365643b509ab73e11bb42fa4df68a8c2bfcc784f90b55c4f7c0de7d"


def test_public_heatmap_golden_is_checked_in() -> None:
    fixture = json.loads(FIXTURE.read_text())
    assert (
        fixture["public_heatmap_sha256"]
        == "8cfe11fab875cd58e0eaa9a8c03896310ebd2a5bc2eadcda2213f08b972ea4f3"
    )
