"""Record a command without overwriting prior evidence; run from the repo root."""

import datetime
import hashlib
import json
import os
import selectors
import subprocess
import sys
from pathlib import Path

output = Path(os.environ.get("XYG_ATTACHMENT_RECEIPT", Path(__file__).resolve().parent))
output.mkdir(parents=True, exist_ok=True)
label, *argv = sys.argv[1:]
record = output / f"{label}.command.json"
log = output / f"{label}.log"
if record.exists() or log.exists():
    raise SystemExit(f"refusing to overwrite {label}")
started = datetime.datetime.now(datetime.UTC)
stdout = output / f"{label}.stdout"
stderr = output / f"{label}.stderr"
with log.open("xb") as combined, stdout.open("xb") as out, stderr.open("xb") as err:
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, out)
        selector.register(process.stderr, selectors.EVENT_READ, err)
        while selector.get_map():
            for key, _ in selector.select():
                chunk = os.read(key.fileobj.fileno(), 65536)
                if chunk:
                    key.data.write(chunk)
                    combined.write(chunk)
                    combined.flush()
                else:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
    exit_code = process.wait()
finished = datetime.datetime.now(datetime.UTC)
keys = (
    "PATH",
    "XYG_NATIVE_LIB",
    "XYG_CHROMIUM",
    "CHROMIUM",
    "XYG_GRAPH_SLOT_BASELINE",
    "XYG_GRAPH_MOTION_BASELINE",
    "XYG_GRAPH_POINTER_BASELINE",
    "XYG_GRAPH_POINTER_CAPTURE",
    "XYG_GRAPH_POINTER_SCREENSHOT",
    "XYG_GRAPH_SESSION_REPORT",
    "XYG_GRAPH_SESSION_SCREENSHOT",
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
            "exit": exit_code,
            "environment": {key: os.environ.get(key) for key in keys},
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            "stdout_sha256": hashlib.sha256(stdout.read_bytes()).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.read_bytes()).hexdigest(),
        },
        indent=2,
    )
    + "\n"
)
print(label, exit_code, flush=True)
raise SystemExit(exit_code)
