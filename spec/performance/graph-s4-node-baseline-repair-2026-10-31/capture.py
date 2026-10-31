"""Bind test-only sources and immutable before/after evidence without builds."""

import ctypes
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
base = "7c02d3df0e769e945ae171f90906f9b17acfc65f"
prior = "80af7df777562605b7ce0bea240c3538a7ebfca7"
prior_root = root.parent / "t3-880cb106"
sources = [
    "packages/xy-node/test/geo-live-hierarchy-fixture.mjs",
    "packages/xy-node/test/geo-live-hierarchy-host.test.mjs",
    "packages/xy-node/test/geom.test.mjs",
]
compared = [
    *sources,
    "packages/xy-node/test/geo-live-host-fixture.mjs",
    "packages/xy-node/test/geoscale-fixture.mjs",
    "packages/xy-node/src/scene.js",
    "packages/xy-node/src/encode.js",
    "packages/xy-node/src/geo-hierarchy.js",
    "packages/xy-node/src/geo-hierarchy-wire.js",
    "packages/xy-node/src/geo-selected.js",
    "python/xyg/_scene_observations.py",
    "crates/xyg-engine/src/kernels.rs",
]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=root)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def artifact(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


assert git("rev-parse", "HEAD").decode().strip() == base
before_sources = {}
for name in compared:
    old = git("show", f"{prior}:{name}")
    assert old == git("show", f"{base}:{name}"), name
    before_sources[name] = sha(old)

changed = git("diff", "--name-only", base).decode().splitlines()
changed = [name for name in changed if not name.startswith(str(receipt.relative_to(root)) + "/")]
assert set(changed) == set(sources), changed
patch = git("diff", "--binary", "--full-index", base, "--", *sources)
(receipt / "test-source.patch").write_bytes(patch)

old_library = prior_root / "target/release/libxyg_core.so"
assert sha(old_library.read_bytes()) == (
    "cef2c70e0d1e0e2f5d26ab8e7e0b5b3a519abe324d549bd56c5a39eafa3fa0ea"
)
old_receipt = prior_root / "spec/performance/graph-s3-review-repair-2026-10-31/results.json"
assert json.loads(old_receipt.read_text())["builtArtifacts"][
    "target/release/libxyg_core.so"
] == sha(old_library.read_bytes())
library = root / "target/release/libxyg_core.so"
native = ctypes.CDLL(str(library))
native.xyg_abi_version.restype = ctypes.c_uint32
assert native.xyg_abi_version() == 398
old_native = ctypes.CDLL(str(old_library))
old_native.xyg_abi_version.restype = ctypes.c_uint32
assert old_native.xyg_abi_version() == 396

commands = {}
for path in sorted(receipt.glob("*.command.json")):
    record = json.loads(path.read_text())
    packed = (receipt / record["log"]).read_bytes()
    raw = gzip.decompress(packed)
    assert sha(packed) == record["gzipSha256"], path
    assert sha(raw) == record["rawSha256"], path
    assert (receipt / record["log"].removesuffix(".gz")).read_bytes() == raw, path
    commands[path.name] = record

full = (receipt / "full-node.txt").read_text()
assert "# pass 1493\n# fail 0\n# cancelled 0\n# skipped 2" in full
assert commands["focused-pass.command.json"]["exitCode"] == 0
assert (
    "# pass 212\n# fail 0\n# cancelled 0\n# skipped 0" in (receipt / "focused-pass.txt").read_text()
)
assert "# pass 4\n# fail 4\n# cancelled 10" in (receipt / "pre-s4-hierarchy.txt").read_text()

original_log = "spec/performance/graph-s4-ci-repair-2026-10-31/full-node.txt.gz"
assert (root / original_log).read_bytes() == git("show", f"{base}:{original_log}")
node = root.parent / "t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin/node"
evidence = {
    "base": base,
    "artifactCommit": None,
    "scope": "Three test-only files; no production changes or new builds",
    "testBinaryFullIndexDiffSha256": sha(patch),
    "sourceHashes": {name: sha((root / name).read_bytes()) for name in sources},
    "before": {
        "commit": prior,
        "nativeAbi": 396,
        "native": artifact(old_library),
        "originalReceipt": artifact(old_receipt),
        "twelveFilesByteIdenticalToRepairBase": before_sources,
        "oldBroadFailureLog": artifact(root / original_log),
    },
    "current": {
        "nativeAbi": 398,
        "native": artifact(library),
        "node": artifact(node),
        "nodeVersion": subprocess.check_output([str(node), "--version"], text=True).strip(),
        "unchangedProductHashes": {
            name: sha((root / name).read_bytes()) for name in compared if name not in sources
        },
    },
    "results": {"focusedPass": 212, "fullPass": 1493, "fullFail": 0, "fullCancelled": 0},
    "existingSkips": [line for line in full.splitlines() if "# SKIP" in line],
    "commands": commands,
}
(receipt / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
print(json.dumps({"sourceFiles": len(sources), "unchangedBeforeFiles": len(before_sources)}))
