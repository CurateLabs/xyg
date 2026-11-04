"""Retain additional completed jobs documenting the same naming failure."""

import gzip
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
jobs = []
for job_id, title in ((126314754097, "Python 3.11 floor"), (126318810230, "Release surfaces")):
    source = Path(f"/tmp/xyg-1089-job-{job_id}.log")
    raw = source.read_bytes()
    text = raw.decode("utf-8-sig")
    packed = gzip.compress(raw, mtime=0)
    destination = out / f"ci-job-{job_id}.log.gz"
    assert not destination.exists()
    destination.write_bytes(packed)
    assert gzip.decompress(destination.read_bytes()) == raw
    record = {
        "runId": 41750490193,
        "jobId": job_id,
        "jobName": title,
        "jobState": "completed failure",
        "head": "909dfe303b4f18f4b6332d9a4c13d68b7d2c3e74",
        "parentDownloadCommand": ["gh", "api", f"repos/CurateLabs/xyg/actions/jobs/{job_id}/logs"],
        "downloadedLogPath": str(source),
        "firstLogTimestamp": text.splitlines()[0].split()[0],
        "lastLogTimestamp": text.splitlines()[-1].split()[0],
        "log": destination.name,
        "rawBytes": len(raw),
        "rawSha256": hashlib.sha256(raw).hexdigest(),
        "gzipSha256": hashlib.sha256(packed).hexdigest(),
        "rerunPerformed": False,
    }
    if job_id == 126314754097:
        summary = "1 failed, 7699 passed, 358 skipped, 113 xfailed, 4 xpassed, 43 warnings"
        assert summary in text and "source-preservation.json:5679:" in text
        record.update(
            summary=summary,
            soleFailure="test_repository_has_no_stale_native_identity",
            failureTimestamp="2026-11-04T01:08:09.3919845Z",
            interpretation="Same exact qualified OSM helper-path false positive; no zero-skip claim.",
        )
    else:
        assert (
            "test=failure" in text and "python_floor=failure" in text and "wheels=skipped" in text
        )
        record.update(
            aggregatedResults={"test": "failure", "python_floor": "failure", "wheels": "skipped"},
            interpretation="Aggregates already-failed test and floor jobs and skipped wheels; no separate product root cause.",
        )
    jobs.append(record)
record_path = out / "additional-ci-jobs.json"
assert not record_path.exists()
record_path.write_text(
    json.dumps(
        {
            "jobs": jobs,
            "parentReportedMatchingComment": {
                "id": 6619726772,
                "updatedAt": "2026-11-04T01:08:20Z",
            },
            "parentLocalReproduction": {"execId": 43589, "exitCode": 1, "sameFailureOnly": True},
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps(jobs, indent=2))
