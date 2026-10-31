"""Prepare parent-source regressions without changing the working source."""

import io
import subprocess
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[3]
base = "dee3ea37540a7126c3082ae59624bb02881bb00f"
output = root / "target/task-tmp/before"
if output.exists():
    raise SystemExit("Use a fresh checkout or remove only this diagnostic scratch directory first")
output.mkdir(parents=True)
archive = subprocess.check_output(
    ["git", "archive", base, "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo", "crates"],
    cwd=root,
)
with tarfile.open(fileobj=io.BytesIO(archive)) as packed:
    packed.extractall(output, filter="data")
(output / "spec").symlink_to(root / "spec", target_is_directory=True)
relative = Path("crates/xyg-engine/src/graphforge/interaction/tests/wire.rs")
current = (root / relative).read_text()
regressions = []
for name in (
    "review_live_owner_stamp_rebind_unbind_and_cross_owner_interleaving",
    "review_style_publication_distinguishes_classes",
):
    start = current.index(f"#[test]\nfn {name}")
    end = current.find("\n#[test]", start + 10)
    regressions.append(current[start : None if end == -1 else end])
with (output / relative).open("a") as target:
    target.write("\n" + "\n".join(regressions))
print(output)
