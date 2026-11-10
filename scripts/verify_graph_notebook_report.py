#!/usr/bin/env python3
"""Validate bounded real-notebook graph evidence; this is not ladder acceptance."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import uuid
from itertools import pairwise
from pathlib import Path

ABI_VERSION = json.loads(
    (Path(__file__).resolve().parents[1] / "spec/abi/xyg-abi.json").read_text()
)["abi_version"]


def _verify_routed_identity(report):
    """The small property/layer fixture is deliberately not a scale oracle."""
    errors = []
    try:
        routed = report["routedIdentity"]
        fixture = routed["fixture"]
        parity = report["nodeParity"]
        targets = report["routed"]
        expected = [
            {
                "kind": "edge",
                "uuid": f"02000000-0000-0000-0000-{i + 1:012d}",
                "index": i,
                "layers": [],
            }
            for i in range(5)
        ]

        def core(row):
            if type(row["index"]) is not int or any(
                type(layer[key]) is not int for layer in row["layers"] for key in ("layer", "row")
            ):
                raise ValueError("untyped canonical identity")
            return {key: row[key] for key in ("kind", "uuid", "index", "layers")}

        if [core(row) for row in fixture["expected"]] != expected:
            errors.append("canonical property edge identities required")
        if fixture["nodeTrace"] != 1 or fixture["edgeTrace"] != 0:
            errors.append("property fixture trace identities required")
        clicks = routed["clicks"]
        actual = []
        for click in clicks:
            identities = click["graphforge"]
            if len(identities) != 1 or core(identities[0]) not in expected:
                errors.append("exact canonical edge callback required")
                continue
            source = identities[0]["index"]
            index = click["index"]
            if (
                type(index) is not int
                or not 0 <= index < len(fixture["edgeSources"])
                or fixture["edgeSources"][index] != [source]
                or click["trace"] != fixture["edgeTrace"]
            ):
                errors.append("routed segment must resolve its canonical source edge")
            actual.append({"trace": click["trace"], "index": index, "identity": identities[0]})
        if {pick["identity"]["index"] for pick in actual} != set(range(5)):
            errors.append("all five edges including parallel and self-loop picks required")
        if [target["source"] for target in targets] != list(range(5)):
            errors.append("one trusted target for every property edge required")
        for target in targets:
            if type(target["source"]) is not int or type(target["index"]) is not int:
                errors.append("typed canonical edge target required")
            if target["pointer"] != {"kind": "pointerdown", "step": "300"} or not any(
                pick["index"] == target["index"] and pick["identity"]["index"] == target["source"]
                for pick in actual
            ):
                errors.append("trusted rendered edge target and callback must agree")
        layered = report["layeredIdentity"]
        expected_layer = {
            "kind": "node",
            "uuid": "01a0f3fd-23dd-76d3-87e7-d765a3665ef5",
            "index": 0,
            "layers": [{"layer": 0, "result_id": "notebook-rank", "row": 0}],
        }
        if (
            core(layered["expected"]) != expected_layer
            or [core(row) for row in layered["click"]["graphforge"]] != [expected_layer]
            or report["layeredPointer"] != {"kind": "pointerdown", "step": "300"}
        ):
            errors.append("trusted layered node must preserve result ID and exact row")
        if (
            parity["ok"] is not True
            or parity["nativeSha256"] != report["expectedNativeHash"]
            or parity["picks"] != actual
            or parity["layered"] != expected_layer
            or parity["nodeMask"] != [0]
            or parity["edgeMask"] != [0]
            or len(parity["inputSha256"]) != 64
        ):
            errors.append("actual Node graphforgePick parity required")
        for pick in parity["picks"]:
            core(pick["identity"])
        core(parity["layered"])
        for document, key in (
            (fixture["composition"], "documentSha256"),
            (layered["composition"], "layeredDocumentSha256"),
        ):
            if (
                len(document) > 2_000_000
                or hashlib.sha256(base64.b64decode(document, validate=True)).hexdigest()
                != parity[key]
            ):
                errors.append("Node parity must bind the notebook composition bytes")
        masks = report["uuidMasks"]
        if sorted(mask["trace"] for mask in masks) != [0, 1]:
            errors.append("both graph UUID highlight planes required")
        for mask in masks:
            count = 7 if mask["trace"] == 0 else 5
            if (
                mask["active"] is not True
                or type(mask["trace"]) is not int
                or type(mask["count"]) is not int
                or mask["count"] != count
                or mask["selected"] != [0]
                or any(type(value) is not int for value in mask["selected"])
                or any(type(value) not in (int, float) for value in mask["values"])
                or mask["values"] != [1] + [0] * (count - 1)
            ):
                errors.append("exact delivered node and edge UUID GPU masks required")
        if routed["identityReleased"] is not True or layered["identityReleased"] is not True:
            errors.append("private notebook identity sessions must be released")
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        errors.append("malformed routed notebook identity evidence")
    return errors


def verify(report, *, expected_abi: int = ABI_VERSION, require_routed: bool = False):
    errors = []
    if report.get("ok") is not True or report.get("external"):
        errors.append("notebook journey must succeed without external data requests")
    if not all(
        text in report.get("presentation", "")
        for text in ("Progressive property graph", "GraphForge result", "Company", "Person")
    ):
        errors.append("default title and composition legend required")
    frames = report.get("frames", [])
    try:
        steps = [int(frame["step"]) for frame in frames]
        if (
            not steps
            or steps[0] != 1
            or steps[-1] != 300
            or any(b <= a for a, b in pairwise(steps))
        ):
            errors.append("native first/intermediate/terminal frames must be ordered")
        if len(steps) < 3 or not all(
            frame["width"] > 0 and frame["height"] > 0 for frame in frames
        ):
            errors.append("painted intermediate frames required")
        actions = report.get("events", {}).get("actions", [])
        if not any(a["kind"] == "keydown" and 1 <= int(a["step"]) < steps[-1] for a in actions):
            errors.append("trusted keyboard input during unfinished layout required")
        if not any(a["kind"] == "wheel" and 1 <= int(a["step"]) < steps[-1] for a in actions):
            errors.append("trusted navigation during unfinished layout required")
        kinds = {event["kind"] for event in report.get("events", {}).get("events", [])}
        if not {"click", "hover", "select"} <= kinds:
            errors.append("callback/readout/programmatic selection path required")
    except (KeyError, IndexError, ValueError, TypeError):
        errors.append("malformed notebook evidence")
    kernel = report.get("kernel", {})
    if (
        len(kernel.get("clicks", [])) < 1
        or kernel.get("hovers", 0) < 1
        or kernel.get("views", 0) < 1
    ):
        errors.append("actual kernel keyboard/readout/navigation callbacks required")
    uuid_selection = report.get("uuidSelection")
    expected_total = 1
    if uuid_selection is not None:
        expected_total = 2
        try:
            requested = uuid_selection["requested"]
            identities = uuid_selection["identities"]
            if (
                not isinstance(requested, list)
                or len(requested) != 2
                or len(set(requested)) != 2
                or any(str(uuid.UUID(value)) != value for value in requested)
                or not isinstance(identities, list)
                or len(identities) != 2
                or [identity["kind"] for identity in identities] != ["node", "edge"]
                or [identity["uuid"] for identity in identities] != requested
            ):
                errors.append("exact node and edge UUID selection request required")
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append("malformed node and edge UUID selection request")
    elif any("graphforge" in click for click in kernel.get("clicks", [])):
        errors.append("typed identity journey requires its UUID selection request")
    if not any(
        event.get("kind") == "select"
        and type(event.get("detail", {}).get("total")) is int
        and event["detail"]["total"] == expected_total
        for event in report.get("events", {}).get("events", [])
    ):
        errors.append(f"exactly {expected_total} Python-origin selected rows must reach the view")
    pointer = report.get("finalPointer", {})
    if (
        report.get("finalPointerVerified") is not True
        or type(pointer.get("before")) is not int
        or type(pointer.get("after")) is not int
        or pointer.get("before", -1) < 0
        or pointer.get("after", 0) <= pointer.get("before", 0)
        or not isinstance(pointer.get("id"), str)
        or pointer.get("id") != pointer.get("expectedId")
    ):
        errors.append("new stationary exact kernel pointer callback after baseline required")
    native = kernel.get("native", {})
    if (
        type(native.get("abi")) is not int
        or native.get("abi") != expected_abi
        or len(native.get("sha256", "")) != 64
        or native.get("sha256") != report.get("expectedNativeHash")
    ):
        errors.append("selected native library evidence required")
    if report.get("kernel", {}).get("otherClicks") != 0:
        errors.append("independent widget callback isolation required")
    if report.get("widgetCount") != 2:
        errors.append("two actual notebook widget views required")
    for key in ("initialPicture", "dimensions"):
        picture = report.get(key, {})
        if picture.get("colors", 0) <= 2 or len(picture.get("sha256", "")) != 64:
            errors.append("nonempty hash-linked graph screenshots required")
    try:
        if not 1 <= int(report.get("initialPicture", {}).get("step", 300)) < 300:
            errors.append("nonterminal initial picture required")
    except (TypeError, ValueError):
        errors.append("invalid initial picture")
    if report.get("kernelVerified") is not True or report.get("disposed") is not True:
        errors.append("kernel callback assertions and disposal required")
    if report.get("pageErrors"):
        errors.append("browser runtime errors")
    if require_routed or any(
        key in report for key in ("routedIdentity", "layeredIdentity", "nodeParity", "uuidMasks")
    ):
        errors.extend(_verify_routed_identity(report))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--require-routed", action="store_true")
    args = parser.parse_args()
    errors = verify(json.loads(args.report.read_text()), require_routed=args.require_routed)
    if errors:
        raise SystemExit("; ".join(errors))
    print("Bounded native graph notebook journey verified; no scale-ladder claim.")


if __name__ == "__main__":
    main()
