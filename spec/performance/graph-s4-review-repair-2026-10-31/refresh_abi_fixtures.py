"""Regenerate existing goldens; admit only their stale ABI-version metadata edit."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
commands = [
    ("density_emit", ["node", "packages/xy-node/scripts/density_emit_cross_host.mjs"], True),
    ("force_emit", ["node", "packages/xy-node/scripts/force_emit_cross_host.mjs"], True),
    (
        "geo",
        ["uv", "run", "python", "packages/xy-node/test/fixtures/write_geo_cross_host_fixtures.py"],
        False,
    ),
    (
        "payload",
        [
            "uv",
            "run",
            "python",
            "packages/xy-node/test/fixtures/write_payload_cross_host_fixtures.py",
        ],
        False,
    ),
    (
        "series_palette",
        ["uv", "run", "python", "tests/test_series_palette_cross_host.py", "--write"],
        False,
    ),
]
proof = []
for stem, argv, stdout_fixture in commands:
    target = root / f"tests/fixtures/{stem}_cross_host.json"
    before_bytes = target.read_bytes()
    before = json.loads(before_bytes)
    output = subprocess.check_output(argv, cwd=root)
    if stdout_fixture:
        target.write_bytes(output)
    after_bytes = target.read_bytes()
    after = json.loads(after_bytes)
    previous_abi = before.pop("abi_version")
    current_abi = after.pop("abi_version")
    if before != after or previous_abi != 396 or current_abi != 397:
        (receipt / f"{stem}-unexpected-golden.json").write_bytes(after_bytes)
        target.write_bytes(before_bytes)
        raise SystemExit(f"refusing non-ABI golden changes: {target}")
    row = {
        "fixture": str(target.relative_to(root)),
        "command": argv,
        "beforeAbi": previous_abi,
        "afterAbi": current_abi,
        "allOtherDataEqual": True,
        "beforeSha256": hashlib.sha256(before_bytes).hexdigest(),
        "afterSha256": hashlib.sha256(after_bytes).hexdigest(),
        "unchangedDataSha256": hashlib.sha256(
            json.dumps(after, sort_keys=True).encode()
        ).hexdigest(),
    }
    proof.append(row)
    print(json.dumps(row))
(receipt / "abi-fixture-metadata-proof.json").write_text(json.dumps(proof, indent=2) + "\n")
