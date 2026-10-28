#!/usr/bin/env python3
"""Inspect this failed preflight receipt without launching a browser or allocating rows."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = "fe7d2ae71d316fd96b9851f3ce6232f76dd19134"
RUN = 40639793475
JOB = 122655020139
ARTIFACT = 12794149653


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(name: str) -> dict:
    return json.loads((HERE / name).read_bytes())


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def main() -> None:
    actual = {p.name for p in HERE.iterdir() if p.is_file()}
    manifest = read_json("manifest.json")
    require(set(manifest) == actual - {"manifest.json", "SHA256SUMS"}, "manifest coverage")
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
        require(name not in sums and sha256((HERE / name).read_bytes()) == expected, name)
        sums[name] = expected
    require(set(sums) == actual - {"SHA256SUMS"}, "SHA256SUMS coverage")

    for name in ("run.json", "attempt-1.json"):
        run = read_json(name)
        require(
            run["id"] == RUN
            and run["run_attempt"] == 1
            and run["head_sha"] == SOURCE
            and run["head_branch"] == "main"
            and run["event"] == "workflow_dispatch"
            and run["status"] == "completed"
            and run["conclusion"] == "failure"
            and run["path"] == ".github/workflows/ceiling-benchmark.yml"
            and run["repository"]["full_name"] == "CurateLabs/xyg",
            name + " terminal source/context binding",
        )
    jobs = read_json("jobs.json")
    require(jobs["total_count"] == 1 and len(jobs["jobs"]) == 1, "single hosted job")
    job = read_json("job.json")
    require(jobs["jobs"][0] == job, "job API equality")
    require(
        job["id"] == JOB
        and job["run_id"] == RUN
        and job["head_sha"] == SOURCE
        and job["status"] == "completed"
        and job["conclusion"] == "failure"
        and job["labels"] == ["blacksmith-12vcpu-macos-15"],
        "job identity",
    )
    steps = {s["name"]: s for s in job["steps"]}
    require(steps["Run ceiling sweep"]["conclusion"] == "failure", "failed sweep")
    for name in (
        "Build native core",
        "Install package + comparison deps",
        "Verify benchmark environment",
        "Build render client",
        "Install Chromium (Playwright)",
        "Upload ceiling report",
    ):
        require(steps[name]["conclusion"] == "success", name)

    artifacts = read_json("artifacts.json")
    artifact = read_json("artifact.json")
    require(artifacts["total_count"] == 1 and artifacts["artifacts"] == [artifact], "artifacts")
    require(
        artifact["id"] == ARTIFACT
        and artifact["workflow_run"]["id"] == RUN
        and artifact["workflow_run"]["head_sha"] == SOURCE,
        "artifact source binding",
    )
    retention = read_json("retention.json")
    for name, entry in retention["archives"].items():
        raw = (HERE / name).read_bytes()
        require(sha256(raw) == entry["sha256"] and len(raw) == entry["bytes"], name)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(archive.testzip() is None, name + " CRC")
            observed = [
                {
                    "name": item.filename,
                    "bytes": item.file_size,
                    "crc32": f"{item.CRC:08x}",
                    "sha256": sha256(archive.read(item)),
                }
                for item in archive.infolist()
            ]
            require(observed == entry["members"], name + " member inventory")
    require(
        artifact["digest"] == "sha256:" + sha256((HERE / "ceiling-benchmark.zip").read_bytes()),
        "GitHub artifact digest",
    )
    preflight_raw = gzip.decompress((HERE / "preflight.json.gz").read_bytes())
    with zipfile.ZipFile(HERE / "ceiling-benchmark.zip") as archive:
        require(
            archive.namelist() == [f"_temp/colored-browser-preflight-{SOURCE}.json"]
            and archive.read(archive.namelist()[0]) == preflight_raw,
            "sole preflight artifact; no host/control/100M reports",
        )
    preflight = json.loads(preflight_raw)
    require(
        preflight["status"] == "failed"
        and preflight["requested_gl"] == "hardware"
        and preflight["hardware_context"]
        == {
            "GITHUB_REPOSITORY": "CurateLabs/xyg",
            "GITHUB_WORKFLOW_REF": "CurateLabs/xyg/.github/workflows/ceiling-benchmark.yml@refs/heads/main",
            "GITHUB_WORKFLOW_SHA": SOURCE,
        },
        "preflight context",
    )
    require(
        preflight["renderer"]["unmaskedRenderer"]
        == "ANGLE (Apple, ANGLE Metal Renderer: Apple Paravirtual device, Unspecified Version)"
        and preflight["renderer"]["version"] == "WebGL 2.0 (OpenGL ES 3.0 Chromium)"
        and preflight["gpu_info"]["gpu"]["featureStatus"]["webgl"] == "enabled"
        and preflight["readback"] == [64, 128, 191, 255]
        and preflight["contextLost"] is False
        and preflight["process_reaped"] is True
        and preflight["profile_removed"] is True,
        "actual renderer/readback/cleanup",
    )
    log = gzip.decompress((HERE / "job-122655020139.log.gz").read_bytes())
    with zipfile.ZipFile(HERE / "logs.zip") as archive:
        require(log == archive.read("0_Ceiling sweep (Blacksmith macOS M4, 48 GB).txt"), "full log")
    text = log.decode("utf-8-sig")
    for needle in (
        SOURCE,
        "INPUT_EXPERIMENT: colored-browser-hardware",
        "INPUT_HARDWARE_GL: true",
        "RendererAdmissionError: " + preflight["failure"],
        "Process completed with exit code 1.",
        "SHA256 digest of uploaded artifact is " + artifact["digest"].split(":")[1],
    ):
        require(needle in text, "log binding: " + needle)

    bindings = read_json("source-bindings.json")
    commit = gzip.decompress((HERE / "source-commit.git.txt.gz").read_bytes())
    require(commit == git("cat-file", "commit", SOURCE), "accepted commit bytes")
    require(
        read_json("source-commit.json")["sha"] == SOURCE
        and read_json("source-commit.json")["tree"]["sha"] == bindings["source_tree"]
        and git("rev-parse", SOURCE + "^{tree}").decode().strip() == bindings["source_tree"],
        "accepted tree identity",
    )
    tree = {}
    for line in git("ls-tree", "-r", SOURCE).decode().splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, blob = metadata.split()
        tree[path] = (mode, kind, blob)
    with tarfile.open(
        fileobj=io.BytesIO(gzip.decompress((HERE / "source-files.tar.gz").read_bytes()))
    ) as archive:
        members = {item.name: item for item in archive if item.isfile()}
        require(set(members) == set(bindings["files"]), "source snapshot coverage")
        for path, entry in bindings["files"].items():
            raw = archive.extractfile(members[path]).read()
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            require(
                len(raw) == entry["bytes"]
                and sha256(raw) == entry["sha256"]
                and blob == entry["git_blob"]
                and tree[path] == (entry["mode"], "blob", blob),
                "accepted source blob: " + path,
            )
    # Evaluate only the accepted pure admission function over archived observations.
    # No imports, authority environment, browser launch, source generation or host worker.
    import ast
    import re

    source = git("show", SOURCE + ":scripts/density_spill_browser_smoke.py").decode()
    function = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "renderer_guard"
    )
    namespace = {"re": re}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), "accepted renderer_guard", "exec"),
        namespace,
    )
    try:
        namespace["renderer_guard"](preflight["renderer"], preflight["gpu_info"], "hardware")
    except ValueError as error:
        require(str(error) == preflight["failure"], "same admission failure")
    else:
        raise ValueError("archived rejected renderer unexpectedly admitted")
    print(
        f"Receipt verified: run {RUN} failed renderer preflight; "
        f"{len(bindings['files'])} accepted source blobs, both ZIP CRCs/digests and full logs match. "
        "Control/100M not started; zero host/browser verifier pairs or chart journeys."
    )


if __name__ == "__main__":
    main()
