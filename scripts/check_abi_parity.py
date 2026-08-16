#!/usr/bin/env python3
"""Fail if host ABI declarations drift from the xyg-core C ABI.

Python ctypes must declare exactly the Rust `xyg_*` symbol set. Node koffi
and `scripts/abi_smoke.py` may bind a subset. Extra host symbols fail.
`ABI_VERSION` must match in Rust, Python, and Node. Stdlib only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

try:
    from gen_abi_manifest import (
        ABI_SMOKE,
        CORE_LIB,
        MANIFEST,
        NATIVE_JS,
        NATIVE_PATH_JS,
        NATIVE_PY,
        ROOT,
        generate_manifest,
        parse_node_abi,
        parse_python_symbols,
        parse_smoke_symbols,
        render_manifest,
    )
except ModuleNotFoundError:  # imported by tests from the repository root
    from scripts.gen_abi_manifest import (
        ABI_SMOKE,
        CORE_LIB,
        MANIFEST,
        NATIVE_JS,
        NATIVE_PATH_JS,
        NATIVE_PY,
        ROOT,
        generate_manifest,
        parse_node_abi,
        parse_python_symbols,
        parse_smoke_symbols,
        render_manifest,
    )


def check_abi_parity(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    rust_path = root / CORE_LIB.relative_to(ROOT)
    native_py = root / NATIVE_PY.relative_to(ROOT)
    native_js = root / NATIVE_JS.relative_to(ROOT)
    native_path_js = root / NATIVE_PATH_JS.relative_to(ROOT)
    smoke_path = root / ABI_SMOKE.relative_to(ROOT)
    manifest_path = root / MANIFEST.relative_to(ROOT)

    generated = generate_manifest(root)
    rendered = render_manifest(generated)
    if not manifest_path.exists():
        errors.append(f"missing ABI manifest {manifest_path}")
    else:
        current = manifest_path.read_text(encoding="utf-8")
        if current != rendered:
            errors.append(
                "spec/abi/xyg-abi.json is stale; run `python3 scripts/gen_abi_manifest.py --write`"
            )

    rust_names = {item["name"]: item for item in generated["symbols"]}
    rust_set = set(rust_names)
    rust_version = generated["abi_version"]

    py_version, py_names = parse_python_symbols(native_py.read_text(encoding="utf-8"))
    smoke_names = parse_smoke_symbols(smoke_path.read_text(encoding="utf-8"))
    node_version, node_arities = parse_node_abi(
        native_js.read_text(encoding="utf-8"),
        native_path_js.read_text(encoding="utf-8"),
    )

    if py_version != rust_version:
        errors.append(
            f"ABI_VERSION mismatch: rust={rust_version} python={py_version} "
            f"({native_py.relative_to(root) if root in native_py.parents else native_py})"
        )
    if node_version != rust_version:
        errors.append(
            f"ABI_VERSION mismatch: rust={rust_version} node={node_version} "
            f"(packages/xy-node/src/native-path.js)"
        )

    for label, names, complete in (
        ("python/xy/_native.py", py_names, True),
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
            "packages/xy-node/src/native.js declares unknown ABI symbols: " + ", ".join(extra_node)
        )
    for name, nargs in sorted(node_arities.items()):
        spec = rust_names.get(name)
        if spec is not None and spec["nargs"] != nargs:
            errors.append(
                f"packages/xy-node/src/native.js {name} arity {nargs} != Rust {spec['nargs']}"
            )

    if not rust_set:
        errors.append(f"{rust_path}: parsed zero xyg_* exports")
    return errors


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
        "Node may bind a subset)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
