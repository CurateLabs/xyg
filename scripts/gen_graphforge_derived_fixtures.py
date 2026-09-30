#!/usr/bin/env python3
"""Derive embedding-view fixtures from the real GraphForge node2vec result.

GraphForge produces embeddings, but caller coordinates (a caller-owned 2D
reduction) and a two-dimensional embedding are not in the 0.5.2 fixture run.
This writes both from `tests/fixtures/graphforge/results/node2vec.arrow`, keeping
its node UUIDs and schema metadata, into `tests/fixtures/graphforge/derived/`:

- `node2vec-coordinates.arrow`: `node_uuid`, `x`, `y` (row index, row index
  squared) as a caller would supply them;
- `node2vec-coordinates-partial.arrow`: the first two of those rows (nodes
  without coordinates);
- `node2vec-2d.arrow`: the same result with `embedding` truncated to two
  dimensions and `graphforge.dimensions = 2`, standing in for a GraphForge
  run with `dimensions: 2`.

    uv run python scripts/gen_graphforge_derived_fixtures.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "fixtures" / "graphforge" / "results" / "node2vec.arrow"
OUT = ROOT / "tests" / "fixtures" / "graphforge" / "derived"


def _stream(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


def build() -> dict[str, bytes]:
    source = ipc.open_stream(SOURCE.read_bytes()).read_all()
    rows = source.num_rows
    coordinates = pa.table(
        {
            "node_uuid": source.column("node_uuid"),
            "x": pa.array([float(i) for i in range(rows)], pa.float64()),
            "y": pa.array([float(i * i) for i in range(rows)], pa.float64()),
        }
    )
    vectors = source.column("embedding").to_pylist()
    two = pa.array([v[:2] for v in vectors], pa.list_(pa.field("item", pa.float32(), False), 2))
    metadata = dict(source.schema.metadata)
    metadata[b"graphforge.dimensions"] = b"2"
    two_d = pa.table(
        [source.column("node_uuid"), two],
        schema=pa.schema(
            [source.schema.field("node_uuid"), pa.field("embedding", two.type, False)],
            metadata=metadata,
        ),
    )
    return {
        "node2vec-coordinates.arrow": _stream(coordinates),
        "node2vec-coordinates-partial.arrow": _stream(coordinates.slice(0, 2)),
        "node2vec-2d.arrow": _stream(two_d),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, data in build().items():
        path = OUT / name
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                stale.append(name)
        else:
            path.write_bytes(data)
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print(f"stale derived fixtures: {', '.join(stale)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
