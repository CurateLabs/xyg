#!/usr/bin/env python3
"""Regenerate GraphForge-canonical Arrow IPC fixtures under tests/fixtures/graphforge/.

Requires the optional ``pyarrow`` dev dependency. Fixtures use GraphForge field
names so hosts exercise the typed ingest path without a GraphForge runtime.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "graphforge"
RESULTS = ROOT / "results"


def _write(name: str, table: pa.Table) -> None:
    path = ROOT / name
    with (
        pa.OSFile(str(path), "wb") as sink,
        pa.ipc.new_file(sink, table.schema) as writer,
    ):
        writer.write_table(table)
    print(f"wrote {path} rows={table.num_rows}")


def _uuid(prefix: int, n: int) -> bytes:
    return bytes([prefix] + [0] * 14 + [n])


def property_graph(results: Path = RESULTS) -> None:
    """The ``property`` base (#934): a Cypher entity result with no analytical
    layer. It exercises the default view: two captions from ``name``, ``title``,
    ``label`` (in that order), a short-identity caption, an unlabeled node, a
    parallel pair, and a self-loop. Written beside the engine-produced bases
    and listed in ``manifest.json``; ``scripts/gen_graphforge_cross_host.py``
    pins its digests."""
    uuid16 = pa.binary(16)
    node_type = pa.struct(
        [
            ("node_uuid", uuid16),
            ("labels", pa.list_(pa.string())),
            ("name", pa.string()),
            ("title", pa.string()),
            ("label", pa.string()),
        ]
    )
    rows = [
        # (labels, name, title, label): caption is the first non-empty of the last three
        (["Person"], "ada", "Dr", "L1"),
        (["Person"], None, "Prof", "L2"),
        (["Company"], None, None, "Acme"),
        (["Company"], "", None, None),
        (None, None, None, None),
    ]
    nodes = pa.table(
        {
            "n": pa.array(
                [
                    {
                        "node_uuid": _uuid(1, i + 1),
                        "labels": labels,
                        "name": name,
                        "title": title,
                        "label": label,
                    }
                    for i, (labels, name, title, label) in enumerate(rows)
                ],
                type=node_type,
            )
        }
    )
    edge_type = pa.struct(
        [
            ("edge_uuid", uuid16),
            ("src_uuid", uuid16),
            ("dst_uuid", uuid16),
            ("rel_type", pa.string()),
        ]
    )
    links = [(1, 2, "KNOWS"), (1, 2, "KNOWS"), (2, 2, "KNOWS"), (1, 3, "WORKS_AT"), (3, 4, "OWNS")]
    edges = pa.table(
        {
            "r": pa.array(
                [
                    {
                        "edge_uuid": _uuid(2, i + 1),
                        "src_uuid": _uuid(1, a),
                        "dst_uuid": _uuid(1, b),
                        "rel_type": kind,
                    }
                    for i, (a, b, kind) in enumerate(links)
                ],
                type=edge_type,
            )
        }
    )
    results.mkdir(parents=True, exist_ok=True)
    for name, table in (("base-property-nodes", nodes), ("base-property-edges", edges)):
        path = results / f"{name}.arrow"
        with pa.OSFile(str(path), "wb") as sink, pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        print(f"wrote {path} rows={table.num_rows}")
    # This producer owns the synthetic base and its index entry. The Core
    # producer clears/rebuilds results first; never depend on a hand-edited
    # manifest entry surviving that run.
    manifest_path = results / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("bases", {})["property"] = {
        "nodes": "base-property-nodes",
        "edges": "base-property-edges",
        "generation": "0190a000-0000-7000-8000-000000000006",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def flat_captions() -> None:
    """A flat node table carrying both ``name`` and ``label`` (#934): captions
    follow ``name``, ``title``, ``label`` in that order, so ``name`` wins."""
    nodes = pa.table(
        {
            "node_uuid": pa.array(
                [
                    "00000000-0000-0000-0000-0000000000a1",
                    "00000000-0000-0000-0000-0000000000a2",
                ],
                type=pa.string(),
            ),
            "name": pa.array(["Name A", None], type=pa.string()),
            "label": pa.array(["Label A", "Label B"], type=pa.string()),
        }
    )
    _write("captions_nodes.arrow", nodes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-directory", type=Path, default=RESULTS)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    property_graph(args.results_directory)
    flat_captions()
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
