"""Pin the ABI-only refresh while retaining complete predecessor packet evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from xyg._abi_generated import ABI_VERSION

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "spec/performance/pr1110-abi-fixtures-2026-11-07"
CURRENT_RECEIPT = ROOT / "spec/performance/filter-catalog-abi-union-2026-11-07"
TRANSITION = json.loads((RECEIPT / "fixture-transition.json").read_text())
UNIFIED_RECEIPT = ROOT / "spec/performance/frozen-combined-module-2026-11-07"
HISTORICAL = RECEIPT
FROZEN_RECEIPT = ROOT / "spec/performance/temporal-graph-freeze-2026-11-07"
FROZEN_TRANSITION = json.loads(
    (
        ROOT / "spec/performance/temporal-worker-export-2026-11-07/fixture-transition.json"
    ).read_text()
)


def assert_abi_only_refresh(
    current: dict, predecessor: dict, *, expected_abi: int = ABI_VERSION
) -> None:
    assert current["abi_version"] == expected_abi
    assert predecessor["abi_version"] == 399
    expected = dict(predecessor, abi_version=expected_abi)
    assert current == expected  # Every field, including complete packets and hashes.


@pytest.mark.parametrize("path", TRANSITION)
def test_complete_fixture_transition(path: str) -> None:
    entry = TRANSITION[path]
    current = (CURRENT_RECEIPT / "abi401-predecessor" / Path(path).name).read_bytes()
    predecessor = (RECEIPT / "predecessor" / Path(path).name).read_bytes()
    assert hashlib.sha256(current).hexdigest() == entry["currentSha256"]
    assert hashlib.sha256(predecessor).hexdigest() == entry["predecessorSha256"]
    assert_abi_only_refresh(json.loads(current), json.loads(predecessor), expected_abi=401)


@pytest.mark.parametrize("path", TRANSITION)
@pytest.mark.parametrize("wrong_abi", [399, ABI_VERSION - 1, ABI_VERSION + 1])
def test_stale_and_wrong_versions_are_rejected(path: str, wrong_abi: int) -> None:
    current = json.loads((ROOT / path).read_bytes())
    predecessor = json.loads((RECEIPT / "predecessor" / Path(path).name).read_bytes())
    current["abi_version"] = wrong_abi
    with pytest.raises(AssertionError):
        assert_abi_only_refresh(current, predecessor)


@pytest.mark.parametrize("path", TRANSITION)
def test_product_packet_drift_is_rejected(path: str) -> None:
    current = json.loads((ROOT / path).read_bytes())
    predecessor = json.loads((RECEIPT / "predecessor" / Path(path).name).read_bytes())
    changed = copy.deepcopy(current)
    # Removing a complete product case must fail even with the correct current ABI.
    changed["cases"].pop()
    with pytest.raises(AssertionError):
        assert_abi_only_refresh(changed, predecessor)


def test_geo_packet_bit_drift_is_rejected_with_consistent_digest() -> None:
    path = "tests/fixtures/geo_cross_host.json"
    current = json.loads((ROOT / path).read_bytes())
    predecessor = json.loads((RECEIPT / "predecessor" / Path(path).name).read_bytes())
    case = current["cases"][0]
    packet = bytearray.fromhex(case["metadata_hex"])
    packet[-1] ^= 1
    case["metadata_hex"] = packet.hex()
    case["metadata_sha256"] = hashlib.sha256(packet).hexdigest()
    with pytest.raises(AssertionError):
        assert_abi_only_refresh(current, predecessor)


@pytest.mark.parametrize("path", TRANSITION)
def test_append_only_401_to_current_transition(path: str) -> None:
    transition = json.loads((CURRENT_RECEIPT / "fixture-transition.json").read_text())[path]
    predecessor = (CURRENT_RECEIPT / "abi401-predecessor" / Path(path).name).read_bytes()
    current = (UNIFIED_RECEIPT / "abi403-predecessor" / Path(path).name).read_bytes()
    assert hashlib.sha256(predecessor).hexdigest() == transition["predecessorSha256"]
    assert hashlib.sha256(current).hexdigest() == transition["currentSha256"]
    assert json.loads(predecessor)["abi_version"] == 401
    assert json.loads(current) == dict(json.loads(predecessor), abi_version=403)


@pytest.mark.parametrize("path", TRANSITION)
def test_complete_402_parent_packets_survive_unified_abi(path: str) -> None:
    transition = json.loads((CURRENT_RECEIPT / "abi402-transition.json").read_text())[path]
    predecessor = (CURRENT_RECEIPT / "abi402-predecessor" / Path(path).name).read_bytes()
    current = (UNIFIED_RECEIPT / "abi403-predecessor" / Path(path).name).read_bytes()
    assert hashlib.sha256(predecessor).hexdigest() == transition["predecessorSha256"]
    assert hashlib.sha256(current).hexdigest() == transition["currentSha256"]
    assert json.loads(predecessor)["abi_version"] == 402
    assert transition["currentAbi"] == 403
    assert json.loads(current) == dict(json.loads(predecessor), abi_version=403)


@pytest.mark.parametrize("path", TRANSITION)
def test_authentic_399_to_401_transition_is_preserved(path: str) -> None:
    historical = json.loads((HISTORICAL / "fixture-transition.json").read_text())[path]
    before = (HISTORICAL / "predecessor" / Path(path).name).read_bytes()
    after = (FROZEN_RECEIPT / "predecessor401" / Path(path).name).read_bytes()
    assert hashlib.sha256(before).hexdigest() == historical["predecessorSha256"]
    assert hashlib.sha256(after).hexdigest() == historical["currentSha256"]
    assert json.loads(after) == dict(json.loads(before), abi_version=401)


@pytest.mark.parametrize("path", TRANSITION)
def test_preserved_402_producer_and_only_version_changed(path: str) -> None:
    prior = (
        ROOT / "spec/performance/temporal-native-render-2026-11-07/predecessor402" / Path(path).name
    )
    before = prior.read_bytes()
    assert hashlib.sha256(before).hexdigest() == FROZEN_TRANSITION[path]["predecessor402Sha256"]
    assert json.loads((ROOT / path).read_bytes()) == dict(
        json.loads(before), abi_version=ABI_VERSION
    )


@pytest.mark.parametrize("path", TRANSITION)
def test_preserved_403_producer_and_only_version_changed(path: str) -> None:
    before = (
        ROOT / "spec/performance/temporal-worker-export-2026-11-07/predecessor403" / Path(path).name
    ).read_bytes()
    assert hashlib.sha256(before).hexdigest() == FROZEN_TRANSITION[path]["predecessor403Sha256"]
    assert json.loads((ROOT / path).read_bytes()) == dict(
        json.loads(before), abi_version=ABI_VERSION
    )


@pytest.mark.parametrize("path", TRANSITION)
def test_frozen_historical_401_to_404_transition(path: str) -> None:
    entry = FROZEN_TRANSITION[path]
    before = (FROZEN_RECEIPT / "predecessor401" / Path(path).name).read_bytes()
    after = (UNIFIED_RECEIPT / "abi404-predecessor" / Path(path).name).read_bytes()
    assert hashlib.sha256(before).hexdigest() == entry["predecessorSha256"]
    assert hashlib.sha256(after).hexdigest() == entry["currentSha256"]
    assert json.loads(before)["abi_version"] == 401
    assert json.loads(after) == dict(json.loads(before), abi_version=404)


@pytest.mark.parametrize("path", TRANSITION)
@pytest.mark.parametrize("predecessor_abi", [403, 404])
def test_both_complete_parent_fixtures_survive_combined_abi(
    path: str, predecessor_abi: int
) -> None:
    entry = json.loads((UNIFIED_RECEIPT / "fixture-transition.json").read_text())[path]
    before = (UNIFIED_RECEIPT / f"abi{predecessor_abi}-predecessor" / Path(path).name).read_bytes()
    after = (ROOT / path).read_bytes()
    assert (
        hashlib.sha256(before).hexdigest() == entry["predecessors"][str(predecessor_abi)]["sha256"]
    )
    assert hashlib.sha256(after).hexdigest() == entry["currentSha256"]
    assert json.loads(before)["abi_version"] == predecessor_abi
    assert entry["currentAbi"] == ABI_VERSION
    assert json.loads(after) == dict(json.loads(before), abi_version=ABI_VERSION)
