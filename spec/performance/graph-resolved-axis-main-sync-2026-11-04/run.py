"""Record append-only synchronization commands without rebuilding producers."""

import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

out = Path(__file__).resolve().parent
root = out.parents[2]
name, *argv = sys.argv[1:]
record_path = out / f"{name}.json"
assert not record_path.exists(), "append-only command records"
env = os.environ.copy()
env.update(
    XYG_SKIP_CARGO="1",
    XYG_SKIP_NODE="1",
    UV_OFFLINE="1",
    XYG_NATIVE_LIB=str(root / "target/release/libxyg_core.so"),
    PATH="/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:"
    + env["PATH"],
)
start = time.monotonic()
result = subprocess.run(argv, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
packed = gzip.compress(result.stdout, mtime=0)
(out / f"{name}.log.gz").write_bytes(packed)
record_path.write_text(
    json.dumps(
        {
            "argv": argv,
            "exitCode": result.returncode,
            "seconds": round(time.monotonic() - start, 3),
            "environment": {
                key: env[key]
                for key in (
                    "XYG_SKIP_CARGO",
                    "XYG_SKIP_NODE",
                    "UV_OFFLINE",
                    "XYG_NATIVE_LIB",
                    "PATH",
                )
            },
            "rawSha256": hashlib.sha256(result.stdout).hexdigest(),
            "gzipSha256": hashlib.sha256(packed).hexdigest(),
            "log": f"{name}.log.gz",
        },
        indent=2,
    )
    + "\n"
)
print(name, result.returncode, result.stdout.decode(errors="replace")[-7000:], flush=True)
sys.exit(result.returncode)
