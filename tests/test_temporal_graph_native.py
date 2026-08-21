from __future__ import annotations

import numpy as np
import pytest

import xyg
from xyg import _native


def _ids(*values: int) -> np.ndarray:
    return np.asarray([[value] * 16 for value in values], dtype=np.uint8).reshape((-1, 16))


def _graph() -> xyg.TemporalGraph:
    return xyg.TemporalGraph(
        node_ids=_ids(1, 2, 3),
        edge_ids=_ids(11, 12),
        source_ids=_ids(1, 2),
        target_ids=_ids(2, 3),
        node_valid_from=(np.asarray([0, 10, 20], dtype=np.int64), np.ones(3, np.uint8)),
        node_valid_to=(np.asarray([30, 20, 40], dtype=np.int64), np.ones(3, np.uint8)),
    )


def test_temporal_graph_frame_preserves_uuid_state_and_frozen_provenance() -> None:
    with _graph() as graph:
        assert graph.required_budget == 12
        graph.set_selection(nodes=_ids(2), edges=_ids(11))
        graph.set_focus("node", bytes([2]) * 16)
        graph.set_pinned(_ids(2))

        frame = graph.frame(revision=1, cursor=20, range=(20, 21))

        assert frame["node_visibility"].tolist() == [1, 0, 1]
        assert frame["edge_visibility"].tolist() == [0, 0]
        assert frame["selected_visible_node_ids"].shape == (0, 16)
        assert frame["selected_node_ids"].tolist() == _ids(2).tolist()
        assert frame["selected_edge_ids"].tolist() == _ids(11).tolist()
        assert frame["pinned_node_ids"].tolist() == _ids(2).tolist()
        assert frame["focused"] == {"kind": "node", "id": bytes([2]) * 16}
        assert frame["focused_visible"] is None
        assert graph.snapshot()["revision"] == 1


def test_temporal_graph_rejects_stale_budget_and_unknown_identity_atomically() -> None:
    with _graph() as graph:
        with pytest.raises(xyg.TemporalGraphError, match="supplied budget") as budget:
            graph.frame(revision=1, cursor=15, range=(15, 16), budget=11)
        assert budget.value.status == -11

        graph.set_selection(nodes=_ids(1))
        with pytest.raises(xyg.TemporalGraphError, match="incomplete or inconsistent") as unknown:
            graph.set_selection(nodes=_ids(99))
        assert unknown.value.status == -1
        frame = graph.frame(revision=1, cursor=15, range=(15, 16))
        assert frame["selected_node_ids"].tolist() == _ids(1).tolist()

        with pytest.raises(xyg.TemporalGraphError, match="revision is stale") as stale:
            graph.frame(revision=1, cursor=15, range=(15, 16))
        assert stale.value.status == -14


def test_temporal_graph_frame_fails_closed_if_a_newer_snapshot_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _graph()
    native_frame = _native.temporal_graph_frame

    def publish_newer(handle: int, **kwargs: object) -> None:
        native_frame(handle, **kwargs)
        newer = dict(kwargs)
        newer["revision"] = 2
        native_frame(handle, **newer)

    monkeypatch.setattr(_native, "temporal_graph_frame", publish_newer)
    try:
        with pytest.raises(xyg.TemporalGraphError, match="revision is stale"):
            graph.frame(revision=1, cursor=15, range=(15, 16))
    finally:
        graph.close()


def test_temporal_graph_lifecycle_and_exact_integer_validation() -> None:
    graph = _graph()
    graph.cancel()  # idle cancellation is intentionally harmless
    with pytest.raises(ValueError, match="revision"):
        graph.frame(revision=-1, cursor=15, range=(15, 16))
    graph.close()
    graph.close()
    with pytest.raises(RuntimeError, match="closed"):
        graph.snapshot()


def test_temporal_graph_plane_mapping_is_strict() -> None:
    kwargs = {
        "node_ids": _ids(1),
        "edge_ids": _ids(),
        "source_ids": _ids(),
        "target_ids": _ids(),
    }
    with pytest.raises(ValueError, match="field names must be strings"):
        xyg.TemporalGraph(
            **kwargs,
            node_valid_from={1: np.asarray([0]), "values": np.asarray([0])},
        )
    with pytest.raises(ValueError, match="timezone must be a string"):
        xyg.TemporalGraph(
            **kwargs,
            node_valid_from={
                "values": np.asarray([0]),
                "validity": np.ones(1, np.uint8),
                "timezone": 1,
            },
        )
