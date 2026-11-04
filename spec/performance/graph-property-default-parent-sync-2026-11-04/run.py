"""Record separate raw stdout/stderr, exact argv and exit without overwrites."""

import datetime
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

out = Path(os.environ.get("XYG_SYNC_RECEIPT", Path(__file__).resolve().parent))
out.mkdir(parents=True, exist_ok=True)
label, *argv = sys.argv[1:]
record = out / f"{label}.json"
paths = {name: out / f"{label}.{name}.log" for name in ("stdout", "stderr")}
assert not record.exists() and not any(p.exists() for p in paths.values()), "append-only receipt"
started = datetime.datetime.now(datetime.UTC)
with paths["stdout"].open("xb") as stdout, paths["stderr"].open("xb") as stderr:
    result = subprocess.run(argv, stdout=stdout, stderr=stderr)
finished = datetime.datetime.now(datetime.UTC)
logs = {}
for name, path in paths.items():
    raw = path.read_bytes()
    compressed = gzip.compress(raw, mtime=0)
    destination = path.with_suffix(path.suffix + ".gz")
    with destination.open("xb") as stream:
        stream.write(compressed)
    logs[name] = {
        "file": destination.name,
        "raw_bytes": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
    }
keys = (
    "PATH",
    "XYG_NATIVE_LIB",
    "XYG_CHROMIUM",
    "CHROMIUM",
    "XYG_WASM_FOUNDATION_ONLY",
    "XYG_SESSION_WASM",
    "XYG_BROWSER_DIST",
    "CARGO_TARGET_DIR",
    "RUSTFLAGS",
    "CARGO_ENCODED_RUSTFLAGS",
    "UV_PROJECT_ENVIRONMENT",
    "PYTHONPATH",
    "XYG_SKIP_CARGO",
    "XYG_SKIP_NODE",
    "UV_OFFLINE",
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
            "logs": logs,
        },
        indent=2,
    )
    + "\n"
)
print(label, result.returncode, flush=True)
raise SystemExit(result.returncode)
