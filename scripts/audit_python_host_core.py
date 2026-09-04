#!/usr/bin/env python3
"""Report core-logic surface in python-scene-migration modules (M2 re-audit).

Stdlib-only companion to ``verify_ownership.py``.  The gate proves every
production file is classified; this script measures how much algorithmic work
remains in Python files tagged ``python-scene-migration`` — the §302 blockers
from ``spec/design/ownership-audit.md``.

When no ``python-scene-migration`` files remain, the script also audits
documented keep-host compatibility/marshal surfaces (static export emitters,
scene observation marshaling, payload density attach) and reports remaining
Node ``node-scene-migration`` inventory for practical parity tracking.

Exit 0 always; prints a human-readable report to stdout.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "spec" / "design" / "ownership-audit.json"
ABI_GENERATED = ROOT / "python" / "xyg" / "_abi_generated.py"

# Legacy scene-migration heuristics.  Keep these for any still-tagged migration
# file, but never present them as keep-host parity evidence.
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

BLOCKER_MAP: dict[str, str] = {}

# Keep-host surfaces that may still carry compatibility export / observation policy.
# Zero ``python-scene-migration`` tags does not mean these are Rust-owned.
KEEP_HOST_POLICY_EXACT: frozenset[str] = frozenset(
    {
        "python/xyg/_paint.py",
        "python/xyg/_layout.py",
        "python/xyg/_scene_marshal.py",
        "python/xyg/_scene_observations.py",
        "python/xyg/_payload_trace_materialize.py",
        "python/xyg/_payload_density.py",
        "python/xyg/_payload.py",
        "python/xyg/_scene_v3.py",
        "python/xyg/_channels_labels.py",
        "python/xyg/_lod_sample.py",
        "python/xyg/_svg_render.py",
        "python/xyg/_raster_render.py",
    }
)

KEEP_HOST_POLICY_PREFIXES: tuple[str, ...] = (
    "python/xyg/_export_",
    "python/xyg/_marks_",
    "python/xyg/_figure_",
    "python/xyg/_channels_",
    "python/xyg/_lod_",
    "python/xyg/_facets_",
    "python/xyg/_annotations_",
)

# Node marshal/coerce surfaces (zero node-scene-migration does not retire these).
NODE_KEEP_HOST_POLICY_EXACT: frozenset[str] = frozenset(
    {
        "packages/xy-node/src/charts.js",
        "packages/xy-node/src/color.js",
        "packages/xy-node/src/encode.js",
        "packages/xy-node/src/figure.js",
        "packages/xy-node/src/graph.js",
        "packages/xy-node/src/scene.js",
        "packages/xy-node/src/pyramid.js",
        "packages/xy-node/src/sankey.js",
        "packages/xy-node/src/payloadTraceMaterialize.js",
    }
)

NODE_KEEP_HOST_POLICY_PREFIXES: tuple[str, ...] = ("packages/xy-node/src/marks/",)

NODE_NATIVE_MODULES: frozenset[str] = frozenset({"./native.js", "./sceneBulkNative.js"})


class NativeCallMetrics:
    """Static, source-backed native call-site inventory for one host file."""

    def __init__(self, lines: int, calls: int, entries: frozenset[str]) -> None:
        self.lines = lines
        self.calls = calls
        self.entries = entries

    @property
    def calls_per_kloc(self) -> float:
        return 1000.0 * self.calls / self.lines if self.lines else 0.0


def _python_native_call_metrics(path: Path) -> NativeCallMetrics:
    """Count calls through imported ``_native``/``kernels`` ABI surfaces."""
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return NativeCallMetrics(0, 0, frozenset())

    modules: set[str] = set()
    direct: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith(("_native", "kernels")):
                    modules.add(alias.asname or alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.endswith(("_native", "kernels")):
                direct.update(
                    alias.asname or alias.name for alias in node.names if alias.name != "*"
                )
            elif module in {"", "xyg"}:
                modules.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name in {"_native", "kernels"}
                )

    entries: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in direct:
            entries.append(function.id)
        elif (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id in modules
        ):
            entries.append(f"{function.value.id}.{function.attr}")
    return NativeCallMetrics(len(text.splitlines()), len(entries), frozenset(entries))


_NODE_IMPORT_RE = re.compile(
    r'import\s*\{(?P<body>.*?)\}\s*from\s*["\'](?P<module>\./(?:native|sceneBulkNative)\.js)["\']\s*;',
    re.DOTALL,
)


def _node_native_call_metrics(path: Path) -> NativeCallMetrics:
    """Count calls to names imported from the handwritten Node ABI adapters."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return NativeCallMetrics(0, 0, frozenset())

    imports: set[str] = set()
    for match in _NODE_IMPORT_RE.finditer(text):
        if match.group("module") not in NODE_NATIVE_MODULES:
            continue
        for item in match.group("body").split(","):
            parts = item.strip().split()
            if not parts:
                continue
            imports.add(parts[-1] if len(parts) >= 3 and parts[-2] == "as" else parts[0])

    entries: list[str] = []
    for name in imports:
        count = len(re.findall(rf"(?<![.$\w]){re.escape(name)}\s*\(", text))
        entries.extend([name] * count)
    return NativeCallMetrics(len(text.splitlines()), len(entries), frozenset(entries))


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
    ("—", "332", "xyg_category_labels_packed", "channels category_label"),
    ("—", "333", "xyg_object_rows_all_stringlike", "channels object stringlike probe"),
    ("—", "334", "xyg_normalize_window", "lod.normalize_window"),
    ("—", "335", "xyg_view_visible_mask", "lod.visible_mask"),
    ("—", "336", "xyg_label_codes_first_seen", "facets._label_codes"),
    ("—", "337", "xyg_object_rows_all_real_numeric", "channels real-numeric probe"),
    ("—", "338", "xyg_sorted_display_label_remap", "channels sorted label remap"),
    ("—", "339", "xyg_factorize_use_native_fixed", "channels native factorize probe"),
    ("—", "340", "xyg_fold_codes_u8", "channels folded palette codes"),
    ("—", "341", "xyg_quantize_unit_u8", "channels quantize unit u8"),
    ("—", "342", "xyg_palette_rows_rgba8", "channels palette rows rgba8"),
    ("—", "343", "xyg_colormap_lut_rgba8", "channels colormap lut rgba8"),
    ("—", "344", "xyg_literal_color_rgba_f64", "channels literal color rgba f64"),
    ("—", "345", "xyg_stratified_sample_range_plan", "lod stratified sample range plan"),
    ("—", "346", "xyg_palette_rows_rgba8 entry flags", "channels palette unresolved flags"),
    ("—", "347", "xyg_categorical_palette", "channels categorical palette repeat"),
    ("—", "347", "xyg_categorical_palette_map_resolve", "channels palette map resolve"),
    ("—", "348", "xyg_color_channel_direct_rgba_f64", "channels resolve_direct_rgba"),
    ("—", "349", "xyg_colormap_is_builtin", "channels is_colormap"),
    ("—", "349", "xyg_colormap_custom_stops_resolve", "channels resolve_colormap"),
    ("—", "350", "xyg_size_range_admit", "channels _size_range"),
    ("—", "351", "xyg_array_is_categorical", "channels _is_categorical"),
    ("—", "352", "xyg_real_numeric_dtype_admit", "channels _as_real_array"),
    ("—", "353", "xyg_object_row_*_tag_from_probe", "channels object-row tag map"),
    ("—", "354", "xyg_category_label_kind_from_probe", "channels category_label kind"),
    ("—", "355", "xyg_category_code_width", "channels categorical code width"),
    ("—", "355", "xyg_category_palette_rows", "channels palette_rgba8 rows"),
    ("—", "356", "xyg_object_row_*_tags_from_probes", "channels object-row tag batch"),
    ("—", "357", "xyg_category_label_kinds_from_probes", "channels category_labels kind batch"),
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

