"""Retain the supplied completed CI job log losslessly without a workflow rerun."""

import gzip
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
source = Path("/tmp/xyg-1089-job-126314754073.log")
raw = source.read_bytes()
packed = gzip.compress(raw, mtime=0)
log_path = out / "ci-job-126314754073.log.gz"
record_path = out / "ci-job.json"
assert not log_path.exists() and not record_path.exists()
assert b"2026-11-04T01:02:37.3113226Z" in raw
assert b"source-preservation.json:5679:" in raw
assert b"a8cc8aa28dca6d43fdb1bc828f586fd1f5f7dfc9" in raw
log_path.write_bytes(packed)
record = {
    "runId": 41750490193,
    "jobId": 126314754073,
    "jobName": "Test (Rust + Python + JS)",
    "jobState": "completed failure",
    "workflowStateAtReport": "still running; no whole-run completion claim",
    "head": "909dfe303b4f18f4b6332d9a4c13d68b7d2c3e74",
    "ciMergeCommit": "a8cc8aa28dca6d43fdb1bc828f586fd1f5f7dfc9",
    "parentDownloadCommand": ["gh", "api", "repos/CurateLabs/xyg/actions/jobs/126314754073/logs"],
    "downloadedLogPath": str(source),
    "firstLogTimestamp": raw.decode().splitlines()[0].split()[0],
    "lastLogTimestamp": raw.decode().splitlines()[-1].split()[0],
    "namingFailureTimestamp": "2026-11-04T01:02:37.3113226Z",
    "failedManifest": "spec/performance/graph-resolved-axis-main-sync-2026-11-04/source-preservation.json",
    "failedManifestLine": 5679,
    "legitimateSourceEntry": "examples/osm/osmium-rs/src/lib.rs",
    "downstreamMissingUploads": ["target/host-delegation-report.json", "consumer-apps-smoke.json"],
    "interpretation": "Definitive naming false positive; later producers skipped after this gate. Missing uploads are downstream, not separate runtime regressions or a flake claim.",
    "log": log_path.name,
    "rawBytes": len(raw),
    "rawSha256": hashlib.sha256(raw).hexdigest(),
    "gzipSha256": hashlib.sha256(packed).hexdigest(),
    "rerunPerformed": False,
}
record_path.write_text(json.dumps(record, indent=2) + "\n")
assert gzip.decompress(log_path.read_bytes()) == raw
print(json.dumps(record, indent=2))
