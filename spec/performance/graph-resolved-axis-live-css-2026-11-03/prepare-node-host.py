"""Reuse installed Node host test dependencies without native/WASM builds."""

import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
source = Path("/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/packages/xy-node")
local = Path("packages/xy-node")
for name in ("package.json", "package-lock.json"):
    assert (source / name).read_bytes() == (local / name).read_bytes()
(local / "node_modules").symlink_to(source / "node_modules", target_is_directory=True)
(out / "node-host-dependencies.json").write_text(
    json.dumps(
        {
            "source": str(source / "node_modules"),
            "lockSha256": hashlib.sha256((local / "package-lock.json").read_bytes()).hexdigest(),
        },
        indent=2,
    )
    + "\n"
)
print("PASS: same-lock installed koffi dependencies linked for Node host tests")
