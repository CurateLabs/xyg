"""Verify actual desktop graph-region identity, pixels and application witnesses."""

from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

if __package__:
    from .verify_vscode_graph_notebook_report import REMOTE_PATHS, _cell_sources, _sha
else:
    from verify_vscode_graph_notebook_report import REMOTE_PATHS, _cell_sources, _sha
ROOT = Path(__file__).resolve().parents[1]
JSON_NAMES = (
    "report.json",
    "run-result.json",
    "controller-complete.json",
    "cleanup.json",
    "installation.json",
    "server-environment.json",
    "served-widget-assets.json",
    "kernel-info.json",
    "inspector-sources.json",
    "graph.ipynb",
)
PICTURES = {
    "capacity-before": ("capacity", "before"),
    "capacity-refused": ("capacity", "after"),
    "capacity-history-refused": ("capacity", "historyPaint"),
    "before": ("before",),
    "before-edges": ("beforeEdges",),
    "box": ("afterBox",),
    "box-edges": ("afterBoxEdges",),
    "lasso": ("afterLasso",),
}


def _require(condition):
    if not condition:
        raise ValueError("contradictory desktop region witness")


def inside(point, polygon):
    hit = False
    for a, b in zip(polygon, polygon[-1:] + polygon[:-1], strict=True):
        if (a[1] > point[1]) != (b[1] > point[1]) and point[0] < (b[0] - a[0]) * (
            point[1] - a[1]
        ) / (b[1] - a[1]) + a[0]:
            hit = not hit
    return hit


def _oracle(data, fixture):
    _require(
        all(
            type(v) in (int, float) and math.isfinite(v) for key in ("x", "y") for v in fixture[key]
        )
    )
    brush, selection = (data["brushes"][-1], data["selections"][-1])
    nodes = []
    for i, (x, y) in enumerate(zip(fixture["x"], fixture["y"], strict=True)):
        hit = (
            inside([x, y], brush["polygon"])
            if brush.get("polygon")
            else brush["x0"] <= x <= brush["x1"] and brush["y0"] <= y <= brush["y1"]
        )
        if hit:
            nodes.append(i)
    edges = [
        i
        for i, (s, t) in enumerate(zip(fixture["edge_source"], fixture["edge_target"], strict=True))
        if s in nodes and t in nodes
    ]
    _require(all(type(v["index"]) is int for v in selection["identities"]))
    identities = sorted(
        [
            (k, fixture[f"{k}_ids"][i], i)
            for k, indices in [("node", nodes), ("edge", edges)]
            for i in indices
        ]
    )
    _require(
        sorted((v["kind"], v["uuid"], v["index"]) for v in selection["identities"]) == identities
    )
    _require(all(isinstance(v["layers"], list) for v in selection["identities"]))
    _require(data["other_selections"] == [])
    node_rows = sorted({fixture["member_of"][i] for i in nodes})
    edge_rows = [
        i
        for i, members in enumerate(fixture["edge_rows"])
        if members and all(m in edges for m in members)
    ]
    for trace, rows in [(fixture["node_trace"], node_rows), (fixture["edge_trace"], edge_rows)]:
        _require(selection["per_trace"].get(str(trace), []) == rows)
    return {
        "nodes": nodes,
        "edges": edges,
        "nodeRows": node_rows,
        "edgeRows": edge_rows,
        "brush": brush,
    }


def _picture(files, name, expected):
    raw = files[name + "-paint.png"]
    with Image.open(io.BytesIO(raw)) as image:
        _require(image.format == "PNG" and 0 < image.width * image.height <= 4194304)
        image.load()
        image = image.convert("RGBA")
        witness = json.loads(files[name + "-pixels.json"])
        samples = []
        for point in witness["points"]:
            x, y = map(round, point)
            samples.append(
                [
                    list(image.getpixel((x + dx, y + dy)))
                    for dx, dy in [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1)]
                ]
                if 2 <= x < image.width - 2 and 2 <= y < image.height - 2
                else None
            )
        actual = {
            "size": [image.width, image.height],
            "samples": samples,
            "paintSha256": _sha(raw),
            "sha256": _sha(files[name + ".png"]),
        }
        _require(actual == expected == witness["result"])
    with Image.open(io.BytesIO(files[name + ".png"])) as screenshot:
        _require(screenshot.format == "PNG" and screenshot.size == tuple(expected["size"]))
        screenshot.load()


