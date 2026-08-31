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

# Heuristic: calls that delegate numeric/policy work to Rust.
DELEGATE_RE = re.compile(
    r"\b(kernels\.|_native\.|scene_encode_product|figure_autorange|"
    r"payload_m4_indices|payload_visible_|valid_indices_f64|"
    r"encoded_column_meta|arrow_style_pack|arrow_shapes|scene_channel_constant_css)\b"
)

# Heuristic: likely host-local orchestration (not exhaustive).
LOCAL_RE = re.compile(
    r"\b(def _emit_|def _pack_|def build_payload|def figure_scene|"
    r"def encode_f32_values|def arrow_shapes|class Figure|class FacetGrid|"
    r"for .+ in range\(|np\.(where|argsort|concatenate|stack))\b"
)

BLOCKER_MAP: dict[str, str] = {
    "python/xyg/_payload.py": "payload emit orchestration",
    "python/xyg/_scene_v3.py": "scene_v3 pack / figure-to-record",
    "_arrowgeom.py": "arrow style pack (ABI 254/257 shapes orchestration)",
    "python/xyg/lod.py": "EncodedColumn meta + LOD host cache",
    "python/xyg/marks.py": "marks composition / validation",
    "python/xyg/facets.py": "facet grid orchestration",
    "python/xyg/_figure.py": "Figure composition hub",
    "python/xyg/_annotations.py": "annotation composition",
    "python/xyg/_fontmetrics.py": "DejaVu metrics table (compat SVG gutters)",
    "python/xyg/_paint.py": "paint dispatch (triangle_mesh_boundary stay-host)",
    "python/xyg/_raster.py": "raster tessellation dispatch + host geometry",
    "python/xyg/_svg.py": "SVG path assembly + host color sample",
    "python/xyg/channels.py": "color channel resolve / LUT pack",
}

NEXT_KERNEL = (
    ("#640", "ABI 254", "xyg_arrow_style_pack", "_arrowgeom._pack_style"),
    ("#641", "ABI 255", "xyg_encoded_column_meta", "lod.encode_f32_values meta"),
    ("#642", "ABI 256", "xyg_scene_channel_constant_css", "_scene_v3 channel CSS"),
)


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

    print("python-scene-migration core-logic re-audit")
    print(f"manifest: {args.manifest.relative_to(ROOT)}")
    print(f"files: {len(paths)}")
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
    print("Merged kernel stack on main (#640 -> #641 -> #642, ABI 254-256):")
    for pr, abi, sym, surface in NEXT_KERNEL:
        print(f"  - {pr} {abi} {sym} → {surface}")

    print()
    print(
        f"Totals: {total_lines} lines, {total_delegate} delegate hooks, "
        f"{total_local} local-orchestration hooks"
    )
    print(
        "Node payload/scene stay-host TAP (#644-#698) records intentional diffs; "
        "Python remains authoritative until kernel emit/scene pack lands."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
