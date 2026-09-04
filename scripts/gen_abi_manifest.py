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
    "*mut XygDensityEmitMeta": "void *",
    "*const XygDensityEmitMeta": "const void *",
    "*const XygPayloadDensityGridMaterializeIn": "const void *",
    "*mut XygPayloadDensityGridMaterializeOut": "void *",
    "*mut XygPayloadDensityTraceEmitPlan": "void *",
    "*mut XygPayloadBuildPlan": "void *",
    "*mut XygPayloadAxisSpecAttachPlan": "void *",
    "*mut XygSceneXytcFigurePlan": "void *",
    "*mut XygSceneXytcTraceDispatchPlan": "void *",
    "*mut XygSceneXytaFigurePlan": "void *",
    "*mut XygSceneXytaTraceDispatchPlan": "void *",
    "*mut XygSceneFigureSupportFigurePlan": "void *",
    "*mut XygSceneFigureSupportTraceDispatchPlan": "void *",
    "*mut XygSceneXyclFigurePlan": "void *",
    "*mut XygSceneXynmFigurePlan": "void *",
    "*mut XygSceneXycfFigurePlan": "void *",
    "*mut XygSceneXyafAnnotationDispatchPlan": "void *",
    "*mut XygScenePublicExportFigurePlan": "void *",
    "*mut XygScenePublicExportTraceDispatchPlan": "void *",
    "*mut XygScenePolarFigurePlan": "void *",
    "*mut XygSceneEncodeProductAttachPlan": "void *",
    "*const XygSceneXytcTracePackIn": "const void *",
    "*const XygSceneXytaTracePackIn": "const void *",
    "*const XygSceneXytaTraceObservationsIn": "const void *",
    "*mut XygSceneXytaTraceObservationsOut": "void *",
    "*const XygSceneXytcTraceObservationsIn": "const void *",
    "*mut XygSceneXytcTraceObservationsOut": "void *",
    "*const XygSceneXytaColorChannelDesc": "const void *",
    "*const XygSceneXytaStyleChannelDesc": "const void *",
    "*const XygSceneXyafPackIn": "const void *",
    "*const XygSceneXycfPackIn": "const void *",
    "*const XygSceneChromePackIn": "const void *",
    "*const XygStringRef": "const void *",
    "*const XygFigureSupportAnnotationObs": "const void *",
    "*const XygFigureSupportAxisObsIn": "const void *",
    "*const XygFigureSupportTraceObsIn": "const void *",
    "*const XygScenePolarInputPackIn": "const void *",
    "*const XygXyafBulkAnnotationIn": "const void *",
    "*const XygPayloadColumnMaterializeIn": "const void *",
    "*mut XygPayloadColumnMaterializeOut": "void *",
    "*const XygPayloadTraceEmitIn": "const void *",
    "*mut XygPayloadTraceEmitOut": "void *",
    "*const XygPayloadTraceColumnDesc": "const void *",
    "*const XygPayloadTraceChannelDesc": "const void *",
    "*mut XygPayloadTraceGeomOut": "void *",
    "*mut XygPayloadTraceChannelOut": "void *",
    "*mut XygPayloadColumnShipEntry": "void *",
    "*mut XygPayloadChannelShipEntry": "void *",
    "*mut XygPayloadDensityGridBufferEntry": "void *",
    "*mut XygPayloadDensityGridAttachEntry": "void *",
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


_GRID_OUTPUT_CONTRACTS = {
    **{
        (name, "out"): ("out_capacity", channels, "bytes", 0, 1)
        for name, channels in {
            "xyg_bin_2d_mean_color": 4,
            "xyg_colormap_rgba": 4,
            "xyg_colormap_rgba_canonical": 4,
            "xyg_density_rgba": 4,
            "xyg_density_rgba_linear": 4,
            "xyg_heatmap_rgba": 4,
            "xyg_rasterize": 4,
            "xyg_rasterize_data": 4,
            "xyg_rasterize_rgb": 3,
            "xyg_rasterize_spans": 4,
        }.items()
    },
    ("xyg_pyramid_compose_color", "out"): (
        "out_capacity",
        1,
        "elements",
        -1,
        "nonnegative_level",
    ),
    ("xyg_pyramid_compose_color", "out_rgba"): (
        "out_rgba_capacity",
        4,
        "bytes",
        -1,
        "nonnegative_level",
    ),
    ("xyg_tile_store_compose_color", "out"): (
        "out_capacity",
        1,
        "elements",
        -1,
        "nonnegative_level",
    ),
    ("xyg_tile_store_compose_color", "out_rgba"): (
        "out_rgba_capacity",
        4,
        "bytes",
        -1,
        "nonnegative_level",
    ),
}

