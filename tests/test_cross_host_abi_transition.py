"""Pin the ABI-only refresh while retaining complete predecessor packet evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from xyg._abi_generated import ABI_VERSION

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "spec/performance/pr1110-abi-fixtures-2026-11-07"
RECEIPT = ROOT / "spec/performance/temporal-graph-freeze-2026-11-07"
TRANSITION = json.loads(
    (
        ROOT / "spec/performance/temporal-worker-export-2026-11-07/fixture-transition.json"
    ).read_text()
)


def assert_abi_only_refresh(current: dict, predecessor: dict) -> None:
    assert current["abi_version"] == ABI_VERSION
    assert predecessor["abi_version"] == 401
    expected = dict(predecessor, abi_version=ABI_VERSION)
    assert current == expected  # Every field, including complete packets and hashes.


@pytest.mark.parametrize("path", TRANSITION)
def test_complete_fixture_transition(path: str) -> None:
    entry = TRANSITION[path]
    current = (ROOT / path).read_bytes()
    predecessor = (RECEIPT / "predecessor401" / Path(path).name).read_bytes()
    assert hashlib.sha256(current).hexdigest() == entry["currentSha256"]
    assert hashlib.sha256(predecessor).hexdigest() == entry["predecessorSha256"]
    assert_abi_only_refresh(json.loads(current), json.loads(predecessor))


@pytest.mark.parametrize("path", TRANSITION)
@pytest.mark.parametrize("wrong_abi", [399, 400, 401, ABI_VERSION + 1])
def test_stale_and_wrong_versions_are_rejected(path: str, wrong_abi: int) -> None:
    current = json.loads((ROOT / path).read_bytes())
    predecessor = json.loads((RECEIPT / "predecessor401" / Path(path).name).read_bytes())
    current["abi_version"] = wrong_abi
    with pytest.raises(AssertionError):
        assert_abi_only_refresh(current, predecessor)


@pytest.mark.parametrize("path", TRANSITION)
def test_product_packet_drift_is_rejected(path: str) -> None:
    current = json.loads((ROOT / path).read_bytes())
    predecessor = json.loads((RECEIPT / "predecessor401" / Path(path).name).read_bytes())
    changed = copy.deepcopy(current)
    # Removing a complete product case must fail even with the correct current ABI.
    changed["cases"].pop()
    with pytest.raises(AssertionError):
        assert_abi_only_refresh(changed, predecessor)


def test_geo_packet_bit_drift_is_rejected_with_consistent_digest() -> None:
    path = "tests/fixtures/geo_cross_host.json"
    current = json.loads((ROOT / path).read_bytes())
    predecessor = json.loads((RECEIPT / "predecessor401" / Path(path).name).read_bytes())
    case = current["cases"][0]
    packet = bytearray.fromhex(case["metadata_hex"])
    packet[-1] ^= 1
    case["metadata_hex"] = packet.hex()
    case["metadata_sha256"] = hashlib.sha256(packet).hexdigest()
    with pytest.raises(AssertionError):
        assert_abi_only_refresh(current, predecessor)


@pytest.mark.parametrize("path", TRANSITION)
def test_authentic_399_to_401_transition_is_preserved(path: str) -> None:
    historical = json.loads((HISTORICAL / "fixture-transition.json").read_text())[path]
    before = (HISTORICAL / "predecessor" / Path(path).name).read_bytes()
    after = (RECEIPT / "predecessor401" / Path(path).name).read_bytes()
    assert hashlib.sha256(before).hexdigest() == historical["predecessorSha256"]
    assert hashlib.sha256(after).hexdigest() == historical["currentSha256"]
    assert json.loads(after) == dict(json.loads(before), abi_version=401)


@pytest.mark.parametrize("path", TRANSITION)
def test_preserved_402_producer_and_only_version_changed(path: str) -> None:
    prior = (
        ROOT / "spec/performance/temporal-native-render-2026-11-07/predecessor402" / Path(path).name
    )
    before = prior.read_bytes()
    assert hashlib.sha256(before).hexdigest() == TRANSITION[path]["predecessor402Sha256"]
    assert json.loads((ROOT / path).read_bytes()) == dict(
        json.loads(before), abi_version=ABI_VERSION
    )


@pytest.mark.parametrize("path", TRANSITION)
def test_preserved_403_producer_and_only_version_changed(path: str) -> None:
    before = (
        ROOT / "spec/performance/temporal-worker-export-2026-11-07/predecessor403" / Path(path).name
    ).read_bytes()
    assert hashlib.sha256(before).hexdigest() == TRANSITION[path]["predecessor403Sha256"]
    assert json.loads((ROOT / path).read_bytes()) == dict(
        json.loads(before), abi_version=ABI_VERSION
    )
