#!/usr/bin/env python3
"""Generate the thin browser adapter for the raw xyg-wasm export manifest."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "spec" / "wasm" / "abi.json"
RUST = ROOT / "crates" / "xyg-wasm" / "src" / "lib.rs"
AGGREGATE_RUST = ROOT / "crates" / "xyg-wasm" / "src" / "aggregate.rs"
GRAPH_RUST = ROOT / "crates" / "xyg-wasm" / "src" / "graph.rs"
OUTPUT = ROOT / "js" / "src" / "wasm_abi_generated.ts"
RUST_TYPED_SERIES_OUTPUT = ROOT / "crates" / "xyg-wasm" / "src" / "typed_series_abi_generated.rs"

TYPED_SERIES_KEYS = {
    "request_magic",
    "header_offsets",
    "header_flags",
    "descriptor_offsets",
    "flags",
    "kinds",
}
HEADER_WIDTHS = {
    "version": 4,
    "header_bytes": 4,
    "flags": 4,
    "series_count": 4,
    "record_count": 4,
    "title_bytes": 4,
    "x_label_bytes": 4,
    "y_label_bytes": 4,
    "reserved0": 4,
    "width": 8,
    "height": 8,
    "margins": 32,
    "x_axis_id": 8,
    "y_axis_id": 8,
    "x_scale_kind": 4,
    "y_scale_kind": 4,
    "x_mask_nonpositive": 4,
    "y_mask_nonpositive": 4,
    "x_lo": 8,
    "x_hi": 8,
    "x_constant": 8,
    "y_lo": 8,
    "y_hi": 8,
    "y_constant": 8,
    "reserved_tail": 24,
}
DESCRIPTOR_WIDTHS = {
    "kind": 4,
    "symbol": 4,
    "record_count": 4,
    "flags": 4,
    "stable_id_base": 8,
    "diameter": 8,
    "stroke_width": 8,
    "fill_rgba": 4,
    "stroke_rgba": 4,
    "x": 4,
    "y": 4,
    "y0": 4,
    "y1": 4,
    "diameters": 4,
    "stable_ids": 4,
}
HEADER_FLAG_KEYS = {"auto_margins", "auto_domain"}
DESCRIPTOR_FLAG_KEYS = {
    "diameters",
    "y0",
    "y1",
    "fill_rgba",
    "stroke_rgba",
    "stable_id_base",
    "stable_ids",
}
KIND_CODES = {"scatter": 0, "line": 1, "bar": 2, "area": 3}
TYPED_SERIES_NUMERIC_KEYS = {
    "typed_series_version",
    "typed_series_header_bytes",
    "typed_series_descriptor_bytes",
    "typed_series_max_series",
    "typed_series_max_records",
    "typed_series_max_text_bytes",
    "typed_series_max_symbol_code",
    "typed_series_peak_fixed_bytes",
    "typed_series_peak_bytes_per_record",
    "typed_series_peak_bytes_per_series",
    "typed_series_peak_input_multiplier",
}


def validate_typed_series(manifest: dict[str, object]) -> None:
    for name in TYPED_SERIES_NUMERIC_KEYS:
        if type(manifest.get(name)) is not int:
            raise SystemExit(f"{name} must be an integer")
    contract = manifest.get("typed_series")
    if not isinstance(contract, dict):
        raise SystemExit("typed_series must be a structured value")
    if set(contract) != TYPED_SERIES_KEYS:
        raise SystemExit("typed_series has missing or unknown keys")
    magic = contract.get("request_magic")
    try:
        magic_bytes = magic.encode("ascii") if isinstance(magic, str) else b""
    except UnicodeEncodeError:
        magic_bytes = b""
    if len(magic_bytes) != 4:
        raise SystemExit("typed_series request_magic must be four ASCII bytes")
    for name, bound_key, widths in (
        ("header_offsets", "typed_series_header_bytes", HEADER_WIDTHS),
        ("descriptor_offsets", "typed_series_descriptor_bytes", DESCRIPTOR_WIDTHS),
    ):
        offsets = contract.get(name)
        if not isinstance(offsets, dict) or set(offsets) != set(widths):
            raise SystemExit(f"typed_series {name} has missing or unknown fields")
        bound = int(manifest[bound_key])
        occupied: list[tuple[int, int, str]] = []
        for field, raw in offsets.items():
            if type(raw) is not int:
                raise SystemExit(f"typed_series {name}.{field} must be an integer")
            value = int(raw)
            width = widths[field]
            alignment = min(width, 8)
            if value < 0 or value + width > bound or value % alignment:
                raise SystemExit(f"typed_series {name}.{field} is outside its record")
            for start, end, other in occupied:
                if value < end and start < value + width:
                    raise SystemExit(f"typed_series {name}.{field} overlaps {other}")
            occupied.append((value, value + width, field))
    for name, expected in (("header_flags", HEADER_FLAG_KEYS), ("flags", DESCRIPTOR_FLAG_KEYS)):
        values = contract.get(name)
        if not isinstance(values, dict) or set(values) != expected:
            raise SystemExit(f"typed_series {name} has missing or unknown fields")
        if any(type(value) is not int for value in values.values()):
            raise SystemExit(f"typed_series {name} values must be integers")
        parsed = [int(value) for value in values.values()]
        if len(parsed) != len(set(parsed)) or any(
            value <= 0 or value > 0xFFFFFFFF or value & (value - 1) for value in parsed
        ):
            raise SystemExit(f"typed_series {name} values must be unique one-hot u32 flags")
    kinds = contract.get("kinds")
    if (
        not isinstance(kinds, dict)
        or any(type(value) is not int for value in kinds.values())
        or kinds != KIND_CODES
    ):
        raise SystemExit("typed_series kinds must be the exact bounded mark-kind map")


def validate_semantic_graph(manifest: dict[str, object]) -> None:
    contract = manifest.get("semantic_graph")
    required = {
        "request_magic",
        "version",
        "header_bytes",
        "header_offsets",
        "max_input_elements",
        "max_painter_traces",
        "themes",
        "semantic_code_max",
        "state_flag_mask",
        "compound_planes",
        "tier",
    }
    if not isinstance(contract, dict) or set(contract) != required:
        raise SystemExit("semantic_graph has missing or unknown fields")
    if contract["request_magic"] != "XYGG" or contract["tier"] != "direct-only":
        raise SystemExit("semantic_graph magic/tier contract is invalid")
    if contract["themes"] != {"light": 0, "dark": 1}:
        raise SystemExit("semantic_graph themes must be the exact closed map")
    expected_compound = {
        "order": ["parents", "parent_validity", "collapsed"],
        "parents": {"type": "u64", "count": "node_count", "default": 0},
        "parent_validity": {"type": "u8", "count": "node_count", "default": 0},
        "collapsed": {"type": "u8", "count": "node_count", "default": 0},
        "presence": "all-three-together-or-zero-defaults",
        "placement": "align8-after-edge-flags; align8-after-collapsed-before-node-label-lengths",
    }
    if contract["compound_planes"] != expected_compound:
        raise SystemExit("semantic_graph compound planes differ from XYGG v3")
    expected_offsets = {
        "version": 4,
        "header_bytes": 8,
        "theme": 12,
        "node_count": 16,
        "edge_count": 20,
        "title_bytes": 24,
        "reserved0": 28,
        "width": 32,
        "height": 40,
        "reserved_tail": 48,
    }
    if contract["header_offsets"] != expected_offsets:
        raise SystemExit("semantic_graph header offsets differ from XYGG v1")
    for key in (
        "version",
        "header_bytes",
        "max_input_elements",
        "max_painter_traces",
        "semantic_code_max",
        "state_flag_mask",
    ):
        if type(contract[key]) is not int or int(contract[key]) <= 0:
            raise SystemExit(f"semantic_graph {key} must be a positive integer")


def validate_compound_transition(manifest: dict[str, object]) -> None:
    expected = {
        "request_magic": "XYGC",
        "request_version": 1,
        "request_header_bytes": 40,
        "request_offsets": {
            "version": 4,
            "header_bytes": 8,
            "action": 12,
            "lod_tier": 16,
            "node_count": 20,
            "target_id": 24,
            "reserved": 32,
        },
        "request_plane_bytes_per_node": 18,
        "request_planes": ["node_ids_u64", "parents_u64", "parent_validity_u8", "collapsed_u8"],
        "output_magic": "XYCO",
        "output_version": 1,
        "output_header_bytes": 16,
        "output_offsets": {"version": 4, "header_bytes": 8, "changed": 12, "collapsed": 16},
        "actions": {"expand": 0, "collapse": 1, "toggle": 2},
        "lod_tiers": {"direct": 0},
        "max_nodes": 1024,
    }
    if manifest.get("compound_transition") != expected:
        raise SystemExit("compound_transition differs from the exact XYGC/XYCO v1 contract")


def render(manifest: dict[str, object]) -> str:
    abi_version = int(manifest["abi_version"])
    scene_version = int(manifest["scene_version"])
    painter_version = int(manifest["painter_version"])
    painter_header_bytes = int(manifest["painter_header_bytes"])
    painter_trace_bytes = int(manifest["painter_trace_bytes"])
    painter_tick_bytes = int(manifest["painter_tick_bytes"])
    painter_max_traces = int(manifest["painter_max_traces"])
    typed_series_version = int(manifest["typed_series_version"])
    typed_series_header_bytes = int(manifest["typed_series_header_bytes"])
    typed_series_descriptor_bytes = int(manifest["typed_series_descriptor_bytes"])
    typed_series_max_series = int(manifest["typed_series_max_series"])
    typed_series_max_records = int(manifest["typed_series_max_records"])
    typed_series_max_text_bytes = int(manifest["typed_series_max_text_bytes"])
    typed_series_max_symbol_code = int(manifest["typed_series_max_symbol_code"])
    typed_series_peak_fixed_bytes = int(manifest["typed_series_peak_fixed_bytes"])
    typed_series_peak_bytes_per_record = int(manifest["typed_series_peak_bytes_per_record"])
    typed_series_peak_bytes_per_series = int(manifest["typed_series_peak_bytes_per_series"])
    typed_series_peak_input_multiplier = int(manifest["typed_series_peak_input_multiplier"])
    typed_series = manifest["typed_series"]
    max_arena_bytes = int(manifest["max_arena_bytes"])
    painter_max_legend_bytes = int(manifest["painter_max_legend_bytes"])
    aggregate = manifest["aggregate"]
    graph = manifest["graph"]
    temporal_graph = manifest["temporal_graph"]
    semantic_graph = manifest["semantic_graph"]
    compound_transition = manifest["compound_transition"]
    statuses = manifest["statuses"]
    exports = manifest["exports"]
    if (
        not isinstance(statuses, dict)
        or not isinstance(exports, list)
        or not isinstance(aggregate, dict)
        or not isinstance(typed_series, dict)
        or not isinstance(graph, dict)
        or not isinstance(temporal_graph, dict)
        or not isinstance(semantic_graph, dict)
    ):
        raise ValueError("aggregate, statuses, and exports must be structured values")

    lines = [
        "// Generated by scripts/gen_wasm_abi.py from spec/wasm/abi.json.",
        "// Do not hand-edit raw WASM signatures or status numbers here.",
        "",
        f"export const XYG_WASM_ABI_VERSION = {abi_version} as const;",
        f"export const XYG_WASM_SCENE_VERSION = {scene_version} as const;",
        f"export const XYG_WASM_PAINTER_VERSION = {painter_version} as const;",
        f"export const XYG_WASM_PAINTER_HEADER_BYTES = {painter_header_bytes} as const;",
        f"export const XYG_WASM_PAINTER_TRACE_BYTES = {painter_trace_bytes} as const;",
        f"export const XYG_WASM_PAINTER_TICK_BYTES = {painter_tick_bytes} as const;",
        f"export const XYG_WASM_PAINTER_MAX_TRACES = {painter_max_traces} as const;",
        f"export const XYG_WASM_TYPED_SERIES_VERSION = {typed_series_version} as const;",
        f"export const XYG_WASM_TYPED_SERIES_HEADER_BYTES = {typed_series_header_bytes} as const;",
        f"export const XYG_WASM_TYPED_SERIES_DESCRIPTOR_BYTES = {typed_series_descriptor_bytes} as const;",
        f"export const XYG_WASM_TYPED_SERIES_MAX_SERIES = {typed_series_max_series} as const;",
        f"export const XYG_WASM_TYPED_SERIES_MAX_RECORDS = {typed_series_max_records} as const;",
        f"export const XYG_WASM_TYPED_SERIES_MAX_TEXT_BYTES = {typed_series_max_text_bytes} as const;",
        f"export const XYG_WASM_TYPED_SERIES_MAX_SYMBOL_CODE = {typed_series_max_symbol_code} as const;",
        f"export const XYG_WASM_TYPED_SERIES_PEAK_FIXED_BYTES = {typed_series_peak_fixed_bytes} as const;",
        f"export const XYG_WASM_TYPED_SERIES_PEAK_BYTES_PER_RECORD = {typed_series_peak_bytes_per_record} as const;",
        f"export const XYG_WASM_TYPED_SERIES_PEAK_BYTES_PER_SERIES = {typed_series_peak_bytes_per_series} as const;",
        f"export const XYG_WASM_TYPED_SERIES_PEAK_INPUT_MULTIPLIER = {typed_series_peak_input_multiplier} as const;",
        f"export const XYG_WASM_TYPED_SERIES_MAGIC = {json.dumps(typed_series['request_magic'])} as const;",
        f"export const XYG_WASM_TYPED_SERIES_HEADER_OFFSETS = {json.dumps(typed_series['header_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_TYPED_SERIES_HEADER_FLAGS = {json.dumps(typed_series['header_flags'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_TYPED_SERIES_DESCRIPTOR_OFFSETS = {json.dumps(typed_series['descriptor_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_TYPED_SERIES_FLAGS = {json.dumps(typed_series['flags'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_TYPED_SERIES_KINDS = {json.dumps(typed_series['kinds'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_MAGIC = {json.dumps(semantic_graph['request_magic'])} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_VERSION = {int(semantic_graph['version'])} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_HEADER_BYTES = {int(semantic_graph['header_bytes'])} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_MAX_INPUT_ELEMENTS = {int(semantic_graph['max_input_elements'])} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_MAX_PAINTER_TRACES = {int(semantic_graph['max_painter_traces'])} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS = {json.dumps(semantic_graph['header_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_THEMES = {json.dumps(semantic_graph['themes'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_MAX_CODE = {int(semantic_graph['semantic_code_max'])} as const;",
        f"export const XYG_WASM_SEMANTIC_GRAPH_STATE_FLAG_MASK = {int(semantic_graph['state_flag_mask'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_MAX_NODES = {int(compound_transition['max_nodes'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_MAGIC = {json.dumps(compound_transition['request_magic'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_VERSION = {int(compound_transition['request_version'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_HEADER_BYTES = {int(compound_transition['request_header_bytes'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_OFFSETS = {json.dumps(compound_transition['request_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_PLANE_BYTES_PER_NODE = {int(compound_transition['request_plane_bytes_per_node'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_OUTPUT_MAGIC = {json.dumps(compound_transition['output_magic'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_OUTPUT_VERSION = {int(compound_transition['output_version'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_OUTPUT_HEADER_BYTES = {int(compound_transition['output_header_bytes'])} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_OUTPUT_OFFSETS = {json.dumps(compound_transition['output_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_ACTIONS = {json.dumps(compound_transition['actions'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_COMPOUND_TRANSITION_LOD_TIERS = {json.dumps(compound_transition['lod_tiers'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_MAX_ARENA_BYTES = {max_arena_bytes} as const;",
        f"export const XYG_WASM_PAINTER_MAX_LEGEND_BYTES = {painter_max_legend_bytes} as const;",
        f"export const XYG_WASM_AGGREGATE_VERSION = {int(aggregate['version'])} as const;",
        f"export const XYG_WASM_AGGREGATE_MAGIC = {json.dumps(aggregate['request_magic'])} as const;",
        f"export const XYG_WASM_AGGREGATE_HEADER_BYTES = {int(aggregate['header_bytes'])} as const;",
        f"export const XYG_WASM_AGGREGATE_OUTPUT_VERSION = {int(aggregate['output_version'])} as const;",
        f"export const XYG_WASM_AGGREGATE_OUTPUT_MAGIC = {json.dumps(aggregate['output_magic'])} as const;",
        f"export const XYG_WASM_AGGREGATE_OUTPUT_HEADER_BYTES = {int(aggregate['output_header_bytes'])} as const;",
        f"export const XYG_WASM_AGGREGATE_FLAG_MEAN_COLOR = {int(aggregate['flag_mean_color'])} as const;",
        f"export const XYG_WASM_AGGREGATE_CHECKPOINT_POINTS = {int(aggregate['checkpoint_points'])} as const;",
        f"export const XYG_WASM_AGGREGATE_MAX_REQUEST_BYTES = {int(aggregate['max_request_bytes'])} as const;",
        f"export const XYG_WASM_AGGREGATE_TOTAL_MEMORY_BYTES = {int(aggregate['total_memory_bytes'])} as const;",
        *[
            f"export const XYG_WASM_AGGREGATE_{name.upper()} = {int(aggregate[name])} as const;"
            for name in (
                "request_stride_count",
                "request_stride_color",
                "accumulator_stride_count",
                "accumulator_stride_color",
                "output_stride_count",
                "output_stride_color",
                "checkpoint_stride_count",
                "checkpoint_stride_color",
                "request_copy_factor",
                "output_copy_factor",
            )
        ],
        f"export const XYG_WASM_AGGREGATE_MAX_POINTS = {int(aggregate['max_points'])} as const;",
        f"export const XYG_WASM_AGGREGATE_MAX_GRID_CELLS = {int(aggregate['max_grid_cells'])} as const;",
        f"export const XYG_WASM_AGGREGATE_OFFSETS = {json.dumps(aggregate['request_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_AGGREGATE_OUTPUT_OFFSETS = {json.dumps(aggregate['output_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_GRAPH_VERSION = {int(graph['version'])} as const;",
        f"export const XYG_WASM_GRAPH_MAGIC = {json.dumps(graph['request_magic'])} as const;",
        f"export const XYG_WASM_GRAPH_HEADER_BYTES = {int(graph['header_bytes'])} as const;",
        f"export const XYG_WASM_GRAPH_OFFSETS = {json.dumps(graph['request_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_GRAPH_FLAGS = {json.dumps(graph['flags'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_GRAPH_OUTPUT_MAGIC = {json.dumps(graph['output_magic'])} as const;",
        f"export const XYG_WASM_GRAPH_OUTPUT_VERSION = {int(graph['output_version'])} as const;",
        f"export const XYG_WASM_GRAPH_OUTPUT_HEADER_BYTES = {int(graph['output_header_bytes'])} as const;",
        f"export const XYG_WASM_GRAPH_OUTPUT_OFFSETS = {json.dumps(graph['output_offsets'], separators=(',', ':'))} as const;",
        f"export const XYG_WASM_GRAPH_MAX_NODES = {int(graph['max_nodes'])} as const;",
        f"export const XYG_WASM_GRAPH_MAX_EDGES = {int(graph['max_edges'])} as const;",
        f"export const XYG_WASM_GRAPH_MAX_STEPS = {int(graph['max_steps'])} as const;",
        f"export const XYG_WASM_GRAPH_REQUEST_COPY_FACTOR = {int(graph['request_copy_factor'])} as const;",
        f"export const XYG_WASM_GRAPH_CONSTRUCTION_BYTES_PER_NODE = {int(graph['construction_bytes_per_node'])} as const;",
        f"export const XYG_WASM_GRAPH_CONSTRUCTION_BYTES_PER_EDGE = {int(graph['construction_bytes_per_edge'])} as const;",
        f"export const XYG_WASM_GRAPH_FIRST_PAINT_STEPS = {int(graph['first_paint_steps'])} as const;",
        f"export const XYG_WASM_GRAPH_DEFAULT_CHUNK_STEPS = {int(graph['default_chunk_steps'])} as const;",
        f"export const XYG_WASM_GRAPH_DEFAULT_MAX_WALL_MS = {int(graph['default_max_wall_ms'])} as const;",
        f"export const XYG_WASM_TEMPORAL_GRAPH_MAGIC = {json.dumps(temporal_graph['request_magic'])} as const;",
        f"export const XYG_WASM_TEMPORAL_GRAPH_VERSION = {int(temporal_graph['version'])} as const;",
        f"export const XYG_WASM_TEMPORAL_GRAPH_CREATE_HEADER_BYTES = {int(temporal_graph['create_header_bytes'])} as const;",
        f"export const XYG_WASM_TEMPORAL_GRAPH_FRAME_HEADER_BYTES = {int(temporal_graph['frame_header_bytes'])} as const;",
        f"export const XYG_WASM_TEMPORAL_GRAPH_OUTPUT_MAGIC = {json.dumps(temporal_graph['output_magic'])} as const;",
        f"export const XYG_WASM_TEMPORAL_GRAPH_OUTPUT_HEADER_BYTES = {int(temporal_graph['output_header_bytes'])} as const;",
        f"export const XYG_WASM_TEMPORAL_GRAPH_MAX_ENTITIES = {int(temporal_graph['max_entities'])} as const;",
        "export const XYG_WASM_STATUS = {",
    ]
    for name, value in statuses.items():
        lines.append(f"  {name}: {int(value)},")
    lines.extend(["} as const;", "", "export interface XygWasmExports {"])
    lines.append("  memory: WebAssembly.Memory;")
    for item in exports:
        if not isinstance(item, dict):
            raise ValueError("export entries must be objects")
        name = str(item["name"])
        params_spec = item.get("params")
        result_spec = item.get("result")
        if not isinstance(params_spec, list) or not all(
            isinstance(value, str) for value in params_spec
        ):
            raise ValueError(f"{name} params must be a string list")
        if not isinstance(result_spec, str):
            raise ValueError(f"{name} result must be a string")
        arity = len(params_spec)
        params = ", ".join(f"arg{index}: number" for index in range(arity))
        lines.append(f"  {name}({params}): number;")
    lines.extend(
        [
            "}",
            "",
            "export function bindXygWasmExports(instance: WebAssembly.Instance): XygWasmExports {",
            "  const raw = instance.exports as Record<string, unknown>;",
            "  if (!(raw.memory instanceof WebAssembly.Memory)) {",
            '    throw new Error("XYG WASM export memory is missing");',
            "  }",
        ]
    )
    for item in exports:
        name = str(item["name"])
        arity = len(item["params"])
        lines.extend(
            [
                f'  if (typeof raw.{name} !== "function" || (raw.{name} as Function).length !== {arity}) {{',
                f'    throw new Error("XYG WASM export {name} has an incompatible signature");',
                "  }",
            ]
        )
    lines.extend(
        [
            "  const bound = raw as unknown as XygWasmExports;",
            "  if (bound.xyg_wasm_abi_version() !== XYG_WASM_ABI_VERSION) {",
            '    throw new Error("XYG WASM ABI version is incompatible");',
            "  }",
            "  if (bound.xyg_wasm_scene_version() !== XYG_WASM_SCENE_VERSION) {",
            '    throw new Error("XYG canonical scene version is incompatible");',
            "  }",
            "  return bound;",
            "}",
            "",
            "export function readXygWasmError(exports: XygWasmExports, handle: number): string {",
            "  const ptr = exports.xyg_wasm_last_error_ptr(handle) >>> 0;",
            "  const len = exports.xyg_wasm_last_error_len(handle) >>> 0;",
            '  if (!ptr || !len) return "XYG WASM operation failed";',
            "  const end = ptr + len;",
            "  if (!Number.isSafeInteger(end) || end > exports.memory.buffer.byteLength) {",
            '    return "XYG WASM returned an invalid error range";',
            "  }",
            "  return new TextDecoder().decode(new Uint8Array(exports.memory.buffer, ptr, len));",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def render_typed_series_rust(manifest: dict[str, object]) -> str:
    contract = manifest["typed_series"]
    assert isinstance(contract, dict)
    lines = [
        "// Generated by scripts/gen_wasm_abi.py from spec/wasm/abi.json.",
        "// Do not hand-edit this typed-series wire contract.",
        "",
        f'pub const SERIES_MAGIC: &[u8; 4] = b"{contract["request_magic"]}";',
        f"pub const SERIES_VERSION: u32 = {int(manifest['typed_series_version'])};",
        f"pub const COMPILE_HEADER_BYTES: usize = {int(manifest['typed_series_header_bytes'])};",
        f"pub const SERIES_DESCRIPTOR_BYTES: usize = {int(manifest['typed_series_descriptor_bytes'])};",
        f"pub const MAX_SERIES: usize = {int(manifest['typed_series_max_series']):_};",
        f"pub const MAX_RECORDS: usize = {int(manifest['typed_series_max_records']):_};",
        f"pub const MAX_TEXT_BYTES: usize = {int(manifest['typed_series_max_text_bytes']):_};",
        f"pub const MAX_SYMBOL_CODE: u32 = {int(manifest['typed_series_max_symbol_code'])};",
        f"pub const SERIES_PEAK_FIXED_BYTES: usize = {int(manifest['typed_series_peak_fixed_bytes']):_};",
        f"pub const SERIES_PEAK_BYTES_PER_RECORD: usize = {int(manifest['typed_series_peak_bytes_per_record']):_};",
        f"pub const SERIES_PEAK_BYTES_PER_SERIES: usize = {int(manifest['typed_series_peak_bytes_per_series']):_};",
        f"pub const SERIES_PEAK_INPUT_MULTIPLIER: usize = {int(manifest['typed_series_peak_input_multiplier'])};",
    ]
    for group, prefix in (
        ("header_offsets", "HEADER"),
        ("descriptor_offsets", "DESCRIPTOR"),
        ("header_flags", "HEADER_FLAG"),
        ("flags", "DESCRIPTOR_FLAG"),
        ("kinds", "KIND"),
    ):
        values = contract[group]
        assert isinstance(values, dict)
        for name, value in values.items():
            ty = "usize" if "offsets" in group else "u32"
            lines.append(f"pub const {prefix}_{name.upper()}: {ty} = {int(value)};")
    lines.extend(
        [
            "pub const HEADER_FLAG_KNOWN: u32 = HEADER_FLAG_AUTO_MARGINS | HEADER_FLAG_AUTO_DOMAIN;",
            "pub const DESCRIPTOR_FLAG_KNOWN: u32 = "
            + "\n    | ".join(
                f"DESCRIPTOR_FLAG_{name.upper()}" for name in sorted(contract["flags"])
            )
            + ";",
            "",
        ]
    )
    semantic = manifest["semantic_graph"]
    assert isinstance(semantic, dict)
    lines.extend(
        [
            f'pub const SEMANTIC_GRAPH_MAGIC: &[u8; 4] = b"{semantic["request_magic"]}";',
            f"pub const SEMANTIC_GRAPH_REQUEST_VERSION: u32 = {int(semantic['version'])};",
            f"pub const SEMANTIC_GRAPH_HEADER_BYTES: usize = {int(semantic['header_bytes'])};",
            f"pub const SEMANTIC_GRAPH_MAX_INPUT_ELEMENTS: usize = {int(semantic['max_input_elements']):_};",
            f"pub const SEMANTIC_GRAPH_MAX_PAINTER_TRACES: usize = {int(semantic['max_painter_traces']):_};",
            "",
        ]
    )
    return "\n".join(lines)


def verify_rust(manifest: dict[str, object]) -> None:
    typed_series = manifest["typed_series"]
    if not isinstance(typed_series, dict):
        raise SystemExit("typed_series must be a structured value")
    source = RUST.read_text(encoding="utf-8")
    constants = {
        "WASM_ABI_VERSION": int(manifest["abi_version"]),
        "SCENE_VERSION": int(manifest["scene_version"]),
    }
    abi_match = re.search(r"pub const WASM_ABI_VERSION: u32 = (\d+);", source)
    if not abi_match or int(abi_match.group(1)) != constants["WASM_ABI_VERSION"]:
        raise SystemExit("xyg-wasm WASM_ABI_VERSION differs from spec/wasm/abi.json")
    engine = (ROOT / "crates" / "xyg-engine" / "src" / "scene.rs").read_text(encoding="utf-8")
    scene_match = re.search(r"pub const SCENE_VERSION: u32 = (\d+);", engine)
    if not scene_match or int(scene_match.group(1)) != constants["SCENE_VERSION"]:
        raise SystemExit("xyg-engine SCENE_VERSION differs from spec/wasm/abi.json")
    semantic = manifest["semantic_graph"]
    assert isinstance(semantic, dict)
    graph_style = (ROOT / "crates" / "xyg-engine" / "src" / "graph_style.rs").read_text(
        encoding="utf-8"
    )
    code_match = re.search(r"pub const MAX_SEMANTIC_CODE: u8 = ([0-9_]+);", graph_style)
    flags_match = re.search(
        r"pub const KNOWN_STATE_FLAGS: u32 = \(1 << ([0-9_]+)\) - 1;", graph_style
    )
    if not code_match or int(code_match.group(1).replace("_", "")) != int(
        semantic["semantic_code_max"]
    ):
        raise SystemExit("xyg-engine MAX_SEMANTIC_CODE differs from semantic_graph manifest")
    if not flags_match or (1 << int(flags_match.group(1).replace("_", ""))) - 1 != int(
        semantic["state_flag_mask"]
    ):
        raise SystemExit("xyg-engine KNOWN_STATE_FLAGS differs from semantic_graph manifest")
    painter_match = re.search(r"pub const BROWSER_PAINTER_VERSION: u32 = (\d+);", engine)
    if not painter_match or int(painter_match.group(1)) != int(manifest["painter_version"]):
        raise SystemExit("xyg-engine BROWSER_PAINTER_VERSION differs from spec/wasm/abi.json")
    for rust_name, manifest_name in (
        ("BROWSER_PAINTER_HEADER_BYTES", "painter_header_bytes"),
        ("BROWSER_PAINTER_TRACE_BYTES", "painter_trace_bytes"),
        ("BROWSER_PAINTER_TICK_BYTES", "painter_tick_bytes"),
        ("MAX_BROWSER_PAINTER_TRACES", "painter_max_traces"),
        ("BROWSER_PAINTER_MAX_LEGEND_BYTES", "painter_max_legend_bytes"),
    ):
        match = re.search(rf"pub const {rust_name}: usize = (\d+);", engine)
        if not match or int(match.group(1)) != int(manifest[manifest_name]):
            raise SystemExit(f"xyg-engine {rust_name} differs from spec/wasm/abi.json")
    compile_source = (ROOT / "crates" / "xyg-wasm" / "src" / "compile.rs").read_text(
        encoding="utf-8"
    )
    if "use crate::typed_series_abi_generated::*;" not in compile_source:
        raise SystemExit("xyg-wasm compile decoder does not consume the generated XYTS contract")
    if re.search(
        r"pub const (?:SERIES_|MAX_(?:SERIES|RECORDS|TEXT|SYMBOL)|COMPILE_HEADER_BYTES)",
        compile_source,
    ):
        raise SystemExit("xyg-wasm compile decoder contains a handwritten XYTS wire constant")
    compound = manifest["compound_transition"]
    assert isinstance(compound, dict)
    compound_source = (ROOT / "crates" / "xyg-wasm" / "src" / "compound.rs").read_text(
        encoding="utf-8"
    )
    for rust_name, manifest_name in (
        ("REQUEST_VERSION", "request_version"),
        ("REQUEST_HEADER_BYTES", "request_header_bytes"),
        ("REQUEST_PLANE_BYTES_PER_NODE", "request_plane_bytes_per_node"),
        ("OUTPUT_VERSION", "output_version"),
        ("OUTPUT_HEADER_BYTES", "output_header_bytes"),
    ):
        match = re.search(rf"const {rust_name}: (?:u32|usize) = ([0-9_]+);", compound_source)
        if not match or int(match.group(1).replace("_", "")) != int(compound[manifest_name]):
            raise SystemExit(f"xyg-wasm {rust_name} differs from compound_transition manifest")
    for offset_name, offset_value in compound["request_offsets"].items():
        rust_name = f"REQUEST_{str(offset_name).upper()}_OFFSET"
        match = re.search(rf"const {rust_name}: usize = ([0-9_]+);", compound_source)
        if not match or int(match.group(1).replace("_", "")) != int(offset_value):
            raise SystemExit(f"xyg-wasm {rust_name} differs from compound_transition manifest")
    for offset_name, offset_value in compound["output_offsets"].items():
        rust_name = f"OUTPUT_{str(offset_name).upper()}_OFFSET"
        match = re.search(rf"const {rust_name}: usize = ([0-9_]+);", compound_source)
        if not match or int(match.group(1).replace("_", "")) != int(offset_value):
            raise SystemExit(f"xyg-wasm {rust_name} differs from compound_transition manifest")
    for rust_name, manifest_name in (
        ("REQUEST_MAGIC", "request_magic"),
        ("OUTPUT_MAGIC", "output_magic"),
    ):
        match = re.search(rf'const {rust_name}: &\[u8; 4\] = b"([A-Z]{{4}})";', compound_source)
        if not match or match.group(1) != compound[manifest_name]:
            raise SystemExit(f"xyg-wasm {rust_name} differs from compound_transition manifest")
    for action_name, action_value in compound["actions"].items():
        rust_name = f"COMPOUND_ACTION_{str(action_name).upper()}"
        match = re.search(rf"pub const {rust_name}: u8 = ([0-9_]+);", graph_style)
        if not match or int(match.group(1).replace("_", "")) != int(action_value):
            raise SystemExit(f"xyg-engine {rust_name} differs from compound_transition manifest")
    for tier_name, tier_value in compound["lod_tiers"].items():
        rust_name = f"GRAPH_LOD_{str(tier_name).upper()}"
        match = re.search(rf"pub const {rust_name}: u8 = ([0-9_]+);", graph_style)
        if not match or int(match.group(1).replace("_", "")) != int(tier_value):
            raise SystemExit(f"xyg-engine {rust_name} differs from compound_transition manifest")
    max_nodes_match = re.search(
        r"pub const MAX_COMPOUND_TRANSITION_NODES: usize = ([0-9_]+);", graph_style
    )
    if not max_nodes_match or int(max_nodes_match.group(1).replace("_", "")) != int(
        compound["max_nodes"]
    ):
        raise SystemExit(
            "xyg-engine MAX_COMPOUND_TRANSITION_NODES differs from compound_transition manifest"
        )
    for name, value in manifest["statuses"].items():
        match = re.search(rf"pub const STATUS_{re.escape(str(name))}: i32 = (\d+);", source)
        if not match or int(match.group(1)) != int(value):
            raise SystemExit(f"xyg-wasm STATUS_{name} differs from spec/wasm/abi.json")
    arena_match = re.search(r"pub const MAX_ARENA_BYTES: usize = ([0-9_ *]+);", source)
    arena_value = (
        0
        if not arena_match
        else math.prod(
            int(part.strip().replace("_", "")) for part in arena_match.group(1).split("*")
        )
    )
    if arena_value != int(manifest["max_arena_bytes"]):
        raise SystemExit("xyg-wasm MAX_ARENA_BYTES differs from spec/wasm/abi.json")
    if int(manifest["aggregate"]["total_memory_bytes"]) > arena_value:
        raise SystemExit("aggregate total_memory_bytes exceeds xyg-wasm MAX_ARENA_BYTES")
    aggregate_source = AGGREGATE_RUST.read_text(encoding="utf-8")
    for rust_name, manifest_name in (
        ("AGGREGATE_MAGIC", "request_magic"),
        ("OUTPUT_MAGIC", "output_magic"),
    ):
        if (
            f'pub const {rust_name}: &[u8; 4] = b"{manifest["aggregate"][manifest_name]}";'
            not in aggregate_source
        ):
            raise SystemExit(f"xyg-wasm aggregate {rust_name} differs from spec/wasm/abi.json")
    graph_source = GRAPH_RUST.read_text(encoding="utf-8")
    for rust_name, manifest_name in (("MAGIC", "request_magic"), ("OUTPUT_MAGIC", "output_magic")):
        if (
            f'const {rust_name}: &[u8; 4] = b"{manifest["graph"][manifest_name]}";'
            not in graph_source
        ):
            raise SystemExit(f"xyg-wasm graph {rust_name} differs from spec/wasm/abi.json")
    for rust_name, manifest_name in (
        ("VERSION", "version"),
        ("HEADER", "header_bytes"),
        ("OUTPUT_HEADER", "output_header_bytes"),
        ("MAX_NODES", "max_nodes"),
        ("MAX_EDGES", "max_edges"),
        ("MAX_STEPS", "max_steps"),
        ("REQUEST_COPY_FACTOR", "request_copy_factor"),
        ("CONSTRUCTION_BYTES_PER_NODE", "construction_bytes_per_node"),
        ("CONSTRUCTION_BYTES_PER_EDGE", "construction_bytes_per_edge"),
    ):
        match = re.search(
            rf"(?:pub\(super\) )?const {rust_name}: (?:u32|usize) = ([0-9_]+);",
            graph_source,
        )
        if not match or int(match.group(1).replace("_", "")) != int(
            manifest["graph"][manifest_name]
        ):
            raise SystemExit(f"xyg-wasm graph {rust_name} differs from spec/wasm/abi.json")
    for rust_name, manifest_name in (
        ("REQUEST_OFFSETS", "request_offsets"),
        ("OUTPUT_OFFSETS", "output_offsets"),
    ):
        expected = list(manifest["aggregate"][manifest_name].values())
        literal = ", ".join(str(value) for value in expected)
        if (
            f"pub const {rust_name}: [usize; {len(expected)}] = [{literal}];"
            not in aggregate_source
        ):
            raise SystemExit(f"xyg-wasm aggregate {rust_name} differs from spec/wasm/abi.json")
    for rust_name, manifest_name in (
        ("AGGREGATE_VERSION", "version"),
        ("AGGREGATE_HEADER_BYTES", "header_bytes"),
        ("OUTPUT_VERSION", "output_version"),
        ("OUTPUT_HEADER_BYTES", "output_header_bytes"),
        ("FLAG_MEAN_COLOR", "flag_mean_color"),
        ("CHECKPOINT_POINTS", "checkpoint_points"),
        ("MAX_REQUEST_BYTES", "max_request_bytes"),
        ("REQUEST_STRIDE_COUNT", "request_stride_count"),
        ("REQUEST_STRIDE_COLOR", "request_stride_color"),
        ("ACCUMULATOR_STRIDE_COUNT", "accumulator_stride_count"),
        ("ACCUMULATOR_STRIDE_COLOR", "accumulator_stride_color"),
        ("OUTPUT_STRIDE_COUNT", "output_stride_count"),
        ("OUTPUT_STRIDE_COLOR", "output_stride_color"),
        ("CHECKPOINT_STRIDE_COUNT", "checkpoint_stride_count"),
        ("CHECKPOINT_STRIDE_COLOR", "checkpoint_stride_color"),
        ("REQUEST_COPY_FACTOR", "request_copy_factor"),
        ("OUTPUT_COPY_FACTOR", "output_copy_factor"),
        ("MAX_POINTS", "max_points"),
        ("MAX_GRID_CELLS", "max_grid_cells"),
    ):
        match = re.search(rf"pub const {rust_name}: (?:u32|usize) = ([0-9_ *]+);", aggregate_source)
        rust_value = (
            0
            if not match
            else math.prod(int(part.strip().replace("_", "")) for part in match.group(1).split("*"))
        )
        if not match or rust_value != int(manifest["aggregate"][manifest_name]):
            raise SystemExit(f"xyg-wasm aggregate {rust_name} differs from spec/wasm/abi.json")
    for item in manifest["exports"]:
        name = str(item["name"])
        signature = re.search(
            rf'pub extern "C" fn {re.escape(name)}\s*\((.*?)\)\s*->\s*([A-Za-z0-9_:]+)\s*\{{',
            source,
            re.DOTALL,
        )
        if not signature:
            raise SystemExit(f"manifest export missing from xyg-wasm: {name}")
        params = []
        for parameter in signature.group(1).split(","):
            parameter = parameter.strip()
            if not parameter:
                continue
            if ":" not in parameter:
                raise SystemExit(f"cannot parse Rust parameter for {name}: {parameter}")
            params.append(parameter.split(":", 1)[1].strip())
        expected_params = [str(value) for value in item["params"]]
        expected_result = str(item["result"])
        if params != expected_params or signature.group(2) != expected_result:
            raise SystemExit(
                f"xyg-wasm signature differs for {name}: "
                f"Rust ({params}) -> {signature.group(2)}, "
                f"manifest ({expected_params}) -> {expected_result}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise SystemExit("unsupported WASM ABI manifest schema")
    validate_typed_series(manifest)
    validate_semantic_graph(manifest)
    validate_compound_transition(manifest)
    verify_rust(manifest)
    expected = render(manifest)
    expected_rust = render_typed_series_rust(manifest)
    if args.check:
        actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if actual != expected:
            raise SystemExit(f"generated WASM adapter is stale: run {Path(__file__).name}")
        actual_rust = (
            RUST_TYPED_SERIES_OUTPUT.read_text(encoding="utf-8")
            if RUST_TYPED_SERIES_OUTPUT.exists()
            else ""
        )
        if actual_rust != expected_rust:
            raise SystemExit(f"generated Rust XYTS contract is stale: run {Path(__file__).name}")
    else:
        OUTPUT.write_text(expected, encoding="utf-8")
        RUST_TYPED_SERIES_OUTPUT.write_text(expected_rust, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
