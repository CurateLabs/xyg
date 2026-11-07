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
CURRENT_RECEIPT = ROOT / "spec/temporal/evidence/46-abi402"
TRANSITION = json.loads((RECEIPT / "fixture-transition.json").read_text())


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
    current = (ROOT / path).read_bytes()
    assert hashlib.sha256(predecessor).hexdigest() == transition["predecessorSha256"]
    assert hashlib.sha256(current).hexdigest() == transition["currentSha256"]
    assert json.loads(predecessor)["abi_version"] == 401
    assert json.loads(current) == dict(json.loads(predecessor), abi_version=ABI_VERSION)