REMAINING_CLOSE: tuple[tuple[str, str], ...] = ()

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
    (
        "Secondary §302 composition hubs",
        "CLOSED — marks/_figure/channels/lod/facets/_annotations/_svg/_raster split to keep-host modules",
    ),
    (
        "Node marshal disposition parity",
        "CLOSED — 0 node-scene-migration tags; node keep-host policy inventory in audit",
    ),
    ("#735 close-contract doc rebase onto main", "CLOSED — merged at 8fa63e1f"),
)

WASM_DIFFERENTIAL_CONTRACTS: tuple[str, ...] = (
    "tests/test_*cross_host*.py",
    "tests/test_scene_trace_pack_abi.py",
    "tests/test_scene_chrome_pack_abi.py",
    "tests/browser/wasm_foundation_page.mjs",
)

WASM_STRUCTURAL_CONTRACTS: tuple[str, ...] = ("tests/test_wasm_ticks_chartview_contract.py",)


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


def _load_manifest(manifest_path: Path) -> dict:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _is_keep_host_policy_surface(path: str) -> bool:
    if path in KEEP_HOST_POLICY_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in KEEP_HOST_POLICY_PREFIXES)


def _is_node_keep_host_policy_surface(path: str) -> bool:
    if path in NODE_KEEP_HOST_POLICY_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in NODE_KEEP_HOST_POLICY_PREFIXES)


