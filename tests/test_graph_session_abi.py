"""S4 low-level ctypes proof; public host wrappers remain S6."""

from __future__ import annotations

import ctypes as ct
import struct

from xyg import _native
from xyg._graphforge_container import DTYPE as D
from xyg._graphforge_container import decode_container, encode_container


def _request(seq: int, rev: int, op: int, extra=()) -> bytes:
    return encode_container(
        "XYGI",
        [
            ("header.u64", 0, D.U64, [91273, 9, seq]),
            ("header.u32", 0, D.U32, [rev, op, 0, 0, 0, 0, 0, 0, 0]),
            *extra,
        ],
    )


def _input(data: bytes):
    return (ct.c_uint8 * len(data)).from_buffer_copy(data)


def test_actual_ctypes_session_retry_capacity_style_and_nonconsuming_poll() -> None:
    document = encode_container(
        "XYGF",
        [
            ("status", 0, D.U32, [0]),
            ("kind", 0, D.UTF8, "graph"),
            ("composition.version", 0, D.U32, [2]),
            ("node.uuid", 0, D.UUID, bytes([1]) * 16 + bytes([2]) * 16),
            ("edge.uuid", 0, D.UUID, bytes([1]) * 16),
            ("edge.derived", 0, D.U8, [0]),
            ("edge.layer", 0, D.U32, [0xFFFFFFFF]),
            ("edge.order", 0, D.I64, [-1]),
            ("edge.path", 0, D.U64, [0xFFFFFFFFFFFFFFFF]),
            ("edge.source", 0, D.U64, [0]),
            ("edge.target", 0, D.U64, [1]),
            ("node.label", 0, D.TEXTS, ["one\tline\n\\", "two"]),
        ],
    )
    opening = _request(
        1,
        0,
        19,
        [
            ("document.bytes", 0, D.BYTES, document),
            ("load.x.f64", 0, D.F64, [0.0, 40.0]),
            ("load.y.f64", 0, D.F64, [0.0, 0.0]),
        ],
    )
    lib = _native._lib
    handle = ct.c_uint64()
    assert (
        lib.xyg_graphforge_session_create(
            _input(document),
            len(document),
            _input(opening),
            len(opening),
            91273,
            9,
            ct.byref(handle),
        )
        == 0
    )

    def command(name, data):
        fn = getattr(lib, name)
        size = ct.c_size_t()
        assert fn(handle.value, _input(data), len(data), None, 0, ct.byref(size)) == -5
        assert size.value > 0
        short = (ct.c_uint8 * size.value)(*([0xA5] * size.value))
        assert (
            fn(handle.value, _input(data), len(data), short, size.value - 1, ct.byref(size)) == -5
        )
        assert bytes(short) == bytes([0xA5]) * size.value
        exact = (ct.c_uint8 * size.value)()
        assert fn(handle.value, _input(data), len(data), exact, len(exact), ct.byref(size)) == 0
        retry = (ct.c_uint8 * size.value)()
        assert fn(handle.value, _input(data), len(data), retry, len(retry), ct.byref(size)) == 0
        assert bytes(retry) == bytes(exact)
        return decode_container(bytes(exact), "XYGR")

    try:
        before = command("xyg_graphforge_session_render", _request(2, 0, 21))
        rev = int(before["header.u32", 0][0])
        selected = command(
            "xyg_graphforge_session_interact",
            _request(3, rev, 10, [("uuids.uuid", 0, D.UUID, bytes([1]) * 16)]),
        )
        assert int(selected["header.u32", 0][0]) == rev
        assert selected["node.flags.u32", 0][0] != before["node.flags.u32", 0][0]
        assert selected["edge.flags.u32", 0][0] != before["edge.flags.u32", 0][0]
        assert "one\\tline\\n\\\\" in selected["companion.text.utf8", 0]
        event = command("xyg_graphforge_session_poll_event", _request(4, rev, 22))
        remote = decode_container(event["outbound.bytes", 0], "XYGI")
        assert list(remote["remote.u64", 0]) == [9, 91273, 1]
        assert struct.unpack_from("<I", remote["refs.bytes", 0])[0] == 2
        empty = command("xyg_graphforge_session_poll_event", _request(5, rev, 22))
        assert ("outbound.bytes", 0) not in empty
    finally:
        assert lib.xyg_graphforge_session_destroy(handle.value) == 0
    assert lib.xyg_graphforge_session_destroy(handle.value) == -10
