#!/usr/bin/env python3
"""Generate the seeded CoSE native/WASM parity golden (issue #35).

The authored fixtures below are run through the native Rust CoSE kernel via the
C ABI and their checkpoint digests are committed to
``tests/fixtures/graphforge/cose-parity/golden.json``. The Python native test,
the Node native test, and the direct-WASM test each recompute the same
checkpoints and require identical digests (spec/design/graph-mark.md, "CoSE
cross-host parity").

    uv run python scripts/gen_cose_parity_golden.py --write
    uv run python scripts/gen_cose_parity_golden.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from xyg import _native  # noqa: E402

GOLDEN = ROOT / "tests" / "fixtures" / "graphforge" / "cose-parity" / "golden.json"
NO_PARENT = None  # JSON null; hosts map it to the u64::MAX "no parent" sentinel
U64_MAX = 0xFFFFFFFFFFFFFFFF
# Tick chunks mirror the progressive schedulers: one initial step, then chunks.
SCHEDULE = [1, 9, 20, 30]
CAMEL_TO_SNAKE = {
    "idealEdgeLength": "ideal_edge_length",
    "repulsionStrength": "repulsion_strength",
    "gravityStrength": "gravity_strength",
    "coolingFactor": "cooling_factor",
    "overlapPadding": "overlap_padding",
    "componentSpacing": "component_spacing",
    "bounds": "bounds",
}


def _lcg_edges(n: int, per_node: int, seed: int) -> tuple[list[int], list[int]]:
    """Deterministic edge list: a ring plus ``per_node`` LCG-chosen chords per node."""
    state = seed
    sources: list[int] = []
    targets: list[int] = []
    for i in range(n):
        sources.append(i)
        targets.append((i + 1) % n)
        for _ in range(per_node):
            state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
            j = (state >> 33) % n
            if j != i:
                sources.append(i)
                targets.append(int(j))
    return sources, targets


def _authored_positions(n: int, seed: int) -> tuple[list[float], list[float]]:
    """Deterministic scattered start positions (LCG), exact in JSON."""
    state = seed
    xs: list[float] = []
    ys: list[float] = []
    for _ in range(n):
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        xs.append(((state >> 11) / (1 << 53) - 0.5) * 8.0)
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        ys.append(((state >> 11) / (1 << 53) - 0.5) * 8.0)
    return xs, ys


def base_fixtures() -> list[dict]:
    out: list[dict] = []
    out.append(
        {
            "name": "path-default",
            "note": "8-node path, default CoSE options, seeded circle start",
            "nNodes": 8,
            "sources": list(range(7)),
            "targets": list(range(1, 8)),
            "seed": 7,
        }
    )
    # Two compounds (nodes 0 and 6 are parents) plus a root-level pair.
    out.append(
        {
            "name": "compound",
            "note": "two compounds with children plus root nodes; custom options",
            "nNodes": 12,
            "sources": [1, 2, 3, 7, 8, 9, 0, 6, 10, 4, 5],
            "targets": [2, 3, 4, 8, 9, 10, 6, 11, 11, 7, 1],
            "parents": [NO_PARENT, 0, 0, 0, 0, 0, NO_PARENT, 6, 6, 6, NO_PARENT, NO_PARENT],
            "cose": {
                "idealEdgeLength": 0.5,
                "repulsionStrength": 1.6,
                "gravityStrength": 0.05,
                "coolingFactor": 0.97,
                "overlapPadding": 0.02,
            },
            "seed": 11,
        }
    )
    out.append(
        {
            "name": "disconnected",
            "note": "three components plus two isolated nodes; explicit component spacing",
            "nNodes": 13,
            "sources": [0, 1, 2, 3, 4, 5, 6, 8, 9],
            "targets": [1, 2, 0, 4, 5, 3, 7, 9, 10],
            "cose": {"componentSpacing": 0.6},
            "seed": 23,
        }
    )
    out.append(
        {
            "name": "pinned-bounds-initial",
            "note": "authored initial positions, two pinned nodes, clamp bounds",
            "nNodes": 6,
            "sources": [0, 1, 2, 3, 4, 0],
            "targets": [1, 2, 3, 4, 5, 3],
            "x": [-0.5, -0.2, 0.0, 0.2, 0.4, 0.5],
            "y": [0.0, 0.1, -0.1, 0.05, 0.0, -0.2],
            "pinned": [1, 0, 0, 0, 0, 1],
            "cose": {"idealEdgeLength": 0.4, "bounds": [-1, -1, 1, 1]},
            "seed": 5,
        }
    )
    s, t = _lcg_edges(200, 1, 0x9E3779B97F4A7C15)
    out.append(
        {
            "name": "random-200-exact-tier",
            "note": "200 nodes, ring + chords; exact repulsion tier",
            "nNodes": 200,
            "sources": s,
            "targets": t,
            "seed": 101,
        }
    )
    s, t = _lcg_edges(700, 1, 0xD1B54A32D192ED03)
    parents = [NO_PARENT] * 700
    for compound in (100, 300):
        for child in range(compound + 1, compound + 31):
            parents[child] = compound
    out.append(
        {
            "name": "random-700-grid-tier-compound",
            "note": "700 nodes (> exact-repulsion bound, uniform-grid tier) with a compound subset",
            "nNodes": 700,
            "sources": s,
            "targets": t,
            "parents": parents,
            "seed": 4242,
        }
    )
    return out


def _component_count(n: int, sources: list[int], targets: list[int]) -> int:
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for s, t in zip(sources, targets, strict=True):
        parent[find(s)] = find(t)
    return len({find(i) for i in range(n)})


def _libm_dependencies(fx: dict) -> list[str]:
    """Rust paths on this fixture that still call the platform ``sin``/``cos``."""
    out = []
    if "x" not in fx:
        out.append("seeded-circle")
    if _component_count(fx["nNodes"], fx["sources"], fx["targets"]) > 1:
        out.append("component-gravity-anchor")
    return out


def fixtures() -> list[dict]:
    """Every graph twice: authored start positions, and the Rust seeded start.

    ``start`` is ``authored`` (explicit x/y) or ``seeded`` (Rust's seeded
    circle). ``libm`` lists the Rust paths exercised by the fixture that call the
    platform ``sin``/``cos`` (seeded circle; per-component gravity anchors), where
    wasm32 may differ from native by ulps; everything else uses only
    ``+ - * / sqrt`` and must agree bitwise.
    """
    out: list[dict] = []
    for fx in base_fixtures():
        if "x" in fx:
            out.append({**fx, "start": "authored", "libm": _libm_dependencies(fx)})
            continue
        xs, ys = _authored_positions(fx["nNodes"], fx["seed"] * 7919 + 1)
        authored = {**fx, "x": xs, "y": ys}
        out.append({**authored, "start": "authored", "libm": _libm_dependencies(authored)})
        out.append(
            {
                **fx,
                "name": fx["name"] + "-seeded",
                "start": "seeded",
                "libm": _libm_dependencies(fx),
            }
        )
    return out


def _digest(x: np.ndarray, y: np.ndarray, alpha: float) -> str:
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(x, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(y, dtype="<f8").tobytes())
    h.update(struct.pack("<d", alpha))
    return h.hexdigest()


def run_native(fx: dict) -> dict:
    cose = {CAMEL_TO_SNAKE[k]: v for k, v in fx.get("cose", {}).items()}
    kwargs: dict = {"algorithm": "cose", "seed": fx["seed"]}
    if "x" in fx:
        kwargs["x"] = np.asarray(fx["x"], dtype=np.float64)
        kwargs["y"] = np.asarray(fx["y"], dtype=np.float64)
    if cose or "pinned" in fx or "parents" in fx:
        kwargs["cose"] = cose
    if "pinned" in fx:
        kwargs["pinned"] = np.asarray(fx["pinned"], dtype=np.uint8)
    if "parents" in fx:
        kwargs["parents"] = np.asarray(
            [U64_MAX if p is None else p for p in fx["parents"]], dtype=np.uint64
        )
    handle = _native.graph_force_create(
        fx["nNodes"],
        np.asarray(fx["sources"], dtype=np.uint64),
        np.asarray(fx["targets"], dtype=np.uint64),
        **kwargs,
    )
    checkpoints = []
    step = 0
    try:
        for take in SCHEDULE:
            x, y, alpha = _native.graph_force_tick(handle, fx["nNodes"], take)
            step += take
            checkpoints.append({"step": step, "alpha": alpha, "sha256": _digest(x, y, alpha)})
    finally:
        _native.graph_force_destroy(handle)
    return {"checkpoints": checkpoints, "x": x.tolist(), "y": y.tolist()}


def build() -> dict:
    cases = []
    for fx in fixtures():
        cases.append({**fx, "expected": run_native(fx)})
    return {
        "version": 1,
        "schedule": SCHEDULE,
        "digest": "sha256(x f64le || y f64le || alpha f64le)",
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1) + "\n"
    if args.write:
        GOLDEN.write_text(text)
        print(f"wrote {GOLDEN.relative_to(ROOT)}")
        return 0
    if GOLDEN.read_text() != text:
        print("cose parity golden is stale; run with --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
