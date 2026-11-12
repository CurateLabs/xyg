"""Complete shared packets plus independent scan oracles through public composition."""

from __future__ import annotations

import ctypes
import json
import math
import struct
from pathlib import Path

import pytest

import xyg
from xyg import _native
from xyg.filter_session import FilterTierCError, decode_reply, execute_packet

FIXTURES = Path(__file__).parent / "fixtures/filter_tier_c"


def test_native_complete_packets_and_independent_oracles():
    stream = (FIXTURES / "session.bin").read_bytes()
    cases = json.loads((FIXTURES / "manifest.json").read_text())["cases"]
    handle = _native._lib.xyg_filter_session_new(1 << 20)
    at = 0
    try:
        for case in cases:
            n, cap, code, reply_n, required = struct.unpack_from("<IIiIQ", stream, at)
            at += 24
            request = stream[at : at + n]
            at += n
            expected = stream[at : at + reply_n]
            at += reply_n
            if code:
                with pytest.raises(RuntimeError, match=f"required capacity {required}"):
                    execute_packet(handle, request, cap)
                continue
            packet = execute_packet(handle, request, cap)
            assert packet == expected, case["name"]
            result = decode_reply(packet)
            if oracle := case["oracle"]:
                assert result["selected_count"] == oracle["selected"]
                if oracle["membership_hex"] is not None:
                    assert result["membership"].hex() == oracle["membership_hex"]
                else:
                    assert [
                        {"id": v["id"], "counts": list(v["counts"])} for v in result["views"]
                    ] == oracle["views"]
        assert at == len(stream)
    finally:
        _native._lib.xyg_filter_session_free(handle)


def chart():
    return xyg.scatter_chart(xyg.scatter(x=[0, 1], y=[2, 3]))


def test_public_composition_exact_counts_and_membership_lifecycle():
    columns = {"a": [0, 0.25, 0.5, 1], "b": [3, 2, 1, 0]}
    with chart().filter_session(columns, source_id=9, first_row=(1 << 53) + 1) as session:
        session.configure(
            {"id": 1, "dimension": "a", "cuts": [0, 1]},
            [{"id": 2, "dimension": "b", "cuts": [1, 3]}],
        )
        result = session.range(0, 0.5)
        assert result["tier"] == 3 and result["rows_read"] == 0
        assert result["views"][0]["counts"] == (0, 2, 1)
        original_hash = result["filter_hash"]
        assert session.range(0.5, 0)["filter_hash"] == original_hash
        with pytest.raises(FilterTierCError) as error:
            session.range(0.1, 0.4)
        assert error.value.status == 6
        assert error.value.reply["filter_hash"] == original_hash
        exact = session.range(0.1, 0.4, exact=True)
        assert exact["tier"] == 2 and exact["fallback"] == 1 and exact["rows_read"] == 4
        session.evict()
        assert session.membership((1 << 53) + 1, 4)["membership"] == b"\x02"
        session.append({"a": [0.2], "b": [2]})
        assert session.membership((1 << 53) + 1, 5)["membership"] == b"\x12"
        with pytest.raises(FilterTierCError) as error:
            session.range(0.1, 0.4, exact=True)
        assert error.value.status == 5
        session.rebuild()
        assert session.range(0.1, 0.4, exact=True)["selected_count"] == 2


@pytest.mark.parametrize("columns", [{"a": [], "b": []}, {"a": [math.nan, math.inf], "b": [1, 2]}])
def test_empty_and_nonfinite_sources(columns):
    with chart().filter_session(columns, source_id=9) as session:
        session.configure(
            {"id": 1, "dimension": "a", "cuts": []}, [{"id": 2, "dimension": "b", "cuts": []}]
        )
        assert session.range(0, 0)["selected_count"] == 0
        assert session.clear()["selected_count"] == len(columns["a"])


def test_native_disposal_and_external_cancellation():
    session = chart().filter_session({"a": [0, 1]}, source_id=9)
    handle = session._handle
    session.configure(
        {"id": 1, "dimension": "a", "cuts": []}, [{"id": 2, "dimension": "a", "cuts": []}]
    )
    assert _native._lib.xyg_filter_session_cancel(handle, session.revision + 1) == 0
    with pytest.raises(FilterTierCError) as error:
        session.range(0, 1)
    assert error.value.status == 4
    assert session.range(0, 1)["selected_count"] == 2
    session.close()
    n = ctypes.c_size_t()
    assert (
        _native._lib.xyg_filter_session_execute(
            handle, (ctypes.c_ubyte * 1)(), 1, None, 0, ctypes.byref(n)
        )
        == -1
    )


