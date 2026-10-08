#!/usr/bin/env python3
"""Generate deterministic synthetic Arrow composition inputs for compiler A/B.

These preserve pinned GraphForge schemas; they measure XYG composition only,
not GraphForge algorithm execution. Run with --out DIR; no server is required.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc

ROOT = Path(__file__).resolve().parents[1]


def generate(out: Path, count: int) -> None:
    fixture = ROOT / "tests/fixtures/graphforge/scale-100"
    schemas = {
        name: ipc.open_stream(fixture / f"{name}.arrow").schema
        for name in ("base-nodes", "base-edges", "pagerank")
    }
    ids = [(0x0199C82CC00070008000000000000000 + i).to_bytes(16, "big") for i in range(count)]
    rows = {
        "base-nodes": [
            {"n": {"node_uuid": uid, "labels": ["Person"], "name": f"p{i}"}}
            for i, uid in enumerate(ids)
        ],
        "base-edges": [
            {
                "r": {
                    "edge_uuid": (0x0199C82CC00170008000000000000000 + i).to_bytes(16, "big"),
                    "src_uuid": uid,
                    "dst_uuid": ids[(i + 1) % count],
                    "rel_type": "KNOWS",
                    "w": 1.0,
                }
            }
            for i, uid in enumerate(ids)
        ],
        "pagerank": [
            {"node_uuid": uid, "score": 1.0 / count, "name": f"p{i}"} for i, uid in enumerate(ids)
        ],
    }
    directory = out / str(count)
    directory.mkdir(parents=True, exist_ok=True)
    for name, values in rows.items():
        table = pa.Table.from_pylist(values, schema=schemas[name])
        with ipc.new_stream(directory / f"{name}.arrow", table.schema) as writer:
            writer.write_table(table)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sizes", default="100,10000,100000")
    args = parser.parse_args()
    for count in map(int, args.sizes.split(",")):
        generate(args.out, count)


if __name__ == "__main__":
    main()
