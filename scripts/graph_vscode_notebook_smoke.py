#!/usr/bin/env python3
"""Run a real VS Code Jupyter notebook with private server/profile ownership.

Requires an installed app and Jupyter extensions, plus an existing Python
server environment. Uses DISPLAY, or explicit authenticated --tcp-xvfb.
Profiles, Jupyter runtime files and X cookies contain secrets: never archive
those directories. The supported report/log allowlist is documented separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import time
import urllib.request
from pathlib import Path

if __package__:
    from .install_vscode_graph_notebook import application_payload, installed_payloads
else:
    from install_vscode_graph_notebook import application_payload, installed_payloads

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--extensions", required=True, type=Path)
    parser.add_argument("--server-python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/vscode_graph_notebook")
    parser.add_argument("--node", type=Path, default=Path(shutil.which("node") or "node"))
    parser.add_argument("--tcp-xvfb", action="store_true")
    parser.add_argument("--fail-after-cell", choices=(1,), type=int)
    args = parser.parse_args()
    code, extensions, python, node, fixture = (
        path.absolute()
        for path in (args.code, args.extensions, args.server_python, args.node, args.fixture)
    )
    native = Path(
        os.environ.get("XYG_NATIVE_LIB", ROOT / "target/release/libxyg_core.so")
    ).resolve()
    if native != (ROOT / "target/release/libxyg_core.so").resolve():
        parser.error(
            "unchanged notebook fixture requires this checkout target/release/libxyg_core.so"
        )
    if not all(path.is_file() for path in (code, python, node, native)):
        parser.error("installed app, Node, server Python and explicit native core are required")
    if not extensions.is_dir() or not fixture.is_dir():
        parser.error("installed Jupyter extensions and fixture directory are required")
    installation_dir = extensions.parent
    installation = json.loads((installation_dir / "installation.json").read_text())
    lock_path = ROOT / "tests/vscode_graph_notebook/toolchain.json"
    lock = json.loads(lock_path.read_text())
    if (
        installation["lockSha256"] != hashlib.sha256(lock_path.read_bytes()).hexdigest()
        or Path(installation["code"]) != code
        or Path(installation["extensions"]) != extensions
        or installed_payloads(lock, extensions, installation_dir / "downloads")
        != installation["payloads"]
        or application_payload(lock["application"], code.parent)
        != installation["applicationPayload"]
        or installation["applicationExecutable"]
        != {
            "bytes": code.stat().st_size,
            "sha256": hashlib.file_digest(code.open("rb"), "sha256").hexdigest(),
        }
    ):
        raise ValueError("installed desktop cohort identity mismatch")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)  # Preserve every previous failed attempt.
    (out / "installation.json").write_text(json.dumps(installation, indent=2) + "\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("GH_TOKEN", "GITHUB_TOKEN", "VSCODE_IPC_HOOK_CLI")
        and not key.endswith("_API_KEY")
    }
    port, debug = free_port(), free_port()
    env.update(
        XYG_NATIVE_LIB=str(native),
        PYTHONPATH=f"{ROOT}/python:{ROOT}/tests",
        TMPDIR=os.environ.get("TMPDIR", "/var/tmp"),
        XYG_NOTEBOOK_PROBE=str(out),
        XYG_NOTEBOOK_SERVER=f"http://127.0.0.1:{port}",
        XYG_NOTEBOOK_DEBUG_PORT=str(debug),
        XYG_VSCODE_VERSION=lock["application"]["version"],
        XYG_JUPYTER_EXTENSION_VERSION=next(
            row["version"] for row in lock["extensions"] if row["id"] == "ms-toolsai.jupyter"
        ),
    )
    env.pop("XYG_VSCODE_FAIL_AFTER_CELL", None)
    if args.fail_after_cell is not None:
        env["XYG_VSCODE_FAIL_AFTER_CELL"] = str(args.fail_after_cell)
    token = secrets.token_hex(32)
    env.update(JUPYTER_TOKEN=token, XYG_NOTEBOOK_TOKEN=token)
    for key, directory in (
        ("JUPYTER_RUNTIME_DIR", "runtime"),
        ("JUPYTER_CONFIG_DIR", "config"),
        ("JUPYTER_DATA_DIR", "data"),
    ):
        path = out / directory
        path.mkdir()
        env[key] = str(path)
    shutil.copyfile(ROOT / "tests/notebook_graph_progressive.ipynb", out / "graph.ipynb")
    user = out / "user/User"
    user.mkdir(parents=True)
    settings = {
        "telemetry.telemetryLevel": "off",
        "extensions.autoCheckUpdates": False,
        "extensions.autoUpdate": False,
        "workbench.startupEditor": "none",
        "security.workspace.trust.enabled": False,
        "git.openRepositoryInParentFolders": "never",
        "git.autofetch": False,
        "jupyter.widgetScriptSources": [],
    }
    (user / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    owned = []
    auth = out / "xauthority"
    command = []

    def spawn(command, filename):
        log = (out / filename).open("wb")
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        owned.append((process, log))
        return process

    def request(path):
        url = f"http://127.0.0.1:{port}" + path
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Authorization": "token " + token}), timeout=5
        ) as response:
            return response.status, response.read()

    try:
        server = spawn(
            [
                str(python),
                "-m",
                "notebook",
                "--no-browser",
                "--ServerApp.ip=127.0.0.1",
                f"--ServerApp.port={port}",
                f"--ServerApp.root_dir={out}",
                "--ServerApp.show_banner=False",
                "--ServerApp.password=",
            ],
            "server.log",
        )
        for _ in range(200):
            try:
                status, _ = request("/api/status")
                if status == 200:
                    break
            except Exception:
                if server.poll() is not None:
                    raise RuntimeError("server exited; inspect server.log") from None
                time.sleep(0.1)
        else:
            raise RuntimeError("authenticated Jupyter server did not become ready")
        _, raw = request("/api/kernelspecs")
        (out / "kernelspecs.json").write_bytes(raw)
        assets = []
        for name in (
            "anywidget/index.js",
            "anywidget/extension.js",
            "jupyter-js-widgets/extension.js",
        ):
            status, raw = request("/nbextensions/" + name)
            installed = python.parent.parent / "share/jupyter/nbextensions" / name
            if status != 200 or raw != installed.read_bytes():
                raise RuntimeError("served widget assets differ from installed environment")
            assets.append(
                {
                    "path": "/nbextensions/" + name,
                    "status": status,
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "installedBytesEqual": True,
                }
            )
        (out / "served-widget-assets.json").write_text(json.dumps(assets, indent=2) + "\n")
        environment = subprocess.check_output(
            [
                str(python),
                "-c",
                "import importlib.metadata as m,json,sys; print(json.dumps({'python':sys.version,'packages':{n:m.version(n) for n in ['notebook','jupyterlab','nbclassic','ipykernel','anywidget','ipywidgets','widgetsnbextension','jupyterlab_widgets']}}))",
            ],
            env=env,
            text=True,
        )
        (out / "server-environment.json").write_text(environment)
        if args.tcp_xvfb:
            for display in range(104, 200):
                with socket.socket() as sock:
                    try:
                        sock.bind(("127.0.0.1", 6000 + display))
                        break
                    except OSError:
                        continue
            else:
                raise RuntimeError("no free private X11 TCP display")
            entry = struct.pack(">H", 65535)
            for value in (
                b"",
                str(display).encode(),
                b"MIT-MAGIC-COOKIE-1",
                secrets.token_bytes(16),
            ):
                entry += struct.pack(">H", len(value)) + value
            auth.write_bytes(entry)
            auth.chmod(0o600)
            env.update(DISPLAY=f"127.0.0.1:{display}", XAUTHORITY=str(auth))
            xvfb = spawn(
                [
                    "sudo",
                    "-n",
                    "Xvfb",
                    f":{display}",
                    "-screen",
                    "0",
                    "1280x900x24",
                    "-nolock",
                    "-nolisten",
                    "unix",
                    "-listen",
                    "tcp",
                    "-auth",
                    str(auth),
                ],
                "xvfb.log",
            )
            for _ in range(100):
                if xvfb.poll() is not None:
                    raise RuntimeError("private Xvfb failed")
                try:
                    with socket.create_connection(("127.0.0.1", 6000 + display), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("private Xvfb did not become ready")
        elif not env.get("DISPLAY"):
            raise RuntimeError("provide DISPLAY or explicit --tcp-xvfb")
        command = [
            str(code),
            "--no-sandbox",
            "--disable-gpu-sandbox",
            "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader",
            f"--remote-debugging-port={debug}",
            "--user-data-dir=" + str(out / "user"),
            "--extensions-dir=" + str(extensions),
            "--extensionDevelopmentPath=" + str(fixture),
            "--skip-welcome",
            "--skip-release-notes",
            str(out / "graph.ipynb"),
        ]
        app = spawn(command, "application.log")
        attachment = spawn([str(node), str(fixture / "page.mjs")], "attach.log")
        attachment_exit = attachment.wait(timeout=220)
        app_exit = app.wait(timeout=45)
        _, raw = request("/api/kernels")
        kernels = [
            {key: value[key] for key in ("id", "name", "execution_state", "connections")}
            for value in json.loads(raw)
        ]
        if len(kernels) == 1:
            info = subprocess.run(
                [str(python), str(fixture / "kernel_info.py"), kernels[0]["id"]],
                env=env,
                cwd=ROOT,
                timeout=15,
                capture_output=True,
                text=True,
            )
            (out / "kernel-info.log").write_text(info.stderr)
            if info.returncode:
                raise RuntimeError("actual kernel identity query failed; inspect kernel-info.log")
            (out / "kernel-info.json").write_text(
                json.dumps(json.loads(info.stdout), indent=2) + "\n"
            )
            for _ in range(50):
                _, raw = request("/api/kernels")
                kernels = [
                    {key: value[key] for key in ("id", "name", "execution_state", "connections")}
                    for value in json.loads(raw)
                ]
                if (
                    len(kernels) == 1
                    and kernels[0]["execution_state"] == "idle"
                    and kernels[0]["connections"] == 0
                ):
                    break
                time.sleep(0.1)
        record = {
            "command": command,
            "attachmentExit": attachment_exit,
            "applicationExit": app_exit,
            "intentionalFailureAfterCell": args.fail_after_cell,
            "serverKernels": kernels,
            "expectedVersions": {
                "vscode": lock["application"]["version"],
                "jupyterExtension": next(
                    row["version"]
                    for row in lock["extensions"]
                    if row["id"] == "ms-toolsai.jupyter"
                ),
            },
        }
        (out / "run-result.json").write_text(json.dumps(record, indent=2) + "\n")
        if (
            attachment_exit
            or app_exit
            or json.loads((out / "controller-complete.json").read_text()).get("ok") is not True
        ):
            raise RuntimeError("actual notebook failed; inspect retained original logs/exits")
        if (
            len(kernels) != 1
            or kernels[0]["name"] != "python3"
            or kernels[0]["execution_state"] != "idle"
        ):
            raise RuntimeError("actual Python kernel did not finish idle")
        print("Actual VS Code notebook application and attachment exited successfully")
        return 0
    finally:
        cleanup = []
        for process, log in reversed(owned):
            if process.poll() is None:
                if process.args[0] == "sudo":
                    subprocess.run(
                        ["sudo", "-n", "kill", "-TERM", str(process.pid)],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if process.args[0] == "sudo":
                        subprocess.run(
                            ["sudo", "-n", "kill", "-KILL", str(process.pid)],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    else:
                        process.kill()
                    process.wait(timeout=10)
            cleanup.append(
                {
                    "executable": Path(process.args[0]).name,
                    "exit": process.returncode,
                    "terminated": process.poll() is not None,
                }
            )
            log.close()
        auth.unlink(missing_ok=True)
        (out / "cleanup.json").write_text(
            json.dumps({"owned": cleanup, "cookieRemoved": not auth.exists()}, indent=2) + "\n"
        )


if __name__ == "__main__":
    raise SystemExit(main())