def verify(files, *, expected_client, expected_native, notebook_source):
    errors = []
    try:
        documents = {name: json.loads(files[name]) for name in JSON_NAMES}
        report = documents["report.json"]
        front = report["frontend"]
        host = report["host"]
        _require(
            report["ok"] is True
            and report["disposed"] is True
            and type(report["dpr"]) is int
            and report["dpr"] == 1
        )
        _require(
            front
            == dict(
                kind="vscode-jupyter",
                appName="Visual Studio Code",
                appHost="desktop",
                version="1.103.2",
                extensionId="ms-toolsai.jupyter",
                jupyterExtension="2025.7.0",
                node="22.17.0",
                notebookType="jupyter-notebook",
                cellCount=4,
                normalGuiMode=True,
            )
        )
        _require(
            not host.get("error")
            and host["selectionRequested"] is True
            and (host["selectionReturned"] is True)
            and (host["executionRequested"] is True)
        )
        _require(
            _cell_sources(documents["graph.ipynb"]) == _cell_sources(json.loads(notebook_source))
        )
        executed = host["executed"]
        _require([r["index"] for r in executed] == [0, 1, 1, 2, 1, 1, 1, 3])
        reports = []
        for order, row in enumerate(executed, 1):
            _require(
                row["execution"]["success"] is True
                and type(row["execution"]["executionOrder"]) is int
                and (row["execution"]["executionOrder"] == order)
            )
            items = [item for output in row["outputs"] for item in output]
            _require(not any("error" in item["mime"] for item in items))
            text = "".join(
                item["data"]
                for item in items
                if item["mime"].startswith("text/")
                or item["mime"] == "application/vnd.code.notebook.stdout"
            )
            if row["index"] == 1:
                _require(text.startswith("XYG graph region report"))
                value = json.loads(text.split("XYG graph region report", 1)[1])
                _require(value["report_sequence"] == len(reports) + 1)
                reports.append(value)
            elif row["index"] == 3:
                _require(
                    json.loads(text.split("XYG graph region cleanup", 1)[1])["released"] is True
                )
        _require(
            reports
            == [report[k] for k in ["initial"]]
            + [report["capacity"]["refused"]]
            + [report[k] for k in ["box", "lasso", "cameraBox"]]
        )
        _require(
            report["initial"]["native_sha256"] == expected_native
            and report["clientSha256"] == expected_client
        )
        fixture = report["initial"]["fixture"]
        for name, nodes, edges in [
            ("box", [1], [2]),
            ("lasso", [0, 1], [0, 1, 2]),
            ("cameraBox", [0], []),
        ]:
            oracle = _oracle(report[name], fixture)
            _require(
                oracle == report[("camera" if name == "cameraBox" else name) + "Expected"]
                and oracle["nodes"] == nodes
                and (oracle["edges"] == edges)
            )
            masks = report[("camera" if name == "cameraBox" else name) + "Masks"]
            for trace, rows in [
                (fixture["node_trace"], oracle["nodeRows"]),
                (fixture["edge_trace"], oracle["edgeRows"]),
            ]:
                mask = next(m for m in masks if m["trace"] == trace)
                _require(
                    mask["active"] is True
                    and all(type(v) in (int, float) and v in (0, 1) for v in mask["values"])
                )
                _require([i for i, v in enumerate(mask["values"]) if v == 1] == rows)
        _require(len(report["lassoExpected"]["brush"]["polygon"]) >= 6)
        capacity = report["capacity"]
        _require(capacity["refused"]["selections"] == capacity["refused"]["brushes"] == [])
        _require(
            capacity["refused"]["state"]["selection"] == {"rows": True}
            and report["initial"]["capacity_owners"] > 0
        )
        _require(
            capacity["before"]["paintSha256"]
            == capacity["after"]["paintSha256"]
            == capacity["historyPaint"]["paintSha256"]
        )
        h = capacity["history"]
        _require(
            h["after"]["state"] == h["before"]
            and h["after"]["past"] == [h["target"]]
            and (h["after"]["future"] == [])
        )
        h = report["combinedHistory"]
        _require(
            len(h["entries"]) == h["past"] + 1
            and h["entries"][-1] == h["before"]
            and (h["back"] is True)
            and (h["forward"] is True)
            and (h["restored"] == h["before"])
            and (h["reapplied"] == h["after"])
        )
        trusted = report["trusted"]
        _require(
            len(trusted) >= 2
            and all(v["trusted"] is True for v in trusted)
            and any(v.get("shift") for v in trusted)
            and any(v["kind"] == "wheel" for v in trusted)
        )
        for name, path in PICTURES.items():
            expected = report
            for key in path:
                expected = expected[key]
            _picture(files, name, expected)
        before = report["before"]["samples"]
        after = report["afterBox"]["samples"]
        _require(sum((abs(a - b) for a, b in zip(before[1][0], after[1][0], strict=True))) <= 9)
        _require(
            any(
                (
                    a and b and (a[0][3] - b[0][3] > 128)
                    for i, (a, b) in enumerate(zip(before, after, strict=True))
                    if i != 1
                )
            )
        )
        shaft = fixture["edge_rows"].index([3])
        loop = fixture["edge_rows"].index([2])
        before = report["beforeEdges"]["samples"]
        after = report["afterBoxEdges"]["samples"]
        _require(max(p[3] for p in before[shaft]) - max(p[3] for p in after[shaft]) > 80)
        _require(abs(max(p[3] for p in before[loop]) - max(p[3] for p in after[loop])) <= 3)
        # The raw GL guards above remain exact. Separately require visible
        # workbench dimming; its persistent selection overlay may tint a
        # selected center, while unselected native centers must visibly dim.
        with Image.open(io.BytesIO(files["before.png"])) as image:
            baseline = image.convert("RGB")
        points = json.loads(files["before-pixels.json"])["points"]
        for name, selected in [("box", [1]), ("lasso", [0, 1])]:
            with Image.open(io.BytesIO(files[name + ".png"])) as image:
                current = image.convert("RGB")
            for i, point in enumerate(points[:4]):
                xy = tuple(map(round, point))
                distance = sum(
                    abs(a - b)
                    for a, b in zip(baseline.getpixel(xy), current.getpixel(xy), strict=True)
                )
                _require(distance <= 64 if i in selected else distance > 128)
        run = documents["run-result.json"]
        complete = documents["controller-complete.json"]
        command = run["command"]
        if (
            type(run["attachmentExit"]) is not int
            or run["attachmentExit"] != 0
            or type(run["applicationExit"]) is not int
            or (run["applicationExit"] != 0)
            or (complete != {"ok": True, "normalGuiMode": True})
            or (complete["ok"] is not True)
            or (complete["normalGuiMode"] is not True)
            or (run["intentionalFailureAfterCell"] is not None)
            or (run["expectedVersions"] != {"vscode": "1.103.2", "jupyterExtension": "2025.7.0"})
            or (not any(arg.startswith("--extensionDevelopmentPath=") for arg in command))
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
            or (type(kernels[0]["connections"]) is not int)
            or (kernels[0]["connections"] != 0)
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
        app_payload = installation["applicationPayload"]
        if (
            len(app_payload["entries"]) != lock["application"]["payloadEntries"]
            or app_payload["entriesSha256"] != lock["application"]["payloadSha256"]
            or _sha(
                json.dumps(app_payload["entries"], sort_keys=True, separators=(",", ":")).encode()
            )
            != app_payload["entriesSha256"]
        ):
            errors.append("complete stock installed application payload required")
        expected_extensions = {row["id"]: row for row in lock["extensions"]}
        if sorted(installation["installed"], key=lambda row: row["id"]) != sorted(
            [{key: row[key] for key in ("id", "version")} for row in lock["extensions"]],
            key=lambda row: row["id"],
        ):
            errors.append("exact installed extension identities required")
        if set(installation["payloads"]) != set(expected_extensions):
            errors.append("exact installed extension payload set required")
        for identifier, payload in installation["payloads"].items():
            expected_payload = expected_extensions[identifier]
            if (
                payload["version"] != expected_payload["version"]
                or payload["vsixSha256"] != expected_payload["sha256"]
                or len(payload["files"]) != expected_payload["payloadFiles"]
                or (payload["filesSha256"] != expected_payload["payloadSha256"])
                or (
                    _sha(
                        json.dumps(payload["files"], sort_keys=True, separators=(",", ":")).encode()
                    )
                    != payload["filesSha256"]
                )
            ):
                errors.append("stock installed extension file bindings required")
        sources = report["inspectedClientSources"]
        if sources != documents["inspector-sources.json"] or not sources:
            errors.append("loaded client source inspection must match its sidecar")
        for source in sources:
            if (
                source["exactClientSource"] is not True
                or source["sha256"] != expected_client
                or type(source["bytes"]) is not int
                or (source["bytes"] <= 0)
                or (not source["url"].startswith("blob:vscode-webview://"))
            ):
                errors.append("actual cached widget module must equal the built shared client")
        _require(documents["run-result.json"]["regionsJourney"] is True)
        _require(
            documents["run-result.json"]["notebookSource"]
            == dict(path="tests/notebook_graph_regions.ipynb", sha256=_sha(notebook_source))
        )
        _require(
            len(report["usedClientSources"]) == 2
            and all(pin in report["inspectedClientSources"] for pin in report["usedClientSources"])
        )
        info = documents["kernel-info.json"]
        server_version = documents["server-environment.json"]["python"].split()[0]
        if (
            info["status"] != "ok"
            or info["implementation"] != "ipython"
            or info["language_info"]["name"] != "python"
            or (info["language_info"]["version"] != server_version)
            or (not server_version.startswith(("3.11.", "3.12.")))
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
            or (row["bytes"] <= 0)
            or (len(row["sha256"]) != 64)
            for row in assets
        ):
            errors.append("served widget scripts must match installed bytes")
        if (
            report["networkScope"]
            != "Renderer requests only; allowlisted host bootstrap traffic; not offline or extension-host Node network audit"
            or not report["network"]
        ):
            errors.append("honest observed renderer network scope required")
        requested_bootstrap = any(
            row["origin"] == "https://cdn.jsdelivr.net" for row in report["network"]
        )
        bootstrap = report["hostAssets"]
        if requested_bootstrap and (not bootstrap):
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
            local = url.scheme == "http" and url.hostname == "127.0.0.1" and (url.port is not None)
            virtual_file = origin == "https://file+.vscode-resource.vscode-cdn.net"
            remote = (
                row["path"] in REMOTE_PATHS.get(origin, set())
                and row["method"] == "GET"
                and (row["hasQuery"] is False)
                and (type(row["bodyBytes"]) is int)
                and (row["bodyBytes"] == 0)
            )
            if row["approved"] is not True or not (local or virtual_file or remote):
                errors.append("unapproved observed renderer network request")
    except (
        AssertionError,
        KeyError,
        IndexError,
        ValueError,
        TypeError,
        AttributeError,
        OSError,
        StopIteration,
    ):
        errors.append("missing, malformed or contradictory desktop region evidence")
    return errors


def verify_failure(files):
    """A real failed report operation must retain its error and close native owners."""
    try:
        failure = json.loads(files["failure.json"])
        run = json.loads(files["run-result.json"])
        complete = json.loads(files["controller-complete.json"])
        cleanup = json.loads(files["cleanup.json"])
        state = json.loads(files["extension-state.json"])
        released = json.loads(files["failure-owner-cleanup.json"])["output"]
        expected = "intentional notebook failure after cell 1"
        _require(failure["error"] == expected and expected in files["attach.log"].decode())
        _require(type(run["attachmentExit"]) is int and run["attachmentExit"] == 1)
        _require(type(run["applicationExit"]) is int and run["applicationExit"] == 0)
        _require(
            run["regionsJourney"] is True
            and type(run["intentionalFailureAfterCell"]) is int
            and run["intentionalFailureAfterCell"] == 1
        )
        _require(complete["ok"] is False)
        _require([r["index"] for r in state["executed"]] == [0, 1, 3])
        for order, row in enumerate(state["executed"], 1):
            _require(
                row["execution"]["success"] is True
                and type(row["execution"]["executionOrder"]) is int
                and row["execution"]["executionOrder"] == order
            )
        actual_cleanup = "".join(
            item["data"]
            for output in state["executed"][-1]["outputs"]
            for item in output
            if item["mime"].startswith("text/")
            or item["mime"] == "application/vnd.code.notebook.stdout"
        )
        _require(actual_cleanup == released)
        _require(released.startswith("XYG graph region cleanup"))
        _require(json.loads(released.split("XYG graph region cleanup", 1)[1])["released"] is True)
        _require(cleanup["cookieRemoved"] is True and len(cleanup["owned"]) >= 3)
        _require(
            all(row["terminated"] is True and type(row["exit"]) is int for row in cleanup["owned"])
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return [
            "failed desktop region operation must preserve its original error and finish native/process cleanup"
        ]
    return []


def read_bundle(directory, *, failure=False):
    names = (
        [
            "failure.json",
            "run-result.json",
            "controller-complete.json",
            "cleanup.json",
            "extension-state.json",
            "attach.log",
            "failure-owner-cleanup.json",
        ]
        if failure
        else [*JSON_NAMES]
    )
    if not failure:
        for name in PICTURES:
            names.extend([name + ".png", name + "-paint.png", name + "-pixels.json"])
    files = {}
    for name in names:
        p = directory / name
        if not p.is_file() or p.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("missing or oversized region witness: " + name)
        files[name] = p.read_bytes()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expect-failure-after-cell", type=int, choices=(1,))
    args = parser.parse_args()
    if args.expect_failure_after_cell is not None:
        errors = verify_failure(read_bundle(args.directory, failure=True))
        if errors:
            raise SystemExit("; ".join(errors))
        print("Original desktop region failure and native/process cleanup verified")
        return
    errors = verify(
        read_bundle(args.directory),
        expected_client=_sha((ROOT / "python/xyg/static/index.js").read_bytes()),
        expected_native=_sha((ROOT / "target/release/libxyg_core.so").read_bytes()),
        notebook_source=(ROOT / "tests/notebook_graph_regions.ipynb").read_bytes(),
    )
    if errors:
        raise SystemExit("; ".join(errors))
    print("Actual VS Code graph regions and desktop sidecars verified")


if __name__ == "__main__":
    main()
