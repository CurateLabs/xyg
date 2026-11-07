"""Acquire an immutable native snapshot; rendered export is a later checkpoint.

Run: uv run python examples/temporal_graph_freeze.py /path/to/frame.xyfg
"""

import sys
from pathlib import Path

import numpy as np

import xyg
from xyg.temporal_graph import uuid_rows


def main():
    first, second, edge = (bytes([n]) * 16 for n in (1, 2, 3))
    with xyg.TemporalGraph(
        node_ids=uuid_rows(first, second),
        edge_ids=uuid_rows(edge),
        source_ids=uuid_rows(first),
        target_ids=uuid_rows(second),
        node_valid_to=(np.asarray([30, 10], dtype=np.int64), np.ones(2, np.uint8)),
    ) as graph:
        graph.set_selection(nodes=uuid_rows(second)).set_pinned(uuid_rows(second))
        graph.frame(revision=1, cursor=10, range=(0, 40))
        with graph.freeze(revision=1, timezone="UTC", window=(0, 40)) as frozen:
            raw = frozen.to_bytes()
        graph.frame(revision=2, cursor=5, range=(0, 40))
    with xyg.FrozenTemporalGraph.from_bytes(raw) as recovered:
        assert recovered.metadata["visible.node.uuid"] == first
        assert recovered.metadata["selected.node.uuid"] == second
        Path(sys.argv[1]).write_bytes(recovered.to_bytes())


if __name__ == "__main__":
    main()
