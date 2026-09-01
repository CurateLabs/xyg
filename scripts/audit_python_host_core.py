#!/usr/bin/env python3
"""Report core-logic surface in python-scene-migration modules (M2 re-audit).

Stdlib-only companion to ``verify_ownership.py``.  The gate proves every
production file is classified; this script measures how much algorithmic work
remains in Python files tagged ``python-scene-migration`` — the §302 blockers
from ``spec/design/ownership-audit.md``.

Exit 0 always; prints a human-readable report to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "spec" / "design" / "ownership-audit.json"
ABI_GENERATED = ROOT / "python" / "xyg" / "_abi_generated.py"

# Heuristic: calls that delegate numeric/policy work to Rust.
DELEGATE_RE = re.compile(
    r"\b(kernels\.|_native\.|scene_encode_product|figure_autorange|"
    r"payload_m4_indices|payload_visible_|valid_indices_f64|"
    r"encoded_column_meta|arrow_style_pack|arrow_shapes|scene_channel_constant_css|"
    r"payload_.*_plan|scene_.*_plan|payload_segments_emit_gather|"
    r"payload_trace_channels_ship_attach|payload_transition_entry_attach|"
    r"payload_column_ship_plan|payload_density_grid_ship_plan|payload_channel_ship_plan|payload_channel_wire_encode|"
    r"payload_trace_emit_materialize|payload_channel_materialize|scene_chrome_pack|"
    r"scene_xytc_trace|scene_xyta_trace|scene_.*_materialize)\b"
)

# Heuristic: likely host-local orchestration (not exhaustive).
LOCAL_RE = re.compile(
    r"\b(def _emit_|def _pack_|def build_payload|def figure_scene|"
    r"def encode_f32_values|def arrow_shapes|class Figure|class FacetGrid|"
    r"for .+ in range\(|np\.(where|argsort|concatenate|stack))\b"
)

BLOCKER_MAP: dict[str, str] = {
    "python/xyg/lod.py": "EncodedColumn meta + LOD host cache",
    "python/xyg/marks.py": "marks composition / validation",
    "python/xyg/facets.py": "facet grid orchestration",
    "python/xyg/_figure.py": "Figure composition hub",
    "python/xyg/_annotations.py": "annotation composition",
    "python/xyg/_fontmetrics.py": "DejaVu metrics table (compat SVG gutters)",
    "python/xyg/_raster.py": "raster tessellation dispatch + host geometry",
    "python/xyg/_svg.py": "SVG path assembly + host color sample",
    "python/xyg/channels.py": "color channel resolve / LUT pack",
}

MERGED_MATERIALIZATION_RETIREMENT: tuple[tuple[str, str, str], ...] = (
    ("#851", "316", "xyg_payload_density_grid_materialize"),
    ("#851", "317", "xyg_scene_xytc_trace_pack"),
    ("#851", "318", "xyg_scene_xyta_trace_pack"),
    ("#853", "319", "xyg_scene_chrome_pack bulk XYCF/XYAF/XYFS"),
    ("#853", "320", "xyg_payload_channel_materialize"),
    ("#853", "321", "xyg_payload_trace_emit_materialize"),
    ("#853", "323", "xyg_scene_xyta_trace_observations_materialize"),
    ("#853", "325", "xyg_scene_xytc_trace_observations_materialize"),
)

MERGED_KERNEL_STACK: tuple[tuple[str, str, str, str], ...] = (
    ("#640", "254", "xyg_arrow_style_pack", "_arrowgeom._pack_style"),
    ("#641", "255", "xyg_encoded_column_meta", "lod.encode_f32_values meta"),
    ("#642", "256", "xyg_scene_channel_constant_css", "_scene_v3 channel CSS"),
    ("—", "326", "xyg_aligned_window", "lod.aligned_window"),
    ("—", "327", "xyg_sample_threshold", "lod._sample_threshold"),
    ("—", "327", "xyg_hash_row_ids", "lod.hash_row_ids"),
    ("—", "328", "xyg_sample_fraction", "lod._sample_fraction"),
    ("—", "329", "xyg_screen_shape", "lod.screen_shape"),
    ("—", "330", "xyg_factorize_display_labels", "channels label-policy"),
    ("—", "331", "xyg_factorize_use_native_probe", "channels factorize probe"),
)

MERGED_SCENE_LANE: tuple[tuple[str, str, str, str], ...] = (
    ("#703", "257", "xyg_arrow_shapes", "_arrowgeom.arrow_shapes"),
    ("#704", "258", "xyg_scene_xyta_colormap_pack", "_scene_v3._pack_xyta_colormap"),
    ("#705", "259", "xyg_scene_xyhf_colormap_pack", "Node xyHfColormap pack"),
    ("#706", "260", "xyg_scene_gradient_spec_pack", "_scene_v3._pack_gradient_spec"),
    ("#707", "261", "xyg_scene_marker_blob_pack", "_scene_v3._pack_marker_blob"),
    ("#708", "262", "xyg_scene_xytc_radius_pack", "_pack_xytc radius trailer"),
    ("#709", "263", "xyg_scene_xytc_color_channel_pack", "_pack_xytc color_ch"),
    ("#710", "264", "xyg_scene_xytc_numeric_style_pack", "_pack_xytc numeric style"),
    ("#711", "265", "xyg_scene_xytc_stroke_perimeter_pack", "_pack_xytc stroke_perimeter"),
    ("#712", "266", "xyg_scene_xytc_hex_pitch_pack", "_pack_xytc hex pitch"),
    ("#713", "267", "xyg_scene_xytc_opacity_pack", "_pack_xytc opacity"),
    ("#714", "268", "xyg_scene_xytc_dash_pattern_pack", "_pack_xytc dash flag"),
    ("#715", "269", "xyg_scene_xytc_paint_presence_pack", "_pack_xytc paint presence"),
    ("#716", "270", "xyg_scene_xytc_meta_flags_pack", "_pack_xytc meta flags"),
    ("#717", "271", "xyg_scene_xytc_color2_flags_pack", "_pack_xytc color2 flags"),
    ("#718", "272", "xyg_scene_xytc_symbol_int_pack", "_pack_xytc symbol int"),
)

MERGED_PAYLOAD_STACK: tuple[tuple[str, str], ...] = (
    ("#719", "xyg_payload_errorbar_role_keys"),
    ("#720", "xyg_payload_bar_compact_admit"),
    ("#721", "xyg_payload_transition_keys_admit"),
    ("#722", "xyg_density_color_classify"),
    ("#723", "xyg_payload_errorbar_role_maps"),
    ("#724", "xyg_density_trace_color_classify"),
    ("#725", "xyg_density_bin_coord_endpoints"),
    ("#726", "xyg_density_uses_channel_colormap"),
    ("#727", "xyg_density_reduction_kind"),
    ("#728", "xyg_density_overlay_omitted_wire"),
    ("#729", "xyg_density_grid_path_identity_state"),
    ("#730", "xyg_density_constant_color_wire_admit"),
    ("#734", "xyg_density_wasm_source_admit"),
    ("#736", "xyg_density_wasm_density_wire_kind"),
    ("#737", "xyg_density_categorical_color_wire_admit"),
    ("#738", "xyg_density_mean_color_wire_admit"),
    ("#739", "xyg_density_channels_dropped_compat"),
    ("#740", "xyg_density_dropped_channel_wire_admit"),
    ("#741", "xyg_density_mean_color_rgba_wire_admit"),
)

MERGED_PAYLOAD_ORCHESTRATION: tuple[tuple[str, str, str], ...] = (
    ("#746", "292", "xyg_payload_segments_emit_gather"),
    ("#747", "293", "xyg_payload_trace_channels_ship_attach"),
    ("#748", "294", "xyg_payload_transition_entry_attach"),
    ("#749", "295", "xyg_payload_base_entry_plan"),
    ("#750", "296", "xyg_payload_nonxy_emit_plan"),
    ("#751", "297", "xyg_payload_bar_hist_emit_plan"),
    ("#752", "298", "xyg_payload_heatmap_emit_plan / mesh_emit_plan"),
    ("#753", "299", "xyg_payload_ribbon_emit_plan"),
    ("#754", "300", "xyg_payload_segments_emit_plan"),
    ("#755", "301", "xyg_payload_scatter_emit_plan"),
    ("#756", "302", "xyg_payload_density_trace_emit_plan"),
    ("#757", "303", "xyg_payload_build_plan"),
    ("#758", "304", "xyg_payload_axis_spec_attach_plan"),
)

MERGED_SCENE_ORCHESTRATION: tuple[tuple[str, str, str], ...] = (
    ("#759", "305", "xyg_scene_xytc_figure_plan / trace_dispatch_plan"),
    ("#760", "306", "xyg_scene_xyta_figure_plan / trace_dispatch_plan"),
    ("#761", "307", "xyg_scene_figure_support / xycl / xynm figure plans"),
    ("#762", "308", "xyg_scene_xycf / xyaf / public_export orchestration"),
    ("#763", "309", "xyg_scene_polar_figure_plan / encode_product_attach_plan"),
)

MERGED_PAYLOAD_GATHER_SHIP: tuple[tuple[str, str, str], ...] = (
    ("#765", "310", "xyg_payload_column_ship_plan"),
    ("#766", "311", "xyg_payload_channel_ship_plan"),
    ("#767", "312", "xyg_payload_channel_wire_encode"),
    ("#768", "313", "xyg_payload_column_ship_plan orientation + thin emit rows"),
    (
        "#769",
        "314",
        "xyg_payload_column_ship_plan density_wasm_source f64 + density_sample registry",
    ),
    (
        "#732",
        "315",
        "xyg_payload_density_grid_ship_plan density grid buffer registry + attach order",
    ),
    (
        "#770",
        "314",
        "channels.ship_registry_attach + Node density wasm_source/sample registry parity",
    ),
)

REMAINING_CLOSE: tuple[tuple[str, str], ...] = (
    (
        "Secondary §302",
        "_svg/_raster compat paths, marks/_figure composition, channels label factorization, lod cache wiring",
    ),
)

M731_CLOSE_CHECKLIST: tuple[tuple[str, str], ...] = (
    ("#731 parent M2 kernelize _payload emit + _scene_v3 pack", "CLOSED — completed 2026-08-31"),
    ("#732 gather/ship + density grid ship (ABI 310-315)", "CLOSED"),
    ("#733 scene orchestration plans (ABI 305-309)", "CLOSED"),
    ("Node stay-host TAP #644-#698 serial merge", "CLOSED — merged on main (#630-#698)"),
    (
        "Cross-host payload + Scene-byte differential proof",
        "CLOSED — payload cross-host + hexbin colormap XYTA scene-byte goldens green",
    ),
    (
        "Host materialization retirement (big pushes 1-3, ABI 316-325)",
        "CLOSED — _payload.py / _scene_v3.py marshal-only; keep-host helpers "
        "_payload_trace_materialize.py / _scene_marshal.py coerce and call Rust",
    ),
    ("Secondary §302 (_svg/_raster, marks, channels labels)", "OPEN — out of #731 bar"),
    ("#735 close-contract doc rebase onto main", "CLOSED — merged at 8fa63e1f"),
)


def _read_abi_version() -> int | None:
    try:
        text = ABI_GENERATED.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("ABI_VERSION = "):
            return int(line.split("=", 1)[1].strip())
    return None


def _load_paths(manifest_path: Path) -> list[str]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    out: list[str] = []
    for entry in data.get("files", []):
        if entry.get("policy") == "python-scene-migration":
            out.append(entry["path"])
    return sorted(out)


def _analyze(path: Path) -> tuple[int, int, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0, 0, 0
    lines = text.splitlines()
    n_lines = len(lines)
    n_delegate = sum(1 for line in lines if DELEGATE_RE.search(line))
    n_local = sum(1 for line in lines if LOCAL_RE.search(line))
    return n_lines, n_delegate, n_local


def _print_stack(title: str, rows: tuple[tuple[str, ...], ...]) -> None:
    print(title)
    for row in rows:
        if len(row) == 4:
            pr, abi, sym, surface = row
            print(f"  - {pr} ABI {abi} {sym} → {surface}")
        elif len(row) == 3:
            pr, abi, sym = row
            print(f"  - {pr} ABI {abi} {sym}")
        elif len(row) == 2:
            pr, sym = row
            print(f"  - {pr} {sym}")
        else:
            print(f"  - {' '.join(row)}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST,
        help="ownership-audit.json path",
    )
    args = parser.parse_args(argv)

    paths = _load_paths(args.manifest)
    if not paths:
        print("audit_python_host_core: no python-scene-migration entries", file=sys.stderr)
        return 1

    abi_version = _read_abi_version()

    print("python-scene-migration core-logic re-audit")
    print(f"manifest: {args.manifest.relative_to(ROOT)}")
    print(f"files: {len(paths)}")
    if abi_version is not None:
        print(f"abi_version: {abi_version}")
    print()

    by_blocker: dict[str, list[str]] = defaultdict(list)
    total_lines = 0
    total_delegate = 0
    total_local = 0

    for rel in paths:
        full = ROOT / rel
        n_lines, n_delegate, n_local = _analyze(full)
        total_lines += n_lines
        total_delegate += n_delegate
        total_local += n_local
        blocker = BLOCKER_MAP.get(rel, "other scene-migration")
        by_blocker[blocker].append(rel)
        ratio = (100.0 * n_delegate / n_lines) if n_lines else 0.0
        print(
            f"{rel}: {n_lines} lines, {n_delegate} delegate hooks ({ratio:.1f}%), "
            f"{n_local} local-orchestration hooks — {blocker}"
        )

    print()
    print("§302 blocker rollup:")
    for blocker in sorted(by_blocker):
        print(f"  - {blocker}: {', '.join(by_blocker[blocker])}")

    print()
    _print_stack("Merged kernel stack on main (#640 -> #642, ABI 254-256):", MERGED_KERNEL_STACK)
    _print_stack("Merged scene lane on main (#703 -> #718, ABI 257-272):", MERGED_SCENE_LANE)
    _print_stack("Merged payload stack on main (#719 -> #741, ABI 273-291):", MERGED_PAYLOAD_STACK)
    _print_stack(
        "Merged payload orchestration on main (#746 -> #758, ABI 292-304, #732):",
        MERGED_PAYLOAD_ORCHESTRATION,
    )
    _print_stack(
        "Merged scene orchestration on main (#759 -> #763, ABI 305-309, #733 CLOSED):",
        MERGED_SCENE_ORCHESTRATION,
    )
    _print_stack(
        "Merged payload gather/ship on main (#765 -> #770/#732, ABI 310-315, #732 CLOSED):",
        MERGED_PAYLOAD_GATHER_SHIP,
    )
    _print_stack(
        "Merged host materialization retirement (#851/#853, ABI 316-325):",
        MERGED_MATERIALIZATION_RETIREMENT,
    )

    print("M2 close contract (#731 — CLOSED 2026-08-31):")
    print("  - #731 CLOSED: kernelize _payload emit and _scene_v3 pack close contract met.")
    print("  - #733 CLOSED: Scene pack dispatch/plan orchestration is Rust-owned (ABI 305-309).")
    print("  - #732 CLOSED: gather/ship registry + density grid ship are Rust-owned (ABI 310-315).")
    print(
        "  - Host materialization retirement CLOSED (big pushes 1-3, ABI 316-325): "
        "_payload.py / _scene_v3.py marshal-only."
    )
    print(
        "  - Admit/encode slices (ABI 218-291), orchestration plans (ABI 292-309), "
        "gather/ship registry (ABI 310-315), and materialization retirement (ABI 316-325) are done."
    )
    print("  - Node stay-host TAP (#630-#698) merged on main.")
    print("  - Stay-host TAP extras are inventory, not an alternate close path.")
    print()

    print("Remaining close blockers:")
    for issue, desc in REMAINING_CLOSE:
        print(f"  - {issue}: {desc}")
    print()

    print("#731 close checklist:")
    for gate, status in M731_CLOSE_CHECKLIST:
        print(f"  - {gate}: {status}")
    print()

    print(
        f"Totals: {total_lines} lines, {total_delegate} delegate hooks, "
        f"{total_local} local-orchestration hooks"
    )
    print(
        "Density grid materialization is kernel-owned (ABI 316). Payload trace emit and "
        "Scene trace pack are marshal-only via ABI 321 and ABI 317-318/323/325. "
        "Keep-host coercion lives in _payload_trace_materialize.py and _scene_marshal.py. "
        "Gather/ship registry and wire-encode policy are kernel-owned (ABI 310-315). "
        "Scene pack orchestration plans are kernel-owned (#733 closed)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
