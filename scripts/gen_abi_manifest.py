#!/usr/bin/env python3
"""Generate the typed ABI contract and low-level host declarations.

The Rust ``extern \"C\"`` surface is the sole signature authority. This
stdlib-only generator writes the JSON contract plus deterministic ctypes and
Koffi declaration modules. Host ergonomics remain handwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
CORE_LIB = ROOT / "crates" / "xyg-core" / "src" / "lib.rs"
NATIVE_PY = ROOT / "python" / "xyg" / "_native.py"
GENERATED_PY = ROOT / "python" / "xyg" / "_abi_generated.py"
NATIVE_JS = ROOT / "packages" / "xy-node" / "src" / "native.js"
GENERATED_JS = ROOT / "packages" / "xy-node" / "src" / "_abi_generated.js"
NATIVE_PATH_JS = ROOT / "packages" / "xy-node" / "src" / "native-path.js"
ABI_SMOKE = ROOT / "scripts" / "abi_smoke.py"
MANIFEST = ROOT / "spec" / "abi" / "xyg-abi.json"
HEADER = ROOT / "spec" / "abi" / "xyg.h"

_NO_MANGLE_FN = re.compile(
    r"#\[no_mangle\]\s*(?:#\[[^\]]+\]\s*)*(?:pub\s+)?(?:unsafe\s+)?"
    r'extern\s+"C"\s+fn\s+(xyg_[A-Za-z0-9_]+)\s*\(',
    re.S,
)
_ABI_CONST_RS = re.compile(r"pub const ABI_VERSION:\s*u32\s*=\s*(\d+)\s*;")
_ABI_CONST_PY = re.compile(r"^ABI_VERSION\s*=\s*(\d+)\s*$", re.M)
_ABI_CONST_JS = re.compile(r"export const ABI_VERSION\s*=\s*(\d+)\s*;")
_CTYPES_SYM = re.compile(r"(?:lib\.|getattr\(lib,\s*[\"'])(xyg_[A-Za-z0-9_]+)")
_KOFFI_FUNC = re.compile(r"lib\.func\(\s*\"([^\"]+)\"\s*\)", re.S)
_KOFFI_PROTO = re.compile(
    r"^(?P<ret>.+?)\s+(?P<name>xyg_[A-Za-z0-9_]+)\s*\((?P<args>.*)\)\s*$",
    re.S,
)

_SCALARS: dict[str, dict[str, Any]] = {
    "f32": {"c": "float", "ctypes": "ctypes.c_float", "koffi": "float", "signed": True, "bits": 32},
    "f64": {
        "c": "double",
        "ctypes": "ctypes.c_double",
        "koffi": "double",
        "signed": True,
        "bits": 64,
    },
    "i32": {
        "c": "int32_t",
        "ctypes": "ctypes.c_int32",
        "koffi": "int32_t",
        "signed": True,
        "bits": 32,
    },
    "i64": {
        "c": "int64_t",
        "ctypes": "ctypes.c_int64",
        "koffi": "int64_t",
        "signed": True,
        "bits": 64,
    },
    "u8": {
        "c": "uint8_t",
        "ctypes": "ctypes.c_uint8",
        "koffi": "uint8_t",
        "signed": False,
        "bits": 8,
    },
    "u16": {
        "c": "uint16_t",
        "ctypes": "ctypes.c_uint16",
        "koffi": "uint16_t",
        "signed": False,
        "bits": 16,
    },
    "u32": {
        "c": "uint32_t",
        "ctypes": "ctypes.c_uint32",
        "koffi": "uint32_t",
        "signed": False,
        "bits": 32,
    },
    "u64": {
        "c": "uint64_t",
        "ctypes": "ctypes.c_uint64",
        "koffi": "uint64_t",
        "signed": False,
        "bits": 64,
    },
    "usize": {
        "c": "size_t",
        "ctypes": "ctypes.c_size_t",
        "koffi": "size_t",
        "signed": False,
        "bits": "pointer",
    },
}
_POINTER_C: dict[str, str] = {
    "*const f32": "const float *",
    "*const f64": "const double *",
    "*const i64": "const int64_t *",
    "*const u8": "const uint8_t *",
    "*const u32": "const uint32_t *",
    "*const u64": "const uint64_t *",
    "*const usize": "const size_t *",
    "*mut f32": "float *",
    "*mut f64": "double *",
    "*mut i32": "int32_t *",
    "*mut i64": "int64_t *",
    "*mut u8": "uint8_t *",
    "*mut u16": "uint16_t *",
    "*const u16": "const uint16_t *",
    "*mut u32": "uint32_t *",
    "*mut u64": "uint64_t *",
    "*mut usize": "size_t *",
    "*mut ZoneMap": "void *",
    "*const XygGraphProjectionDescriptor": "const void *",
    "*const XygGraphCompoundSceneDescriptor": "const void *",
    "*const XygCoseDescriptor": "const void *",
    "*const XygTemporalColumnDescriptor": "const void *",
    "*const XygTemporalIntervalDescriptor": "const void *",
    "*const XygTemporalControllerDescriptor": "const void *",
    "*const XygTemporalGraphDescriptor": "const void *",
    "*mut XygTemporalGraphSnapshotMeta": "void *",
    "*const XygTemporalGraphSnapshotBuffers": "const void *",
    "*const i32": "const int32_t *",
    "*const *const f64": "const double *const *",
    "*const *const u8": "const uint8_t *const *",
    "*mut *const f64": "const double **",
}


def _take_paren_contents(text: str, start: int) -> tuple[str, int]:
    depth = 1
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[start:index], index + 1
    raise ValueError("unbalanced parentheses in extern C signature")


def _split_top_level(source: str) -> list[str]:
    source = re.sub(r"//[^\n]*", "", source).strip()
    if not source:
        return []
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in source:
        if char in "(<[":
            depth += 1
        elif char in ")>]":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def _type_contract(rust_type: str, *, argument: bool) -> dict[str, Any]:
    rust_type = " ".join(rust_type.split())
    scalar = _SCALARS.get(rust_type)
    if scalar is not None:
        return {
            "rust": rust_type,
            "c": scalar["c"],
            "ctypes": scalar["ctypes"],
            "koffi": scalar["koffi"],
            "kind": "scalar",
            "bits": scalar["bits"],
            "signed": scalar["signed"],
            "pointer_depth": 0,
            "direction": "value" if argument else "return",
            "nullable": False,
        }
    c_type = _POINTER_C.get(rust_type)
    if c_type is None:
        raise ValueError(
            f"unsupported Rust FFI type {rust_type!r}; add an explicit safe C/ctypes/Koffi mapping"
        )
    if not argument:
        raise ValueError(f"pointer return type {rust_type!r} is not supported")
    mutable = rust_type.startswith("*mut")
    return {
        "rust": rust_type,
        "c": c_type,
        "ctypes": "ctypes.c_void_p",
        "koffi": c_type,
        "kind": "pointer",
        "bits": "pointer",
        "signed": None,
        "pointer_depth": rust_type.count("*"),
        "direction": "out" if mutable else "in",
        "nullable": "contract-defined",
        "buffer_contract": (
            "caller-owned writable storage; pointer/length requirements are documented by the symbol"
            if mutable
            else "borrowed read-only storage; pointer/length requirements are documented by the symbol"
        ),
    }


def _node_name(symbol: str) -> str:
    parts = symbol.removeprefix("xyg_").split("_")
    return "xy" + "".join(part[:1].upper() + part[1:] for part in parts)


def _c_signature(name: str, returns: dict[str, Any], arguments: list[dict[str, Any]]) -> str:
    args = ", ".join(f"{item['type']['c']} {item['name']}" for item in arguments)
    return f"{returns['c']} {name}({args})"


def parse_rust_abi(text: str) -> dict[str, Any]:
    version_match = _ABI_CONST_RS.search(text)
    if version_match is None:
        raise ValueError("ABI_VERSION not found in crates/xyg-core/src/lib.rs")
    symbols: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match_fn in _NO_MANGLE_FN.finditer(text):
        name = match_fn.group(1)
        if name in seen:
            raise ValueError(f"duplicate #[no_mangle] symbol {name}")
        seen.add(name)
        args_source, end = _take_paren_contents(text, match_fn.end())
        arguments: list[dict[str, Any]] = []
        for raw in _split_top_level(args_source):
            if ":" not in raw:
                raise ValueError(f"{name}: argument lacks name/type separator: {raw!r}")
            arg_name, rust_type = raw.split(":", 1)
            arg_name = arg_name.strip().removeprefix("mut ")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", arg_name):
                raise ValueError(f"{name}: unsupported argument name {arg_name!r}")
            arguments.append({"name": arg_name, "type": _type_contract(rust_type, argument=True)})
        rest = text[end:].lstrip()
        rust_return = "void"
        if rest.startswith("->"):
            rust_return = rest[2:].split("{", 1)[0].strip()
        if rust_return == "void":
            returns = {
                "rust": "void",
                "c": "void",
                "ctypes": "None",
                "koffi": "void",
                "kind": "void",
                "bits": 0,
                "signed": None,
                "pointer_depth": 0,
                "direction": "return",
                "nullable": False,
            }
        else:
            returns = _type_contract(rust_return, argument=False)
        symbols.append(
            {
                "name": name,
                "node_name": _node_name(name),
                "nargs": len(arguments),
                "arguments": arguments,
                "returns": returns,
                "c_signature": _c_signature(name, returns, arguments),
            }
        )
    symbols.sort(key=lambda item: item["name"])
    signature_source = "\n".join(item["c_signature"] for item in symbols) + "\n"
    return {
        "abi_version": int(version_match.group(1)),
        "artifact": "xyg_core",
        "prefix": "xyg_",
        "source": "crates/xyg-core/src/lib.rs",
        "signature_sha256": hashlib.sha256(signature_source.encode()).hexdigest(),
        "symbols": symbols,
    }


def parse_python_symbols(text: str) -> tuple[int, set[str]]:
    match = _ABI_CONST_PY.search(text)
    if match is None:
        raise ValueError("ABI_VERSION not found in generated Python ABI declarations")
    return int(match.group(1)), set(_CTYPES_SYM.findall(text))


def parse_smoke_symbols(text: str) -> set[str]:
    return set(_CTYPES_SYM.findall(text))


def _count_c_args(args_source: str) -> int:
    stripped = args_source.strip()
    return 0 if not stripped or stripped == "void" else len(_split_top_level(stripped))


def parse_node_abi(js_text: str, path_text: str = "") -> tuple[int, dict[str, int]]:
    match = _ABI_CONST_JS.search(js_text) or _ABI_CONST_JS.search(path_text)
    if match is None:
        raise ValueError("ABI_VERSION not found in generated Node ABI declarations")
    symbols: dict[str, int] = {}
    for prototype in _KOFFI_FUNC.findall(js_text):
        parsed = _KOFFI_PROTO.match(prototype.strip())
        if parsed is None:
            raise ValueError(f"unparseable koffi prototype: {prototype!r}")
        name = parsed.group("name")
        nargs = _count_c_args(parsed.group("args"))
        if name in symbols and symbols[name] != nargs:
            raise ValueError(f"duplicate koffi symbol {name} with conflicting arity")
        symbols[name] = nargs
    return int(match.group(1)), symbols


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_manifest(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=False) + "\n"


def render_python_bindings(manifest: dict[str, Any]) -> str:
    symbols = manifest["symbols"]
    version = next(item for item in symbols if item["name"] == "xyg_abi_version")
    lines = [
        '"""Generated ctypes declarations. Do not edit; run scripts/gen_abi_manifest.py --write."""',
        "",
        "from __future__ import annotations",
        "",
        "import ctypes",
        "",
        "# fmt: off",
        "",
        f"ABI_VERSION = {manifest['abi_version']}",
        f'SIGNATURE_SHA256 = "{manifest["signature_sha256"]}"',
        "",
        "",
        "def bind_abi_version(lib: ctypes.CDLL):",
        f"    function = lib.{version['name']}",
        f"    function.restype = {version['returns']['ctypes']}",
        "    function.argtypes = []",
        "    return function",
        "",
        "",
        "def bind_generated_abi(lib: ctypes.CDLL) -> None:",
    ]
    for symbol in symbols:
        if symbol["name"] == "xyg_abi_version":
            continue
        argtypes = ", ".join(item["type"]["ctypes"] for item in symbol["arguments"])
        lines.extend(
            [
                f"    # {symbol['c_signature']}",
                f"    function = lib.{symbol['name']}",
                f"    function.restype = {symbol['returns']['ctypes']}",
                f"    function.argtypes = [{argtypes}]",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_node_bindings(manifest: dict[str, Any]) -> str:
    symbols = manifest["symbols"]
    version = next(item for item in symbols if item["name"] == "xyg_abi_version")
    lines = [
        "// Generated Koffi declarations. Do not edit; run scripts/gen_abi_manifest.py --write.",
        "",
        f"export const ABI_VERSION = {manifest['abi_version']};",
        f'export const SIGNATURE_SHA256 = "{manifest["signature_sha256"]}";',
        "",
        "export function bindAbiVersion(lib) {",
        f'  return lib.func("{version["c_signature"]}");',
        "}",
        "",
    ]
    for symbol in symbols:
        if symbol["name"] == "xyg_abi_version":
            continue
        lines.append(f"export let {symbol['node_name']};")
    lines.extend(["", "export function bindGeneratedAbi(lib) {"])
    for symbol in symbols:
        if symbol["name"] == "xyg_abi_version":
            continue
        lines.append(f'  {symbol["node_name"]} = lib.func("{symbol["c_signature"]}");')
    lines.extend(["}", ""])
    return "\n".join(lines)


def render_c_header(manifest: dict[str, Any]) -> str:
    lines = [
        "/* Generated C ABI header. Do not edit; run scripts/gen_abi_manifest.py --write. */",
        "#ifndef XYG_ABI_H",
        "#define XYG_ABI_H",
        "",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        f"#define XYG_ABI_VERSION {manifest['abi_version']}",
        f'#define XYG_ABI_SIGNATURE_SHA256 "{manifest["signature_sha256"]}"',
        "",
        "#ifdef __cplusplus",
        'extern "C" {',
        "#endif",
        "",
    ]
    lines.extend(f"{symbol['c_signature']};" for symbol in manifest["symbols"])
    lines.extend(
        [
            "",
            "#ifdef __cplusplus",
            "}",
            "#endif",
            "",
            "#endif /* XYG_ABI_H */",
            "",
        ]
    )
    return "\n".join(lines)


def generate_manifest(root: Path = ROOT) -> dict[str, Any]:
    text = (root / "crates/xyg-core/src/lib.rs").read_text(encoding="utf-8")
    return parse_rust_abi(text)


def generated_outputs(root: Path = ROOT) -> dict[Path, str]:
    manifest = generate_manifest(root)
    return {
        root / "spec/abi/xyg-abi.json": render_manifest(manifest),
        root / "python/xyg/_abi_generated.py": render_python_bindings(manifest),
        root / "packages/xy-node/src/_abi_generated.js": render_node_bindings(manifest),
        root / "spec/abi/xyg.h": render_c_header(manifest),
    }


def _stale_outputs(outputs: dict[Path, str]) -> Iterable[Path]:
    for path, expected in outputs.items():
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            yield path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write every generated ABI artifact")
    parser.add_argument(
        "--check", action="store_true", help="fail if any generated ABI artifact is stale"
    )
    args = parser.parse_args(argv)
    outputs = generated_outputs()
    if args.check:
        stale = list(_stale_outputs(outputs))
        if stale:
            for path in stale:
                print(
                    f"{path.relative_to(ROOT)} is stale; run `python3 scripts/gen_abi_manifest.py --write`",
                    file=sys.stderr,
                )
            return 1
        manifest = generate_manifest()
        print(
            f"ABI artifacts current ({len(manifest['symbols'])} symbols, v{manifest['abi_version']})"
        )
        return 0
    if args.write:
        for path, rendered in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
        return 0
    sys.stdout.write(outputs[MANIFEST])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
