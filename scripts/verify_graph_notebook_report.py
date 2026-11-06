#!/usr/bin/env python3
"""Validate bounded real-notebook graph evidence; this is not ladder acceptance."""

from __future__ import annotations

import argparse
import json
import uuid
from itertools import pairwise
from pathlib import Path


def geometry_expected(mode):
    """Property fixture endpoints are authored in gen_graphforge_ipc_fixtures.py."""
    oracle = (
        Path(__file__).resolve().parents[1] / "tests/fixtures/graphforge/notebook_geometry.json"
    )
    return json.loads(oracle.read_text())[mode]


def verify_geometry(report):
    try:
        journeys = report["geometry"]
        callbacks = report["geometryCallbacks"]
        if len(journeys) != 4 or len(callbacks) != 4:
            return ["four exact geometric callbacks required"]
        for i, (phase, mode) in enumerate(
            (
                ("progressive", "box"),
                ("progressive", "lasso"),
                ("complete", "box"),
                ("complete", "lasso"),
            )
        ):
            journey = journeys[i]
            step = journey["startStep"]
            if (
                journey["phase"] != phase
                or journey["mode"] != mode
                or not (
                    1 <= step <= journey["endStep"] < 300
                    if phase == "progressive"
                    else step == journey["endStep"] == 300
                )
            ):
                return ["geometric gesture phase mismatch"]
            if callbacks[i]["identities"] != geometry_expected(mode) or journey[
                "expected"
            ] != geometry_expected(mode):
                return ["exact geometric kind/UUID/provenance mismatch"]
            pointer = journey["pointer"]
            path = journey["path"]
            if (
                type(step) is not int
                or type(journey["endStep"]) is not int
                or len(path) != (2 if mode == "box" else 5)
                or (mode == "lasso" and path[0] != path[-1])
                or [pointer[0]["x"], pointer[0]["y"]] != path[0]
                or [pointer[-1]["x"], pointer[-1]["y"]] != path[-1]
                or any(
                    point not in [[event["x"], event["y"]] for event in pointer] for point in path
                )
            ):
                return ["exact complete geometric pointer vertices required"]
            kinds = [event["kind"] for event in pointer]
            if (
                kinds[0] != "pointerdown"
                or kinds[-1] != "pointerup"
                or kinds.count("pointermove") < (4 if mode == "box" else 8)
                or any(
                    event["target"] != "CANVAS" or event["trusted"] is not True for event in pointer
                )
            ):
                return ["complete trusted canvas pointer path required"]
            if journey["picture"]["colors"] <= 2 or len(journey["picture"]["sha256"]) != 64:
                return ["visible geometric selection capture required"]
        for box, lasso in ((journeys[0], journeys[1]), (journeys[2], journeys[3])):
            if not box["picture"]["edgeInk"] > max(20, lasso["picture"]["edgeInk"] * 2):
                return ["visible edge masks must distinguish box and loop-only lasso"]
        return []
    except (KeyError, IndexError, TypeError, ValueError):
        return ["missing or malformed exact geometric selection proof"]


def verify(report):
    errors = verify_geometry(report)
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
        native.get("abi") != 399
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
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    errors = verify(json.loads(args.report.read_text()))
    if errors:
        raise SystemExit("; ".join(errors))
    print("Bounded native graph notebook journey verified; no scale-ladder claim.")


if __name__ == "__main__":
    main()
