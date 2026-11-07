"""Save the exact non-receipt candidate patch and its input hashes once."""

import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
output = Path(__file__).resolve().parent
prefix = str(output.relative_to(root)) + "/"
tracked = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], text=True).splitlines()
untracked = subprocess.check_output(
    ["git", "ls-files", "--others", "--exclude-standard"], text=True
).splitlines()
paths = sorted(
    p
    for p in set(tracked + untracked)
    if not p.startswith(prefix)
    and not p.startswith("spec/performance/graph-picked-target-checkpoint-2026-11-04/")
)
patch = subprocess.check_output(
    ["git", "diff", "--binary", "HEAD", "--", *[p for p in paths if p in tracked]]
)
for path in paths:
    if path in untracked:
        result = subprocess.run(
            ["git", "diff", "--no-index", "--binary", "/dev/null", path],
            capture_output=True,
            check=False,
        )
        if result.returncode != 1:
            raise RuntimeError(result.stderr.decode())
        patch += result.stdout
inputs = sorted(
    set(
        paths
        + [
            "Cargo.toml",
            "Cargo.lock",
            ".cargo/config.toml",
            "rust-toolchain.toml",
            "package.json",
            "package-lock.json",
            "js/build.mjs",
            "js/package-wasm.mjs",
            "js/optimize-wasm.mjs",
            "spec/wasm/abi.json",
            "spec/abi/xyg-abi.json",
        ]
    )
)
manifest = {
    "base": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "nonreceipt_patch_sha256": hashlib.sha256(patch).hexdigest(),
    "changed_paths": paths,
    "input_sha256": {
        p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in inputs if Path(p).is_file()
    },
    "note": "Candidate uncommitted; patch includes new Rust test and design contracts. No receipt files are included in this patch hash.",
}
with (output / "full-nonreceipt.patch").open("xb") as stream:
    stream.write(patch)
with (output / "source-inputs.json").open("x") as stream:
    json.dump(manifest, stream, indent=2)
    stream.write("\n")
print(json.dumps(manifest, indent=2))
