#!/usr/bin/env python3
"""Download the completed, existing run. Read-only GitHub APIs; no benchmark execution."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = 40075049750
SOURCE = "959e1004924774711a35df7ab1317cca30b18d68"
BASE = "repos/CurateLabs/xyg/actions/"
os.environ["TMPDIR"] = str(HERE / "task-tmp")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def dump(name: str, value: object) -> None:
    (HERE / name).write_text(json.dumps(value, indent=2) + "\n")


def api(endpoint: str, name: str) -> bytes:
    raw = subprocess.check_output(["gh", "api", BASE + endpoint])
    (HERE / name).write_bytes(raw)
    return raw


def compressed(name: str, raw: bytes) -> None:
    with (
        (HERE / name).open("wb") as stream,
        gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0, compresslevel=9) as gz,
    ):
        gz.write(raw)


def main() -> None:
    run = json.loads(api(f"runs/{RUN}", "workflow-run.json"))
    assert run["id"] == RUN and run["head_sha"] == SOURCE and run["run_attempt"] == 1
    assert run["status"] == "completed", "Run still active; nothing dispatched/retried/canceled"
    api(f"workflows/{run['workflow_id']}", "workflow.json")
    api(f"runs/{RUN}/attempts/1", "workflow-attempt-1.json")
    jobs = json.loads(api(f"runs/{RUN}/attempts/1/jobs", "jobs-attempt-1.json"))
    assert jobs["total_count"] == len(jobs["jobs"])
    retention = {
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "run_id": RUN,
        "attempt": 1,
        "source_commit": SOURCE,
        "artifact_archives": [],
        "job_logs": [],
    }
    verifier_lines = []
    for job in jobs["jobs"]:
        jid = job["id"]
        api(f"jobs/{jid}", f"job-{jid}.json")
        # Direct stdout -> owned path, with no gh run view cache or shared /tmp.
        log_path = HERE / f"job-{jid}.log"
        with log_path.open("wb") as stream:
            subprocess.run(["gh", "api", BASE + f"jobs/{jid}/logs"], stdout=stream, check=True)
        raw = log_path.read_bytes()
        compressed(log_path.name + ".gz", raw)
        log_path.unlink()
        verifier_lines.extend(
            line
            for line in raw.splitlines(keepends=True)
            if b"INVALID:" in line or b"Valid evidence:" in line
        )
        retention["job_logs"].append(
            {
                "job_id": jid,
                "endpoint": BASE + f"jobs/{jid}/logs",
                "retained": log_path.name + ".gz",
                "decoded_bytes": len(raw),
                "decoded_sha256": digest(raw),
            }
        )
    (HERE / "hosted-verifier-output.txt").write_bytes(b"".join(verifier_lines))
    artifacts = json.loads(api(f"runs/{RUN}/artifacts", "artifacts.json"))
    assert artifacts["total_count"] == len(artifacts["artifacts"])
    for artifact in artifacts["artifacts"]:
        aid = artifact["id"]
        api(f"artifacts/{aid}", f"artifact-{aid}.json")
        filename = f"ceiling-benchmark-{aid}.zip"
        raw = api(f"artifacts/{aid}/zip", filename)
        assert artifact["digest"] == "sha256:" + digest(raw)
        archive = {
            "artifact_id": aid,
            "file": filename,
            "bytes": len(raw),
            "github_digest": artifact["digest"],
            "sha256": digest(raw),
            "digest_match": True,
            "members": [],
        }
        with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
            assert zipped.testzip() is None
            for member in zipped.infolist():
                if member.is_dir():
                    continue
                original = zipped.read(member)
                assert member.filename.endswith(f"density-comparison-{SOURCE}.json")
                retained = Path(member.filename).name + ".gz"
                compressed(retained, original)
                archive["members"].append(
                    {
                        "name": member.filename,
                        "crc32": f"{member.CRC:08x}",
                        "bytes": len(original),
                        "sha256": digest(original),
                        "compressed_bytes_in_zip": member.compress_size,
                        "retained": retained,
                    }
                )
        retention["artifact_archives"].append(archive)
    dump("retention.json", retention)
    print(
        json.dumps(
            {
                "conclusion": run["conclusion"],
                "jobs": len(jobs["jobs"]),
                "artifacts": len(artifacts["artifacts"]),
                "verifier_lines": [x.decode().strip() for x in verifier_lines],
            }
        )
    )


if __name__ == "__main__":
    main()