_ENCODED_OUTPUT_CONTRACTS = {
    (name, "out"): "out_capacity"
    for name in (
        "xyg_rasterize_png",
        "xyg_rasterize_png_data",
        "xyg_rasterize_png_spans",
    )
}

_DEFAULT_PALETTE_OUTPUT_CONTRACTS = {
    ("xyg_default_palette_utf8", "out"): (
        "out_cap",
        7,
        "concatenated fixed-width lowercase #rrggbb rows",
    ),
    ("xyg_default_palette_rgba8", "out"): (
        "out_cap",
        4,
        "packed straight-alpha RGBA8 rows",
    ),
}


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
            contract = _type_contract(rust_type, argument=True)
            grid_contract = _GRID_OUTPUT_CONTRACTS.get((name, arg_name))
            if grid_contract is not None:
                capacity_argument, channels, unit, failure_status, success_status = grid_contract
                pixel_format = (
                    "f32 count grid"
                    if unit == "elements"
                    else ("RGB8" if channels == 3 else "straight-alpha RGBA8")
                )
                factors = [{"argument": "w"}, {"argument": "h"}]
                if channels != 1:
                    factors.append({"constant": channels})
                contract["buffer_contract"] = (
                    f"caller-owned writable packed {pixel_format} row-major storage; must be "
                    f"non-null and contain at least {channels} * w * h bytes with a "
                    f"{channels} * w row stride; w and h must be non-zero; total byte size must "
                    f"not exceed isize::MAX; checked-size overflow or insufficient capacity "
                    f"returns {failure_status} before any write"
                )
                if unit == "elements":
                    contract["buffer_contract"] = (
                        "caller-owned writable packed f32 count-grid storage; must be non-null "
                        "and contain at least w * h elements; w and h must be non-zero; total "
                        "byte size must not exceed isize::MAX; checked-size overflow or "
                        f"insufficient capacity returns {failure_status} before any write"
                    )
                contract["length_contract"] = {
                    "unit": unit,
                    "capacity_argument": capacity_argument,
                    "required_checked_product": factors,
                    "maximum_total_bytes": "isize::MAX",
                    "pixel_format": pixel_format,
                    "layout": "packed_row_major",
                    "row_stride_checked_product": [
                        {"argument": "w"},
                        {"constant": channels},
                    ],
                    "null_output": "reject_before_write",
                    "zero_dimensions": "reject_before_write",
                    "short_capacity": "reject_before_write",
                    "success_status": success_status,
                    "failure_status": failure_status,
                }
            encoded_capacity = _ENCODED_OUTPUT_CONTRACTS.get((name, arg_name))
            if encoded_capacity is not None:
                contract["buffer_contract"] = (
                    "caller-owned writable encoded PNG byte storage; must be non-null; "
                    f"{encoded_capacity} is measured in bytes and must be in 1..=isize::MAX; "
                    "zero or impossible Rust slice capacity returns usize::MAX before output "
                    "access"
                )
                contract["length_contract"] = {
                    "unit": "bytes",
                    "capacity_argument": encoded_capacity,
                    "minimum_capacity": 1,
                    "maximum_total_bytes": "isize::MAX",
                    "payload_format": "PNG byte stream",
                    "layout": "encoded",
                    "null_output": "reject_before_access",
                    "zero_capacity": "reject_before_access",
                    "oversized_capacity": "reject_before_access",
                    "success_status": "encoded_byte_count",
                    "failure_status": "usize::MAX",
                }
            palette_contract = _DEFAULT_PALETTE_OUTPUT_CONTRACTS.get((name, arg_name))
            if palette_contract is not None:
                capacity_argument, row_bytes, payload_format = palette_contract
                contract["buffer_contract"] = (
                    f"query-first caller-owned {payload_format}; {capacity_argument} is measured "
                    "in bytes; null with zero capacity returns the required byte count, short "
                    "capacity returns the required count without mutation, and null with nonzero "
                    "capacity returns usize::MAX"
                )
                contract["length_contract"] = {
                    "unit": "bytes",
                    "capacity_argument": capacity_argument,
                    "required_checked_product": [
                        {"symbol": "xyg_default_palette_rows"},
                        {"constant": row_bytes},
                    ],
                    "payload_format": payload_format,
                    "null_output_zero_capacity": "size_query",
                    "null_output_nonzero_capacity": "usize::MAX",
                    "short_capacity": "required_byte_count_without_write",
                    "success_status": "required_byte_count",
                    "failure_status": "usize::MAX",
                }
            arguments.append({"name": arg_name, "type": contract})
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


