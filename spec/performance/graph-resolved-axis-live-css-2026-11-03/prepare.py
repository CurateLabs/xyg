"""Copy pinned producer artifacts only after verifying committed source identity."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
BASE = "e768ce25194bf3ebcc1a0de1df37696da3948295"
DONOR = Path("/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836")
HISTORY = ROOT / "spec/performance/graph-resolved-scene-integration-2026-11-03"


def sha(data):
    return hashlib.sha256(data).hexdigest()


files = (
    subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            BASE,
            "crates",
            "Cargo.toml",
            "Cargo.lock",
            "rust-toolchain.toml",
        ]
    )
    .decode()
    .splitlines()
)
identities = {}
for name in files:
    committed = subprocess.check_output(["git", "show", f"{BASE}:{name}"])
    assert (ROOT / name).read_bytes() == committed
    # The original producer receipt records these immutable artifact hashes;
    # donor source must still match the exact base, including uncommitted files.
    assert (DONOR / name).read_bytes() == committed, name
    identities[name] = sha(committed)
artifacts = {}
expected = json.loads((HISTORY / "evidence.json").read_text())["artifacts"]
for name in [
    "target/release/libxyg_core.so",
    *[str(p.relative_to(DONOR)) for p in (DONOR / "packages/xy-client/dist").glob("xyg-wasm*")],
]:
    assert name in expected, name
    data = (DONOR / name).read_bytes()
    assert sha(data) == expected[name]["sha256"], name
    dest = ROOT / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    artifacts[name] = {"source": str(DONOR / name), "sha256": sha(data), "bytes": len(data)}
    if name.startswith("packages/"):
        dest = ROOT / "python/xyg/static" / Path(name).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
baseline = "target/task-tmp/resolved-spine-188f-baseline/packages/xy-client/dist/index.js"
dest = ROOT / baseline
dest.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(DONOR / baseline, dest)
assert sha(dest.read_bytes()) == "351fa5038800204a13a99ae9cb91612472e3368f6d7ecd4829d589e39b16acd7"
if not (ROOT / "node_modules").exists():
    (ROOT / "node_modules").symlink_to(DONOR / "node_modules", target_is_directory=True)
(ROOT / "target/task-tmp").mkdir(parents=True, exist_ok=True)
(OUT / "reused-producers.json").write_text(
    json.dumps(
        {
            "base": BASE,
            "donorHead": subprocess.check_output(["git", "-C", str(DONOR), "rev-parse", "HEAD"])
            .decode()
            .strip(),
            "sourceIdentity": identities,
            "artifacts": artifacts,
            "artifactCommit": None,
            "historicalReceipt": str(HISTORY.relative_to(ROOT) / "evidence.json"),
            "historicalReceiptSha256": sha((HISTORY / "evidence.json").read_bytes()),
        },
        indent=2,
    )
    + "\n"
)
print(
    f"PASS: {len(identities)} exact native/WASM source files; pinned artifacts copied without rebuild"
)
