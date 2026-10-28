#!/usr/bin/env python3
"""Read-only retention/hash inspection; never generate data or validate hosted authority."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

SOURCE = "d005b0063d9909392786a18262ff1306e3e8f54c"
RUN = 40618320164
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
    require(
        run["conclusion"] == attempt["conclusion"]
        and run["conclusion"] in ("success", "failure", "cancelled", "timed_out"),
        "terminal outcome preserved",
    )
    require(
        run["head_branch"] == "main"
        and run["event"] == "workflow_dispatch"
        and run["name"] == "Interactive ceiling benchmark",
        "actual main workflow identity",
    )
    workflow = read_json("workflow.json")
    require(
        workflow["id"] == run["workflow_id"]
        and workflow["path"] == ".github/workflows/ceiling-benchmark.yml",
        "workflow API binding",
    )
    outcome = read_json("summary.json")["hosted_outcome"]
    verifier = (HERE / "hosted-verifier-output.txt").read_text()
    require(
        outcome["run_id"] == RUN
        and outcome["source_commit"] == SOURCE
        and outcome["run_conclusion"] == run["conclusion"]
        and outcome["hosted_structural_verifier_accepted"]
        == (
            run["status"] == "completed"
            and run["conclusion"] == "success"
            and "Valid evidence:" in verifier
            and "INVALID:" not in verifier
        ),
        "descriptive hosted outcome binding",
    )
    commit = read_json("source-commit.json")
    require(commit["sha"] == SOURCE, "source commit API binding")
    require(
        gzip.decompress((HERE / "source-commit.git.txt.gz").read_bytes())
        == git("cat-file", "-p", SOURCE),
        "exact historical signed commit bytes",
    )
    require(
        commit["commit"]["tree"]["sha"] == git("rev-parse", SOURCE + "^{tree}").decode().strip(),
        "source tree API binding",
    )
    retention = read_json("retention.json")
    jobs = read_json("jobs-attempt-1.json")["jobs"]
    require(
        {j["id"] for j in jobs} == {j["job_id"] for j in retention["job_logs"]}, "job log coverage"
    )
    all_logs = b""
    all_verifier_lines = b""
    for job in retention["job_logs"]:
        metadata = read_json(f"job-{job['job_id']}.json")
        require(metadata["head_sha"] == SOURCE and metadata["run_id"] == RUN, "job source binding")
        log = gzip.decompress((HERE / job["retained"]).read_bytes())
        require(SOURCE.encode() in log, "checkout/source SHA missing from hosted log")
        require(sha256(log) == job["decoded_sha256"], "original job log digest")
        require(len(log) == job["decoded_bytes"], "original job log length")
        extracted = b"".join(
            line
            for line in log.splitlines(keepends=True)
            if b"INVALID:" in line or b"Valid evidence:" in line
        )
        all_logs += log
        all_verifier_lines += extracted
    require(
        all_verifier_lines == (HERE / "hosted-verifier-output.txt").read_bytes(),
        "hosted verifier output",
    )
    artifacts = read_json("artifacts.json")["artifacts"]
    require(len(artifacts) == len(retention["artifact_archives"]), "artifact coverage")
    for archive in retention["artifact_archives"]:
        metadata = next(a for a in artifacts if a["id"] == archive["artifact_id"])
        require(
            metadata["workflow_run"]["id"] == RUN
            and metadata["workflow_run"]["head_sha"] == SOURCE,
            "artifact run/source binding",
        )
        raw = (HERE / archive["file"]).read_bytes()
        require(metadata["digest"] == "sha256:" + sha256(raw), "GitHub ZIP digest")
        require(metadata["size_in_bytes"] == len(raw), "GitHub ZIP length")
        require(sha256(raw).encode() in all_logs, "ZIP digest missing from hosted upload log")
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
    for snapshot, original in {
        "ceiling-benchmark.yml.txt": ".github/workflows/ceiling-benchmark.yml",
        "verify_density_comparison_report.py.txt": "scripts/verify_density_comparison_report.py",
        "comparison-count-oracle.md.txt": "spec/design/comparison-count-oracle.md",
        "comparison-host-admission.md.txt": "spec/design/comparison-host-admission.md",
        "density-comparison-report-contract.md.txt": "spec/design/density-comparison-report-contract.md",
        "_ux_comparison_host.py.txt": "benchmarks/_ux_comparison_host.py",
        "_ux_live_host.py.txt": "benchmarks/_ux_live_host.py",
        "bench_density_comparison.py.txt": "benchmarks/bench_density_comparison.py",
        "requirements-ci.lock.txt": "benchmarks/requirements-ci.lock",
    }.items():
        require(
            (HERE / snapshot).read_bytes() == git("show", f"{SOURCE}:{original}"),
            "historical snapshot " + snapshot,
        )
    actual = read_json("actual-values.json")
    require(
        actual["log_input_environment"]
        == {
            "INPUT_EXPERIMENT": "density-comparison",
            "INPUT_SIZES": "1000000,100000000,1000000000",
            "INPUT_ARMS": "xy-density,plotly-aggregate,datashader-aggregate",
            "INPUT_REPETITIONS": "2",
            "INPUT_TIMEOUT": "300",
            "INPUT_MEMORY_GIB": "20",
            "INPUT_HARDWARE_GL": "false",
        },
        "actual hosted input values",
    )
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
        require(report["sizes"] == [1_000_000, 100_000_000, 1_000_000_000], "actual sizes")
        require(
            report["arms"] == ["xy-density", "plotly-aggregate", "datashader-aggregate"],
            "actual arms",
        )
        require(
            report["repetitions"] == 2 and report["profile"] == "f64-memmap",
            "actual profile/repetitions",
        )
        argv = report["argv"]
        for key, value in {
            "--sizes": "1000000,100000000,1000000000",
            "--arms": "xy-density,plotly-aggregate,datashader-aggregate",
            "--repetitions": "2",
            "--timeout": "300",
            "--memory-gib": "20",
            "--profile": "f64-memmap",
            "--chunk": "1000000",
            "--disk-gib": "20",
            "--step-timeout": "15",
        }.items():
            require(argv[argv.index(key) + 1] == value, "actual argv " + key)
        require("--hardware" not in argv, "unexpected hardware request")
        require(
            report["environment"]["python"]["version"].startswith("3.12."), "actual Python target"
        )
        lock = git("show", SOURCE + ":benchmarks/requirements-ci.lock").decode()
        pins = dict(
            line.split("==")
            for line in lock.splitlines()
            if line and not line.startswith((" ", "#"))
        )
        versions = report["environment"]["package_versions"]
        require(
            actual["report_argv"] == argv and actual["report_environment"] == report["environment"],
            "actual-values report binding",
        )
        hosted_versions = actual["hosted_environment_check"]["packages"]
        require(
            all(hosted_versions[name] == version for name, version in versions.items()),
            "hosted import check vs report versions",
        )
        for name, version in versions.items():
            if name in pins:
                require(version == pins[name], "actual version vs historical pin " + name)
        for name, version in hosted_versions.items():
            if name in pins:
                require(version == pins[name], "hosted import check vs historical pin " + name)
        require(
            report["limits"]
            == {
                "host_or_browser_timeout_s": 300.0,
                "step_timeout_s": 15.0,
                "rss_bytes_per_tree": 21474836480,
                "rss_poll_ms": 50,
            },
            "actual phase/RSS guards",
        )
        for size, source in report["sources"].items():
            n = int(size)
            require(
                source["actual_rows"] == n and source["dtype"] == "<f8", "source row/dtype metadata"
            )
            require(
                all(c["bytes"] == n * 8 for c in source["columns"].values()), "source byte metadata"
            )
            require(len(source["windows"]) == 32, "source window metadata")
        print(
            "Actual input argv, Python target, pinned package versions and source metadata match."
        )
        print("Retained cell statuses:", [c["status"] for c in report["results"]])
    print("Retention hashes, GitHub ZIP digest/CRC/member bytes and historical source bindings OK.")
    print(
        "Metadata inspection only; hosted verifier output remains the authority-context evidence."
    )


if __name__ == "__main__":
    main()
