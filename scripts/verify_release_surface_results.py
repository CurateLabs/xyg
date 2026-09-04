#!/usr/bin/env python3
"""Fail the aggregate Release surfaces gate on failed or unexpected skipped jobs."""

from __future__ import annotations

import argparse

SUCCESS = "success"
OPTIONAL_RESULTS = {"skipped", "success"}


def verify(*, required: bool, results: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for name in ("test", "wasm_foundation", "python_floor"):
        if results.get(name) != SUCCESS:
            errors.append(f"{name} must succeed, got {results.get(name)!r}")
    for name in (
        "browser_conformance",
        "sdist",
        "wheels",
        "install_without_rust",
        "authored_scene",
    ):
        result = results.get(name)
        if required and result != SUCCESS:
            errors.append(f"release-surface job {name} must succeed, got {result!r}")
        elif not required and result not in OPTIONAL_RESULTS:
            errors.append(f"optional release-surface job {name} failed with {result!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--required", choices=("true", "false"), required=True)
    parser.add_argument("--job", action="append", default=[])
    args = parser.parse_args()
    results: dict[str, str] = {}
    for item in args.job:
        name, separator, result = item.partition("=")
        if not separator or not name or not result:
            parser.error(f"invalid --job value {item!r}; expected NAME=RESULT")
        results[name] = result
    errors = verify(required=args.required == "true", results=results)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Release surfaces aggregate accepted every applicable job.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
