#!/usr/bin/env python3
"""Validate bounded real-notebook graph evidence; this is not ladder acceptance."""

from __future__ import annotations

import argparse
import json
from itertools import pairwise
from pathlib import Path


def verify(report):
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
    if not any(
        event.get("kind") == "select" and event.get("detail", {}).get("total") == 1
        for event in report.get("events", {}).get("events", [])
    ):
        errors.append("exactly one Python-origin selected row must reach the view")
    if report.get("finalPointerVerified") is not True:
        errors.append("stationary native pointer callback verification required")
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
