#!/usr/bin/env python3
"""Reproduce the 51-row retained-session companion Arrow fixture (no runtime policy)."""

from pathlib import Path

import pyarrow as pa

path = (
    Path(__file__).resolve().parents[1] / "tests/fixtures/graphforge/session_companion_nodes.arrow"
)
node = pa.struct(
    [("node_uuid", pa.binary(16)), ("labels", pa.list_(pa.string())), ("name", pa.string())]
)
table = pa.table(
    {
        "n": pa.array(
            [
                {
                    "node_uuid": (i + 1).to_bytes(16, "big"),
                    "labels": ["Companion"],
                    "name": "tab\tnewline\nslash\\<img>雪" if i == 0 else f"Node {i + 1}",
                }
                for i in range(51)
            ],
            type=node,
        )
    }
)
with pa.OSFile(str(path), "wb") as sink, pa.ipc.new_stream(sink, table.schema) as writer:
    writer.write_table(table)
print(f"wrote {path}: {table.num_rows} nodes")
