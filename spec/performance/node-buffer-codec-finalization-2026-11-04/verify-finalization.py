"""Verify the two authorized Buffer sync merges without executing frozen proofs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BUFFER = "eb9ea4c78a5acec192cd6fd98d9edb86fa3ae48c"
REPAIR = "562a2adfa97a6a3b5629d9ba5f98da564ba1e2b5"
PARENT = "7c581024f968519c074e990b4eb6a34ffe2fbd96"
MAIN = "2fbbe5f038032841bcb095a9e101421e25771496"
POINTER = "2568ac711d912625d54d083e38b29d51b415ad5c"
REPAIR_DIR = ROOT / "spec/performance/graph-node-first-paint-1k-review-repair-2026-11-04"
BUFFER_FILES = {
    "packages/xy-node/src/graphforge-container.js",
    "packages/xy-node/test/graphforge-container.test.mjs",
    "packages/xy-node/test/graphforge.test.mjs",
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return digest(path.read_bytes())


def tree(commit: str, path: str) -> dict[str, str]:
    result = {}
    for item in git("ls-tree", "-rz", commit, "--", path).split(b"\0"):
        if item:
            metadata, name = item.split(b"\t", 1)
            result[name.decode()] = metadata.decode().split()[2]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incoming", required=True, choices=(REPAIR, PARENT))
    parser.add_argument("--prior", required=True)
    parser.add_argument("--candidate")
    args = parser.parse_args()
    incoming, prior, candidate = args.incoming, args.prior, args.candidate
    if candidate:
        parents = git("show", "-s", "--format=%P", candidate).decode().strip().split()
        assert parents == [prior, incoming], parents
    else:
        assert git("rev-parse", "HEAD").decode().strip() == prior
        assert git("rev-parse", "MERGE_HEAD").decode().strip() == incoming
    assert git("rev-parse", f"{MAIN}^{{tree}}") == git("rev-parse", f"{POINTER}^{{tree}}")

    before, received = tree(prior, "spec/performance"), tree(incoming, "spec/performance")
    assert all(before[p] == received[p] for p in before.keys() & received.keys())
    protected = before | received
    if candidate:
        current = tree(candidate, "spec/performance")
    else:
        current = {}
        for item in git("ls-files", "--stage", "-z", "--", "spec/performance").split(b"\0"):
            if item:
                metadata, name = item.split(b"\t", 1)
                _, object_id, stage = metadata.decode().split()
                assert stage == "0", name
                current[name.decode()] = object_id
    assert all(current.get(p) == value for p, value in protected.items())
    assert git("diff", "--", "spec/performance", f":(exclude){OUT.relative_to(ROOT)}/**") == b""
    intermediate = json.loads((OUT / "intermediate-sha256.json").read_text())
    assert all(sha(ROOT / p) == value for p, value in intermediate.items())

    # Every product/build/test byte stays at the Buffer implementation tip.
    product_paths = ("packages", "crates", "js", "python", "scripts", "tests", ".github")
    endpoint = [candidate] if candidate else []
    assert git("diff", "--name-only", BUFFER, *endpoint, "--", *product_paths) == b""
    changed = (
        git("diff", "--name-only", incoming, *endpoint, "--", *product_paths).decode().splitlines()
    )
    assert set(changed) == BUFFER_FILES, changed
    for path in BUFFER_FILES:
        assert (ROOT / path).read_bytes() == git("show", f"{BUFFER}:{path}"), path

    # The six recorded maps include exact snapshots of preparatory helper versions.
    preservation = json.loads((REPAIR_DIR / "preservation.json").read_text())
    maps = preservation["captureSourceResolutions"]
    for source_map in maps.values():
        for identity in source_map.values():
            assert sha(ROOT / identity["resolvedSource"]) == identity["sha256"]
    artifacts = preservation["runtimeArtifactSha256"]
    for path, value in artifacts.items():
        assert sha(ROOT / path) == value, path
    inventory_path = "spec/releases/0.6.0-api-inventory.json"
    inventory = json.loads((ROOT / inventory_path).read_text())
    for tip in (BUFFER, incoming):
        previous = json.loads(git("show", f"{tip}:{inventory_path}"))
        assert set(previous) == set(inventory)
        changed_fields = {k for k in previous if previous[k] != inventory[k]}
        assert changed_fields <= {"sourceProvenance", "sourceSha256"}, changed_fields
    assert len(inventory["gaps"]) == 685
    histories = {}
    for prefix in (
        "graph-node-first-paint-1k-2026-11-04",
        "graph-node-first-paint-1k-parent-sync-2026-11-04",
        "graph-node-first-paint-1k-review-repair-2026-11-04",
        "graph-node-first-paint-1k-accepted-main-sync-2026-11-04",
        "node-buffer-codec-2026-11-04",
        "node-buffer-codec-parent-sync-2026-11-04",
    ):
        entries = {
            p: value
            for p, value in protected.items()
            if p.startswith(f"spec/performance/{prefix}/")
        }
        histories[prefix] = {
            "files": len(entries),
            "gitBlobManifestSha256": digest(json.dumps(entries, sort_keys=True).encode()),
        }
    print(
        json.dumps(
            {
                "bufferImplementation": BUFFER,
                "prior": prior,
                "incoming": incoming,
                "candidate": candidate,
                "normalParentsVerified": [prior, incoming],
                "acceptedMainTreeEqualsReviewedPointer": True,
                "allInheritedPerformanceFilesExact": len(protected),
                "allInheritedPerformanceManifestSha256": digest(
                    json.dumps(protected, sort_keys=True).encode()
                ),
                "protectedHistories": histories,
                "intermediateFilesSha256": intermediate,
                "bufferFilesSha256": {p: sha(ROOT / p) for p in sorted(BUFFER_FILES)},
                "productBuildTestTreesExactAtBufferTip": True,
                "productDifferencesFromIncoming": changed,
                "captureSourceMapsVerified": len(maps),
                "runtimeArtifactSha256": artifacts,
                "nodePackageTreeSourceIdenticalToCaptures": False,
                "proofRerun": False,
                "artifactScope": "Exact file bytes now; no new producer loading, rebuild, origin or mapped-memory attestation",
                "inventoryContractsClassificationGapsAcceptanceUnchanged": True,
                "gaps": 685,
                "reviewAndCI": "Parent reports incoming approval; combined candidate requires independent final review and new CI",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
