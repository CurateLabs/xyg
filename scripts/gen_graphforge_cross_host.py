#!/usr/bin/env python3
"""Pin GraphForge request/document bytes across the Python and Node hosts.

Writes ``tests/fixtures/graphforge/cross_host.json``: one case per GraphForge
contract fixture (with its ledger intent) plus multi-layer, render, select,
coordinates, and failure cases, each with the SHA-256 of the ``XYGQ`` request
and the ``XYGF`` document the Python host produces. ``tests/test_graphforge.py``
and ``packages/xy-node/test/graphforge-cross-host.test.mjs`` build the same
requests from the case list and must reproduce both digests; Node/WASM
equivalence is ``graphforge-wasm-parity.test.mjs``.

    uv run python scripts/gen_graphforge_cross_host.py          # write
    uv run python scripts/gen_graphforge_cross_host.py --check  # verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "tests" / "fixtures" / "graphforge" / "results"
DERIVED = ROOT / "tests" / "fixtures" / "graphforge" / "derived"
OUT = ROOT / "tests" / "fixtures" / "graphforge" / "cross_host.json"

# Non-graph intents per algorithm (everything else composes as a graph).
INTENTS = {
    "is_dag": "table",
    "has_euler_circuit": "table",
    "has_euler_path": "table",
    "is_planar": "table",
    "chromatic_number": "table",
    "triangle_count": "table",
    "count_automorphisms": "table",
    "modularity": "table",
    "transitivity": "table",
    "conductance": "bar-chart",
    "triad_census": "bar-chart",
    "dyad_census": "bar-chart",
    "node2vec": "parallel-coordinates",
    "graphsage": "parallel-coordinates",
    "fast_random_projection": "parallel-coordinates",
    "hashgnn": "parallel-coordinates",
}


def cases() -> list[dict[str, Any]]:
    manifest = json.loads((RESULTS / "manifest.json").read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for contract in manifest["contracts"]:
        algorithm = contract["algorithm"]
        base = manifest["fixtures"][algorithm]["base"]
        out.append(
            {
                "name": algorithm,
                "base": base,
                "layers": [
                    {
                        "result": algorithm,
                        "intent": INTENTS.get(algorithm, "graph"),
                        "generation": base,
                        "result_id": f"result-{algorithm}",
                    }
                ],
            }
        )
    out.append(
        {
            "name": "multi-layer + render + select",
            "base": "cyclic",
            "layers": [
                {"result": name, "intent": "graph", "generation": "cyclic"}
                for name in ("pagerank", "louvain", "node_similarity", "dijkstra")
            ],
            "select": [],
            "render": {"width": 640, "height": 420, "theme": "dark", "title": "GraphForge"},
        }
    )
    out.append(
        {
            "name": "rows and policies",
            "base": "cyclic",
            "layers": [
                {
                    "result": "pagerank",
                    "intent": "graph",
                    "generation": "cyclic",
                    "result_id": "r1",
                    "missing": "hide",
                    "extra": "drop",
                    "rows": [2, 0],
                }
            ],
        }
    )
    out.append(
        {
            "name": "coordinates",
            "layers": [
                {
                    "result": "node2vec",
                    "intent": "embedding-coordinates",
                    "coordinates": "node2vec-coordinates",
                }
            ],
        }
    )
    out.append(
        {
            "name": "stale generation",
            "base": "cyclic",
            "layers": [{"result": "pagerank", "intent": "graph", "generation": "dag"}],
        }
    )
    out.append(
        {
            "name": "coordinates required",
            "layers": [{"result": "node2vec", "intent": "embedding-coordinates"}],
        }
    )
    return out


def build_request(case: dict[str, Any]) -> bytes:
    """The ``XYGQ`` bytes for a case (Python host)."""
    from xyg import encode_graphforge_request

    manifest = json.loads((RESULTS / "manifest.json").read_text(encoding="utf-8"))

    def arrow(name: str) -> bytes:
        return (RESULTS / f"{name}.arrow").read_bytes()

    base = None
    if case.get("base"):
        spec = manifest["bases"][case["base"]]
        base = {
            "tables": [arrow(spec["nodes"]), arrow(spec["edges"])],
            "generation": spec["generation"],
        }
    layers = []
    for layer in case["layers"]:
        built: dict[str, Any] = {"result": arrow(layer["result"]), "intent": layer["intent"]}
        if layer.get("generation"):
            built["generation"] = manifest["bases"][layer["generation"]]["generation"]
        for key in ("result_id", "missing", "extra", "rows"):
            if key in layer:
                built[key] = layer[key]
        if layer.get("coordinates"):
            built["coordinates"] = (DERIVED / f"{layer['coordinates']}.arrow").read_bytes()
        layers.append(built)
    return encode_graphforge_request(
        layers=layers, base=base, select=case.get("select"), render=case.get("render")
    )


def digests() -> dict[str, Any]:
    from xyg._graphforge import compose_graphforge_request

    out = []
    for case in cases():
        request = build_request(case)
        document = compose_graphforge_request(request)
        out.append(
            {
                **case,
                "request_sha256": hashlib.sha256(request).hexdigest(),
                "document_sha256": hashlib.sha256(document).hexdigest(),
            }
        )
    return {"schema": "xyg.graphforge-cross-host/v1", "cases": out}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(digests(), indent=2) + "\n"
    if args.check:
        if OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT} is stale; regenerate it", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