def _keep_host_policy_paths(manifest: dict) -> list[str]:
    out: list[str] = []
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if entry.get("policy") != "python-host":
            continue
        if _is_keep_host_policy_surface(path):
            out.append(path)
    return sorted(out)


def _node_keep_host_policy_paths(manifest: dict) -> list[str]:
    out: list[str] = []
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if entry.get("policy") != "node-host":
            continue
        if _is_node_keep_host_policy_surface(path):
            out.append(path)
    return sorted(out)


def _policy_paths_by_tag(manifest: dict, policy: str) -> list[str]:
    return sorted(
        entry["path"] for entry in manifest.get("files", []) if entry.get("policy") == policy
    )


def _print_policy_surface_block(
    label: str,
    paths: list[str],
    *,
    host: str,
    top_n: int = 15,
) -> NativeCallMetrics:
    total_lines = 0
    total_calls = 0
    total_entries: set[str] = set()
    rows: list[tuple[int, int, int, str]] = []

    analyze = _python_native_call_metrics if host == "python" else _node_native_call_metrics

    for rel in paths:
        metrics = analyze(ROOT / rel)
        total_lines += metrics.lines
        total_calls += metrics.calls
        total_entries.update(metrics.entries)
        rows.append((metrics.lines, metrics.calls, len(metrics.entries), rel))

    print(f"  {label}: {len(paths)}")
    density = 1000.0 * total_calls / total_lines if total_lines else 0.0
    print(
        f"  totals: {total_lines} lines, {total_calls} native call sites, "
        f"{len(total_entries)} distinct ABI entries, {density:.1f} calls/KLOC"
    )
    print("  top surfaces by line count:")
    for n_lines, n_calls, n_entries, rel in sorted(rows, reverse=True)[:top_n]:
        row_density = 1000.0 * n_calls / n_lines if n_lines else 0.0
        print(
            f"    - {rel}: {n_lines} lines, {n_calls} native calls, "
            f"{n_entries} ABI entries, {row_density:.1f} calls/KLOC"
        )
    return NativeCallMetrics(total_lines, total_calls, frozenset(total_entries))


def _print_keep_host_policy_audit(manifest_path: Path) -> None:
    manifest = _load_manifest(manifest_path)
    py_paths = _keep_host_policy_paths(manifest)
    node_paths = _node_keep_host_policy_paths(manifest)
    node_migration = _policy_paths_by_tag(manifest, "node-scene-migration")
    browser_paths = _policy_paths_by_tag(manifest, "browser-scene-migration")

    print("Keep-host policy surface audit (compatibility export + marshal seams):")
    print(
        "  Zero scene-migration tags does not retire these surfaces; "
        "see spec/design/ownership-audit.md post-M2 inventory."
    )
    _print_policy_surface_block("python keep-host policy files", py_paths, host="python")
    print()
    _print_policy_surface_block("node keep-host policy files", node_paths, host="node", top_n=10)
    print()

    print("Cross-host disposition parity:")
    print(
        f"  node-scene-migration files: {len(node_migration)} "
        f"({sum(_analyze(ROOT / rel)[0] for rel in node_migration)} lines)"
    )
    if node_migration:
        for rel in node_migration[:8]:
            n_lines, n_delegate, n_local = _analyze(ROOT / rel)
            print(f"    - {rel}: {n_lines} lines, {n_delegate} delegate, {n_local} local")
        if len(node_migration) > 8:
            print(f"    - ... and {len(node_migration) - 8} more")
    if browser_paths:
        browser_lines = sum(_analyze(ROOT / rel)[0] for rel in browser_paths)
        print(f"  browser-scene-migration files: {len(browser_paths)} ({browser_lines} lines)")
        for rel in browser_paths:
            n_lines, _, _ = _analyze(ROOT / rel)
            print(f"    - {rel}: {n_lines} lines")
    print(
        "  practical Node/WASM parity requires migration tags at zero and "
        "keep-host inventories to stay marshal/coerce only or documented debt."
    )
    print()
    _print_wasm_parity_audit(manifest)


