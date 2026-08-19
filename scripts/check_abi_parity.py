#!/usr/bin/env python3
"""Fail if host ABI declarations drift from the xyg-core C ABI.

Generated Python ctypes and Node Koffi declarations must exactly match the
Rust `xyg_*` symbol set. `scripts/abi_smoke.py` may bind a focused subset.
`ABI_VERSION` must match in Rust, Python, and Node. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

try:
    from gen_abi_manifest import (
        ABI_SMOKE,
        CORE_LIB,
        GENERATED_JS,
        GENERATED_PY,
        MANIFEST,
        ROOT,
        generate_manifest,
        generated_outputs,
        parse_node_abi,
        parse_python_symbols,
        parse_smoke_symbols,
        render_manifest,
    )
except ModuleNotFoundError:  # imported by tests from the repository root
    from scripts.gen_abi_manifest import (
        ABI_SMOKE,
        CORE_LIB,
        GENERATED_JS,
        GENERATED_PY,
        MANIFEST,
        ROOT,
        generate_manifest,
        generated_outputs,
        parse_node_abi,
        parse_python_symbols,
        parse_smoke_symbols,
        render_manifest,
    )


def iter_prior_abi_contracts(root: Path) -> Iterator[dict[str, object]]:
    """Yield every readable historical ABI contract, newest first."""
    history = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            "--format=%H",
            "--",
            "spec/abi/xyg-abi.json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    for revision in history.stdout.splitlines() if history.returncode == 0 else []:
        previous = subprocess.run(
            ["git", "-C", str(root), "show", f"{revision}:spec/abi/xyg-abi.json"],
            check=False,
            capture_output=True,
            text=True,
        )
        if previous.returncode:
            continue
        try:
            contract = json.loads(previous.stdout)
        except json.JSONDecodeError:
            continue
        if isinstance(contract, dict):
            yield contract


def check_abi_parity(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    rust_path = root / CORE_LIB.relative_to(ROOT)
    generated_py = root / GENERATED_PY.relative_to(ROOT)
    generated_js = root / GENERATED_JS.relative_to(ROOT)
    smoke_path = root / ABI_SMOKE.relative_to(ROOT)
    manifest_path = root / MANIFEST.relative_to(ROOT)

    generated = generate_manifest(root)
    rendered = render_manifest(generated)
    for path, expected in generated_outputs(root).items():
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            errors.append(
                f"{path.relative_to(root)} is stale; run "
                "`python3 scripts/gen_abi_manifest.py --write`"
            )
    if not manifest_path.exists():
        errors.append(f"missing ABI manifest {manifest_path}")
    else:
        current = manifest_path.read_text(encoding="utf-8")
        if current != rendered:
            errors.append(
                "spec/abi/xyg-abi.json is stale; run `python3 scripts/gen_abi_manifest.py --write`"
            )

    if not smoke_path.exists():
        errors.append("scripts/abi_smoke.py is missing; restore the stdlib ABI smoke gate")
    if not generated_py.exists() or not generated_js.exists() or not smoke_path.exists():
        return errors

    rust_names = {item["name"]: item for item in generated["symbols"]}
    rust_set = set(rust_names)
    rust_version = generated["abi_version"]

    # A signature change is a versioned product event. Compare the working
    # contract with the nearest prior typed contract in history so a multi-
    # commit branch cannot conceal a missing ABI_VERSION bump.
    for old in iter_prior_abi_contracts(root):
        old_hash = old.get("signature_sha256")
        if old_hash and old_hash != generated["signature_sha256"]:
            if old.get("abi_version") == rust_version:
                changes = describe_signature_changes(old, generated)
                detail = (
                    "; ".join(changes)
                    if changes
                    else (f"contract hash {old_hash} -> {generated['signature_sha256']}")
                )
                errors.append(f"ABI signature changed without an ABI_VERSION bump: {detail}")
            break

    py_version, py_names = parse_python_symbols(generated_py.read_text(encoding="utf-8"))
    smoke_names = parse_smoke_symbols(smoke_path.read_text(encoding="utf-8"))
    node_version, node_arities = parse_node_abi(generated_js.read_text(encoding="utf-8"))

    if py_version != rust_version:
        errors.append(
            f"ABI_VERSION mismatch: rust={rust_version} python={py_version} "
            f"({generated_py.relative_to(root) if root in generated_py.parents else generated_py})"
        )
    if node_version != rust_version:
        errors.append(
            f"ABI_VERSION mismatch: rust={rust_version} node={node_version} "
            f"(packages/xy-node/src/_abi_generated.js)"
        )

    for label, names, complete in (
        ("python/xy/_abi_generated.py", py_names, True),
        ("scripts/abi_smoke.py", smoke_names, False),
    ):
        extra = sorted(names - rust_set)
        if extra:
            errors.append(f"{label} declares unknown ABI symbols: {', '.join(extra)}")
        if complete:
            missing = sorted(rust_set - names)
            if missing:
                errors.append(f"{label} missing Rust ABI symbols: {', '.join(missing)}")
        elif "xyg_abi_version" not in names:
            errors.append(f"{label} must bind xyg_abi_version")

    extra_node = sorted(set(node_arities) - rust_set)
    if extra_node:
        errors.append(
            "packages/xy-node/src/_abi_generated.js declares unknown ABI symbols: "
            + ", ".join(extra_node)
        )
    missing_node = sorted(rust_set - set(node_arities))
    if missing_node:
        errors.append(
            "packages/xy-node/src/_abi_generated.js missing Rust ABI symbols: "
            + ", ".join(missing_node)
        )
    for name, nargs in sorted(node_arities.items()):
        spec = rust_names.get(name)
        if spec is not None and spec["nargs"] != nargs:
            errors.append(
                f"packages/xy-node/src/_abi_generated.js {name} arity {nargs} != Rust {spec['nargs']}"
            )

    if not rust_set:
        errors.append(f"{rust_path}: parsed zero xyg_* exports")
    return errors


def describe_signature_changes(
    previous: dict[str, object], current: dict[str, object]
) -> list[str]:
    """Name every added, removed, or re-typed symbol in an ABI contract."""

    def signatures(manifest: dict[str, object]) -> dict[str, str]:
        symbols = manifest.get("symbols")
        if not isinstance(symbols, list):
            return {}
        result: dict[str, str] = {}
        for item in symbols:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            signature = item.get("c_signature")
            if isinstance(name, str) and isinstance(signature, str):
                result[name] = signature
        return result

    old = signatures(previous)
    new = signatures(current)
    changes: list[str] = []
    for name in sorted(old.keys() | new.keys()):
        if name not in old:
            changes.append(f"{name}: added `{new[name]}`")
        elif name not in new:
            changes.append(f"{name}: removed `{old[name]}`")
        elif old[name] != new[name]:
            changes.append(f"{name}: `{old[name]}` -> `{new[name]}`")
    return changes


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    errors = check_abi_parity()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    generated = generate_manifest()
    print(
        f"ABI parity ok ({len(generated['symbols'])} symbols, v{generated['abi_version']}; "
        "both hosts generated from the typed contract)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
