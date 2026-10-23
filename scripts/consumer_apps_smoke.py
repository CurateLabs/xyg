"""Run the real Streamlit and Node/vanilla TypeScript application consumers.

Usage: uv run python scripts/consumer_apps_smoke.py --chromium /path/to/chrome
Requires built native/client/WASM artifacts and locked dev dependencies. Missing
inputs fail the gate. The apps use local synthetic data and loopback ports only.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from stage_node_packages import stage_facade, stage_platform

ROOT = Path(__file__).resolve().parents[1]


def installed_consumers(
    directory: Path, wheel: Path | None
) -> tuple[Path, Path, dict[str, str], dict[str, object]]:
    """Install finished artifacts, never editable sources or native overrides."""
    build_env = dict(os.environ)
    cargo = Path.home() / ".cargo" / "bin"
    if not shutil.which("cargo") and (cargo / "cargo").is_file():
        build_env["PATH"] = str(cargo) + os.pathsep + build_env["PATH"]
    if wheel is None:
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(directory / "artifacts")],
            cwd=ROOT,
            env={**build_env, "XYG_REQUIRE_WASM": "1"},
            check=True,
        )
        [wheel] = (directory / "artifacts").glob("*.whl")
    wheel = wheel.resolve()
    subprocess.run(
        [
            sys.executable,
            "scripts/verify_wheel.py",
            "--expect-native",
            "--require-wasm",
            str(wheel),
        ],
        cwd=ROOT,
        check=True,
    )
    constraints = subprocess.check_output(
        [
            "uv",
            "export",
            "--locked",
            "--group",
            "dev",
            "--group",
            "consumers",
            "--no-hashes",
            "--no-header",
            "--no-emit-project",
        ],
        cwd=ROOT,
        text=True,
    )
    requirements = directory / "constraints.txt"
    requirements.write_text(constraints)
    python = directory / "python" / "bin" / "python"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(python.parent.parent)], check=True
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--constraint",
            str(requirements),
            str(wheel),
            "streamlit",
            "pytest",
        ],
        check=True,
    )
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "PYTHONHOME", "XYG_NATIVE_LIB", "NODE_PATH"}
    }
    subprocess.run(
        [
            str(python),
            "-c",
            "import sys, importlib.util, pathlib, xyg; "
            "assert pathlib.Path(xyg.__file__).is_relative_to(sys.prefix); "
            "assert importlib.util.find_spec('reflex_xy') is None; "
            "import xyg._native as native; "
            "assert pathlib.Path(native._lib._name).is_relative_to(sys.prefix)",
        ],
        cwd=directory,
        env=clean_env,
        check=True,
    )
    # The framework is optional for core collection but mandatory here. A
    # broken/missing AppTest import must fail before pytest can skip the module.
    streamlit_version = subprocess.check_output(
        [
            str(python),
            "-c",
            "from streamlit.testing.v1 import AppTest; "
            "from importlib.metadata import version; print(version('streamlit'))",
        ],
        cwd=directory,
        env=clean_env,
        text=True,
    ).strip()
    config = directory / "pytest.ini"
    config.write_text("[pytest]\n")
    result_path = ROOT / "consumer-apps-smoke" / "streamlit-app-tests.xml"
    result = subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            "--noconftest",
            "-c",
            str(config),
            "-q",
            "--junitxml",
            str(result_path),
            str(ROOT / "tests/test_streamlit_consumer.py"),
        ],
        cwd=directory,
        env=clean_env,
        text=True,
        capture_output=True,
    )
    (result_path.with_suffix(".txt")).write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr)
    result.check_returncode()
    suites = ET.parse(result_path).getroot().iter("testsuite")
    counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
    if not counts["tests"] or any(counts[key] for key in ("failures", "errors", "skipped")):
        raise RuntimeError(f"required installed Streamlit AppTests did not all execute: {counts}")

    version = "0.0.0-test.1063"  # local-only candidate; never published
    platform_id = subprocess.check_output(
        ["node", "-p", "process.platform+'-'+process.arch"],
        text=True,
    ).strip()
    staged = directory / "staged"
    platform = stage_platform(platform_id=platform_id, wheel=wheel, output=staged, version=version)
    facade = stage_facade(
        client=ROOT / "packages/xy-client/dist/standalone.js", output=staged, version=version
    )
    client = staged / "xyg-client"
    client.mkdir()
    manifest = json.loads((ROOT / "packages/xy-client/package.json").read_text())
    manifest["version"] = version
    (client / "package.json").write_text(json.dumps(manifest))
    shutil.copytree(ROOT / "packages/xy-client/dist", client / "dist")
    archives = []
    hashes = {wheel.name: hashlib.sha256(wheel.read_bytes()).hexdigest()}
    for package in (platform, facade, client):
        packed = json.loads(
            subprocess.check_output(
                ["npm", "pack", "--json", "--pack-destination", str(directory)],
                cwd=package,
                text=True,
            )
        )
        if isinstance(packed, list):
            [entry] = packed
        else:
            [entry] = packed.values()
        archive = directory / entry["filename"]
        archives.append(str(archive))
        hashes[archive.name] = hashlib.sha256(archive.read_bytes()).hexdigest()
    node = directory / "node"
    node.mkdir()
    (node / "package.json").write_text('{"private":true,"type":"module"}')
    subprocess.run(
        ["npm", "install", "--offline", "--ignore-scripts", "--no-audit", "--no-fund", *archives],
        cwd=node,
        check=True,
    )
    # Finished npm archives must resolve inside this clean install.
    subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import {createRequire} from 'node:module';import {realpathSync} from 'node:fs';"
            "const r=createRequire(process.cwd()+'/package.json');"
            "for(const name of ['@curatelabs/xyg-node','@curatelabs/xyg'])"
            "if(!realpathSync(r.resolve(name)).startsWith(process.cwd()+'/node_modules/'))"
            "throw Error('consumer escaped installed artifacts');",
        ],
        cwd=node,
        check=True,
    )
    return python, node, hashes, {"streamlit": streamlit_version, "app_tests": counts}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"consumer exited ({process.returncode}) before serving {url}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    raise RuntimeError(f"consumer did not serve {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", required=True)
    parser.add_argument(
        "--wheel", type=Path, help="consume this exact wheel instead of building one"
    )
    args = parser.parse_args()
    (ROOT / "consumer-apps-smoke.json").unlink(missing_ok=True)
    subprocess.run(
        [
            "node",
            "node_modules/typescript/bin/tsc",
            "--noEmit",
            "--skipLibCheck",
            "--target",
            "ES2022",
            "--module",
            "ESNext",
            "--moduleResolution",
            "bundler",
            "--lib",
            "ES2022,DOM",
            "examples/vanilla-ts/app.ts",
        ],
        cwd=ROOT,
        check=True,
    )
    output = ROOT / "consumer-apps-smoke"
    output.mkdir(exist_ok=True)
    ports = (free_port(), free_port())
    commands = [
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "examples/streamlit/app.py",
            "--server.port",
            str(ports[0]),
            "--server.address",
            "127.0.0.1",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        ["node", "examples/vanilla-ts/server.mjs"],
    ]
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "PYTHONHOME", "XYG_NATIVE_LIB", "NODE_PATH"}
    }
    processes: list[subprocess.Popen[str]] = []
    with contextlib.ExitStack() as stack:
        directory = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix=".consumer-smoke-", dir=ROOT))
        )
        python, node_install, hashes, consumer_facts = installed_consumers(directory, args.wheel)
        commands[0][0] = str(python)
        commands[0][4] = str(ROOT / "examples/streamlit/app.py")
        commands[1][1] = str(ROOT / "examples/vanilla-ts/server.mjs")
        try:
            for i, command in enumerate(commands):
                log = stack.enter_context((output / f"host-{i}.log").open("w"))
                executable = str(python) if i == 0 else shutil.which("node")
                if executable is None:
                    raise RuntimeError("Node is required for the Node consumer")
                # Consume the Python app without Node on PATH, and the Node app
                # without Python on PATH. Build/test tools stay in this runner.
                executable_dir = directory / f"host-{i}-bin"
                executable_dir.mkdir()
                (executable_dir / ("python" if i == 0 else "node")).symlink_to(executable)
                host_env = {
                    **env,
                    "PORT": str(ports[i]),
                    "PATH": str(executable_dir),
                    "XYG_CONSUMER_INSTALL": str(node_install),
                }
                forbidden = ("node",) if i == 0 else ("python", "python3")
                if any(shutil.which(name, path=host_env["PATH"]) for name in forbidden):
                    raise RuntimeError("forbidden host runtime is available on consumer PATH")
                processes.append(
                    subprocess.Popen(
                        command,
                        cwd=directory,
                        env=host_env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                )
                wait_for(f"http://127.0.0.1:{ports[i]}", processes[-1])
            subprocess.run(
                [
                    "node",
                    "scripts/consumer_apps_smoke.mjs",
                    "--chromium",
                    args.chromium,
                    "--streamlit-url",
                    f"http://127.0.0.1:{ports[0]}",
                    "--node-url",
                    f"http://127.0.0.1:{ports[1]}",
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
        except Exception:
            for path in sorted(output.glob("host-*.log")):
                print(f"{path.name}:\n{path.read_text()[-4000:]}", file=sys.stderr)
            raise
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    report = json.loads((ROOT / "consumer-apps-smoke.json").read_text())
    report["python"] = sys.version.split()[0]
    report.update(consumer_facts)
    report["installed_artifacts"] = hashes
    report["host_path_isolation"] = {"python_without_node": True, "node_without_python": True}
    (ROOT / "consumer-apps-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
