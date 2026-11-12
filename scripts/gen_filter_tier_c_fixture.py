#!/usr/bin/env python3
"""Generate immutable XYFC/XYFR packets, verifying counts with an independent scan."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import struct
from itertools import pairwise
from pathlib import Path

from xyg import _native
from xyg.filter_session import decode_reply, request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tests/fixtures/filter_tier_c"


def generate(*, check_only: bool = False):
    DEST.mkdir(parents=True, exist_ok=True)
    source_id, first, budget = 71, (1 << 53) + 9, 1 << 20
    columns = [
        [-1.0, 0.0, 0.25, 0.5, 1.0, 1.25, 2.0, math.nan, math.inf, -math.inf],
        [5.0, 4.0, 3.0, 2.0, 1.0, 0.0, -1.0, math.nan, 8.0, 9.0],
        [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
        [0.0, -1.0, -2.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0],
    ]
    views = [
        (11, 1, [1.0, 3.0, 5.0]),
        (12, 2, [0.0, 2.0]),
        (13, 3, [-1.0, 0.0]),
        (14, 4, [10.0, 11.0]),
        (15, 0, [0.0, 0.5, 1.0]),
    ]
    active_dimension = 0
    cuts = [0.0, 1.0, 2.0]
    intent = None
    source_revision = 1
    revision = 0
    entries, stream = [], bytearray()
    handle = _native._lib.xyg_filter_session_new(1 << 20)

    def frame(op, *, args=(), bounds=(0.0, 0.0), exact=False, payload=b"", **kw):
        nonlocal revision
        revision += 1
        return request(
            op,
            revision=revision,
            source_id=source_id,
            source_revision=source_revision,
            budget_bytes=budget,
            args=args,
            bounds=bounds,
            exact=exact,
            payload=payload,
            **kw,
        )

    def check(name, packet, status=0, oracle=False, membership=False, capacity=1 << 20):
        out = (ctypes.c_ubyte * capacity)()
        data = (ctypes.c_ubyte * len(packet)).from_buffer_copy(packet)
        n = ctypes.c_size_t()
        code = _native._lib.xyg_filter_session_execute(
            handle, data, len(packet), out, capacity, ctypes.byref(n)
        )
        reply = bytes(out[: n.value]) if code == 0 else b""
        entry = {
            "name": name,
            "adapter_status": code,
            "required": n.value,
            "status": status,
            "oracle": None,
        }
        if code == 0:
            result = decode_reply(reply)
            assert result["status"] == status, (name, result["status"], status)
            if oracle or membership:
                # Independent hashlib implementation of the normative stamp;
                # these are known authoring/source facts, not decoded hash inputs.
                encoded = struct.pack("<4Q", source_id, 1, source_revision, active_dimension)
                encoded += bytes([intent is not None])
                if intent is not None:
                    normalized = sorted(intent)
                    encoded += struct.pack("<2d", *(0.0 if x == 0.0 else x for x in normalized))
                digest = hashlib.blake2s(encoded, digest_size=8, person=b"xyfilt01").digest()
                assert result["filter_hash"] == int.from_bytes(digest, "little"), name
                assert result["source_id"] == source_id and result["epoch"] == 1, name
                assert result["source_revision"] == source_revision, name
                assert result["first_row"] == first and result["source_rows"] == len(columns[0]), (
                    name
                )
                assert result["requested_revision"] == struct.unpack_from("<Q", packet, 16)[0], name
                assert result["revision"] == result["requested_revision"], name
                assert result["affected_count"] == len(views), name
                assert result["active_view"] == 10 + active_dimension, name
                channels = 1 + sum(len(edges) + 1 for _, _, edges in views)
                cells = len(cuts) + 1
                index_bytes = 4 * (cells + 1) * channels + 8 * channels + 16 * cells
                if membership and name in {"intent-survives-eviction", "intent-survives-append"}:
                    index_bytes = 0
                assert result["index_bytes"] == index_bytes, name
                expected_resident = (
                    512
                    + len(columns) * 24
                    + sum(len(c) * 8 for c in columns)
                    + len(cuts) * 8
                    + len(views) * 64
                    + sum(len(edges) * 8 for _, _, edges in views)
                    + index_bytes
                )
                assert result["resident_bytes"] == expected_resident, name
                assert result["peak_bytes"] <= budget, name
                if result["tier"] == 3:
                    assert result["rows_read"] == 0 and result["fallback"] == 0, name
                elif membership:
                    assert result["tier"] == 2 and result["fallback"] == 2, name
                else:
                    assert result["tier"] == 2 and result["fallback"] == 1, name
                    assert result["rows_read"] == len(columns[0]), name
                selected = [
                    intent is None or (math.isfinite(x) and min(intent) <= x <= max(intent))
                    for x in columns[active_dimension]
                ]
                expected = []
                if oracle:
                    for view_id, dim, edges in views:
                        # Deliberately independent full scan: compare every row to each bin interval.
                        boundaries = [-math.inf, *edges, math.inf]
                        counts = [
                            sum(
                                yes and math.isfinite(x) and lo <= x < hi
                                for yes, x in zip(selected, columns[dim], strict=True)
                            )
                            for lo, hi in pairwise(boundaries)
                        ]
                        expected.append({"id": view_id, "counts": counts})
                    assert [
                        {"id": v["id"], "counts": list(v["counts"])} for v in result["views"]
                    ] == expected, name
                    assert result["selected_count"] == sum(selected), name
                if membership:
                    expected_bits = bytes(
                        sum(int(yes) << bit for bit, yes in enumerate(selected[i : i + 8]))
                        for i in range(0, len(selected), 8)
                    )
                    assert result["membership"] == expected_bits, name
                entry["oracle"] = {
                    "selected": sum(selected),
                    "views": expected,
                    "membership_hex": result["membership"].hex() if membership else None,
                }
        else:
            assert code == -4 and capacity == 0 and n.value > 0
        stream.extend(struct.pack("<IIiIQ", len(packet), capacity, code, len(reply), n.value))
        stream.extend(packet)
        stream.extend(reply)
        entries.append(entry)
        return reply

    def config(active=10, dim=0, active_cuts=None, passive=None):
        active_cuts = cuts if active_cuts is None else active_cuts
        passive = views if passive is None else passive
        payload = struct.pack("<Q", len(active_cuts)) + struct.pack(
            f"<{len(active_cuts)}d", *active_cuts
        )
        for view_id, d, edges in passive:
            payload += struct.pack("<QQQ", view_id, d, len(edges)) + struct.pack(
                f"<{len(edges)}d", *edges
            )
        return frame(3, args=(active, dim, len(passive)), payload=payload)

    try:
        payload = b"".join(struct.pack(f"<{len(c)}d", *c) for c in columns)
        check("open-five-dimensional-source", frame(1, args=(5, 10, first), payload=payload))
        check("configure-five-passive-views", config())
        for name, bounds, exact, status in [
            ("indexed-inclusive", (0.0, 0.5), False, 0),
            ("boundary-refused", (0.1, 0.4), False, 6),
            ("boundary-exact", (0.1, 0.4), True, 0),
            ("reversed-exact", (0.4, 0.1), True, 0),
            ("zero-width-exact", (0.25, 0.25), True, 0),
            ("zero-width-indexed", (2.0, 2.0), False, 0),
            ("empty-indexed", (4.0, 5.0), False, 0),
            ("all-finite-indexed", (-5.0, 5.0), False, 0),
        ]:
            if status == 0:
                intent = bounds
            check(name, frame(5, bounds=bounds, exact=exact), status, oracle=status == 0)
        intent = None
        check("clear-includes-nonfinite-active", frame(7), oracle=True)
        intent = (0.0, 0.5)
        check("persistent-intent", frame(5, bounds=intent), oracle=True)
        check(
            "membership-u64-source-rows", frame(9, args=(first, len(columns[0]))), membership=True
        )
        check("evict", frame(6))
        check("intent-survives-eviction", frame(9, args=(first, len(columns[0]))), membership=True)
        check("evicted-query-fails-closed", frame(5, bounds=intent), 5)
        check("rebuild", frame(4))
        check("rebuilt-index", frame(5, bounds=intent), oracle=True)
        added = [[0.25, 3.0], [2.0, 4.0], [1.0, 2.0], [-1.0, 1.0], [10.0, 11.0]]
        check(
            "append-invalidates-index",
            frame(
                2,
                args=(5, 2, first + len(columns[0])),
                payload=b"".join(struct.pack("<2d", *c) for c in added),
            ),
        )
        columns = [c + a for c, a in zip(columns, added, strict=True)]
        source_revision += 1
        check("intent-survives-append", frame(9, args=(first, len(columns[0]))), membership=True)
        check("append-requires-rebuild", frame(5, bounds=intent), 5)
        check("rebuild-appended-source", frame(4))
        check("appended-indexed-query", frame(5, bounds=intent), oracle=True)
        failed = frame(5, bounds=(2.0, 3.0))
        check("publication-capacity-failure", failed, capacity=0)
        check(
            "failed-publication-keeps-intent",
            frame(9, args=(first, len(columns[0]))),
            membership=True,
        )
        check(
            "append-publication-capacity-failure",
            frame(
                2,
                args=(5, 2, first + len(columns[0])),
                payload=b"".join(struct.pack("<2d", *c) for c in added),
            ),
            capacity=0,
        )
        check(
            "failed-append-keeps-source-and-intent",
            frame(9, args=(first, len(columns[0]))),
            membership=True,
        )
        cancel_packet = frame(8)
        check("cancel-watermark", cancel_packet)
        check("cancelled-request-replay", cancel_packet, 4)
        check("newer-request-after-cancel", frame(5, bounds=intent), oracle=True)
        stale = bytearray(frame(5, bounds=intent))
        struct.pack_into("<Q", stale, 16, revision - 1)
        check("stale-newer-revision", bytes(stale), 3)
        wrong = bytearray(frame(5, bounds=intent))
        struct.pack_into("<Q", wrong, 24, source_id + 1)
        check("wrong-source-fails-closed", bytes(wrong), 7)
        check("oversized-wire-size-native-wasm-parity", frame(9, args=(first, (1 << 64) - 1)), 2)
        check("nonmonotone-cuts", config(active_cuts=[1.0, 1.0]), 1)
        check("nonfinite-cuts", config(active_cuts=[math.inf]), 1)
        wrong_epoch = bytearray(frame(5, bounds=intent))
        struct.pack_into("<Q", wrong_epoch, 32, 2)
        check("wrong-source-epoch", bytes(wrong_epoch), 7)
        check(
            "append-schema-mismatch",
            frame(
                2,
                args=(4, 1, first + len(columns[0])),
                payload=struct.pack("<4d", 1.0, 2.0, 3.0, 4.0),
            ),
            7,
        )
        check("nonfinite-bounds", frame(5, bounds=(math.nan, 1.0)), 1)
        check("duplicate-view-id", config(passive=[views[0], views[0]]), 1)
        check(
            "checked-index-budget-refusal",
            config(
                active_cuts=list(map(float, range(4096))),
                passive=[(11, 1, list(map(float, range(2000))))],
            ),
            2,
        )
        check("configure-publication-capacity-failure", config(active=99), capacity=0)
        check("budget-refusal-keeps-current-index", frame(5, bounds=intent), oracle=True)
        check("unsupported-active-dimension-switch-with-intent", config(dim=1), 1)
        intent = None
        check("clear-before-active-switch", frame(7), oracle=True)
        check("switch-active-view", config(active=11, dim=1))
        active_dimension = 1
        intent = (1.0, 4.0)
        check("different-active-dimension-exact", frame(5, bounds=intent, exact=True), oracle=True)
        bad = frame(5, bounds=intent)[:-1]
        check("truncated-request", bad, 1)
    finally:
        _native._lib.xyg_filter_session_free(handle)
    manifest = (
        json.dumps({"schema": "xyg.filter-tier-c/v1", "cases": entries}, indent=2) + "\n"
    ).encode()
    for name, payload in (("session.bin", bytes(stream)), ("manifest.json", manifest)):
        if check_only:
            assert (DEST / name).read_bytes() == payload, f"stale shared fixture {name}"
        else:
            (DEST / name).write_bytes(payload)
    print(f"verified {len(entries)} complete packets with independent exact and metadata oracles")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    generate(check_only=parser.parse_args().check)
