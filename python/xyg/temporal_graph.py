"""Ergonomic native host for Rust-owned identity-safe temporal graphs."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any, Self, cast

import numpy as np

from . import _native

TemporalGraphError = _native.TemporalNativeError


def _plane_handle(plane: object | None, name: str) -> int:
    if plane is None:
        return 0
    if isinstance(plane, Mapping):
        if not all(isinstance(key, str) for key in plane):
            raise ValueError(f"{name} field names must be strings")
        mapping = cast(Mapping[str, object], plane)
        unknown = set(mapping) - {"values", "validity", "timezone"}
        if unknown:
            raise ValueError(f"{name} has unknown fields: {', '.join(sorted(unknown))}")
        try:
            values = mapping["values"]
            validity = mapping["validity"]
        except KeyError as error:
            raise ValueError(f"{name} requires values and validity") from error
        timezone = mapping.get("timezone", "UTC")
        if not isinstance(timezone, str):
            raise ValueError(f"{name}.timezone must be a string")
    else:
        try:
            values, validity = cast(Any, plane)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} must be (values, validity) or a mapping") from error
        timezone = "UTC"
    return _native.temporal_column_create(values, validity, timezone=timezone)


class TemporalGraph:
    """Filter canonical graph identity by integer UTC-microsecond time.

    Temporal planes may be ``(values, validity)`` pairs or mappings with
    ``values``, ``validity``, and optional ``timezone``. Missing validity
    planes are unbounded. ``frame`` returns both visible-frame membership and
    the persistent selection/focus/pin provenance required by static exports.
    """

    def __init__(
        self,
        *,
        node_ids: Any,
        edge_ids: Any,
        source_ids: Any,
        target_ids: Any,
        node_valid_from: object | None = None,
        node_valid_to: object | None = None,
        node_event_at: object | None = None,
        edge_valid_from: object | None = None,
        edge_valid_to: object | None = None,
        edge_event_at: object | None = None,
        directed: bool = True,
    ) -> None:
        self._handle: int | None = None
        projection = _native.graph_projection_create(
            node_ids, edge_ids, source_ids, target_ids, directed=directed
        )
        columns: list[int] = []
        try:
            for name, plane in (
                ("node_valid_from", node_valid_from),
                ("node_valid_to", node_valid_to),
                ("node_event_at", node_event_at),
                ("edge_valid_from", edge_valid_from),
                ("edge_valid_to", edge_valid_to),
                ("edge_event_at", edge_event_at),
            ):
                columns.append(_plane_handle(plane, name))
            self._handle = _native.temporal_graph_create(
                projection,
                node_valid_from=columns[0],
                node_valid_to=columns[1],
                node_event_at=columns[2],
                edge_valid_from=columns[3],
                edge_valid_to=columns[4],
                edge_event_at=columns[5],
            )
        finally:
            for column in columns:
                if column:
                    _native.temporal_column_destroy(column)
            _native.graph_projection_destroy(projection)

    def _open_handle(self) -> int:
        if self._handle is None:
            raise RuntimeError("TemporalGraph is closed")
        return self._handle

    @property
    def required_budget(self) -> int:
        """Exact minimum work units for one frame, computed by Rust."""
        return _native.temporal_graph_required_budget(self._open_handle())

    def set_selection(self, *, nodes: Any = (), edges: Any = ()) -> Self:
        _native.temporal_graph_set_selection(self._open_handle(), nodes, edges)
        return self

    def set_focus(self, kind: str | None = None, entity_id: Any | None = None) -> Self:
        if kind is None:
            _native.temporal_graph_set_focus(self._open_handle(), 0)
        elif kind in ("node", "edge"):
            _native.temporal_graph_set_focus(
                self._open_handle(), 1 if kind == "node" else 2, entity_id
            )
        else:
            raise ValueError("kind must be 'node', 'edge', or None")
        return self

    def set_pinned(self, node_ids: Any = ()) -> Self:
        _native.temporal_graph_set_pinned(self._open_handle(), node_ids)
        return self

    def frame(
        self,
        *,
        revision: int,
        cursor: int,
        range: tuple[int, int],
        budget: int | None = None,
    ) -> dict[str, object]:
        """Publish a newer frame and return exact membership/provenance."""
        if not isinstance(range, tuple) or len(range) != 2:
            raise ValueError("range must be a (start, end) tuple")
        _native.temporal_graph_frame(
            self._open_handle(),
            revision=revision,
            cursor_micros=cursor,
            range_start_micros=range[0],
            range_end_micros=range[1],
            budget=budget,
        )
        snapshot = _native.temporal_graph_snapshot(self._open_handle())
        if snapshot["revision"] != revision:
            raise TemporalGraphError(-14)
        return snapshot

    def snapshot(self) -> dict[str, object]:
        """Return the last complete frame without recomputing it."""
        return _native.temporal_graph_snapshot(self._open_handle())

    def cancel(self) -> None:
        """Cooperatively cancel an in-flight frame from another thread."""
        _native.temporal_graph_cancel(self._open_handle())

    def close(self) -> None:
        """Cancel owned work and release the native graph; idempotent."""
        handle, self._handle = self._handle, None
        if handle is not None:
            _native.temporal_graph_destroy(handle)

    def __enter__(self) -> Self:
        self._open_handle()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def uuid_rows(*values: bytes) -> np.ndarray[Any, np.dtype[np.uint8]]:
    """Build an ``(n, 16)`` uint8 UUID buffer without string re-encoding."""
    if any(len(value) != 16 for value in values):
        raise ValueError("every UUID must contain exactly 16 bytes")
    if not values:
        return np.empty((0, 16), dtype=np.uint8)
    return np.frombuffer(b"".join(values), dtype=np.uint8).reshape((-1, 16)).copy()
