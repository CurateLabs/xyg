#!/usr/bin/env python3
"""Generate spec/abi/xyg-abi.json from the xyg-core C ABI surface.

Parses `#[no_mangle] extern "C" fn xyg_*` declarations in
`crates/xyg-core/src/lib.rs`. Hosts do not edit the manifest by hand —
regenerate it as part of any ABI change and keep it in lock-step with
`ABI_VERSION`. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
CORE_LIB = ROOT / "crates" / "xyg-core" / "src" / "lib.rs"
NATIVE_PY = ROOT / "python" / "xy" / "_native.py"
NATIVE_JS = ROOT / "packages" / "xy-node" / "src" / "native.js"
NATIVE_PATH_JS = ROOT / "packages" / "xy-node" / "src" / "native-path.js"
ABI_SMOKE = ROOT / "scripts" / "abi_smoke.py"
MANIFEST = ROOT / "spec" / "abi" / "xyg-abi.json"

_NO_MANGLE_FN = re.compile(
    r"#\[no_mangle\]\s*(?:#\[[^\]]+\]\s*)*(?:pub\s+)?(?:unsafe\s+)?"
    r'extern\s+"C"\s+fn\s+(xyg_[A-Za-z0-9_]+)\s*\(',
    re.S,
)
_ABI_CONST_RS = re.compile(r"pub const ABI_VERSION:\s*u32\s*=\s*(\d+)\s*;")
_ABI_CONST_PY = re.compile(r"^ABI_VERSION\s*=\s*(\d+)\s*$", re.M)
_ABI_CONST_JS = re.compile(r"export const ABI_VERSION\s*=\s*(\d+)\s*;")
_CTYPES_SYM = re.compile(r"lib\.(xyg_[A-Za-z0-9_]+)\.(?:restype|argtypes)")
_KOFFI_FUNC = re.compile(r"lib\.func\(\s*\"([^\"]+)\"\s*\)", re.S)
_KOFFI_PROTO = re.compile(
    r"^(?P<ret>.+?)\s+(?P<name>xyg_[A-Za-z0-9_]+)\s*\((?P<args>.*)\)\s*$",
    re.S,
)


def _take_paren_contents(text: str, start: int) -> tuple[str, int]:
    """Return the contents of the `(...)` whose interior starts at `start`."""
    depth = 1
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    raise ValueError("unbalanced parentheses in extern C signature")


def _count_args(args_src: str) -> int:
    stripped = re.sub(r"//[^\n]*", "", args_src).strip()
    if not stripped:
        return 0
    depth = 0
    parts = 1
    for ch in stripped:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts += 1
    return parts


def parse_rust_abi(text: str) -> dict:
    match = _ABI_CONST_RS.search(text)
    if match is None:
        raise ValueError("ABI_VERSION not found in crates/xyg-core/src/lib.rs")
    symbols = []
    seen: set[str] = set()
    for match_fn in _NO_MANGLE_FN.finditer(text):
        name = match_fn.group(1)
        if name in seen:
            raise ValueError(f"duplicate #[no_mangle] symbol {name}")
        seen.add(name)
        args_src, end = _take_paren_contents(text, match_fn.end())
        rest = text[end:].lstrip()
        returns = "void"
        if rest.startswith("->"):
            returns = rest[2:].split("{", 1)[0].strip()
        symbols.append(
            {
                "name": name,
                "nargs": _count_args(args_src),
                "returns": returns,
            }
        )
    symbols.sort(key=lambda item: item["name"])
    return {
        "abi_version": int(match.group(1)),
        "artifact": "xyg_core",
        "prefix": "xyg_",
        "source": "crates/xyg-core/src/lib.rs",
        "symbols": symbols,
    }


def parse_python_symbols(text: str) -> tuple[int, set[str]]:
    match = _ABI_CONST_PY.search(text)
    if match is None:
        raise ValueError("ABI_VERSION not found in python/xy/_native.py")
    return int(match.group(1)), set(_CTYPES_SYM.findall(text))


def parse_smoke_symbols(text: str) -> set[str]:
    return set(_CTYPES_SYM.findall(text))


def parse_node_abi(js_text: str, path_text: str) -> tuple[int, dict[str, int]]:
    match = _ABI_CONST_JS.search(path_text)
    if match is None:
        raise ValueError("ABI_VERSION not found in packages/xy-node/src/native-path.js")
    symbols: dict[str, int] = {}
    for proto in _KOFFI_FUNC.findall(js_text):
        parsed = _KOFFI_PROTO.match(proto.strip())
        if parsed is None:
            raise ValueError(f"unparseable koffi prototype: {proto!r}")
        name = parsed.group("name")
        nargs = _count_args(parsed.group("args"))
        if name in symbols and symbols[name] != nargs:
            raise ValueError(f"duplicate koffi symbol {name} with conflicting arity")
        symbols[name] = nargs
    return int(match.group(1)), symbols


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_manifest(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=False) + "\n"


def generate_manifest(root: Path = ROOT) -> dict:
    text = (root / "crates" / "xyg-core" / "src" / "lib.rs").read_text(encoding="utf-8")
    return parse_rust_abi(text)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write spec/abi/xyg-abi.json (default: print to stdout)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the checked-in manifest is stale",
    )
    args = parser.parse_args(argv)
    manifest = generate_manifest()
    rendered = render_manifest(manifest)
    if args.check:
        current = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
        if current != rendered:
            print(
                "spec/abi/xyg-abi.json is stale; run `python3 scripts/gen_abi_manifest.py --write`",
                file=sys.stderr,
            )
            return 1
        print(
            f"ABI manifest current ({len(manifest['symbols'])} symbols, v{manifest['abi_version']})"
        )
        return 0
    if args.write:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(rendered, encoding="utf-8")
        print(f"wrote {MANIFEST.relative_to(ROOT)} ({len(manifest['symbols'])} symbols)")
        return 0
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
