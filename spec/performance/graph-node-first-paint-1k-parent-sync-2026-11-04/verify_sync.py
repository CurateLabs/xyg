#!/usr/bin/env python3
"""Verify metadata-only sync, complete parent history and exact proof/artifact reuse."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
OLD = "7195d070843d507757213e7816862072eed9f39b"
PARENT = "2568ac711d912625d54d083e38b29d51b415ad5c"
PROOF = "spec/performance/graph-node-first-paint-1k-2026-11-04/"
INVENTORY = "spec/releases/0.6.0-api-inventory.json"
INCOMING = {"spec/design/browser-wasm.md", "spec/design/graph-interaction.md"}
RETAINED = {
    "spec/design/host-parity.md",
    "spec/design/dual-host-parity-matrix.md",
    "spec/design/graphforge-node-scheduling.md",
    "spec/design/graph-mark.md",
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def contents(path: str, mode: str) -> bytes:
    file = ROOT / path
    return os.readlink(file).encode() if mode == "120000" else file.read_bytes()


def main() -> None:
    baseline = json.loads((OUT / "before-sync.json").read_text())
    inventory = json.loads((ROOT / INVENTORY).read_text())
    inventory_changes = {}
    for revision in (OLD, PARENT):
        prior = json.loads(git("show", f"{revision}:{INVENTORY}"))
        changed = [key for key in inventory if prior.get(key) != inventory[key]]
        assert set(changed) <= {"sourceProvenance", "sourceSha256"}, changed
        assert set(prior) == set(inventory)
        assert len(inventory["gaps"]) == 685
        assert inventory["contracts"] == prior["contracts"]
        assert inventory["acceptance"] == prior["acceptance"]
        assert inventory["contractSha256"] == prior["contractSha256"]
        inventory_changes[revision] = {
            "changedTopLevelFields": changed,
            "changedSourceHashes": [
                path
                for path, sha in inventory["sourceSha256"].items()
                if prior["sourceSha256"].get(path) != sha
            ],
            "sourceProvenanceBefore": prior["sourceProvenance"],
            "sourceProvenanceAfter": inventory["sourceProvenance"],
        }
    manifests: dict[str, dict] = {}
    cache: dict[str, str] = {}
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert process.stdin and process.stdout
    try:
        for revision in (OLD, PARENT):
            records = {}
            for record in git("ls-tree", "-r", "-z", revision).split(b"\0"):
                if not record:
                    continue
                header, encoded_path = record.split(b"\t", 1)
                mode, kind, oid = header.decode().split()
                path = encoded_path.decode()
                assert kind == "blob", (path, kind)
                if oid not in cache:
                    process.stdin.write(oid.encode() + b"\n")
                    process.stdin.flush()
                    reply = process.stdout.readline().decode().split()
                    size = int(reply[2])
                    data = process.stdout.read(size)
                    assert len(data) == size
                    assert process.stdout.read(1) == b"\n"
                    cache[oid] = digest(data)
                actual = digest(contents(path, mode))
                expected = cache[oid]
                if revision == OLD and path in INCOMING:
                    expected = digest(git("show", f"{PARENT}:{path}"))
                if revision == PARENT and path in RETAINED:
                    expected = manifests[OLD][path]["sha256"]
                assert actual == expected or path == INVENTORY, (revision, path)
                records[path] = {
                    "mode": mode,
                    "gitBlob": oid,
                    "sha256": cache[oid],
                    "currentSha256": actual,
                    "identical": actual == cache[oid],
                }
            manifests[revision] = records
    finally:
        process.stdin.close()
        process.wait(timeout=10)
    assert process.returncode == 0
    for revision, records in manifests.items():
        for path, record in records.items():
            if path.startswith("spec/performance/"):
                assert record["identical"], (revision, path)
        for path in ("spec/api/capability-matrix.md", "docs/styling/capabilities.md"):
            assert records[path]["identical"]
    proof_files = {
        path: record for path, record in manifests[OLD].items() if path.startswith(PROOF)
    }
    assert all(record["identical"] for record in proof_files.values())
    for path, sha in baseline["runtimeArtifactSha256"].items():
        assert digest((ROOT / path).read_bytes()) == sha, path
    raw = json.loads((ROOT / PROOF / Path("raw/unheld/result.json")).read_text())
    for path, sha in raw["sourceHashes"].items():
        assert digest((ROOT / path).read_bytes()) == sha, path
    for record in ("raw/unheld/result.json", "raw/held/result.json"):
        assert manifests[OLD][PROOF + record]["identical"]
    result = {
        "candidateBefore": OLD,
        "intendedPrBase": PARENT,
        "acceptedMain": baseline["acceptedMain"],
        "metadataChanges": inventory_changes,
        "unchangedContractsClassificationAcceptanceAndGaps": True,
        "gaps": 685,
        "proofFilesPreserved": len(proof_files),
        "runtimeArtifactSha256": baseline["runtimeArtifactSha256"],
        "proofIdentityReuseOnly": True,
        "browserOrNativeBuildOrMeasurementRerun": False,
        "proofClockBases": raw["protocol"]["clocks"],
        "timingsUnchanged": raw["timings"],
        "scope": "Metadata-only parent sync. Existing partial 1k evidence and limits unchanged; no performance acceptance.",
    }
    (OUT / "preservation.json").write_text(json.dumps(result, indent=2) + "\n")
    (OUT / "complete-parent-file-identities.json").write_text(
        json.dumps(manifests, indent=2) + "\n"
    )
    print(
        f"PASS: complete identities for {len(manifests[OLD])} old-candidate and "
        f"{len(manifests[PARENT])} parent files; {len(proof_files)} proof files and "
        f"{len(baseline['runtimeArtifactSha256'])} runtime artifacts exact; 685 gaps unchanged."
    )


if __name__ == "__main__":
    main()
