#!/usr/bin/env python3
"""Verify the accepted-main sync without rerunning or modifying frozen proofs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
REPAIR = "562a2adfa97a6a3b5629d9ba5f98da564ba1e2b5"
MAIN = "2fbbe5f038032841bcb095a9e101421e25771496"
POINTER = "2568ac711d912625d54d083e38b29d51b415ad5c"
PREFIX = "spec/performance/graph-node-first-paint-1k"
REPAIR_DIR = ROOT / f"{PREFIX}-review-repair-2026-11-04"
INVENTORY = "spec/releases/0.6.0-api-inventory.json"
DOC = "spec/design/graphforge-node-scheduling.md"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    assert git("rev-parse", f"{MAIN}^{{tree}}") == git("rev-parse", f"{POINTER}^{{tree}}")
    # Whole tracked tree: the only permitted existing-file changes are these
    # current documentation/provenance bytes. This includes build inputs,
    # contracts, all historical receipts, every test and every runtime helper.
    changed = git("diff", "--name-only", REPAIR).decode().splitlines()
    prefix = str(OUT.relative_to(ROOT)) + "/"
    assert all(p in {DOC, INVENTORY} or p.startswith(prefix) for p in changed), changed
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    assert all(p.startswith(prefix) for p in untracked), untracked
    protected = {}
    for item in git("ls-tree", "-rz", REPAIR).split(b"\0"):
        if not item:
            continue
        metadata, raw_path = item.split(b"\t", 1)
        path = raw_path.decode()
        if path.startswith(PREFIX):
            data = git("cat-file", "blob", metadata.decode().split()[2])
            digest = hashlib.sha256(data).hexdigest()
            assert sha(ROOT / path) == digest, path
            protected[path] = digest
    historical_count = len(protected)
    assert historical_count == 361, historical_count
    before = json.loads(git("show", f"{REPAIR}:{INVENTORY}"))
    current = json.loads((ROOT / INVENTORY).read_text())
    fields = sorted(k for k in before if before[k] != current[k])
    assert set(before) == set(current)
    assert set(fields) <= {"sourceProvenance", "sourceSha256"}, fields
    assert len(current["gaps"]) == 685
    artifact_paths = json.loads(
        (ROOT / f"{PREFIX}-parent-sync-2026-11-04/before-sync.json").read_text()
    )["runtimeArtifactSha256"]
    for path, digest in artifact_paths.items():
        assert sha(ROOT / path) == digest, path
    # Recheck every previously resolved capture source, including snapshots of
    # preparatory versions. Do not execute the frozen output-writing verifier.
    preservation = json.loads((REPAIR_DIR / "preservation.json").read_text())
    resolutions = preservation["captureSourceResolutions"]
    for source_map in resolutions.values():
        for identity in source_map.values():
            assert sha(ROOT / identity["resolvedSource"]) == identity["sha256"]
    capture_facts = {}
    for mode in ("unheld", "held"):
        path = REPAIR_DIR / f"raw/{mode}/result.json"
        record = json.loads(path.read_text())
        capture_facts[mode] = {
            "resultSha256": sha(path),
            "sourceBase": record["sourceBase"],
            "status": record["status"],
            "meaning": "Unmodified historical runtime observation; not rerun in this sync.",
        }
    histories = {}
    for commit in (REPAIR, MAIN, POINTER, "7195d070843d507757213e7816862072eed9f39b"):
        history = git("rev-list", commit)
        histories[commit] = {
            "commitTreeParents": git("show", "-s", "--format=%H %T %P", commit).decode().strip(),
            "reachableCommits": len(history.splitlines()),
            "revListSha256": hashlib.sha256(history).hexdigest(),
        }
    result = {
        "repairParent": REPAIR,
        "acceptedMainParent": MAIN,
        "acceptedMainEqualsReviewedPointerTree": git("rev-parse", f"{MAIN}^{{tree}}")
        .decode()
        .strip(),
        "histories": histories,
        "historicalFileCount": historical_count,
        "historicalFileSha256": protected,
        "existingChangedPaths": [p for p in changed if not p.startswith(prefix)],
        "wholeTrackedTreeProtectedExcept": [DOC, INVENTORY],
        "inventoryChangedFields": fields,
        "inventorySourceHashChanges": sorted(
            p
            for p, digest in current["sourceSha256"].items()
            if before["sourceSha256"].get(p) != digest
        ),
        "gaps": 685,
        "contractsClassificationsAcceptanceUnchanged": True,
        "runtimeArtifactSha256": artifact_paths,
        "artifactScope": "File bytes checked now; no fresh 1k producer selection attestation or build-origin proof. Focused test-only loader cases are separate.",
        "captureSourceMapsVerified": len(resolutions),
        "captureFacts": capture_facts,
        "observationManifestSha256": sha(REPAIR_DIR / "observations.json"),
        "productionChanged": False,
    }
    # Stdout allows capture.py to retain each check separately without writing
    # into prior immutable receipts or overwriting an earlier result.
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
