#!/usr/bin/env python3
"""Write independent join expectations for the GraphForge result fixtures.

Decodes `tests/fixtures/graphforge/results/*.arrow` with pyarrow (not the Rust
reader) and records, per fixture, the UUID -> value pairs a composition must
reproduce, plus base-graph entity counts. Host tests (Node, Python) compare
Rust compositions against this file, so a join bug cannot hide behind a
decoder that shares its assumptions.

    uv run python scripts/gen_graphforge_composition_expectations.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pyarrow.ipc as ipc

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "tests" / "fixtures" / "graphforge" / "results"
OUT = ROOT / "tests" / "fixtures" / "graphforge" / "composition_expectations.json"

# fixture -> (identity field, value fields)
LAYERS = {
    "pagerank": ("node_uuid", ["score"]),
    "betweenness": ("node_uuid", ["score"]),
    "louvain": ("node_uuid", ["community_id"]),
    "hdbscan": ("node_uuid", ["community_id"]),
    "dfs": ("node_uuid", ["depth", "order"]),
    "topological_sort": ("node_uuid", ["order"]),
    "node_coloring": ("node_uuid", ["color"]),
    "find": ("node_uuid", ["score"]),
    "max_flow_edges": ("edge_uuid", ["flow"]),
    "min_cost_max_flow_edges": ("edge_uuid", ["flow", "unit_cost", "flow_cost"]),
    "minimum_spanning_tree": ("edge_uuid", ["weight"]),
    "edge_coloring": ("edge_uuid", ["color"]),
    "minimum_k_spanning_tree": ("edge_uuid", ["tree_id", "weight"]),
}


def _table(name: str):
    return ipc.open_stream((RESULTS / f"{name}.arrow").read_bytes()).read_all()


def _uuid(raw: bytes) -> str:
    h = raw.hex()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def build() -> dict:
    manifest = json.loads((RESULTS / "manifest.json").read_text())
    out: dict = {"graphforgeVersion": manifest["graphforgeVersion"], "bases": {}, "layers": {}}
    for base, spec in manifest["bases"].items():
        nodes = _table(spec["nodes"]).column("n").to_pylist()
        edges = _table(spec["edges"]).column("r").to_pylist()
        out["bases"][base] = {
            "generation": spec["generation"],
            "nodes": len(nodes),
            "edges": len(edges),
            "nodeUuids": [_uuid(n["node_uuid"]) for n in nodes],
        }
    for name, (id_field, value_fields) in LAYERS.items():
        table = _table(name)
        ids = [_uuid(v) for v in table.column(id_field).to_pylist()]
        values = {field: table.column(field).to_pylist() for field in value_fields}
        rows: dict[str, dict] = {}
        for row, uid in enumerate(ids):
            # First row wins, as the composition records for shared trees.
            rows.setdefault(uid, {"row": row, **{f: values[f][row] for f in value_fields}})
        out["layers"][name] = {
            "base": manifest["fixtures"][name]["base"],
            "identity": id_field,
            "values": value_fields,
            "rows": rows,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed file differs")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    if args.check:
        if OUT.read_text() != text:
            print(f"{OUT.relative_to(ROOT)} is stale; rerun without --check", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
