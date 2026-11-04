"""Record canonical staged source diff and actual local artifact identities."""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import subprocess
from pathlib import Path

root = Path.cwd()
out = Path(__file__).resolve().parent
base = "188f7450bff332e0be6a80bf97b15b86e74b48ae"
paths = [
    "js/src/48_wasm_scene.ts",
    "js/src/50_chartview.ts",
    "spec/design/browser-wasm.md",
    "tests/browser/resolved_axis_spines.mjs",
    "tests/browser/resolved_axis_slots.mjs",
    "tests/browser/resolved_axis_precision.mjs",
]
argv = ["git", "diff", "--cached", "--binary", "--full-index", base, "--", *paths]
diff = subprocess.check_output(argv)
assert diff
(out / "source.diff.gz").write_bytes(gzip.compress(diff, mtime=0))
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
artifacts = {}
for directory in ("packages/xy-client/dist", "python/xyg/static"):
    for p in sorted((root / directory).iterdir()):
        if p.is_file() and p.suffix in (".js", ".wasm", ".json"):
            artifacts[str(p.relative_to(root))] = {
                "bytes": p.stat().st_size,
                "sha256": sha(p.read_bytes()),
            }
for name in ("target/release/libxyg_core.so", "packages/xyg-node-linux-x64/libxyg_core.so"):
    p = root / name
    artifacts[name] = {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
value = {
    "base": base,
    "worktree": str(root),
    "branch": subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(),
    "source_diff_argv": argv,
    "source_diff_sha256": sha(diff),
    "source_diff_excludes_receipts": True,
    "source_files": {name: sha((root / name).read_bytes()) for name in paths},
    "actual_artifacts": artifacts,
    "native_wasm_rebuilt": False,
    "python": platform.python_version(),
    "node": subprocess.check_output(["node", "--version"], text=True).strip(),
    "chromium": json.loads((out / "property-literal/browser.json").read_text())["browser"],
    "platform": platform.platform(),
}
(out / "source.json").write_text(json.dumps(value, indent=2) + "\n")
print(json.dumps(value, indent=2))
