"""Verify the normal accepted-main merge without executing immutable proofs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PRIOR = "6e240f4bd3189640779fd684e97072923cbfb9c8"
MAIN = "3ebf70c3aa5a351aeec3843da14ba2aa197b469e"
REVIEWED = "7c581024f968519c074e990b4eb6a34ffe2fbd96"
BUFFER = "eb9ea4c78a5acec192cd6fd98d9edb86fa3ae48c"
DOC = "spec/design/graphforge-node-scheduling.md"
INVENTORY = "spec/releases/0.6.0-api-inventory.json"
REPAIR = ROOT / "spec/performance/graph-node-first-paint-1k-review-repair-2026-11-04"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return digest(path.read_bytes())


def tree(commit: str, path: str) -> dict[str, str]:
    entries = {}
    for item in git("ls-tree", "-rz", commit, "--", path).split(b"\0"):
        if item:
            metadata, name = item.split(b"\t", 1)
            entries[name.decode()] = metadata.decode().split()[2]
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    args = parser.parse_args()
    endpoint = [args.candidate] if args.candidate else []
    if args.candidate:
        assert git("show", "-s", "--format=%P", args.candidate).decode().split() == [PRIOR, MAIN]
    else:
        assert git("rev-parse", "HEAD").decode().strip() == PRIOR
        assert git("rev-parse", "MERGE_HEAD").decode().strip() == MAIN
    expected_tree = "9087e452eea598c7c38976f8442b4a53c74de59d"
    assert git("rev-parse", f"{MAIN}^{{tree}}").decode().strip() == expected_tree
    assert git("rev-parse", f"{REVIEWED}^{{tree}}").decode().strip() == expected_tree
    prefix = OUT.relative_to(ROOT).as_posix() + "/"
    changed = git("diff", "--name-only", PRIOR, *endpoint).decode().splitlines()
    assert all(p in {DOC, INVENTORY} or p.startswith(prefix) for p in changed), changed
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    assert all(p.startswith(prefix) for p in untracked), untracked
    assert git("diff", "--name-only", BUFFER, *endpoint, "--", ".", ":(exclude)spec/**") == b""

    prior, incoming = tree(PRIOR, "spec/performance"), tree(MAIN, "spec/performance")
    assert all(prior[p] == incoming[p] for p in prior.keys() & incoming.keys())
    protected = prior | incoming
    if args.candidate:
        current = tree(args.candidate, "spec/performance")
    else:
        current = {}
        for item in git("ls-files", "--stage", "-z", "--", "spec/performance").split(b"\0"):
            if item:
                metadata, name = item.split(b"\t", 1)
                _, object_id, stage = metadata.decode().split()
                assert stage == "0", name
                current[name.decode()] = object_id
    assert all(current.get(p) == value for p, value in protected.items())
    assert git("diff", "--", "spec/performance", f":(exclude){prefix}**") == b""
    histories = {}
    for name in (
        "graph-node-first-paint-1k-2026-11-04",
        "graph-node-first-paint-1k-parent-sync-2026-11-04",
        "graph-node-first-paint-1k-review-repair-2026-11-04",
        "graph-node-first-paint-1k-accepted-main-sync-2026-11-04",
        "node-buffer-codec-2026-11-04",
        "node-buffer-codec-parent-sync-2026-11-04",
        "node-buffer-codec-finalization-2026-11-04",
    ):
        entries = {
            p: value for p, value in protected.items() if p.startswith(f"spec/performance/{name}/")
        }
        histories[name] = {
            "files": len(entries),
            "gitBlobManifestSha256": digest(json.dumps(entries, sort_keys=True).encode()),
        }

    finalization = ROOT / "spec/performance/node-buffer-codec-finalization-2026-11-04"
    intermediate = json.loads((finalization / "intermediate-sha256.json").read_text())
    assert all(sha(ROOT / p) == value for p, value in intermediate.items())
    preservation = json.loads((REPAIR / "preservation.json").read_text())
    maps = preservation["captureSourceResolutions"]
    for source_map in maps.values():
        for identity in source_map.values():
            assert sha(ROOT / identity["resolvedSource"]) == identity["sha256"]
    artifacts = preservation["runtimeArtifactSha256"]
    for path, value in artifacts.items():
        assert sha(ROOT / path) == value, path
    inventory = json.loads((ROOT / INVENTORY).read_text())
    before = json.loads(git("show", f"{PRIOR}:{INVENTORY}"))
    assert set(before) == set(inventory)
    inventory_changes = sorted(k for k in before if before[k] != inventory[k])
    assert set(inventory_changes) <= {"sourceProvenance", "sourceSha256"}, inventory_changes
    assert len(inventory["gaps"]) == 685
    buffer_files = [
        "packages/xy-node/src/graphforge-container.js",
        "packages/xy-node/test/graphforge-container.test.mjs",
        "packages/xy-node/test/graphforge.test.mjs",
    ]
    assert all((ROOT / p).read_bytes() == git("show", f"{BUFFER}:{p}") for p in buffer_files)
    lineage = {
        tip: git("show", "-s", "--format=%H %T %P", tip).decode().strip()
        for tip in (PRIOR, MAIN, REVIEWED, BUFFER, "a7ae010fdf5f38fca2f9b8bba8ef4070139e2b39")
    }
    print(
        json.dumps(
            {
                "prior": PRIOR,
                "acceptedMain": MAIN,
                "candidate": args.candidate,
                "normalParents": [PRIOR, MAIN],
                "reviewedTip": REVIEWED,
                "mainEqualsReviewedTree": expected_tree,
                "lineage": lineage,
                "protectedPerformanceFilesExact": len(protected),
                "protectedPerformanceGitBlobManifestSha256": digest(
                    json.dumps(protected, sort_keys=True).encode()
                ),
                "protectedHistories": histories,
                "allTrackedBytesOutsideSpecEqualApprovedBuffer": True,
                "bufferFilesSha256": {p: sha(ROOT / p) for p in buffer_files},
                "captureSourceMapsExact": len(maps),
                "runtimeArtifactSha256": artifacts,
                "intermediate20FilesSha256Exact": True,
                "inventoryChangedFields": inventory_changes,
                "inventorySourceHashChanges": sorted(
                    p
                    for p, value in inventory["sourceSha256"].items()
                    if before["sourceSha256"].get(p) != value
                ),
                "inventoryContractsClassificationGapsAcceptanceUnchanged": True,
                "gaps": 685,
                "existingChangedPaths": [p for p in changed if not p.startswith(prefix)],
                "proofRerun": False,
                "wholeNodePackageIdenticalToHistoricalCapture": False,
                "artifactClaim": "Exact file bytes only; no new runtime loading, native origin, build or mapped-memory attestation",
                "rustChildImported": False,
                "finalReviewAndNewCIRequiredBeforePushOrQueue": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
