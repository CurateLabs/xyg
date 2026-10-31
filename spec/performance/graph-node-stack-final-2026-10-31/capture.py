"""Bind reviewed Node code, combined source, real assets and integration checks."""

import ctypes
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
node = "c1a277dfa094568697f42217cdd6fa65fd0f23b0"
s4 = "93cb8570e72d9d21cb48def6679728b10396e3cc"


def command(*argv: str) -> bytes:
    return subprocess.check_output(argv, cwd=root)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


names = command("git", "diff", "--name-only", s4).decode().splitlines()
sources = {
    name: sha((root / name).read_bytes())
    for name in sorted(names)
    if not name.startswith("spec/performance/") and (root / name).is_file()
}
historical = {}
for ref in (node, s4):
    for line in (
        command("git", "ls-tree", "-r", ref, "--", "spec/performance").decode().splitlines()
    ):
        metadata, name = line.split("\t", 1)
        expected = metadata.split()[2]
        assert name not in historical or historical[name] == expected, name
        historical[name] = expected
for name, expected in historical.items():
    data = (root / name).read_bytes()
    assert (
        hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == expected
    ), name

assert command("git", "diff", s4, "--", "crates", "spec/abi", "spec/wasm") == b""
assert (
    command(
        "git", "diff", node, "--", "packages/xy-node/src", "crates", "js", "spec/abi", "spec/wasm"
    )
    == b""
)
library = root / "target/release/libxyg_core.so"
native = ctypes.CDLL(str(library))
native.xyg_abi_version.restype = ctypes.c_uint32
assert native.xyg_abi_version() == 398
artifacts = ["target/release/libxyg_core.so"]
prior_assets = json.loads(
    (root / "spec/performance/graph-s4-ci-repair-2026-10-31/evidence.json").read_text()
)["artifacts"]
for name in (
    "index.js",
    "standalone.js",
    "wasm-worker.js",
    "xyg-wasm.wasm",
    "xyg-wasm-inline.js",
    "xyg-wasm.manifest.json",
):
    browser = f"packages/xy-client/dist/{name}"
    python = f"python/xyg/static/{name}"
    assert (root / browser).read_bytes() == (root / python).read_bytes(), name
    assert sha((root / browser).read_bytes()) == prior_assets[browser]["sha256"], name
    artifacts.extend([browser, python])
module = (root / "packages/xy-client/dist/xyg-wasm.wasm").read_bytes()
assert len(module) == 1860254
assert sha(module) == "27835ac2610b53ffb79af2a2db1510547fe8be334cad0eebf06b347986bd9099"
foundation_path = root / "spec/performance/graph-s4-ci-repair-2026-10-31/full-foundation.json"
commands = {p.name: json.loads(p.read_text()) for p in sorted(receipt.glob("*.command.json"))}
assert all(c["exitCode"] == 0 for c in commands.values()), commands
for c in commands.values():
    compressed = (receipt / c["log"]).read_bytes()
    raw = (receipt / f"{c['name']}.txt").read_bytes()
    assert gzip.decompress(compressed) == raw
    assert sha(compressed) == c["gzipSha256"] and sha(raw) == c["rawSha256"]
installed_log = (
    root / "spec/performance/graph-node-review-followup-2026-10-31/installed.txt"
).read_text()
install_roots = set(
    re.findall(
        re.escape(str(root)) + r"/target/task-tmp/node35-clean-install\.[A-Za-z0-9]+", installed_log
    )
)
assert len(install_roots) == 1, install_roots
install_root = Path(install_roots.pop())
installed_source = install_root / "consumer/node_modules/@curatelabs/xyg-node/src"
for name in (
    "graphforge.js",
    "graphforge_layout.js",
    "graphforge_layout_worker.js",
    "force_scheduler.js",
    "_abi_generated.js",
):
    assert (installed_source / name).read_bytes() == (
        root / "packages/xy-node/src" / name
    ).read_bytes()
installed_artifacts = [*install_root.glob("wheels/*.whl"), *install_root.glob("packs/*.tgz")]
assert len(installed_artifacts) == 5, installed_artifacts
patch = command("git", "diff", "--binary", "--full-index", s4, "--", ".", ":!spec/performance")
record = {
    "scope": "Final Node/S4 normal-merge verification; no release cohort/milestone acceptance",
    "artifactCommit": None,
    "reviewedNode": node,
    "reviewedS4": s4,
    "workingHead": command("git", "rev-parse", "HEAD").decode().strip(),
    "nonreceiptBinaryFullIndexDiffSha256": sha(patch),
    "sources": sources,
    "historicalFilesUnchanged": len(historical),
    "nativeAbi": 398,
    "artifacts": {
        name: {"bytes": (root / name).stat().st_size, "sha256": sha((root / name).read_bytes())}
        for name in artifacts
    },
    "commands": commands,
    "installedArtifacts": {
        str(p.relative_to(root)): {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
        for p in installed_artifacts
    },
    "outputs": {
        p.name: sha(p.read_bytes())
        for p in sorted(receipt.iterdir())
        if p.suffix in {".png", ".bin"}
        or p.name in {"result.json", "initial-spec.json", "final-spec.json"}
    },
    "reusedInstalledAndJourney": {
        "path": "spec/performance/graph-node-review-followup-2026-10-31/evidence.json",
        "sha256": sha(
            (
                root / "spec/performance/graph-node-review-followup-2026-10-31/evidence.json"
            ).read_bytes()
        ),
        "basis": "No product/native/client/WASM source changes relative to reviewed Node follow-up; installed sources and all paired production assets reverified here",
    },
    "reusedFullFoundation": {
        "path": str(foundation_path.relative_to(root)),
        "sha256": sha(foundation_path.read_bytes()),
        "basis": "Rust and all paired production assets match S4 CI repair; full strict-CSP foundation reused by exact hashes; fresh native Node paint/pick/pan proof retained here",
    },
}
(receipt / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
print(
    json.dumps(
        {"sources": len(sources), "historicalFiles": len(historical), "commands": len(commands)}
    )
)