def _length_contract_comments(symbol: dict[str, Any]) -> list[str]:
    comments = []
    for argument in symbol["arguments"]:
        contract = argument["type"].get("length_contract")
        if contract is None:
            continue
        if contract.get("null_output_zero_capacity") == "size_query":
            factors = " * ".join(
                str(factor.get("argument", factor.get("symbol", factor.get("constant"))))
                for factor in contract["required_checked_product"]
            )
            comments.append(
                f"{argument['name']}: query-first {contract['payload_format']}; "
                f"{contract['capacity_argument']} >= checked({factors}) {contract['unit']}; "
                "null with zero capacity queries the required count; short capacity returns "
                f"that count without writing; null with nonzero capacity returns {contract['failure_status']}"
            )
            continue
        if "required_checked_product" not in contract:
            comments.append(
                f"{argument['name']}: {contract['capacity_argument']} must be "
                f"{contract['minimum_capacity']}..={contract['maximum_total_bytes']} "
                f"{contract['unit']}; null output, zero capacity, or impossible slice size "
                f"returns {contract['failure_status']} before output access; success returns "
                f"{contract['success_status']}"
            )
            continue
        factors = " * ".join(
            str(factor.get("argument", factor.get("constant")))
            for factor in contract["required_checked_product"]
        )
        comments.append(
            f"{argument['name']}: {contract['capacity_argument']} >= checked({factors}) "
            f"{contract['unit']} and total bytes <= {contract['maximum_total_bytes']}; null "
            f"output, zero dimensions, arithmetic overflow, impossible slice size, or short "
            f"capacity returns {contract['failure_status']} before output access; success "
            f"returns {contract['success_status']}"
        )
    return comments


_TRACE_SIZE_ARGUMENT_RE = re.compile(
    r"(?:^n$|(?:^|_)(?:len|count|capacity|cap|bytes|width|height|rows|cols|"
    r"points|items|series|groups|marks|styles|w|h)(?:$|_))"
)
_TRACE_INTEGER_TYPES = frozenset(
    {"size_t", "uint64_t", "uint32_t", "uint16_t", "uint8_t", "int64_t", "int32_t"}
)


