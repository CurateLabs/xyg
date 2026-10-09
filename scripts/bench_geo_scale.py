#!/usr/bin/env python3
"""Measure the real bounded Rust geographic source/LOD protocol, not a planner.

Each scale runs in a fresh native process with OS maximum-RSS measurement.
Source rows are regenerated chunk-by-chunk; no source-wide array/file is built.
The separate 1B case only invokes GeoSourcePlan and is expressly not measured data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import selectors
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "spec/performance/geo-scale-2026-10-08"


def command(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def cpu_memory() -> tuple[str, int]:
    if sys.platform == "darwin":
        return command(["sysctl", "-n", "machdep.cpu.brand_string"]), int(
            command(["sysctl", "-n", "hw.memsize"])
        )
    if sys.platform.startswith("linux"):
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            platform.processor(),
        )
        memory = next(
            int(line.split()[1]) * 1024
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemTotal:")
        )
        return cpu, memory
    raise RuntimeError(
        "This harness requires macOS time -l or Linux GNU time -v for actual per-run RSS"
    )


def environment() -> dict:
    cpu, memory = cpu_memory()
    disk = shutil.disk_usage(ROOT)
    authority = sorted((ROOT / "crates/xyg-engine/src").rglob("*.rs")) + [
        ROOT / "Cargo.toml",
        ROOT / "Cargo.lock",
        ROOT / "crates/xyg-engine/src/geo_scale_protocol.rs",
        ROOT / "crates/xyg-engine/src/geo_source.rs",
        ROOT / "crates/xyg-engine/src/geo_source_session.rs",
        ROOT / "crates/xyg-engine/src/geo_lod.rs",
        ROOT / "crates/xyg-engine/src/geo_lod_scene.rs",
        ROOT / "crates/xyg-engine/src/geo_membership_session.rs",
        ROOT / "crates/xyg-engine/src/bin/geo_scale_bench.rs",
        Path(__file__).resolve(),
    ]
    return dict(
        schema_version=1,
        recorded_at=datetime.now(UTC).isoformat(),
        platform=platform.platform(),
        architecture=platform.machine(),
        cpu=cpu,
        logical_cpus=os.cpu_count(),
        memory_bytes=memory,
        disk_total_bytes=disk.total,
        disk_free_bytes=disk.free,
        python=sys.version,
        rust=command(["rustc", "-Vv"]),
        git_head=command(["git", "rev-parse", "HEAD"]),
        git_branch=command(["git", "branch", "--show-current"]),
        worktree_status=command(["git", "status", "--short"]),
        source_sha256={
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in authority
        },
        backend="native shared Rust geo_scale_protocol (not C ABI marshaling or browser Worker)",
        build_command="cargo build --release -p xyg-engine --bin geo_scale_bench",
        feature="default raster",
        source_allocation="one 65,536-row regenerated chunk; no whole-source array/file",
        rss_method="macOS /usr/bin/time -l maximum resident set size bytes"
        if sys.platform == "darwin"
        else "Linux GNU /usr/bin/time -v maximum resident set size KiB converted to bytes",
        caveats=[
            "One shared process ledger per fresh native child",
            "RSS includes runtime and measured export allocations",
            "Processor ledger metric is sampled at lifecycle boundaries, not a transient allocation high-water mark",
            "Generated chunk encoding/regeneration cost is included in read/query latency",
            "Five sessions retain concurrent candidates/Scenes; one pending read at a time; serial round-robin CPU",
            "Synthetic chunk-aligned time permits coarse temporal pruning; spatial points are unordered",
            "One run per scale is descriptive evidence, not a confidence interval or competitor win",
            "No GPU paint/VRAM/controller/network latency is measured",
        ],
    )


def source_snapshot(out: Path) -> dict:
    """Preserve and independently reapply the exact source delta before timing."""
    roots = [
        "Cargo.toml",
        "Cargo.lock",
        "rust-toolchain.toml",
        ".cargo",
        "crates/xyg-engine",
        "scripts/bench_geo_scale.py",
    ]
    patch = subprocess.check_output(["git", "diff", "HEAD", "--binary", "--", *roots], cwd=ROOT)
    new = command(["git", "ls-files", "--others", "--exclude-standard", "--", *roots]).splitlines()
    for path in new:
        diff = subprocess.run(
            ["git", "diff", "--no-index", "--binary", "/dev/null", path],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if diff.returncode != 1:
            raise RuntimeError(f"Source capture failed for {path}: {diff.stderr!r}")
        patch += diff.stdout
    patch_path = out / "measured-source.patch"
    patch_path.write_bytes(patch)
    tracked = command(["git", "ls-files", "--", *roots]).splitlines()
    with tempfile.TemporaryDirectory(prefix="xyg-geo-source-proof-") as tmp:
        destination = Path(tmp)
        with tempfile.TemporaryFile() as archive:
            subprocess.run(
                ["git", "archive", "HEAD", *tracked], cwd=ROOT, stdout=archive, check=True
            )
            archive.seek(0)
            with tarfile.open(fileobj=archive) as contents:
                contents.extractall(destination, filter="data")
        subprocess.run(["git", "apply", str(patch_path)], cwd=destination, check=True)
        for path in tracked + new:
            actual, reconstructed = ROOT / path, destination / path
            if actual.exists() != reconstructed.exists() or (
                actual.is_file() and actual.read_bytes() != reconstructed.read_bytes()
            ):
                raise RuntimeError(f"Reconstructed source differs at {path}")
    return dict(
        source_patch_file=patch_path.name,
        source_patch_sha256=hashlib.sha256(patch).hexdigest(),
        source_patch_base=command(["git", "rev-parse", "HEAD"]),
        source_reconstruction_verified=True,
    )


def run(binary: Path, rows: int, iteration: int, out: Path, *, planner: bool = False) -> dict:
    suffix = "planner" if planner else f"{rows}-r{iteration}"
    args = [str(binary), *(["--plan-only"] if planner else []), str(rows)]
    timed = ["/usr/bin/time", "-l" if sys.platform == "darwin" else "-v", *args]
    print(f"Starting {suffix}", flush=True)
    start = time.perf_counter()
    process = subprocess.Popen(
        timed, cwd=ROOT, text=True, bufsize=1, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert process.stdout is not None and process.stderr is not None
    metrics, stderr = [], []
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, "metric")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            for key, _ in selector.select(timeout=10):
                line = key.fileobj.readline()
                if not line:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "metric":
                    value = json.loads(line)
                    metrics.append(value)
                    if value["event"] == "phase":
                        print(f"{suffix} {value['name']}: {value['ms']:.1f} ms", flush=True)
                else:
                    stderr.append(line)
                    if line.startswith("rows="):
                        print(line.strip(), flush=True)
    returncode = process.wait()
    raw = "".join(stderr)
    pattern = (
        r"(\d+)\s+maximum resident set size"
        if sys.platform == "darwin"
        else r"Maximum resident set size \(kbytes\):\s*(\d+)"
    )
    match = re.search(pattern, raw)
    if match is None:
        raise RuntimeError(f"Missing OS RSS evidence for {suffix}: {raw[-1500:]}")
    peak = int(match[1]) * (1 if sys.platform == "darwin" else 1024)
    result = dict(
        schema_version=1,
        source_rows=rows,
        iteration=iteration,
        planner_only=planner,
        command=timed,
        elapsed_seconds=time.perf_counter() - start,
        returncode=returncode,
        maximum_resident_bytes=peak,
        metrics=metrics,
        completed=any(item["event"] == "completed" for item in metrics),
        resource_limit=any(item.get("resource_limit") for item in metrics),
    )
    out.joinpath(f"{suffix}.json").write_text(json.dumps(result, indent=2) + "\n")
    out.joinpath(f"{suffix}.stderr.txt").write_text(raw)
    print(f"Finished {suffix}: RSS {peak / 1024**2:.1f} MiB, status {returncode}", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rows", nargs="+", type=int, default=[1000, 100_000, 1_000_000, 10_000_000, 100_000_000]
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-build", action="store_true")
    options = parser.parse_args()
    if options.repeat < 1 or any(n < 1 or n > 100_000_000 for n in options.rows):
        parser.error("measured scales must be 1..100M rows, repeat positive; 1B is planner-only")
    out = options.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not options.no_build:
        subprocess.run(
            ["cargo", "build", "--release", "-p", "xyg-engine", "--bin", "geo_scale_bench"],
            cwd=ROOT,
            check=True,
        )
    binary = ROOT / "target/release/geo_scale_bench"
    if not binary.is_file():
        raise RuntimeError("Release benchmark binary missing")
    proof = source_snapshot(out)
    recorded = environment()
    recorded.update(proof)
    recorded.update(
        historical_only=False,
        concurrent_workloads_controlled=False,
        concurrent_workload_note="Frozen engine source; other host/browser/WASM development may run. No quiet-host or competitor timing claim.",
        measured_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
    )
    out.joinpath("environment.json").write_text(json.dumps(recorded, indent=2) + "\n")
    # Pin executable contents even if another developer rebuilds the release path.
    with tempfile.TemporaryDirectory(prefix="xyg-geo-bench-binary-") as tmp:
        pinned = Path(tmp) / binary.name
        shutil.copy2(binary, pinned)
        return measure(pinned, options, out, recorded)


def measure(binary: Path, options: argparse.Namespace, out: Path, recorded: dict) -> int:
    results = []
    for rows in options.rows:
        for iteration in range(1, options.repeat + 1):
            result = run(binary, rows, iteration, out)
            results.append(result)
            if result["returncode"]:
                out.joinpath("summary.json").write_text(
                    json.dumps(
                        dict(
                            schema_version=1,
                            stopped_after_explicit_failure=True,
                            measured_runs=results,
                            billion_row_measured=False,
                        ),
                        indent=2,
                    )
                    + "\n"
                )
                return 3
    planner = run(binary, 1_000_000_000, 1, out, planner=True)
    now = environment()["source_sha256"]
    recorded["source_drift_after_measurement"] = {
        path: value for path, value in now.items() if recorded["source_sha256"].get(path) != value
    }
    out.joinpath("environment.json").write_text(json.dumps(recorded, indent=2) + "\n")
    out.joinpath("summary.json").write_text(
        json.dumps(
            dict(
                schema_version=1,
                stopped_after_explicit_failure=False,
                measured_runs=results,
                planner=planner,
                billion_row_measured=False,
            ),
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
