"""Archive parent-supplied local CI logs without changing their bytes."""

import gzip
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
records = {}
for job in (126318615894, 126322626934):
    source = Path(f"/tmp/xyg-1090-job-{job}.log")
    raw = source.read_bytes()
    destination = out / f"ci-job-{job}.log.gz"
    packed = gzip.compress(raw, mtime=0)
    with destination.open("xb") as stream:
        stream.write(packed)
    assert gzip.decompress(packed) == raw
    records[str(job)] = {
        "source": str(source),
        "archive": destination.name,
        "raw_bytes": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "gzip_sha256": hashlib.sha256(packed).hexdigest(),
    }
record = out / "additional-ci-logs.json"
with record.open("x") as stream:
    stream.write(json.dumps(records, indent=2) + "\n")
print("Archived two parent-supplied CI logs byte-exact; no remote access")