def _trace_metadata(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build privacy-bounded metadata for generated test tracing.

    Pointer arguments are recorded only as present/absent. Scalar values are
    recorded only when their ABI names identify sizes or capacities, so an
    execution trace cannot accidentally retain user data.
    """

    metadata: dict[str, dict[str, Any]] = {}
    for symbol in manifest["symbols"]:
        if symbol["name"] == "xyg_abi_version":
            continue
        arguments = []
        for index, argument in enumerate(symbol["arguments"]):
            contract = argument["type"]
            if contract["pointer_depth"]:
                arguments.append((index, argument["name"], "pointer"))
            elif contract["c"] in _TRACE_INTEGER_TYPES and _TRACE_SIZE_ARGUMENT_RE.search(
                argument["name"]
            ):
                arguments.append((index, argument["name"], "size"))
        metadata[symbol["name"]] = {
            "node_name": symbol["node_name"],
            "arguments": arguments,
            "returns_size": symbol["returns"]["c"] == "size_t",
        }
    return metadata


def render_python_bindings(manifest: dict[str, Any]) -> str:
    symbols = manifest["symbols"]
    version = next(item for item in symbols if item["name"] == "xyg_abi_version")
    lines = [
        '"""Generated ctypes declarations. Do not edit; run scripts/gen_abi_manifest.py --write."""',
        "",
        "from __future__ import annotations",
        "",
        "import ctypes",
        "import json",
        "import os",
        "from typing import Any, TypedDict",
        "",
        "# fmt: off",
        "",
        "class _AbiTraceMetadata(TypedDict):",
        "    node_name: str",
        "    arguments: list[tuple[int, str, str]]",
        "    returns_size: bool",
        "",
        "",
        f"ABI_VERSION = {manifest['abi_version']}",
        f'SIGNATURE_SHA256 = "{manifest["signature_sha256"]}"',
        f"ABI_TRACE_METADATA: dict[str, _AbiTraceMetadata] = {_trace_metadata(manifest)!r}",
        "",
        "",
        "class GeneratedAbiTraceFault(RuntimeError):",
        '    """Sentinel raised only by the generated test trace proxy."""',
        "",
        "",
        "def _trace_pointer_present(value: Any) -> bool:",
        "    if value is None:",
        "        return False",
        "    scalar = getattr(value, 'value', value)",
        "    return scalar is not None and scalar != 0",
        "",
        "",
        "def _trace_size_value(value: Any) -> str:",
        "    return str(int(getattr(value, 'value', value)))",
        "",
        "",
        "class _GeneratedAbiTraceProxy:",
        "    def __init__(self, lib: Any, observer: Any, fault_symbols: Any) -> None:",
        "        self._lib = lib",
        "        self._observer = observer",
        "        self._fault_symbols = frozenset(fault_symbols)",
        "        self._call_index = 0",
        "",
        "    def __getattr__(self, name: str) -> Any:",
        "        target = getattr(self._lib, name)",
        "        metadata = ABI_TRACE_METADATA.get(name)",
        "        if metadata is None:",
        "            return target",
        "",
        "        def traced(*args: Any) -> Any:",
        "            self._call_index += 1",
        "            shaped = {}",
        "            for index, argument_name, kind in metadata['arguments']:",
        "                value = args[index]",
        "                if kind == 'pointer':",
        "                    shaped[argument_name] = {",
        "                        'kind': 'pointer',",
        "                        'present': _trace_pointer_present(value),",
        "                    }",
        "                else:",
        "                    shaped[argument_name] = {",
        "                        'kind': 'size',",
        "                        'value': _trace_size_value(value),",
        "                    }",
        "            event = {",
        "                'call_index': self._call_index,",
        "                'symbol': name,",
        "                'arguments': shaped,",
        "            }",
        "            if name in self._fault_symbols:",
        "                event['outcome'] = 'injected_fault'",
        "                self._observer(event)",
        "                raise GeneratedAbiTraceFault(f'XYG_ABI_TRACE_FAULT:{name}')",
        "            try:",
        "                result = target(*args)",
        "            except BaseException as exc:",
        "                event['outcome'] = 'error'",
        "                event['error_type'] = type(exc).__name__",
        "                self._observer(event)",
        "                raise",
        "            event['outcome'] = 'ok'",
        "            if metadata['returns_size']:",
        "                event['returned_size'] = str(int(result))",
        "            self._observer(event)",
        "            return result",
        "",
        "        return traced",
        "",
        "",
        "def trace_generated_abi(lib: Any, observer: Any, fault_symbols: Any = ()) -> Any:",
        '    """Wrap a bound library for privacy-bounded test-only ABI tracing."""',
        "",
        "    return _GeneratedAbiTraceProxy(lib, observer, fault_symbols)",
        "",
        "",
        "def trace_generated_abi_from_env(lib: Any) -> Any:",
        '    """Enable JSONL tracing only when the executable-proof env is set."""',
        "",
        "    path = os.environ.get('XYG_ABI_TRACE_FILE')",
        "    if not path:",
        "        return lib",
        "    journey = os.environ.get('XYG_ABI_TRACE_JOURNEY', 'unclassified')",
        "    faults = filter(None, os.environ.get('XYG_ABI_TRACE_FAULT', '').split(','))",
        "",
        "    def observe(event: dict[str, Any]) -> None:",
        "        record = {'host': 'python', 'journey': journey, **event}",
        "        payload = (json.dumps(record, sort_keys=True, separators=(',', ':')) + '\\n').encode()",
        "        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)",
        "        try:",
        "            os.write(fd, payload)",
        "        finally:",
        "            os.close(fd)",
        "",
        "    return trace_generated_abi(lib, observe, faults)",
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
        for contract_comment in _length_contract_comments(symbol):
            lines.append(f"    # Buffer contract: {contract_comment}")
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
        'import { appendFileSync } from "node:fs";',
        "",
        f"export const ABI_VERSION = {manifest['abi_version']};",
        f'export const SIGNATURE_SHA256 = "{manifest["signature_sha256"]}";',
        f"export const ABI_TRACE_METADATA = {json.dumps(_trace_metadata(manifest), separators=(',', ':'))};",
        "",
        "export class GeneratedAbiTraceFault extends Error {",
        "  constructor(symbol) {",
        "    super(`XYG_ABI_TRACE_FAULT:${symbol}`);",
        '    this.name = "GeneratedAbiTraceFault";',
        "  }",
        "}",
        "",
        "const _rawGeneratedAbi = new Map();",
        "let _generatedAbiTraceIndex = 0;",
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
    lines.extend(["", "function _setGeneratedAbiBinding(name, value) {", "  switch (name) {"])
    for symbol in symbols:
        if symbol["name"] == "xyg_abi_version":
            continue
        lines.append(f'    case "{symbol["node_name"]}": {symbol["node_name"]} = value; return;')
    lines.extend(
        [
            "    default: throw new Error(`unknown generated ABI binding: ${name}`);",
            "  }",
            "}",
            "",
            "function _tracePointerPresent(value) {",
            "  return value !== null && value !== undefined && value !== 0 && value !== 0n;",
            "}",
            "",
            "function _traceGeneratedCall(symbol, raw, metadata, observer, faultSymbols) {",
            "  return (...args) => {",
            "    _generatedAbiTraceIndex += 1;",
            "    const shaped = {};",
            "    for (const [index, argumentName, kind] of metadata.arguments) {",
            "      const value = args[index];",
            '      shaped[argumentName] = kind === "pointer"',
            '        ? { kind: "pointer", present: _tracePointerPresent(value) }',
            '        : { kind: "size", value: String(value) };',
            "    }",
            "    const event = { call_index: _generatedAbiTraceIndex, symbol, arguments: shaped };",
            "    if (faultSymbols.has(symbol)) {",
            '      event.outcome = "injected_fault";',
            "      observer(event);",
            "      throw new GeneratedAbiTraceFault(symbol);",
            "    }",
            "    try {",
            "      const result = raw(...args);",
            '      event.outcome = "ok";',
            "      if (metadata.returns_size) event.returned_size = String(result);",
            "      observer(event);",
            "      return result;",
            "    } catch (error) {",
            '      event.outcome = "error";',
            '      event.error_type = error?.constructor?.name ?? "Error";',
            "      observer(event);",
            "      throw error;",
            "    }",
            "  };",
            "}",
            "",
            "export function _testConfigureGeneratedAbiTrace(observer, faultSymbols = []) {",
            "  const faults = new Set(faultSymbols);",
            "  _generatedAbiTraceIndex = 0;",
            "  for (const [symbol, metadata] of Object.entries(ABI_TRACE_METADATA)) {",
            "    const nodeName = metadata.node_name;",
            "    const raw = _rawGeneratedAbi.get(nodeName);",
            "    if (!raw) continue;",
            "    _setGeneratedAbiBinding(",
            "      nodeName,",
            "      observer == null && faults.size === 0",
            "        ? raw",
            "        : _traceGeneratedCall(symbol, raw, metadata, observer ?? (() => {}), faults),",
            "    );",
            "  }",
            "}",
            "",
            "export function _configureGeneratedAbiTraceFromEnv() {",
            "  const path = process.env.XYG_ABI_TRACE_FILE;",
            "  if (!path) return;",
            '  const journey = process.env.XYG_ABI_TRACE_JOURNEY ?? "unclassified";',
            '  const faults = (process.env.XYG_ABI_TRACE_FAULT ?? "").split(",").filter(Boolean);',
            "  _testConfigureGeneratedAbiTrace((event) => {",
            '    const record = { host: "node", journey, ...event };',
            "    appendFileSync(path, `${JSON.stringify(record)}\\n`, { mode: 0o600 });",
            "  }, faults);",
            "}",
        ]
    )
    lines.extend(["", "export function bindGeneratedAbi(lib) {"])
    for symbol in symbols:
        if symbol["name"] == "xyg_abi_version":
            continue
        for contract_comment in _length_contract_comments(symbol):
            lines.append(f"  // Buffer contract: {contract_comment}")
        lines.extend(
            [
                f'  {symbol["node_name"]} = lib.func("{symbol["c_signature"]}");',
                f'  _rawGeneratedAbi.set("{symbol["node_name"]}", {symbol["node_name"]});',
            ]
        )
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
    for symbol in manifest["symbols"]:
        for contract_comment in _length_contract_comments(symbol):
            lines.append(f"/* Buffer contract: {contract_comment}. */")
        lines.append(f"{symbol['c_signature']};")
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
    core = root / "crates/xyg-core/src"
    text = (core / "lib.rs").read_text(encoding="utf-8")
    ffi_files = [
        core / "scene_bulk_pack_ffi.rs",
        core / "payload_trace_emit_ffi.rs",
        core / "scene_xyta_trace_observations_ffi.rs",
        core / "scene_xytc_trace_observations_ffi.rs",
    ]
    for ffi in ffi_files:
        if ffi.is_file():
            text = text + "\n" + ffi.read_text(encoding="utf-8")
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
