"""Recreate 188f JS sources locally; reuse installed build dependencies read-only."""

import subprocess
from pathlib import Path

root = Path.cwd()
base = "188f7450bff332e0be6a80bf97b15b86e74b48ae"
out = root / "target/task-tmp/resolved-spine-188f-baseline"
out.mkdir(parents=True, exist_ok=True)
files = subprocess.check_output(
    [
        "git",
        "ls-tree",
        "-r",
        "--name-only",
        base,
        "--",
        "js",
        "package.json",
        "package-lock.json",
        "packages/xy-client/package.json",
    ],
    text=True,
).splitlines()
for name in files:
    p = out / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(subprocess.check_output(["git", "show", f"{base}:{name}"]))
if not (out / "node_modules").exists():
    (out / "node_modules").symlink_to(root / "node_modules")
print("Prepared isolated historical JS build sources:", out)
