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
        "a77e26707a3e980f88a823122781a80b72468af9"
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
    assert hexbin["count"] == "f39a0cdb44b31ff98813acc3a3a571b0b13ea613f642c029ed418cf815b86b84"
    assert hexbin["mean"] == hexbin["sum"]
    assert hexbin["mean"] == "ff483c0b93089af6a5fb81779f1cc54c6169dafd1a6d169446b8ea95202b1572"
    assert "public_heatmap_sha256" not in fixture
