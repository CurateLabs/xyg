#!/usr/bin/env python3
"""Generate/check immutable complete linked packets, verified by a scalar oracle."""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from filter_density_oracle import DensityOracle  # noqa: E402
from xyg import _native  # noqa: E402
from xyg.filter_session import (  # noqa: E402
    FilterTierCError,
    FilterTierCSession,
    decode_reply,
    request,
)


def generate():
    import xyg.filter_session as client

    stream, entries = bytearray(), []
    oracle = DensityOracle()
    original = client.execute_packet
    name = "open"

    def capture(handle, packet, capacity=2 << 20):
        reply = original(handle, packet, capacity)
        result = decode_reply(reply)
        oracle.check(packet, result)
        stream.extend(
            struct.pack("<IIiIQ", len(packet), capacity, 0, len(reply), len(reply)) + packet + reply
        )
        entries.append(
            dict(
                name=name,
                status=result["status"],
                tier=result["tier"],
                rows=result["rows_read"],
                selected=result["selected_count"],
            )
        )
        return reply

    client.execute_packet = capture
    columns = {
        "a": [-2.0, -1.0, -0.5, -0.0, 0.0, 0.25, 0.5, 1.0, 1.5, 2.0, math.nan, math.inf, -math.inf],
        "b": [1.0, 0.0, -1.0, 0.0, 0.5, 1.0, -0.5, 1.5, -1.5, 0.25, 0.0, 1.0, 2.0],
        "c": [0.0, 1.0, -1.0, 1.5, -1.5, 0.5, 0.0, -0.5, 0.25, 1.0, 2.0, 0.0, -1.0],
        "d": [1.0, -1.0, 0.0, 0.5, 1.5, -1.5, -0.5, 0.25, 1.0, 0.0, 0.0, 1.0, -1.0],
        "e": [0.5, 1.0, -1.0, 0.0, 0.25, 1.5, -1.5, -0.5, 1.0, 0.0, 1.0, 0.0, 2.0],
    }
    names = list(columns)
    views = [
        dict(
            id=i + 1,
            x=dim,
            y=names[(i + 1) % 5],
            width=4,
            height=4,
            x_range=[-2.0, 2.0],
            y_range=[2.0, -2.0],
        )
        for i, dim in enumerate(names)
    ]

    def active(i):
        return dict(id=i + 1, dimension=names[i], cuts=[-1.0, 0.0, 1.0])

    s = FilterTierCSession(
        columns, source_id=112, epoch=7, first_row=(1 << 64) - 100, budget_bytes=1 << 20
    )

    def call(label, method, *args, status=0, **kwargs):
        nonlocal name
        name = label
        try:
            out = method(*args, **kwargs)
            assert status == 0, (label, status)
            return out
        except FilterTierCError as e:
            assert e.status == status, (label, e.status, status)

    try:
        call("configure-2d-five-views", s.configure_density, active(0), views)
        call("all-paint", s.paint)
        for label, lo, hi in [
            ("aligned", -1.0, -0.5),
            ("partial", 0.1, 0.6),
            ("zero", -0.0, 0.0),
            ("reversed", 1.0, -1.0),
            ("empty", 4.0, 5.0),
            ("all-finite", -3.0, 3.0),
        ]:
            call(label, s.range, lo, hi, exact=True)
            call(label + "-paint", s.paint, exact=True)
            call(label + "-membership", s.membership, s.first_row, s.rows)
        call("partial-refusal", s.range, 0.1, 0.2, status=6)
        call("nonfinite", s.range, math.nan, 0.0, status=1)
        call("clear", s.clear)
        call(
            "A-and-B-base",
            s.base_filter,
            [dict(dimension="b", lo=-1.0, hi=1.0)],
            bytes([0xFF, 0x1F]),
        )
        call("base-rebuild", s.paint, exact=True)
        call("C-a", s.range, -0.5, 1.0, exact=True)
        call("begin", s.begin_edit)
        call("switch-active-b", s.configure_density, active(1), views)
        call("C-b-and-C-a", s.range, 0.0, 0.5, exact=True)
        call("composed-paint", s.paint, exact=True)
        call("composed-membership", s.membership, s.first_row, s.rows)
        call("cancel-edit", s.cancel_edit)
        call("cancel-restored-paint", s.paint, exact=True)
        call("cancel-restored-membership", s.membership, s.first_row, s.rows)
        call("begin-again", s.begin_edit)
        call("switch-active-c", s.configure_density, active(2), views)
        call("C-c", s.range, 0.0, 1.0, exact=True)
        call("commit", s.commit_edit)
        call("evict", s.evict)
        call("evicted-membership", s.membership, s.first_row, s.rows)
        call("automatic-rebuild", s.paint, exact=True)
        call("append-with-persistent-mask", s.append, {dim: [0.25] for dim in names})
        call("append-rebuild-mask-excludes-new-row", s.paint, exact=True)
        call("append-membership", s.membership, s.first_row, s.rows)
        call("remove-base-mask", s.base_filter)
        call("base-invalidation-paint", s.paint, exact=True)
        call("clear-after-eviction", s.evict)
        call("clear-without-index", s.clear)
        call("clear-paint", s.paint)
        bad = [dict(v) for v in views]
        bad[0]["width"] = 65536
        call("product-budget-refusal", s.configure_density, active(0), bad, status=2)
        bad = [dict(v) for v in views]
        bad[0]["x_range"] = [0.0, 0.0]
        call("zero-domain-refusal", s.configure_density, active(0), bad, status=1)
        call("after-refused-config", s.paint)
        # Publication failure must leave predicate and visible revision intact.
        name = "capacity-failure"
        s.revision += 1
        packet = request(
            5,
            revision=s.revision,
            source_id=s.source_id,
            epoch=s.epoch,
            source_revision=s.source_revision,
            budget_bytes=s.budget_bytes,
            bounds=(0.1, 0.2),
            exact=True,
        )
        import ctypes

        output = (ctypes.c_ubyte * 1)()
        written = ctypes.c_size_t()
        data = (ctypes.c_ubyte * len(packet)).from_buffer_copy(packet)
        code = _native._lib.xyg_filter_session_execute(
            s._handle, data, len(packet), output, 1, ctypes.byref(written)
        )
        assert code == -4
        stream.extend(struct.pack("<IIiIQ", len(packet), 1, code, 0, written.value) + packet)
        entries.append(dict(name=name, status=-4))
        call("capacity-failed-intent-not-published", s.paint)
        call("cancellation-watermark", s.cancel)
        call("after-cancel-newer", s.paint)
        return bytes(stream), dict(schema="xyg.filter-linked-density/v1", cases=entries)
    finally:
        s.close()
        client.execute_packet = original


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stream, manifest = generate()
    directory = ROOT / "tests/fixtures/filter_tier_c"
    outputs = {
        directory / "density.bin": stream,
        directory / "density.json": (json.dumps(manifest, indent=2) + "\n").encode(),
    }
    for path, data in outputs.items():
        if args.check:
            assert path.read_bytes() == data, f"fixture drift: {path}"
        else:
            path.write_bytes(data)
    print(
        f"{len(manifest['cases'])} linked density complete packets and independent count/membership/paint/hash oracles"
    )


if __name__ == "__main__":
    main()
