"""Thin programmatic client for Rust's versioned ordinary filter session."""

from __future__ import annotations

import ctypes
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from . import _native


def request(
    op: int,
    *,
    revision: int,
    source_id: int,
    epoch: int = 1,
    source_revision: int = 1,
    budget_bytes: int = 64 << 20,
    args: Sequence[int] = (),
    bounds: tuple[float, float] = (0, 0),
    exact: bool = False,
    payload: bytes = b"",
) -> bytes:
    if not isinstance(exact, bool):
        raise TypeError("exact must be boolean")
    if 96 + len(payload) > 256 << 20:
        raise ValueError("XYFC packet exceeds its transport extent")
    return (
        struct.pack(
            "<4sIII8Q2d",
            b"XYFC",
            1,
            op,
            int(exact),
            revision,
            source_id,
            epoch,
            source_revision,
            budget_bytes,
            *(tuple(args) + (0,) * (3 - len(args))),
            *bounds,
        )
        + payload
    )


def decode_reply(packet: bytes) -> dict[str, Any]:
    if len(packet) < 192 or packet[:8] != b"XYFR\x01\0\0\0":
        raise ValueError("invalid XYFR packet")
    fields = [
        "requested_revision",
        "revision",
        "source_id",
        "epoch",
        "source_revision",
        "filter_hash",
        "tier",
        "index_bytes",
        "resident_bytes",
        "peak_bytes",
        "rows_read",
        "prefix_cells_read",
        "fallback",
        "active_view",
        "selected_count",
        "affected_count",
        "newest_revision",
        "first_row",
        "source_rows",
        "page_first",
        "membership_bytes",
        "has_intent",
    ]
    result = dict(zip(fields, struct.unpack_from("<22Q", packet, 16), strict=True))
    result["status"] = struct.unpack_from("<I", packet, 8)[0]
    if result["status"] or result["tier"] == 0:
        result["selected_count"] = None
    result["packet"] = packet
    if result["affected_count"] > 64 or result["membership_bytes"] > 8192:
        raise ValueError("invalid XYFR bounds")
    views = []
    at = 192
    for _ in range(result["affected_count"]):
        view_id, n = struct.unpack_from("<QQ", packet, at)
        at += 16
        if n > 65536 or at + n * 8 > len(packet):
            raise ValueError("invalid XYFR bin extent")
        counts = struct.unpack_from(f"<{n}Q", packet, at)
        at += n * 8
        views.append({"id": view_id, "counts": counts})
    if at + result["membership_bytes"] != len(packet):
        raise ValueError("invalid XYFR length")
    result["views"] = views
    result["membership"] = packet[at:]
    return result


class FilterTierCError(ValueError):
    def __init__(self, reply: dict[str, Any]):
        super().__init__(f"Filter Tier C rejected request (status {reply['status']})")
        self.status = reply["status"]
        self.reply = reply


def execute_packet(handle: int, packet: bytes, capacity: int = 1 << 20) -> bytes:
    output = (ctypes.c_ubyte * capacity)()
    data = (ctypes.c_ubyte * len(packet)).from_buffer_copy(packet)
    written = ctypes.c_size_t()
    status = _native._lib.xyg_filter_session_execute(
        handle, data, len(packet), output, capacity, ctypes.byref(written)
    )
    if status:
        raise RuntimeError(
            f"native filter adapter failed ({status}); required capacity {written.value}"
        )
    return bytes(output[: written.value])


class FilterTierCSession:
    """Own canonical f64 columns and one Rust-selected active index.

    Create through ``Chart.filter_session``. Counts use the indexed exact subset;
    ``exact=True`` explicitly permits a recorded full boundary scan. Membership
    is an independent bounded canonical-row page, never an indexed timing claim.
    """

    def __init__(
        self,
        columns: Mapping[str, Sequence[float]],
        *,
        source_id: int,
        epoch: int = 1,
        first_row: int = 0,
        budget_bytes: int = 64 << 20,
    ):
        self.names = tuple(columns)
        self.source_id, self.epoch = source_id, epoch
        self.source_revision = 1
        self.revision = 0
        self.budget_bytes, self.first_row = budget_bytes, first_row
        self.rows = len(next(iter(columns.values()))) if columns else 0
        self._handle = _native._lib.xyg_filter_session_new(budget_bytes)
        if not self._handle:
            raise RuntimeError("filter session allocation refused")
        try:
            self._call(1, args=(len(columns), self.rows, first_row), payload=self._columns(columns))
        except BaseException:
            self.close()
            raise

    def _columns(self, columns):
        if tuple(columns) != self.names or any(
            len(c) != len(next(iter(columns.values()))) for c in columns.values()
        ):
            raise ValueError("filter columns must retain schema order and equal lengths")
        rows = len(next(iter(columns.values()))) if columns else 0
        if 96 + len(columns) * rows * 8 > 256 << 20:
            raise ValueError(
                "XYFC columns exceed the transport extent; append bounded chunks instead"
            )
        return b"".join(struct.pack(f"<{len(c)}d", *c) for c in columns.values())

    def _call(self, op, **kwargs):
        if not self._handle:
            raise RuntimeError("filter session is closed")
        self.revision += 1
        packet = request(
            op,
            revision=self.revision,
            source_id=self.source_id,
            epoch=self.epoch,
            source_revision=self.source_revision,
            budget_bytes=self.budget_bytes,
            **kwargs,
        )
        result = decode_reply(execute_packet(self._handle, packet))
        if result["status"]:
            raise FilterTierCError(result)
        self.source_revision, self.rows = result["source_revision"], result["source_rows"]
        return result

    def configure(self, active: Mapping, views: Sequence[Mapping]):
        def axis(v):
            cuts = v["cuts"]
            return struct.pack("<Q", len(cuts)) + struct.pack(f"<{len(cuts)}d", *cuts)

        payload = axis(active)
        for v in views:
            payload += struct.pack("<QQ", v["id"], self.names.index(v["dimension"])) + axis(v)
        return self._call(
            3,
            args=(active["id"], self.names.index(active["dimension"]), len(views)),
            payload=payload,
        )

    def range(self, lo: float, hi: float, *, exact: bool = False):
        return self._call(5, bounds=(lo, hi), exact=exact)

    def clear(self):
        return self._call(7)

    def evict(self):
        return self._call(6)

    def rebuild(self):
        return self._call(4)

    def cancel(self):
        return self._call(8)

    def membership(self, first: int, count: int):
        return self._call(9, args=(first, count))

    def append(self, columns: Mapping[str, Sequence[float]]):
        payload = self._columns(columns)
        rows = len(next(iter(columns.values())))
        return self._call(2, args=(len(columns), rows, self.first_row + self.rows), payload=payload)

    def close(self):
        if getattr(self, "_handle", 0):
            _native._lib.xyg_filter_session_free(self._handle)
            self._handle = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()
