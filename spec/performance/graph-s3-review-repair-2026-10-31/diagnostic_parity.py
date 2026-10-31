"""Run existing parity against explicitly diagnostic bytes after packaging fails."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
artifact = json.loads((receipt / "final-artifact.json").read_text())
source = root / artifact["output"]
destination = root / "packages/xy-client/dist/xyg-wasm.wasm"
assert not destination.exists(), "diagnostic parity must not overwrite packaged assets"
data = source.read_bytes()
assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
print(f"DIAGNOSTIC ONLY: {source} -> {destination}; sha256={artifact['sha256']}")
try:
    destination.write_bytes(data)
    result = subprocess.run(
        [
            "node",
            "--test",
            "--test-concurrency=2",
            "--test-timeout=20000",
            "packages/xy-node/test/graphforge-wasm-parity.test.mjs",
            "packages/xy-node/test/cose-wasm-parity.test.mjs",
        ],
        cwd=root,
    )
finally:
    destination.unlink(missing_ok=True)
    print("Diagnostic copy removed. No packaged asset set or foundation acceptance.")
sys.exit(result.returncode)
