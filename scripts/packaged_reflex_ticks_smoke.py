#!/usr/bin/env python3
"""Compile and exercise actual Reflex XYCharts from one installed wheel.

Provision an isolated environment with the wheel's Reflex extra first. This
runner verifies its installed bytes, copies only the small application fixture,
and retains the production build/runtime logs and real-browser results.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/packaged_reflex_ticks_app"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_install(python: Path, wheel: Path, cwd: Path, env: dict[str, str]) -> dict:
    probe = """
import hashlib, importlib.metadata as m, json, pathlib, platform
import xyg, reflex_xy, xyg.kernels as k
base = pathlib.Path(xyg.__file__).resolve().parent.parent
if pathlib.Path(reflex_xy.__file__).resolve().parent.parent != base:
 raise ValueError('xyg and reflex_xy must belong to the same isolated install')
names = sorted(p.relative_to(base).as_posix() for package in ['xyg','reflex_xy']
 for p in (base/package).rglob('*')
 if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
print(json.dumps({'version':m.version('xyg'),'reflex':m.version('reflex'),'backend':k.BACKEND,
 'xygRoot':str(pathlib.Path(xyg.__file__).resolve().parent),'python':platform.python_version(),
 'platform':platform.platform(),'files':{n:hashlib.sha256((base/n).read_bytes()).hexdigest() for n in names},
 'dependencies':dict(sorted((d.metadata['Name'],d.version) for d in m.distributions()))}))
"""
    result = json.loads(
        subprocess.check_output([str(python), "-c", probe], cwd=cwd, env=env, text=True)
    )
    if Path(result["xygRoot"]).is_relative_to(ROOT) or result["backend"] != "native":
        raise ValueError("proof requires an installed native wheel outside the checkout")
    with zipfile.ZipFile(wheel) as archive:
        expected_names = {
            name
            for name in archive.namelist()
            if name.startswith(("xyg/", "reflex_xy/"))
            and not name.endswith(("/", ".pyc"))
            and "__pycache__" not in Path(name).parts
        }
        if set(result["files"]) != expected_names:
            raise ValueError("installed package file inventory differs from exact wheel")
        for name, expected in result["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"installed file differs from exact wheel: {name}")
        metadata = next(name for name in archive.namelist() if name.endswith("/METADATA"))
        version = next(
            line.removeprefix("Version: ")
            for line in archive.read(metadata).decode().splitlines()
            if line.startswith("Version: ")
        )
        if result["version"] != version:
            raise ValueError("installed distribution version differs from wheel metadata")
    result["fileCount"] = len(result["files"])
    result["fileInventorySha256"] = hashlib.sha256(
        json.dumps(result["files"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", type=Path, required=True, help="isolated installed-wheel Python"
    )
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--work-root", type=Path, help="temporary application parent (disk-backed if needed)"
    )
    parser.add_argument("--source-commit", help="declared immutable wheel source")
    parser.add_argument("--base-commit", help="base commit of an uncommitted build")
    parser.add_argument("--source-ledger", type=Path, help="source hashes captured at build")
    parser.add_argument("--source-state", choices=("clean", "uncommitted"), default="clean")
    args = parser.parse_args()
    if args.source_commit and not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("--source-commit must be a complete lowercase Git SHA")
    if args.base_commit and not re.fullmatch(r"[0-9a-f]{40}", args.base_commit):
        parser.error("--base-commit must be a complete lowercase Git SHA")
    if args.source_state == "uncommitted" and (
        args.source_commit or not args.base_commit or not args.source_ledger
    ):
        parser.error(
            "uncommitted builds require --base-commit and --source-ledger, "
            "and cannot declare --source-commit"
        )
    # Preserve a virtualenv interpreter's symlink: resolving it selects the
    # base interpreter and loses the installed wheel environment.
    python = Path(os.path.abspath(args.python))
    wheel, output = args.wheel.resolve(), args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    source_ledger = None
    if args.source_ledger:
        source_ledger = output.with_name(output.stem + ".source.json")
        source_ledger.write_bytes(args.source_ledger.read_bytes())
    env = dict(os.environ)
    for key in ("PYTHONPATH", "XYG_NATIVE_LIB", "VIRTUAL_ENV"):
        env.pop(key, None)
    env["REFLEX_TELEMETRY_ENABLED"] = "false"
    if args.work_root:
        args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="xyg-packaged-reflex-app-", dir=args.work_root
    ) as temporary:
        app_dir = Path(temporary) / "app"
        shutil.copytree(FIXTURE, app_dir)
        installed = inspect_install(python, wheel, app_dir, env)
        standalone_html = Path(temporary) / "density.html"
        subprocess.run(
            [str(python), str(FIXTURE / "standalone_export.py"), str(standalone_html)],
            cwd=app_dir,
            env=env,
            check=True,
            timeout=60,
        )
        retained_html = output.with_name(output.stem + ".export.html.gz")
        retained_html.write_bytes(gzip.compress(standalone_html.read_bytes(), mtime=0))
        standalone_report = output.with_name(output.stem + ".export.json")
        standalone_result = subprocess.run(
            ["node", str(ROOT / "scripts/packaged_density_export_browser.mjs")],
            cwd=app_dir,
            env={
                **env,
                "XYG_DENSITY_EXPORT": str(standalone_html),
                "XYG_DENSITY_EXPORT_REPORT": str(standalone_report),
            },
            check=False,
            timeout=90,
        )
        if standalone_result.returncode:
            raise SystemExit(standalone_result.returncode)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        env["XYG_REFLEX_PORT"] = str(port)
        compile_log = output.with_name(output.stem + ".compile.log")
        runtime_log = output.with_name(output.stem + ".runtime.log")
        with compile_log.open("w") as log:
            subprocess.run(
                [str(python), "-m", "reflex", "compile", "--dry"],
                cwd=app_dir,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=300,
            )
        with runtime_log.open("w") as log:
            server = subprocess.Popen(
                [str(python), "-m", "reflex", "run", "--env", "prod", "--single-port"],
                cwd=app_dir,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                origin = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        raise RuntimeError(f"Reflex exited; inspect {runtime_log}")
                    try:
                        with urllib.request.urlopen(origin, timeout=1) as response:
                            if response.status == 200:
                                break
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(0.2)
                else:
                    raise TimeoutError(f"Reflex never became ready; inspect {runtime_log}")
                runtime_processes = json.loads(
                    subprocess.check_output(
                        [
                            str(python),
                            "-c",
                            "import json,psutil,sys; p=psutil.Process(int(sys.argv[1])); "
                            "print(json.dumps([{'pid':x.pid,'name':x.name(),'exe':x.exe()} "
                            "for x in [p,*p.children(recursive=True)]]))",
                            str(server.pid),
                        ],
                        cwd=app_dir,
                        env=env,
                        text=True,
                    )
                )
                if any(
                    Path(process["exe"]).name in {"node", "nodejs", "bun"}
                    for process in runtime_processes
                ):
                    raise RuntimeError("compiled Python app still requires a Node/Bun process")
                asset_dir = app_dir / "assets/external/reflex_xy/assets"
                for filename, package_path in (
                    ("xy_client.js", "xyg/static/index.js"),
                    ("wasm-worker.js", "xyg/static/wasm-worker.js"),
                    ("xyg-wasm.wasm", "xyg/static/xyg-wasm.wasm"),
                ):
                    if sha256(asset_dir / filename) != installed["files"][package_path]:
                        raise ValueError(
                            f"compiled app linked different packaged bytes: {filename}"
                        )
                browser_report = output.with_name(output.stem + ".browser.json")
                browser_result = subprocess.run(
                    ["node", str(ROOT / "scripts/packaged_reflex_ticks_browser.mjs")],
                    cwd=app_dir,
                    env={
                        **env,
                        "XYG_REFLEX_ORIGIN": origin,
                        "XYG_REFLEX_REPORT": str(browser_report),
                    },
                    check=False,
                    timeout=180,
                )
                frontend_records = []
                for name in ("package.json", "bun.lock", "bun.lockb", "package-lock.json"):
                    source = app_dir / ".web" / name
                    if source.exists():
                        destination = output.with_name(output.stem + ".frontend." + name)
                        shutil.copyfile(source, destination)
                        frontend_records.append(destination)
            finally:
                if server.poll() is None:
                    os.killpg(server.pid, signal.SIGTERM)
                    try:
                        server.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(server.pid, signal.SIGKILL)
                        server.wait()
        harness = [
            ROOT / "scripts/packaged_reflex_ticks_smoke.py",
            ROOT / "scripts/packaged_reflex_ticks_browser.mjs",
            ROOT / "scripts/packaged_density_export_browser.mjs",
            *sorted(path for path in FIXTURE.rglob("*.py") if "__pycache__" not in path.parts),
        ]
        report = {
            "schemaVersion": 1,
            "status": "passed" if browser_result.returncode == 0 else "failed",
            "sourceCommit": args.source_commit,
            "artifactSource": (
                "working-tree-build" if args.source_state == "uncommitted" else "immutable-artifact"
            ),
            "artifactCommit": args.source_commit,
            "baseCommit": args.base_commit,
            "sourceState": args.source_state,
            "wheel": {"file": wheel.name, "sha256": sha256(wheel)},
            "installed": installed,
            "runtimeProcesses": runtime_processes,
            "harness": {str(path.relative_to(ROOT)): sha256(path) for path in harness},
            "evidence": {
                path.name: sha256(path)
                for path in (
                    compile_log,
                    runtime_log,
                    browser_report,
                    standalone_report,
                    *frontend_records,
                    *([source_ledger] if source_ledger else []),
                )
            },
            "publicExport": {
                "sha256": sha256(standalone_html),
                "bytes": standalone_html.stat().st_size,
                "localCompressedFile": str(retained_html),
                "localCompressedSha256": sha256(retained_html),
                "retention": "Generated client bundle remains local; recreate with exact wheel and fixture.",
            },
            "limitations": [
                "One Linux x64 installed-wheel and Reflex version; not final RC or full #54 acceptance.",
                "Frontend compilation provisions Node/Bun dependencies; no claim about a Node-free build.",
                "Tick WASM setup fails closed; the separate file export cases retain Rust density overview pixels.",
            ],
        }
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"packaged Reflex evidence: {output}")
        if browser_result.returncode:
            raise SystemExit(browser_result.returncode)


if __name__ == "__main__":
    main()
