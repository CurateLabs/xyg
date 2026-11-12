"""One Rust transaction, exact density, and narrowly admitted legacy compatibility."""

import math
import struct

import pytest

from xyg import filter_session as protocol


def session():
    owner = protocol.FilterTierCSession(
        {"a": [0.0, 1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0, 0.0]},
        source_id=112,
        first_row=(1 << 63) + 17,
    )
    owner.configure_density(
        dict(id=1, dimension="a", cuts=[2]),
        [dict(id=1, x="a", y="b", width=2, height=2, x_range=[0, 4], y_range=[0, 4])],
    )
    return owner


def test_range_paint_exact_counts_membership_and_refusal(monkeypatch):
    with session() as owner, session() as reference:
        execute = protocol.execute_packet
        calls = []

        def capture(handle, packet):
            calls.append(struct.unpack_from("<II", packet, 4))
            return execute(handle, packet)

        monkeypatch.setattr(protocol, "execute_packet", capture)
        for bounds in [(0, 1), (3, 2), (0.25, 2.5), (-1, 4), (9, 10), (-0.0, 0.0)]:
            calls.clear()
            reply = owner.range_paint(*bounds, exact=True)
            assert calls == [(3, 5)]
            reference.range(*bounds, exact=True)
            expected = reference.paint(exact=True)
            for key in ("filter_hash", "selected_count", "views", "density", "fallback"):
                assert reply[key] == expected[key]
            assert (
                owner.membership(owner.first_row, 4)["membership"]
                == reference.membership(reference.first_row, 4)["membership"]
            )
        before = owner.paint(exact=True)
        for value in (math.nan, math.inf, -math.inf):
            calls.clear()
            with pytest.raises(protocol.FilterTierCError) as error:
                owner.range_paint(value, 1, exact=True)
            assert calls == [(3, 5)]
            assert error.value.reply["newest_revision"] == error.value.reply["requested_revision"]
            assert owner.paint(exact=True)["filter_hash"] == before["filter_hash"]


@pytest.mark.parametrize("interrupt", [None, "newer", "close"])
def test_legacy_version_refusal_does_not_retry_obsolete_intent(monkeypatch, interrupt):
    with session() as owner:
        execute = protocol.execute_packet
        calls = []

        def old_peer(handle, packet):
            version, op = struct.unpack_from("<II", packet, 4)
            calls.append((version, op))
            if version == 3:
                # Exercise Rust's real unknown-version rejection; the copied
                # previous library is additionally covered in the receipt.
                old = bytearray(packet)
                struct.pack_into("<I", old, 4, 0xFFFFFFFF)
                reply = execute(handle, old)
                if interrupt == "newer":
                    owner.range(2, 3, exact=True)
                elif interrupt == "close":
                    owner.close()
                return reply
            return execute(handle, packet)

        monkeypatch.setattr(protocol, "execute_packet", old_peer)
        if interrupt:
            with pytest.raises(protocol.FilterTierCError):
                owner.range_paint(0, 1, exact=True)
            assert calls == ([(3, 5), (1, 5)] if interrupt == "newer" else [(3, 5)])
            assert getattr(owner, "_range_paint_support", None) is None
        else:
            assert owner.range_paint(0, 1, exact=True)["selected_count"] == 2
            assert calls == [(3, 5), (1, 5), (1, 11)]
            calls.clear()
            assert owner.range_paint(2, 3, exact=True)["selected_count"] == 2
            assert calls == [(1, 5), (1, 11)]
