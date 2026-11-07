#!/usr/bin/env python3
"""Run the real mounted temporal WebviewPanel journey with an installed VS Code.

Use an existing DISPLAY, or --tcp-xvfb when /tmp cannot hold X11 lock/socket
files. That explicit mode starts an authenticated private Xvfb using sudo -n;
its cookie is local, mode0600, never logged, and removed on exit.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tcp-xvfb", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    native = ROOT / "target/release/libxyg_core.so"
    if not args.code.is_file() or not native.is_file():
        parser.error("installed VS Code executable and this checkout's native core are required")
    env = dict(
        os.environ,
        TMPDIR=os.environ.get("TMPDIR", "/var/tmp"),
        XYG_NATIVE_LIB=str(native),
        XYG_GEO_VSCODE_REPORT=str(output / "report.json"),
        XYG_GEO_VSCODE_CAPTURE_READY=str(output / "capture-ready"),
    )
    auth, xvfb, process = output / "xauthority", None, None
    ready = output / "capture-ready"
    done = output / "capture-ready.done"
    ready.unlink(missing_ok=True)
    done.unlink(missing_ok=True)
    xcommand = []
    with (output / "xvfb.log").open("wb") as xlog, (output / "application.log").open("wb") as log:
        try:
            if args.tcp_xvfb:
                for display in range(104, 200):
                    with socket.socket() as probe:
                        try:
                            probe.bind(("127.0.0.1", 6000 + display))
                            break
                        except OSError:
                            continue
                else:
                    raise RuntimeError("no free private X11 TCP display")
                entry = struct.pack(">H", 65535)  # FamilyWild, exact display + private cookie.
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
                xcommand = [
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
                ]
                xvfb = subprocess.Popen(xcommand, env=env, stdout=xlog, stderr=subprocess.STDOUT)
                for _ in range(100):
                    if xvfb.poll() is not None:
                        raise RuntimeError("private Xvfb failed; inspect xvfb.log")
                    try:
                        with socket.create_connection(("127.0.0.1", 6000 + display), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("private Xvfb did not become ready")
            elif not env.get("DISPLAY"):
                parser.error("provide DISPLAY or use --tcp-xvfb")
            command = [
                str(args.code.resolve()),
                "--no-sandbox",
                "--disable-gpu-sandbox",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--verbose",
                "--user-data-dir=" + str(output / "user"),
                "--extensions-dir=" + str(output / "extensions"),
                "--extensionDevelopmentPath=" + str(ROOT / "tests/vscode_geo_mounted_temporal"),
                "--extensionTestsPath=" + str(ROOT / "tests/vscode_geo_mounted_temporal/test.cjs"),
                "--disable-extensions",
                "--skip-welcome",
                "--skip-release-notes",
            ]
            process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            captured = False
            while process.poll() is None:
                if not captured and ready.exists():
                    capture = (
                        "from PIL import ImageGrab;ImageGrab.grab(xdisplay="
                        + repr(env["DISPLAY"])
                        + ").save("
                        + repr(str(output / "capture.png"))
                        + ")"
                    )
                    subprocess.run([sys.executable, "-c", capture], env=env, check=True)
                    done.write_text("captured\n")
                    captured = True
                time.sleep(0.05)
            record = dict(
                command=command,
                xvfb=xcommand,
                exit=process.returncode,
                environment={
                    k: env[k]
                    for k in ("TMPDIR", "DISPLAY", "XYG_NATIVE_LIB", "XYG_GEO_VSCODE_REPORT")
                },
            )
            (output / "command.json").write_text(json.dumps(record, indent=2) + "\n")
            if process.returncode:
                return process.returncode
            report = json.loads((output / "report.json").read_text())
            if not captured or report.get("ok") is not True:
                raise RuntimeError("VS Code did not qualify and capture the mounted journey")
            print(json.dumps(report))
            return 0
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
            if xvfb is not None:
                subprocess.run(
                    ["sudo", "-n", "kill", "-TERM", str(xvfb.pid)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                xvfb.wait()
            auth.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
