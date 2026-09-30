#!/usr/bin/env python3
"""Deterministic GraphForge bulk-construction inputs for the composition bench.

Writes, per size, the Arrow IPC batches GraphForge's `publishBulkNodes` /
`publishBulkEdges` accept (bulk contract v1): `nodes-<n>.arrow`
(`node_uuid`, `label`, `name`) and `edges-<n>.arrow` (`edge_uuid`,
`rel_type`, `source_uuid`, `target_uuid`, `w`), two edges per node on a seeded
small-world pattern. `benchmarks/bench_graphforge_compose.mjs` publishes them
into a real GraphForge graph, runs the engine's algorithms, and composes the
engine's own output.

    uv run python benchmarks/gen_graphforge_scale_inputs.py --out DIR --sizes 100,1000,10000,100000
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc

META = {
    b"graphforge.bulk_contract_version": b"1",
    b"graphforge.row_order": b"logical_input_order",
}


def _write(path: Path, table: pa.Table) -> None:
    with ipc.new_stream(str(path), table.schema) as writer:
        writer.write_table(table)


# A fixed millisecond timestamp keeps the inputs byte-reproducible; GraphForge
# requires UUIDv7 identities.
_EPOCH_MS = 1_760_000_000_000


def _uuid(rng: random.Random) -> bytes:
    raw = bytearray(_EPOCH_MS.to_bytes(6, "big") + rng.getrandbits(80).to_bytes(10, "big"))
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return bytes(raw)


def build(n: int, out: Path, seed: int = 7) -> None:
    rng = random.Random(seed + n)
    ids = [_uuid(rng) for _ in range(n)]
    nodes = pa.table(
        [
            pa.array(ids, pa.binary(16)),
            pa.array(["Person"] * n),
            pa.array([f"p{i}" for i in range(n)]),
        ],
        schema=pa.schema(
            [
                pa.field("node_uuid", pa.binary(16), True),
                pa.field("label", pa.string(), False),
                pa.field("name", pa.string(), True),
            ],
            metadata={**META, b"graphforge.bulk_kind": b"node"},
        ),
    )
    sources, targets, weights = [], [], []
    for i in range(n):
        for hop in (1, rng.randrange(2, max(3, n // 10))):
            sources.append(ids[i])
            targets.append(ids[(i + hop) % n])
            weights.append(1.0 + rng.random())
    m = len(sources)
    edges = pa.table(
        [
            pa.array([_uuid(rng) for _ in range(m)], pa.binary(16)),
            pa.array(["KNOWS"] * m),
            pa.array(sources, pa.binary(16)),
            pa.array(targets, pa.binary(16)),
            pa.array(weights, pa.float64()),
        ],
        schema=pa.schema(
            [
                pa.field("edge_uuid", pa.binary(16), True),
                pa.field("rel_type", pa.string(), False),
                pa.field("source_uuid", pa.binary(16), False),
                pa.field("target_uuid", pa.binary(16), False),
                pa.field("w", pa.float64(), True),
            ],
            metadata={**META, b"graphforge.bulk_kind": b"edge"},
        ),
    )
    _write(out / f"nodes-{n}.arrow", nodes)
    _write(out / f"edges-{n}.arrow", edges)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sizes", default="100,1000,10000,100000")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for size in (int(s) for s in args.sizes.split(",")):
        build(size, args.out)
        print(f"wrote nodes/edges for n={size}")


if __name__ == "__main__":
    main()
