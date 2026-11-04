"""Verify parent build inputs/reused binaries and current shipping outputs."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
approved = json.loads(
    (receipt.parent / "graph-s5b-pointer-selection-2026-11-04/artifacts.json").read_text()
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert len(approved["sourceInputs"]) == 301
source_inputs = {path: sha(root / path) for path in approved["sourceInputs"]}
changed_inputs = [
    path for path, digest in source_inputs.items() if digest != approved["sourceInputs"][path]
]
assert set(changed_inputs) == {
    "js/src/63_graph_controller.ts",
}, changed_inputs
artifacts = {
    path: {"bytes": (root / path).stat().st_size, "sha256": sha(root / path)}
    for path in approved["artifacts"]
}
changed = []
for path, actual in artifacts.items():
    if actual != approved["artifacts"][path]:
        assert Path(path).name in ("index.js", "standalone.js"), path
        changed.append(path)
assert len(changed) == 4, changed
wasm = root / "packages/xy-client/dist/xyg-wasm.wasm"
optimized = json.loads(
    subprocess.check_output(
        [
            "node",
            "--input-type=module",
            "-e",
            'import{readFileSync,writeFileSync,existsSync}from"node:fs";'
            'import{gzipSync}from"node:zlib";'
            'import{createHash}from"node:crypto";'
            "const b=readFileSync(process.argv[1]),g=gzipSync(b,{level:6});"
            "if(existsSync(process.argv[2])){"
            "if(!readFileSync(process.argv[2]).equals(g))throw Error('refusing to overwrite retained module');"
            "}else writeFileSync(process.argv[2],g);"
            "console.log(JSON.stringify({bytes:b.length,gzip6:g.length,"
            'sha256:createHash("sha256").update(b).digest("hex"),'
            'gzip6Sha256:createHash("sha256").update(g).digest("hex")}));',
            str(wasm),
            str(receipt / "shipping-module.wasm.gz"),
        ],
        text=True,
    )
)
for key, actual in optimized.items():
    assert actual == approved["optimized"][key], (key, actual)
result = {
    "verifiedApprovedBuildInputs": 301,
    "sourceInputs": source_inputs,
    "changedInputs": changed_inputs,
    "unchangedInputCount": 301 - len(changed_inputs),
    "artifacts": artifacts,
    "changedPairedAssets": changed,
    "optimized": {
        **optimized,
        "limits": approved["optimized"]["limits"],
        "headroom": approved["optimized"]["headroom"],
    },
    "versions": approved["versions"],
    "provenance": "Approved parent native/raw-WASM reused by verified byte identity; client and normal shipping packager rebuilt locally. No fresh Rust compilation claimed.",
}
destination = receipt / "artifacts.json"
serialized = json.dumps(result, indent=2) + "\n"
if destination.exists():
    assert destination.read_text() == serialized, "refusing to overwrite retained artifacts"
else:
    destination.write_text(serialized)
print(json.dumps({k: v for k, v in result.items() if k != "sourceInputs"}, indent=2))
