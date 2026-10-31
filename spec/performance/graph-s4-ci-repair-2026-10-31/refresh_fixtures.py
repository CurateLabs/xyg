"""Run official fixture producers; require ABI-label-only changes to 398."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
node_stems = [
    "animation_emit",
    "default_styled_emit",
    "tooltip_len_emit",
    "density_emit",
    "force_emit",
]
python_stems = ["payload_attach", "payload_chrome", "payload", "geo"]
rows = []
for stem in [*node_stems, *python_stems, "series_palette"]:
    path = root / f"tests/fixtures/{stem}_cross_host.json"
    before_bytes = path.read_bytes()
    before = json.loads(before_bytes)
    if stem in node_stems:
        argv = ["node", f"packages/xy-node/scripts/{stem}_cross_host.mjs"]
        result = subprocess.run(argv, cwd=root, check=True, capture_output=True)
        path.write_bytes(result.stdout)
    else:
        argv = (
            ["uv", "run", "python", "tests/test_series_palette_cross_host.py", "--write"]
            if stem == "series_palette"
            else [
                "uv",
                "run",
                "python",
                f"packages/xy-node/test/fixtures/write_{stem}_cross_host_fixtures.py",
            ]
        )
        subprocess.run(argv, cwd=root, check=True)
    after = json.loads(path.read_bytes())
    before_abi, after_abi = before.pop("abi_version"), after.pop("abi_version")
    canonical_before = json.dumps(before, sort_keys=True, separators=(",", ":"))
    canonical_after = json.dumps(after, sort_keys=True, separators=(",", ":"))
    if before_abi not in {396, 397} or after_abi != 398 or canonical_before != canonical_after:
        path.write_bytes(before_bytes)
        raise AssertionError(f"Producer changed content beyond ABI metadata: {stem}")
    rows.append(
        {
            "path": str(path.relative_to(root)),
            "command": argv,
            "oldAbi": before_abi,
            "newAbi": after_abi,
            "beforeSha256": hashlib.sha256(before_bytes).hexdigest(),
            "afterSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "unchangedDataSha256": hashlib.sha256(canonical_before.encode()).hexdigest(),
        }
    )
(receipt / "fixture-metadata-proof.json").write_text(json.dumps(rows, indent=2) + "\n")
print(json.dumps({"fixtures": len(rows), "change": "top-level ABI labels only"}))
