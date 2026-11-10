#!/usr/bin/env python3
"""Verify an actual desktop VS Code/Jupyter graph journey and its sidecars.

The shared graph semantics are identical to the Lab/Notebook7 verifier. Desktop
application, process, source, execution and screenshot witnesses are additional
requirements, not substitutes for those graph assertions. Network evidence
covers observed renderer requests only, including disclosed host bootstrap CDN
traffic; it does not certify offline operation or the extension host's traffic.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

if __package__:
    from .graph_notebook_pixels import mark_witness
    from .verify_graph_notebook_report import verify as verify_graph
else:
    from graph_notebook_pixels import mark_witness
    from verify_graph_notebook_report import verify as verify_graph

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_ORDER = [0, 1, 2, 3, 6, 4, 5, 7, 8, 9]
REMOTE_PATHS = {
    "https://unpkg.com": {"/"},
    "https://cdn.jsdelivr.net": {"/npm/requirejs@2.3.6/bin/r.min.js"},
    "https://main.vscode-cdn.net": {"/extensions/chat.json"},
    "https://marketplace.visualstudio.com": {
        "/_apis/public/gallery/vscode/xyg-local-test/xyg-graph-notebook-proof/latest"
    },
}
REQUIRED_JSON = (
    "installation.json",
    "report.json",
    "run-result.json",
    "controller-complete.json",
    "cleanup.json",
    "served-widget-assets.json",
    "server-environment.json",
    "kernel-info.json",
    "inspector-sources.json",
    "graph.ipynb",
    "identity-parity-input.json",
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _cell_sources(notebook):
    return [
        {"cell_type": cell["cell_type"], "source": "".join(cell["source"])}
        for cell in notebook["cells"]
    ]


def verify(files, *, expected_client, expected_native, notebook_source):
    """Return errors for a bounded bundle of named raw artifact bytes."""
    errors = []
    try:
        documents = {name: json.loads(files[name]) for name in REQUIRED_JSON}
        report = documents["report.json"]
        # Desktop identity is checked below. Do not admit it as a Lab frontend.
        graph = {key: value for key, value in report.items() if key != "frontend"}
        errors.extend(verify_graph(graph, require_routed=True))
        front, host = report["frontend"], report["host"]
        if (
            front
            != {
                "kind": "vscode-jupyter",
                "appName": "Visual Studio Code",
                "appHost": "desktop",
                "version": "1.103.2",
                "extensionId": "ms-toolsai.jupyter",
                "jupyterExtension": "2025.7.0",
                "node": "22.17.0",
                "notebookType": "jupyter-notebook",
                "cellCount": 10,
                "normalGuiMode": True,
            }
            or host["vscode"] != front["version"]
            or host["appName"] != front["appName"]
            or host["appHost"] != front["appHost"]
            or host["node"] != front["node"]
            or host["normalGuiMode"] is not True
            or front["normalGuiMode"] is not True
            or type(front["cellCount"]) is not int
            or host["extension"]["id"] != front["extensionId"]
            or host["extension"]["version"] != front["jupyterExtension"]
            or host["notebook"]["type"] != front["notebookType"]
            or type(host["notebook"]["cellCount"]) is not int
            or host["notebook"]["cellCount"] != 10
            or host.get("error")
            or host["selectionRequested"] is not True
            or host["selectionReturned"] is not True
            or host["executionRequested"] is not True
        ):
            errors.append("actual named desktop application/Jupyter notebook required")
        if _cell_sources(documents["graph.ipynb"]) != _cell_sources(json.loads(notebook_source)):
            errors.append("all ten original notebook cell sources must remain unchanged")
        executed = host["executed"]
        if [row["index"] for row in executed] != EXECUTION_ORDER:
            errors.append("ten actual notebook cells must execute in the required order")
        text_outputs = {}
        for order, row in enumerate(executed, 1):
            execution = row["execution"]
            if (
                type(row["index"]) is not int
                or execution["success"] is not True
                or type(execution["executionOrder"]) is not int
                or execution["executionOrder"] != order
            ):
                errors.append("each actual Python execution must succeed with its own order")
            items = [item for output in row["outputs"] for item in output]
            if any("error" in item["mime"] for item in items):
                errors.append("actual Python errors cannot qualify")
            text_outputs[row["index"]] = "".join(
                item["data"]
                for item in items
                if item["mime"].startswith("text/")
                or item["mime"] == "application/vnd.code.notebook.stdout"
            )
        for index, prefix, value in (
            (1, "XYG graph kernel responsive", report["kernel"]),
            (2, "XYG graph Python rows selected", report["uuidSelection"]),
            (5, "XYG graph disposed", report["finalPointer"]),
            (6, "XYG identity fixture", report["routedIdentity"]["fixture"]),
            (7, "XYG routed identity", report["routedIdentity"]),
            (9, "XYG layered identity", report["layeredIdentity"]),
        ):
            text = text_outputs[index]
            if not text.startswith(prefix) or json.loads(text[len(prefix) :].strip()) != value:
                errors.append("actual cell output must bind its graph evidence")
        clock = report["frameTimeOrigin"]
        timing = next(row for row in executed if row["index"] == 1)["execution"]["timing"]
        if (
            not all(_number(x) for x in (clock, timing["startTime"], timing["endTime"]))
            or not clock + report["frames"][0]["time"]
            <= timing["startTime"]
            <= timing["endTime"]
            < clock + report["frames"][-1]["time"]
        ):
            errors.append(
                "a real concurrent Python cell must finish between initial and terminal paint"
            )
        run = documents["run-result.json"]
        complete = documents["controller-complete.json"]
        command = run["command"]
        if (
            type(run["attachmentExit"]) is not int
            or run["attachmentExit"] != 0
            or type(run["applicationExit"]) is not int
            or run["applicationExit"] != 0
            or complete != {"ok": True, "normalGuiMode": True}
            or complete["ok"] is not True
            or complete["normalGuiMode"] is not True
            or run["intentionalFailureAfterCell"] is not None
            or run["expectedVersions"] != {"vscode": "1.103.2", "jupyterExtension": "2025.7.0"}
            or not any(arg.startswith("--extensionDevelopmentPath=") for arg in command)
            or any(
                arg.startswith(("--extensionTestsPath", "--disable-extensions")) for arg in command
            )
        ):
            errors.append("normal-GUI application and attachment must both exit successfully")
        kernels = run["serverKernels"]
        if (
            len(kernels) != 1
            or kernels[0]["name"] != "python3"
            or kernels[0]["execution_state"] != "idle"
            or type(kernels[0]["connections"]) is not int
            or kernels[0]["connections"] != 0
        ):
            errors.append(
                "one actual Python kernel must be idle and disconnected after application quit"
            )
        cleanup = documents["cleanup.json"]
        if (
            cleanup["cookieRemoved"] is not True
            or len(cleanup["owned"]) < 3
            or any(
                row["terminated"] is not True or type(row["exit"]) is not int
                for row in cleanup["owned"]
            )
        ):
            errors.append("direct owned processes and private X cookie must be cleaned up")
        lock_path = ROOT / "tests/vscode_graph_notebook/toolchain.json"
        lock = json.loads(lock_path.read_text())
        installation = documents["installation.json"]
        expected_artifacts = [
            ("vscode-linux-x64.tar.gz", lock["application"]["bytes"], lock["application"]["sha256"])
        ] + [
            (row["id"] + "-" + row["version"] + ".vsix", row["bytes"], row["sha256"])
            for row in lock["extensions"]
        ]
        if (
            installation["lockSha256"] != _sha(lock_path.read_bytes())
            or installation["applicationExecutable"]
            != {
                "bytes": lock["application"]["executableBytes"],
                "sha256": lock["application"]["executableSha256"],
            }
            or sorted(
                (row["file"], row["bytes"], row["sha256"]) for row in installation["artifacts"]
            )
            != sorted(expected_artifacts)
        ):
            errors.append("official pinned application and VSIX artifact identities required")
        expected_extensions = {row["id"]: row for row in lock["extensions"]}
        if set(installation["payloads"]) != set(expected_extensions):
            errors.append("exact installed extension payload set required")
        for identifier, payload in installation["payloads"].items():
            expected_payload = expected_extensions[identifier]
            if (
                payload["version"] != expected_payload["version"]
                or payload["vsixSha256"] != expected_payload["sha256"]
                or len(payload["files"]) != expected_payload["payloadFiles"]
                or payload["filesSha256"] != expected_payload["payloadSha256"]
                or _sha(
                    json.dumps(payload["files"], sort_keys=True, separators=(",", ":")).encode()
                )
                != payload["filesSha256"]
            ):
                errors.append("stock installed extension file bindings required")
        if (
            report["expectedNativeHash"] != expected_native
            or report["clientSha256"] != expected_client
        ):
            errors.append("selected native and current built client must match expected bytes")
        sources = report["inspectedClientSources"]
        if sources != documents["inspector-sources.json"] or not sources:
            errors.append("loaded client source inspection must match its sidecar")
        for source in sources:
            if (
                source["exactClientSource"] is not True
                or source["sha256"] != expected_client
                or type(source["bytes"]) is not int
                or source["bytes"] <= 0
                or not source["url"].startswith("blob:vscode-webview://")
            ):
                errors.append("actual cached widget module must equal the built shared client")
        used = report["usedClientSources"]
        if len(used["initial"]) != 2 or used["primary"] != used["initial"][0]:
            errors.append("both isolated initial widget canvases must have source bindings")
        if any(source not in sources for source in [*used["initial"], used["layered"]]):
            errors.append("every used primary/peer/layered canvas must bind an inspected module")
        for name, key in (
            ("initial.png", "initialPicture"),
            ("final.png", "dimensions"),
            ("connected.png", "connectedPicture"),
        ):
            raw = files[name]
            with Image.open(io.BytesIO(raw)) as image:
                if image.width <= 0 or image.height <= 0 or image.width * image.height > 4_194_304:
                    raise ValueError("oversized desktop screenshot")
                image.load()
                rgb = image.convert("RGB")
                picture = report[key]
                if (
                    image.format != "PNG"
                    or _sha(raw) != picture["sha256"]
                    or rgb.width != picture["width"]
                    or rgb.height != picture["height"]
                    or len(rgb.getcolors(rgb.width * rgb.height)) != picture["colors"]
                ):
                    errors.append("actual workbench PNG pixels, dimensions and hashes must match")
        geometry = report["connectedGeometry"]
        ranges = geometry["ranges"]
        api_views = [
            event["detail"]["ranges"]
            for event in report["events"]["events"]
            if event["kind"] == "view_change"
            and event["detail"].get("source") == "api"
            and event["detail"].get("phase") == "end"
        ]
        if not api_views or ranges not in api_views:
            errors.append("mark projection must bind an actual public view-change event")
        native_positions = report["routedIdentity"]["fixture"]["positions"]
        for axis in ("x", "y"):
            if len(geometry["positions"][axis]) != 5 or any(
                not _number(actual) or not math.isclose(actual, expected, rel_tol=0, abs_tol=2e-5)
                for actual, expected in zip(
                    geometry["positions"][axis], native_positions[axis], strict=True
                )
            ):
                errors.append("displayed positions must match accepted native source positions")
        witness = mark_witness(files["connected.png"], native_positions, ranges)
        if report["markPixels"] != witness:
            errors.append("four actual native-center mark pixel witnesses required")
        parity_input = documents["identity-parity-input.json"]
        if (
            parity_input
            != {key: report[key] for key in ("routedIdentity", "layeredIdentity", "uuidMasks")}
            or _sha(files["identity-parity-input.json"]) != report["nodeParity"]["inputSha256"]
            or json.loads(files["identity-parity.log"]) != report["nodeParity"]
        ):
            errors.append("actual public Node invocation must bind input and complete output")
        info = documents["kernel-info.json"]
        server_version = documents["server-environment.json"]["python"].split()[0]
        if (
            info["status"] != "ok"
            or info["implementation"] != "ipython"
            or info["language_info"]["name"] != "python"
            or info["language_info"]["version"] != server_version
            or not server_version.startswith(("3.11.", "3.12."))
        ):
            errors.append(
                "actual kernel protocol identity must match the recorded server interpreter"
            )
        packages = documents["server-environment.json"]["packages"]
        if packages != {
            "notebook": "7.5.8",
            "jupyterlab": "4.5.11",
            "nbclassic": "1.3.3",
            "ipykernel": "7.4.0",
            "anywidget": "0.11.0",
            "ipywidgets": "8.1.9",
            "widgetsnbextension": "4.0.16",
            "jupyterlab_widgets": "3.0.17",
        }:
            errors.append("recorded server/widget cohort versions required")
        assets = documents["served-widget-assets.json"]
        if {row["path"] for row in assets} != {
            "/nbextensions/anywidget/index.js",
            "/nbextensions/anywidget/extension.js",
            "/nbextensions/jupyter-js-widgets/extension.js",
        } or len(assets) != 3:
            errors.append("installed widget asset response set required")
        if any(
            row["status"] != 200
            or row["installedBytesEqual"] is not True
            or type(row["bytes"]) is not int
            or row["bytes"] <= 0
            or len(row["sha256"]) != 64
            for row in assets
        ):
            errors.append("served widget scripts must match installed bytes")
        if (
            report["networkScope"]
            != (
                "Renderer requests only; allowlisted host bootstrap traffic; not offline or extension-host Node network audit"
            )
            or not report["network"]
        ):
            errors.append("honest observed renderer network scope required")
        requested_bootstrap = any(
            row["origin"] == "https://cdn.jsdelivr.net" for row in report["network"]
        )
        bootstrap = report["hostAssets"]
        if requested_bootstrap and not bootstrap:
            errors.append("observed host bootstrap response bytes must be pinned")
        for asset in bootstrap:
            if asset != {
                "origin": "https://cdn.jsdelivr.net",
                "path": "/npm/requirejs@2.3.6/bin/r.min.js",
                "status": 200,
                "bytes": 422855,
                "sha256": "b7534fbf3cd3c6559fe1d1a0ce64fbb574aca3f866531509a61b3678888ca4ae",
            }:
                errors.append("host bootstrap response changed from the observed named cohort")
        for row in report["network"]:
            origin = row["origin"]
            url = urlparse(origin)
            local = url.scheme == "http" and url.hostname == "127.0.0.1" and url.port is not None
            virtual_file = origin == "https://file+.vscode-resource.vscode-cdn.net"
            remote = (
                row["path"] in REMOTE_PATHS.get(origin, set())
                and row["method"] == "GET"
                and row["hasQuery"] is False
                and type(row["bodyBytes"]) is int
                and row["bodyBytes"] == 0
            )
            if row["approved"] is not True or not (local or virtual_file or remote):
                errors.append("unapproved observed renderer network request")
    except (KeyError, IndexError, ValueError, TypeError, AttributeError, OSError, StopIteration):
        errors.append("missing or malformed actual desktop notebook evidence")
    return errors


def verify_failure(files):
    """The intentional failure must remain a failure and finish direct teardown."""
    errors = []
    try:
        failure = json.loads(files["failure.json"])
        run = json.loads(files["run-result.json"])
        complete = json.loads(files["controller-complete.json"])
        cleanup = json.loads(files["cleanup.json"])
        state = json.loads(files["extension-state.json"])
        expected = "intentional notebook failure after cell 1"
        if (
            failure["error"] != expected
            or expected not in files["attach.log"].decode()
            or type(run["attachmentExit"]) is not int
            or run["attachmentExit"] != 1
            or type(run["applicationExit"]) is not int
            or run["applicationExit"] != 0
            or type(run["intentionalFailureAfterCell"]) is not int
            or run["intentionalFailureAfterCell"] != 1
            or complete["ok"] is not False
            or [row["index"] for row in state["executed"]] != [0, 1]
            or any(row["execution"]["success"] is not True for row in state["executed"])
        ):
            errors.append("original intentional failure and actual two-cell execution required")
        if (
            cleanup["cookieRemoved"] is not True
            or len(cleanup["owned"]) < 3
            or any(
                row["terminated"] is not True or type(row["exit"]) is not int
                for row in cleanup["owned"]
            )
        ):
            errors.append("failed notebook must close every direct owned process and cookie")
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append("missing or malformed failure cleanup evidence")
    return errors


def read_bundle(directory, *, failure=False):
    names = (
        (
            "failure.json",
            "run-result.json",
            "controller-complete.json",
            "cleanup.json",
            "extension-state.json",
            "attach.log",
        )
        if failure
        else (*REQUIRED_JSON, "initial.png", "final.png", "connected.png", "identity-parity.log")
    )
    files = {}
    for name in names:
        path = directory / name
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("missing or oversized notebook witness: " + name)
        files[name] = path.read_bytes()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expect-failure-after-cell", type=int, choices=(1,))
    args = parser.parse_args()
    try:
        if args.expect_failure_after_cell is not None:
            errors = verify_failure(read_bundle(args.directory, failure=True))
        else:
            errors = verify(
                read_bundle(args.directory),
                expected_client=_sha((ROOT / "python/xyg/static/index.js").read_bytes()),
                expected_native=_sha((ROOT / "target/release/libxyg_core.so").read_bytes()),
                notebook_source=(ROOT / "tests/notebook_graph_progressive.ipynb").read_bytes(),
            )
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
    if errors:
        raise SystemExit("; ".join(errors))
    print(
        "Intentional notebook failure and direct cleanup verified."
        if args.expect_failure_after_cell is not None
        else "Bounded actual VS Code/Jupyter graph journey verified; no whole-issue or scale claim."
    )


if __name__ == "__main__":
    main()