def test_independent_boundary_oracle_and_index_storage_independence():
    import random

    random_source = random.Random(112)
    index_bytes = []
    for n in (0, 7, 511):
        columns = {
            "a": [random_source.random() * 4 - 2 for _ in range(n)],
            "b": [random_source.random() * 8 - 4 for _ in range(n)],
        }
        with chart().filter_session(columns, source_id=9) as session:
            session.configure(
                {"id": 1, "dimension": "a", "cuts": [-1, 0, 1]},
                [{"id": 2, "dimension": "b", "cuts": [-2, 0, 2]}],
            )
            for lo, hi in [(-3, 3), (0, 0), (0.001, 0.999), (1, -1), (5, 6)]:
                result = session.range(lo, hi, exact=True)
                selected = [min(lo, hi) <= x <= max(lo, hi) for x in columns["a"]]
                assert result["selected_count"] == sum(selected)
                expected = tuple(
                    sum(
                        yes and left <= y < right
                        for yes, y in zip(selected, columns["b"], strict=True)
                    )
                    for left, right in [(-math.inf, -2), (-2, 0), (0, 2), (2, math.inf)]
                )
                assert result["views"][0]["counts"] == expected
            index_bytes.append(result["index_bytes"])
            # Four active cells, five channels: exact private u32 prefix,
            # public u64 totals, and f64 extrema; no row-count-dependent mask.
            assert result["index_bytes"] == 4 * 5 * 5 + 8 * 5 + 16 * 4
    assert len(set(index_bytes)) == 1  # No row words appear in the index allocation.


@pytest.mark.parametrize("operation,version", [(1, 1), (16, 2)])
def test_prefix_row_bound_refuses_before_source_publication(operation, version):
    stream = (FIXTURES / "session.bin").read_bytes()
    size = struct.unpack_from("<I", stream)[0]
    source = stream[24 : 24 + size]
    packet = bytearray(source)
    struct.pack_into("<II", packet, 4, version, operation)
    struct.pack_into("<Q", packet, 64, (1 << 32))
    handle = _native._lib.xyg_filter_session_new(1 << 20)
    try:
        refused = decode_reply(execute_packet(handle, bytes(packet)))
        assert refused["status"] == 2
        assert refused["revision"] == 0 and refused["source_rows"] == 0
        assert refused["index_bytes"] == 0
        recovered = bytearray(source)
        struct.pack_into("<Q", recovered, 16, 2)
        assert decode_reply(execute_packet(handle, bytes(recovered)))["status"] == 0
    finally:
        _native._lib.xyg_filter_session_free(handle)


def test_malformed_newer_headers_do_not_poison_native_protocol_watermark():
    stream = (FIXTURES / "session.bin").read_bytes()

    def record(at):
        n, _, _, reply_n, _ = struct.unpack_from("<IIiIQ", stream, at)
        start = at + 24
        return (
            stream[start : start + n],
            stream[start + n : start + n + reply_n],
            start + n + reply_n,
        )

    source, source_reply, at = record(0)
    config, config_reply, _ = record(at)
    handle = _native._lib.xyg_filter_session_new(1 << 20)
    try:
        assert execute_packet(handle, source) == source_reply
        operation = bytearray(source[:96])
        struct.pack_into("<I", operation, 8, 99)
        struct.pack_into("<Q", operation, 16, 100)
        flags = bytearray(operation)
        struct.pack_into("<I", flags, 8, 5)
        struct.pack_into("<I", flags, 12, 2)
        struct.pack_into("<Q", flags, 16, 101)
        for packet in (operation, flags):
            reply = decode_reply(execute_packet(handle, bytes(packet)))
            assert reply["status"] == 1 and reply["revision"] == 1
            assert reply["selected_count"] is None
        assert execute_packet(handle, config) == config_reply
    finally:
        _native._lib.xyg_filter_session_free(handle)


def test_fixture_generator_independently_verifies_metadata_and_complete_packets():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/gen_filter_tier_c_fixture.py", "--check"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "47 complete packets with independent exact and metadata oracles" in result.stdout
