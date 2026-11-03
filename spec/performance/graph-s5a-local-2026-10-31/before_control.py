"""Compare real parent/S5a C-ABI replies, including same-revision changes."""

import ctypes as ct
import hashlib
import json
import struct
from pathlib import Path

from xyg._graphforge_container import DTYPE as D
from xyg._graphforge_container import decode_container, encode_container

ROOT = Path(__file__).resolve().parents[3]


def request(seq, rev, op, extra=()):
    return encode_container(
        "XYGI",
        [
            ("header.u64", 0, D.U64, [7081, 9, seq]),
            ("header.u32", 0, D.U32, [rev, op, 0, 0, 0, 0, 0, 0, 0]),
            *extra,
        ],
    )


def run(library):
    lib = ct.CDLL(str(library))
    byte_ptr = ct.POINTER(ct.c_uint8)
    create = lib.xyg_graphforge_session_create
    create.argtypes = [
        byte_ptr,
        ct.c_size_t,
        byte_ptr,
        ct.c_size_t,
        ct.c_uint64,
        ct.c_uint64,
        ct.POINTER(ct.c_uint64),
    ]
    destroy = lib.xyg_graphforge_session_destroy
    destroy.argtypes = [ct.c_uint64]

    def data(value):
        return (ct.c_uint8 * len(value)).from_buffer_copy(value)

    document = encode_container(
        "XYGF",
        [
            ("status", 0, D.U32, [0]),
            ("kind", 0, D.UTF8, "graph"),
            ("composition.version", 0, D.U32, [2]),
            ("node.uuid", 0, D.UUID, bytes([1]) * 16 + bytes([2]) * 16),
            ("edge.uuid", 0, D.UUID, bytes([3]) * 16),
            ("edge.derived", 0, D.U8, [0]),
            ("edge.layer", 0, D.U32, [0xFFFFFFFF]),
            ("edge.order", 0, D.I64, [-1]),
            ("edge.path", 0, D.U64, [0xFFFFFFFFFFFFFFFF]),
            ("edge.source", 0, D.U64, [0]),
            ("edge.target", 0, D.U64, [1]),
        ],
    )
    opening = request(
        1,
        0,
        19,
        [
            ("document.bytes", 0, D.BYTES, document),
            ("load.x.f64", 0, D.F64, [0.0, 40.0]),
            ("load.y.f64", 0, D.F64, [0.0, 0.0]),
        ],
    )
    handle = ct.c_uint64()
    assert (
        create(
            data(document), len(document), data(opening), len(opening), 7081, 9, ct.byref(handle)
        )
        == 0
    )

    def command(name, value):
        fn = getattr(lib, name)
        fn.argtypes = [
            ct.c_uint64,
            byte_ptr,
            ct.c_size_t,
            byte_ptr,
            ct.c_size_t,
            ct.POINTER(ct.c_size_t),
        ]
        count = ct.c_size_t()
        assert fn(handle.value, data(value), len(value), None, 0, ct.byref(count)) == -5
        result = (ct.c_uint8 * count.value)()
        assert fn(handle.value, data(value), len(value), result, count.value, ct.byref(count)) == 0
        return bytes(result)

    try:
        rendered = command("xyg_graphforge_session_render", request(2, 0, 21))
        revision = decode_container(rendered, "XYGR")["header.u32", 0][0]
        selected = command(
            "xyg_graphforge_session_interact",
            request(3, revision, 10, [("uuids.uuid", 0, D.UUID, bytes([1]) * 16)]),
        )
        return rendered, selected
    finally:
        assert destroy(handle.value) == 0


baseline = ROOT / "target/task-tmp/s5a-parent-target/release/libxyg_core.so"
current = ROOT / "target/release/libxyg_core.so"
before, after = run(baseline), run(current)
records = []


def raw_sections(value):
    count, names = struct.unpack_from("<II", value, 8)
    names_start = 32 + count * 40
    result = {}
    for i in range(count):
        off, length, dtype, index, start, n, byte_length = struct.unpack_from(
            "<IIIIQQQ", value, 32 + i * 40
        )
        name = value[names_start + off : names_start + off + length].decode("ascii")
        result[name, index] = (dtype, n, value[start : start + byte_length])
    assert names_start + names <= len(value)
    return result


for name, old, new in zip(["render", "same_revision_select"], before, after, strict=True):
    left, right = raw_sections(old), raw_sections(new)
    extra = set(right) - set(left)
    assert len([key for key in extra if key[0].startswith("gpu.")]) == 33
    assert len(extra) == 38
    assert not any(
        key[0].startswith(("gpu.", "outcome.", "focus.action.", "disclosure.")) for key in left
    )
    # Compare exact dtype, count and payload; envelope offsets necessarily move.
    assert set(left) <= set(right)
    for key, value in left.items():
        assert value == right[key], key
    records.append(
        {
            "operation": name,
            "beforeBytes": len(old),
            "afterBytes": len(new),
            "beforeSha256": hashlib.sha256(old).hexdigest(),
            "afterSha256": hashlib.sha256(new).hexdigest(),
            "unchangedSections": len(left),
            "newSections": len(extra),
        }
    )
print(
    json.dumps(
        {
            "parent": "1044cdf2175d57dbed2c5088f747f812a982dc08",
            "baselineLibrarySha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            "currentLibrarySha256": hashlib.sha256(current.read_bytes()).hexdigest(),
            "controls": records,
        },
        indent=2,
    )
)