def _print_wasm_parity_audit(manifest: dict) -> None:
    adapter_paths = _policy_paths_by_tag(manifest, "browser-wasm-adapter")
    generated_paths = _policy_paths_by_tag(manifest, "browser-wasm-generated")
    wasm_migration_paths = _policy_paths_by_tag(manifest, "browser-wasm-migration")
    browser_client_paths = _policy_paths_by_tag(manifest, "browser-client")
    browser_migration = _policy_paths_by_tag(manifest, "browser-scene-migration")

    print("WASM / browser host parity inventory:")
    print(
        "  ChartView primary Cartesian + colorbar ticks consume Rust/WASM via "
        "js/src/49_wasm_ticks.ts; js/src/30_ticks.ts is the documented compatibility "
        "fallback for uncovered axes. Browser tick policy remains OPEN under #869; "
        "this inventory does not count the fallback as parity proof."
    )
    print(f"  browser-client paint modules: {len(browser_client_paths)}")
    print(
        f"  browser-wasm-adapter modules: {len(adapter_paths)} "
        f"({sum(_analyze(ROOT / rel)[0] for rel in adapter_paths)} lines)"
    )
    for rel in adapter_paths[:6]:
        n_lines, _, _ = _analyze(ROOT / rel)
        print(f"    - {rel}: {n_lines} lines")
    if len(adapter_paths) > 6:
        print(f"    - ... and {len(adapter_paths) - 6} more")
    print(f"  browser-wasm-generated modules: {len(generated_paths)}")
    if wasm_migration_paths:
        print(f"  browser-wasm-migration modules: {len(wasm_migration_paths)}")
    if browser_migration:
        browser_lines = sum(_analyze(ROOT / rel)[0] for rel in browser_migration)
        print(
            f"  browser-scene-migration compatibility generators: "
            f"{len(browser_migration)} ({browser_lines} lines)"
        )
        for rel in browser_migration:
            n_lines, _, _ = _analyze(ROOT / rel)
            print(f"    - {rel}: {n_lines} lines")
    print("  differential proof contracts:")
    for contract in WASM_DIFFERENTIAL_CONTRACTS:
        print(f"    - {contract}")
    print("  structural adapter contracts (not parity differentials):")
    for contract in WASM_STRUCTURAL_CONTRACTS:
        print(f"    - {contract}")
    print()


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
    abi_version = _read_abi_version()

    print("python-scene-migration core-logic re-audit")
    print(f"manifest: {args.manifest.relative_to(ROOT)}")
    print(f"files: {len(paths)}")
    if abi_version is not None:
        print(f"abi_version: {abi_version}")
    print()

    if not paths:
        print("No python-scene-migration production files remain.")
        print()
        print("§302 blocker rollup: (none)")
        print()
        _print_stack(
            "Merged kernel stack on main (#640 -> #642, ABI 254-256):", MERGED_KERNEL_STACK
        )
        _print_stack("Merged scene lane on main (#703 -> #718, ABI 257-272):", MERGED_SCENE_LANE)
        _print_stack(
            "Merged payload stack on main (#719 -> #741, ABI 273-291):", MERGED_PAYLOAD_STACK
        )
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
        print(
            "  - #733 CLOSED: Scene pack dispatch/plan orchestration is Rust-owned (ABI 305-309)."
        )
        print(
            "  - #732 CLOSED: gather/ship registry + density grid ship are Rust-owned (ABI 310-315)."
        )
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
        print("Totals: 0 lines, 0 delegate hooks, 0 local-orchestration hooks")
        print(
            "Density grid materialization is kernel-owned (ABI 316). Payload trace emit "
            "and Scene trace pack are marshal-only via ABI 321 and ABI 317-318/323/325. "
            "Keep-host coercion lives in _payload_trace_materialize.py and _scene_marshal.py. "
            "Gather/ship registry and wire-encode policy are kernel-owned (ABI 310-315). "
            "Scene pack orchestration plans are kernel-owned (#733 closed)."
        )
        _print_keep_host_policy_audit(args.manifest)
        return 0

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
