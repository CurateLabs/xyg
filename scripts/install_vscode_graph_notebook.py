#!/usr/bin/env python3
"""Install the pinned Linux desktop test cohort in a new private directory.

Downloads official app/VSIX bytes, checks complete hashes and lengths before
using them, and invokes the app's own extension installer. Nothing installs to a
user profile or ships in XYG. A cache is an optional directory of exact named
artifacts; cached files receive the same checks as downloaded ones.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tests/vscode_graph_notebook/toolchain.json"


def checked_artifact(record, path, cache):
    source = cache / path.name if cache else None
    if source and source.is_file():
        shutil.copyfile(source, path)
    else:
        with urllib.request.urlopen(record["url"], timeout=60) as response, path.open("wb") as file:
            encoding = response.headers.get("Content-Encoding", "identity").lower()
            if encoding not in ("identity", "gzip"):
                raise ValueError("unsupported artifact transport encoding")
            stream = gzip.GzipFile(fileobj=response) if encoding == "gzip" else response
            while block := stream.read(1024 * 1024):
                if file.tell() + len(block) > record["bytes"]:
                    raise ValueError("oversized test artifact: " + path.name)
                file.write(block)
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if path.stat().st_size != record["bytes"] or digest != record["sha256"]:
        raise ValueError("test artifact identity mismatch: " + path.name)
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest}


def application_payload(lock, code_root):
    """Recheck all installed files and directories against the pinned archive map."""
    entries = {}
    for path in sorted(code_root.rglob("*")):
        info = path.lstat()
        name = path.relative_to(code_root).as_posix()
        if stat.S_ISREG(info.st_mode):
            with path.open("rb") as file:
                digest = hashlib.file_digest(file, "sha256").hexdigest()
            entries[name] = {
                "kind": "file",
                "bytes": info.st_size,
                "sha256": digest,
                "executable": bool(info.st_mode & 0o111),
            }
        elif stat.S_ISDIR(info.st_mode):
            entries[name] = {"kind": "directory"}
        else:
            # This exact official archive has no links or special files.
            raise ValueError("unexpected installed application entry: " + name)
    digest = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if len(entries) != lock["payloadEntries"] or digest != lock["payloadSha256"]:
        raise ValueError("installed application payload changed")
    return {"entries": entries, "entriesSha256": digest}


def installed_payloads(lock, extensions, downloads):
    payloads = {}
    installed = {}
    for directory in extensions.iterdir():
        if directory.is_dir():
            if directory.is_symlink():
                raise ValueError("linked installed extension directory")
            manifest = json.loads((directory / "package.json").read_text())
            identifier = manifest["publisher"] + "." + manifest["name"]
            if identifier in installed:
                raise ValueError("duplicate installed extension ID: " + identifier)
            installed[identifier] = directory
    if set(installed) != {row["id"] for row in lock["extensions"]}:
        raise ValueError("unexpected installed extension set")
    for row in lock["extensions"]:
        directory = installed[row["id"]]
        archive_path = downloads / (row["id"] + "-" + row["version"] + ".vsix")
        with archive_path.open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != row["sha256"]:
                raise ValueError("installed source VSIX mismatch")
        with zipfile.ZipFile(archive_path) as archive:
            expected = {
                name[len("extension/") :]: archive.read(name)
                for name in archive.namelist()
                if name.startswith("extension/") and not name.endswith("/")
            }
            expected[".vsixmanifest"] = archive.read("extension.vsixmanifest")
        paths = {
            str(path.relative_to(directory)): path
            for path in directory.rglob("*")
            if path.is_file()
        }
        if paths.keys() != expected.keys():
            raise ValueError("installed extension file set mismatch")
        for name, raw in expected.items():
            actual = paths[name].read_bytes()
            if name == "package.json":
                metadata = json.loads(actual)
                metadata.pop("__metadata", None)  # Added by the stock installer.
                if metadata != json.loads(raw):
                    raise ValueError("installed extension manifest changed")
            elif actual != raw:
                raise ValueError("installed extension payload changed: " + name)
        canonical = {}
        for name, path in sorted(paths.items()):
            raw = path.read_bytes()
            if name == "package.json":
                manifest = json.loads(raw)
                manifest.pop("__metadata", None)
                raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            canonical[name] = hashlib.sha256(raw).hexdigest()
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if len(canonical) != row["payloadFiles"] or digest != row["payloadSha256"]:
            raise ValueError("installed canonical payload differs from its lock")
        payloads[row["id"]] = {
            "version": row["version"],
            "vsixSha256": row["sha256"],
            "files": canonical,
            "filesSha256": digest,
        }
    return payloads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64":
        parser.error("this named desktop test cohort is Linux x86_64 only")
    lock = json.loads(LOCK.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    downloads = output / "downloads"
    downloads.mkdir()
    cache = args.cache.resolve() if args.cache else None
    record = {"lockSha256": hashlib.sha256(LOCK.read_bytes()).hexdigest(), "artifacts": []}
    app = lock["application"]
    app_archive = downloads / "vscode-linux-x64.tar.gz"
    record["artifacts"].append(checked_artifact(app, app_archive, cache))
    # The standard data filter rejects traversal, external links and special files.
    with tarfile.open(app_archive, "r:gz") as archive:
        archive.extractall(output / "application", filter="data")
    code_root = output / "application/VSCode-linux-x64"
    code = code_root / "code"
    cli = code_root / "bin/code"
    product = json.loads((code_root / "resources/app/product.json").read_text())
    package = json.loads((code_root / "resources/app/package.json").read_text())
    if product["commit"] != app["commit"] or package["version"] != app["version"]:
        raise ValueError("installed desktop app version/commit mismatch")
    app_payload = application_payload(app, code_root)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("GH_TOKEN", "GITHUB_TOKEN", "VSCODE_IPC_HOOK_CLI")
        and not key.endswith("_API_KEY")
    }
    extensions = output / "extensions"
    user = output / "install-user"
    (user / "User").mkdir(parents=True)
    (user / "User/settings.json").write_text(
        json.dumps(
            {
                "extensions.autoCheckUpdates": False,
                "extensions.autoUpdate": False,
                "telemetry.telemetryLevel": "off",
            }
        )
        + "\n"
    )
    # Install the four pack dependencies explicitly before the Jupyter extension.
    for extension in sorted(
        lock["extensions"], key=lambda item: item["id"] == "ms-toolsai.jupyter"
    ):
        artifact = downloads / (extension["id"] + "-" + extension["version"] + ".vsix")
        record["artifacts"].append(checked_artifact(extension, artifact, cache))
        with zipfile.ZipFile(artifact) as archive:
            manifest = json.loads(archive.read("extension/package.json"))
        if (
            manifest["publisher"] + "." + manifest["name"] != extension["id"]
            or manifest["version"] != extension["version"]
        ):
            raise ValueError("VSIX manifest mismatch")
        command = [
            str(cli),
            "--install-extension",
            str(artifact),
            "--user-data-dir=" + str(user),
            "--extensions-dir=" + str(extensions),
        ]
        with (output / (extension["id"] + ".log")).open("wb") as log:
            subprocess.run(
                command, env=env, check=True, timeout=90, stdout=log, stderr=subprocess.STDOUT
            )
    installed = []
    for path in extensions.iterdir():
        if not path.is_dir():
            continue
        manifest = json.loads((path / "package.json").read_text())
        installed.append(
            {"id": manifest["publisher"] + "." + manifest["name"], "version": manifest["version"]}
        )
    expected = [{key: row[key] for key in ("id", "version")} for row in lock["extensions"]]
    if sorted(installed, key=lambda row: row["id"]) != sorted(expected, key=lambda row: row["id"]):
        raise ValueError("installed extension set differs from the pinned cohort")
    record.update(
        code=str(code),
        extensions=str(extensions),
        installed=installed,
        payloads=installed_payloads(lock, extensions, downloads),
        applicationPayload=app_payload,
        applicationExecutable={
            "bytes": code.stat().st_size,
            "sha256": hashlib.file_digest(code.open("rb"), "sha256").hexdigest(),
        },
    )
    if record["applicationExecutable"] != {
        "bytes": app["executableBytes"],
        "sha256": app["executableSha256"],
    }:
        raise ValueError("installed application executable changed")
    (output / "installation.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Pinned actual desktop notebook test cohort installed and verified")


if __name__ == "__main__":
    main()
