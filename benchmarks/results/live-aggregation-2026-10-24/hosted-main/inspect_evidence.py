#!/usr/bin/env python3
"""Read-only retention/hash inspection; never generate data or validate hosted authority."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

SOURCE = "a8b3e10801fa3c1b96eddd7b244a1d64e0778bad"
RUN = 40066499687
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def read_json(name: str) -> dict:
    return json.loads((HERE / name).read_bytes())


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def main() -> None:
    manifest = read_json("manifest.json")
    actual_files = {p.name for p in HERE.iterdir() if p.is_file()}
    require(set(manifest) == actual_files - {"manifest.json", "SHA256SUMS"}, "manifest coverage")
    for name, entry in manifest.items():
        raw = (HERE / name).read_bytes()
        require(len(raw) == entry["bytes"] and sha256(raw) == entry["sha256"], name)
        if name.endswith(".gz"):
            decoded = gzip.decompress(raw)
            require(
                len(decoded) == entry["decoded_bytes"]
                and sha256(decoded) == entry["decoded_sha256"],
                "decoded " + name,
            )
            require(raw[4:8] == bytes(4) and not raw[3] & 8, "deterministic gzip " + name)
    sums = {}
    for line in (HERE / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        require(name not in sums, "duplicate SHA256SUMS entry")
        require(sha256((HERE / name).read_bytes()) == expected, "SHA256SUMS " + name)
        sums[name] = expected
    require(set(sums) == actual_files - {"SHA256SUMS"}, "SHA256SUMS coverage")

    run = read_json("workflow-run.json")
    attempt = read_json("workflow-attempt-1.json")
    for metadata in (run, attempt):
        require(
            metadata["id"] == RUN
            and metadata["run_attempt"] == 1
            and metadata["head_sha"] == SOURCE
            and metadata["status"] == "completed",
            "terminal run binding",
        )
    retention = read_json("retention.json")
    jobs = read_json("jobs-attempt-1.json")["jobs"]
    require(
        {j["id"] for j in jobs} == {j["job_id"] for j in retention["job_logs"]}, "job log coverage"
    )
    for job in retention["job_logs"]:
        metadata = read_json(f"job-{job['job_id']}.json")
        require(metadata["head_sha"] == SOURCE and metadata["run_id"] == RUN, "job source binding")
        log = gzip.decompress((HERE / job["retained"]).read_bytes())
        require(sha256(log) == job["decoded_sha256"], "original job log digest")
        require(len(log) == job["decoded_bytes"], "original job log length")
        extracted = b"".join(
            line
            for line in log.splitlines(keepends=True)
            if b"INVALID:" in line or b"Valid evidence:" in line
        )
        require(
            extracted == (HERE / "hosted-verifier-output.txt").read_bytes(),
            "hosted verifier output",
        )
    artifacts = read_json("artifacts.json")["artifacts"]
    require(len(artifacts) == len(retention["artifact_archives"]), "artifact coverage")
    for archive in retention["artifact_archives"]:
        metadata = next(a for a in artifacts if a["id"] == archive["artifact_id"])
        raw = (HERE / archive["file"]).read_bytes()
        require(metadata["digest"] == "sha256:" + sha256(raw), "GitHub ZIP digest")
        require(read_json(f"artifact-{metadata['id']}.json") == metadata, "artifact API binding")
        with zipfile.ZipFile(HERE / archive["file"]) as zipped:
            require(zipped.testzip() is None, "ZIP CRC check")
            files = [m for m in zipped.infolist() if not m.is_dir()]
            require(len(files) == len(archive["members"]), "ZIP member coverage")
            for member, record in zip(files, archive["members"], strict=True):
                original = zipped.read(member)
                require(member.filename == record["name"], "ZIP member name")
                require(f"{member.CRC:08x}" == record["crc32"], "ZIP member CRC")
                require(sha256(original) == record["sha256"], "ZIP member digest")
                require(
                    original == gzip.decompress((HERE / record["retained"]).read_bytes()),
                    "ZIP original bytes differ from gzip-decoded bytes",
                )

    bindings = read_json("source-bindings.json")
    require(bindings["source_commit"] == SOURCE, "historical source commit")
    require(
        git("rev-parse", SOURCE + "^{tree}").decode().strip() == bindings["git_tree_oid"],
        "Git tree",
    )
    listing = {}
    for entry in git("ls-tree", "-r", "-z", SOURCE).split(b"\0"):
        if entry:
            metadata, path = entry.split(b"\t")
            listing[path.decode()] = metadata.split()[2].decode()
    for folder, tree in bindings["product_trees"].items():
        suffix = tree["pattern"][1:]
        files = {p for p in listing if p.startswith(folder + "/") and p.endswith(suffix)}
        require(files == set(tree["files"]), "historical tree file coverage")
        digest = hashlib.sha256()
        for path in sorted(files, key=Path):
            raw = git("show", f"{SOURCE}:{path}")
            record = tree["files"][path]
            require(listing[path] == record["git_blob_oid"], "historical Git blob")
            require(len(raw) == record["bytes"] and sha256(raw) == record["sha256"], path)
            digest.update(path.encode() + b"\0")
            digest.update(bytes.fromhex(sha256(raw)))
        require(digest.hexdigest() == tree["sha256"], "historical product tree digest")
    for path, record in bindings["historical_files"].items():
        raw = git("show", f"{SOURCE}:{path}")
        require(sha256(raw) == record["sha256"], "historical file " + path)
    for filename, binding in bindings["reports"].items():
        raw = gzip.decompress((HERE / filename).read_bytes())
        require(sha256(raw) == binding["decoded_sha256"], "bound report bytes")
        report = json.loads(raw)
        require(report["environment"]["git"]["commit"] == SOURCE, "report source commit")
        require(report["environment"]["git"]["dirty"] is False, "report clean source")
        require(
            set(report["provenance_sha256"]) == set(binding["provenance"]), "provenance coverage"
        )
        for key, entry in binding["provenance"].items():
            require(report["provenance_sha256"][key] == entry["recorded_sha256"], key)
            if key.endswith(":tree_sha256"):
                require(
                    entry["recorded_sha256"]
                    == bindings["product_trees"][key.split(":")[0]]["sha256"],
                    key,
                )
            elif key in listing:
                require(sha256(git("show", f"{SOURCE}:{key}")) == entry["recorded_sha256"], key)
            else:
                require(entry["locally_verified"] is False, "unavailable executable disclosure")
        expected = {
            (n, arm, rep)
            for n in (1_000_000, 100_000_000, 1_000_000_000)
            for arm in ("xy-density", "plotly-aggregate", "datashader-aggregate")
            for rep in (0, 1)
        }
        cells = [(c["n"], c["arm"], c["repetition"]) for c in report["results"]]
        require(len(cells) == 18 and set(cells) == expected, "18-cell coverage")
        print("Retained cell statuses:", [c["status"] for c in report["results"]])
    print("Retention hashes, GitHub ZIP digest/CRC/member bytes and historical source bindings OK.")
    print(
        "Metadata inspection only; hosted verifier output remains the authority-context evidence."
    )


if __name__ == "__main__":
    main()
