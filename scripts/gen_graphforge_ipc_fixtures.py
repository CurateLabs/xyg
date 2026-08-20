#!/usr/bin/env python3
"""Regenerate GraphForge-canonical Arrow IPC fixtures under tests/fixtures/graphforge/.

Requires the optional ``pyarrow`` dev dependency. Fixtures use GraphForge field
names so hosts exercise the typed ingest path without a GraphForge runtime.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "graphforge"


def _write(name: str, table: pa.Table) -> None:
    path = ROOT / name
    with (
        pa.OSFile(str(path), "wb") as sink,
        pa.ipc.new_file(sink, table.schema) as writer,
    ):
        writer.write_table(table)
    print(f"wrote {path} rows={table.num_rows}")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    nodes = pa.table(
        {
            "node_uuid": pa.array(
                [
                    "00000000-0000-0000-0000-000000000001",
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000003",
                ],
                type=pa.string(),
            ),
            "labels": pa.array(["Airport", "Airport", "City"], type=pa.string()),
            "rank": pa.array([1.0, 2.0, 3.0], type=pa.float64()),
            "provenance_row": pa.array([10, 11, 12], type=pa.uint64()),
        }
    )
    edges = pa.table(
        {
            "edge_uuid": pa.array(
                [
                    "10000000-0000-0000-0000-000000000001",
                    "10000000-0000-0000-0000-000000000002",
                    "10000000-0000-0000-0000-000000000003",
                    "10000000-0000-0000-0000-000000000004",
                ],
                type=pa.string(),
            ),
            "src_uuid": pa.array(
                [
                    "00000000-0000-0000-0000-000000000001",
                    "00000000-0000-0000-0000-000000000001",
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000003",
                ],
                type=pa.string(),
            ),
            "dst_uuid": pa.array(
                [
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000003",
                    "00000000-0000-0000-0000-000000000003",
                ],
                type=pa.string(),
            ),
            "relationship_type": pa.array(["ROUTE", "ROUTE", "SERVES", "SELF"], type=pa.string()),
            "weight": pa.array([1.5, 2.5, 3.0, 0.1], type=pa.float64()),
            "provenance_row": pa.array([100, 101, 102, 103], type=pa.uint64()),
        }
    )
    bad_edges = pa.table(
        {
            "edge_uuid": pa.array(["10000000-0000-0000-0000-000000000099"], type=pa.string()),
            "src_uuid": pa.array(["00000000-0000-0000-0000-000000000001"], type=pa.string()),
            "dst_uuid": pa.array(["00000000-0000-0000-0000-000000000099"], type=pa.string()),
            "relationship_type": pa.array(["MISSING"], type=pa.string()),
            "provenance_row": pa.array([9], type=pa.uint64()),
        }
    )
    dup_edges = pa.table(
        {
            "edge_uuid": pa.array(
                [
                    "10000000-0000-0000-0000-000000000001",
                    "10000000-0000-0000-0000-000000000001",
                ],
                type=pa.string(),
            ),
            "src_uuid": pa.array(
                [
                    "00000000-0000-0000-0000-000000000001",
                    "00000000-0000-0000-0000-000000000002",
                ],
                type=pa.string(),
            ),
            "dst_uuid": pa.array(
                [
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000003",
                ],
                type=pa.string(),
            ),
            "relationship_type": pa.array(["A", "B"], type=pa.string()),
            "provenance_row": pa.array([1, 2], type=pa.uint64()),
        }
    )
    _write("airports_nodes.arrow", nodes)
    _write("airports_edges.arrow", edges)
    _write("airports_edges_missing_endpoint.arrow", bad_edges)
    _write("airports_edges_duplicate_edge.arrow", dup_edges)


if __name__ == "__main__":
    main()
