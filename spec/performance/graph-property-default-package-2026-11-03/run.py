"""Record a command without overwriting prior evidence; run from the repo root."""

import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

output = Path(os.environ.get("XYG_PACKAGE_RECEIPT", Path(__file__).resolve().parent))
output.mkdir(parents=True, exist_ok=True)
label, *argv = sys.argv[1:]
record = output / f"{label}.command.json"
log = output / f"{label}.log"
if record.exists() or log.exists():
    raise SystemExit(f"refusing to overwrite {label}")
started = datetime.datetime.now(datetime.UTC)
with log.open("xb") as stream:
    result = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT)
finished = datetime.datetime.now(datetime.UTC)
keys = (
    "PATH",
    "XYG_NATIVE_LIB",
    "XYG_CHROMIUM",
    "CHROMIUM",
    "XYG_GRAPH_PROPERTY_EVIDENCE",
    "XYG_WASM_FOUNDATION_REPORT",
    "XYG_WASM_FOUNDATION_ONLY",
    "XYG_SESSION_WASM",
    "XYG_BROWSER_DIST",
    "CARGO_TARGET_DIR",
    "RUSTFLAGS",
    "CARGO_ENCODED_RUSTFLAGS",
    "UV_PROJECT_ENVIRONMENT",
    "PYTHONPATH",
)
record.write_text(
    json.dumps(
        {
            "argv": argv,
            "cwd": str(Path.cwd()),
            "started": started.isoformat(),
            "finished": finished.isoformat(),
            "elapsed_seconds": (finished - started).total_seconds(),
            "exit": result.returncode,
            "environment": {key: os.environ.get(key) for key in keys},
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        },
        indent=2,
    )
    + "\n"
)
print(label, result.returncode, flush=True)
raise SystemExit(result.returncode)
