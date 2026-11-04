"""Preserve sibling-branch evidence of the same cause without a second fix."""

import gzip
import hashlib
import json
import re
from pathlib import Path

out = Path(__file__).resolve().parent
source = Path("/tmp/xyg-1090-job-126318615791.log")
raw = source.read_bytes()
text = raw.decode("utf-8-sig")
head = re.search(r"Merge ([0-9a-f]{40}) into ([0-9a-f]{40})", text)
assert head and head[1].startswith("9b05")
failure = next(line for line in text.splitlines() if "source-preservation.json:5679:" in line)
packed = gzip.compress(raw, mtime=0)
log_path = out / "ci-job-126318615791.log.gz"
record_path = out / "shared-ci-job.json"
assert not log_path.exists() and not record_path.exists()
log_path.write_bytes(packed)
record = {
    "pullRequest": 1090,
    "runId": 41751542330,
    "jobId": 126318615791,
    "jobName": "Test",
    "jobState": "completed failure",
    "head": head[1],
    "ciMergeBase": head[2],
    "firstLogTimestamp": text.splitlines()[0].split()[0],
    "lastLogTimestamp": text.splitlines()[-1].split()[0],
    "namingFailureTimestamp": failure.split()[0],
    "sameHistoricalManifestLine": 5679,
    "source": str(source),
    "log": log_path.name,
    "rawBytes": len(raw),
    "rawSha256": hashlib.sha256(raw).hexdigest(),
    "gzipSha256": hashlib.sha256(packed).hexdigest(),
    "interpretation": "Same exact qualified OSM helper-path false positive; no separate product root cause or duplicate fix. Parent owns integration after new independent review.",
    "rerunPerformed": False,
}
record_path.write_text(json.dumps(record, indent=2) + "\n")
assert gzip.decompress(log_path.read_bytes()) == raw
print(json.dumps(record, indent=2))
