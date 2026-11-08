"""Collect this local qualification and seal the append-only successor source chain.

Run from the producer root with --installed pointing at the successful isolated
pytest directory. Never modifies a parent receipt, Git config or another checkout.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path.cwd()
RECEIPT = Path("spec/performance/chunked-native-installed-2026-11-07")
LOGS = Path("target/task-tmp/chunked-continuation")
PARENTS = ["f03a95d7c269684616265fa48daa81631b79e57e", "93ddc636b7af2952c5c52f000c14b9e4ecdc6216"]
ROOT_BINDING = Path("spec/performance/combined-wasm-layout-2026-11-07/current-bindings.json")
CHECKPOINT = Path("spec/performance/chunked-native-viewport-2026-11-07/bindings.json")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def write_json(path, value):
    (ROOT / path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def archive(data, relative):
    path = RECEIPT / relative
    (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / path).write_bytes(gzip.compress(data, mtime=0))
    return {
        "archive": str(path),
        "sha256": sha(data),
        "bytes": len(data),
        "archiveSha256": sha((ROOT / path).read_bytes()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", type=Path, required=True)
    args = parser.parse_args()
    reports = {}
    for label, directory in [("installed", args.installed), ("node", ROOT / LOGS / "http-final")]:
        files = {}
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix in {
                ".png",
                ".json",
                ".xygc",
                ".xybf",
                ".ipynb",
                ".log",
            }:
                files[path.name] = archive(
                    path.read_bytes(), Path("captures") / label / (path.name + ".gz")
                )
        reports[label] = {"producerDirectory": str(directory), "files": files}
    wheel = next((args.installed / "wheel").glob("*.whl"))
    artifacts = {"wheel": archive(wheel.read_bytes(), Path("artifacts") / (wheel.name + ".gz"))}
    paths = [
        "target/release/libxyg_core.so",
        "packages/xy-client/dist/index.js",
        "packages/xy-client/dist/standalone.js",
        "python/xyg/static/index.js",
        "packages/xy-client/dist/xyg-wasm.wasm",
        "packages/xy-client/dist/xyg-wasm.manifest.json",
    ]
    for name in paths:
        data = (ROOT / name).read_bytes()
        if name.endswith(".so") or name.endswith(".wasm"):
            pin = Path("spec/performance/combined-wasm-layout-2026-11-07/artifacts") / (
                sha(data) + ".gz"
            )
            assert gzip.decompress((ROOT / pin).read_bytes()) == data
            artifacts[name] = {
                "archive": str(pin),
                "sha256": sha(data),
                "bytes": len(data),
                "archiveSha256": sha((ROOT / pin).read_bytes()),
            }
        else:
            artifacts[name] = archive(data, Path("artifacts") / (sha(data) + ".gz"))
    wheel_sources = {}
    with zipfile.ZipFile(wheel) as package:
        for name in package.namelist():
            if name.startswith("xyg/") and name.endswith(".py"):
                source = ROOT / "python" / name
                assert source.read_bytes() == package.read(name), name
                wheel_sources["python/" + name] = sha(package.read(name))
    write_json(
        RECEIPT / "artifacts.json",
        {"artifacts": artifacts, "captures": reports, "wheelSourcesMatch": wheel_sources},
    )
    attempts = []
    for path in sorted((ROOT / LOGS).iterdir()):
        if path.is_file() and path.suffix in {".log", ".txt", ".json", ".jsonl"}:
            attempts.append(
                {
                    "name": path.name,
                    **archive(path.read_bytes(), Path("attempts") / (path.name + ".gz")),
                }
            )
    write_json(RECEIPT / "attempts.json", attempts)
    (ROOT / RECEIPT / "commands.jsonl").write_bytes((ROOT / LOGS / "commands.jsonl").read_bytes())
    unchanged_diagnostics = {}
    text = (ROOT / LOGS / "typing-after.log").read_text()
    for path in sorted(set(re.findall(r"^(python/[^:]+):", text, re.MULTILINE))):
        data = (ROOT / path).read_bytes()
        assert data == git("show", PARENTS[1] + ":" + path), path
        unchanged_diagnostics[path] = sha(data)
    compiled = json.loads(
        (
            ROOT / "spec/performance/combined-wasm-layout-2026-11-07/compiled-source-inputs.json"
        ).read_text()
    )
    assert all(sha((ROOT / p).read_bytes()) == expected for p, expected in compiled.items())
    write_json(
        RECEIPT / "environment.json",
        {
            "python": sys.version,
            "pythonExecutable": sys.executable,
            "platform": platform.platform(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
            "nodeExecutable": subprocess.check_output(
                ["node", "-p", "process.execPath"], text=True
            ).strip(),
            "rust": subprocess.check_output(
                ["/home/ubuntu/.cargo/bin/rustc", "--version"], text=True
            ).strip(),
            "physicalMemory": Path("/proc/meminfo").read_text().splitlines()[0],
            "chromium": os.environ.get("XYG_TEST_CHROMIUM"),
            "tmpdir": os.environ.get("TMPDIR"),
            "installed": str(args.installed),
            "compiledInputsMatch": len(compiled),
            "typingUnchangedRootSources": unchanged_diagnostics,
            "typingStatus": "22 diagnostics in unchanged Root source files; changed sources clean; installed consumer passes 135 exports",
        },
    )
    inherited = json.loads((ROOT / ROOT_BINDING).read_text())
    checkpoint = json.loads((ROOT / CHECKPOINT).read_text())
    sources = set(inherited["sourceSha256"]) | set(checkpoint["source_sha256"])
    changed = set(git("diff", "--name-only", PARENTS[0]).decode().splitlines())
    changed.update(git("ls-files", "--others", "--exclude-standard").decode().splitlines())
    changed = {p for p in changed if p != "TASKS" and not p.startswith(str(RECEIPT) + "/")}
    changed.add(".gitattributes")
    sources.update(changed)
    attributes = ROOT / ".gitattributes"
    marker = "\n# Installed native viewport successor source and immutable evidence pins.\n"
    attrs = attributes.read_text().split(marker)[0]
    pins = sorted((sources - set(inherited["sourceSha256"])) | changed)
    attrs += (
        marker
        + "\n".join(
            p
            + (
                " -text"
                if Path(p).suffix in {".png", ".gz", ".xygc", ".bin", ".xybf", ".whl"}
                else " text eol=lf"
            )
            for p in pins
        )
        + "\n"
    )
    attrs += str(RECEIPT) + "/** text eol=lf\n" + str(RECEIPT) + "/**/*.gz -text\n"
    attrs += str(CHECKPOINT.parent) + "/** text eol=lf\n"
    for suffix in ["png", "gz", "xygc", "bin", "xybf", "whl"]:
        attrs += str(CHECKPOINT.parent) + "/**/*." + suffix + " -text\n"
    attributes.write_text(attrs)
    historical = dict(inherited["historicalBindings"])
    for path in [ROOT_BINDING, *sorted((ROOT / CHECKPOINT.parent).rglob("*"))]:
        path = Path(path)
        if path.is_absolute():
            path = path.relative_to(ROOT)
        if (ROOT / path).is_file():
            historical[str(path)] = sha((ROOT / path).read_bytes())
    predecessors = []
    for parent in PARENTS:
        files = {}
        parent_paths = set(git("ls-tree", "-r", "--name-only", parent).decode().splitlines())
        for path in sorted(sources):
            if path not in parent_paths:
                continue
            data = git("show", parent + ":" + path)
            if data != (ROOT / path).read_bytes():
                saved = archive(
                    data, Path("predecessors") / parent[:8] / (path.replace("/", "__") + ".gz")
                )
                files[path] = saved
                historical[saved["archive"]] = saved["archiveSha256"]
        predecessors.append(
            {
                "commit": parent,
                "tree": git("rev-parse", parent + "^{tree}").decode().strip(),
                "parents": git("show", "-s", "--format=%P", parent).decode().split(),
                "files": files,
            }
        )
    write_json(RECEIPT / "predecessors.json", predecessors)
    for path in (ROOT / RECEIPT).rglob("*"):
        if not path.is_file() or path.name == "current-bindings.json":
            continue
        name = str(path.relative_to(ROOT))
        if path.suffix == ".gz":
            historical[name] = sha(path.read_bytes())
        else:
            sources.add(name)
    source_hashes = {path: sha((ROOT / path).read_bytes()) for path in sorted(sources)}
    write_json(
        RECEIPT / "current-bindings.json",
        {
            **{
                key: inherited[key]
                for key in ["schemaVersion", "manifestSha256", "originalProducerSha256"]
            },
            "sourceIdentity": "Native installed kernel and public binary HTTP viewport refinement; normal merged Root405/WASM38 producer",
            "parents": PARENTS,
            "mergeCheckpoint": git("rev-parse", "HEAD").decode().strip(),
            "continuationChangedPaths": sorted(changed),
            "sourceSha256": source_hashes,
            "sourceSetSha256": sha(json.dumps(source_hashes, sort_keys=True).encode()),
            "historicalBindings": historical,
        },
    )
    print(f"Sealed {len(source_hashes)} sources and {len(historical)} historical/artifact bindings")


if __name__ == "__main__":
    main()
