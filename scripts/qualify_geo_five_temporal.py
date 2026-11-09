#!/usr/bin/env python3
"""Run one qualification command with source, runtime, exit and log bindings."""

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--directory", default="target/task-tmp/five-temporal-successor")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    destination = ROOT / args.directory
    destination.mkdir(parents=True, exist_ok=True)
    record = destination / (args.name + ".receipt.json")
    if record.exists():
        raise SystemExit("receipt exists; choose a new name")
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).split(b"\0")
    compiled_manifest = (
        "spec/performance/dense-native-navigation-union-2026-11-08/compiled-input-equality.json"
    )
    compiled_inputs = json.loads((ROOT / compiled_manifest).read_text())
    assert len(compiled_inputs) == 324
    for name, expected in compiled_inputs.items():
        if digest(ROOT / name)["sha256"] != expected:
            raise SystemExit("native/config input differs from qualified parent: " + name)
    inputs = {}
    for raw in paths:
        if not raw:
            continue
        name = raw.decode()
        path = ROOT / name
        required = name in compiled_inputs or name == compiled_manifest
        if not path.is_file() or not (
            required
            or name.startswith(
                (
                    "crates/",
                    "python/",
                    "js/",
                    "scripts/",
                    "tests/",
                    "vendor/",
                    ".cargo/",
                    "spec/design/",
                )
            )
            or name.startswith("packages/xy-node/")
            or name
            in (
                "Cargo.toml",
                "Cargo.lock",
                "rust-toolchain.toml",
                "package.json",
                "package-lock.json",
                "pyproject.toml",
                "uv.lock",
                "hatch_build.py",
                "AGENTS.md",
            )
        ):
            continue
        if not required and path.suffix not in (
            ".rs",
            ".py",
            ".js",
            ".ts",
            ".mjs",
            ".json",
            ".ipynb",
            ".toml",
            ".lock",
            ".md",
        ):
            continue
        inputs[name] = digest(path)
        archive = destination / "source" / (inputs[name]["sha256"] + ".gz")
        if not archive.exists():
            archive.parent.mkdir(exist_ok=True)
            archive.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    runtime = {}
    runtime_paths = [
        os.environ.get("XYG_NATIVE_LIB"),
        os.environ.get("XYG_CLIENT_ESM"),
        os.environ.get("XYG_WASM_ARTIFACT", "packages/xy-client/dist/xyg-wasm.wasm"),
        os.environ.get("XYG_GEO_CATALOG_NATIVE", "target/debug/geo_layers_conformance"),
        "packages/xy-client/dist/index.js",
        "packages/xy-client/dist/standalone.js",
        "python/xyg/static/index.js",
        "python/xyg/static/standalone.js",
        command[0],
        *[str(p) for p in (ROOT / "target/debug").glob("*conformance")],
        os.environ.get("XYG_CHROMIUM"),
    ]
    for value in runtime_paths:
        if value and Path(value).is_file():
            runtime[value] = digest(Path(value))
    started = time.time()
    output = destination / (args.name + ".log")
    with output.open("wb") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    changed = [
        name
        for name, before in inputs.items()
        if not (ROOT / name).is_file() or digest(ROOT / name) != before
    ]
    runtime_changed = [
        name
        for name, before in runtime.items()
        if not Path(name).is_file() or digest(Path(name)) != before
    ]
    data = {
        "command": command,
        "cwd": str(ROOT),
        "environment": {
            k: v
            for k, v in os.environ.items()
            if k.startswith("XYG_") or k in ("TMPDIR", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE")
        },
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source": inputs,
        "compiledInputCount": len(compiled_inputs),
        "sourceChangedDuringRun": changed,
        "runtime": runtime,
        "runtimeChangedDuringRun": runtime_changed,
        "exit": result.returncode,
        "elapsedSeconds": time.time() - started,
        "log": {"path": str(output), **digest(output)},
    }
    record.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({"receipt": str(record), "exit": result.returncode, "sourceChanged": changed}))
    return result.returncode or bool(changed) or bool(runtime_changed)


if __name__ == "__main__":
    raise SystemExit(main())
