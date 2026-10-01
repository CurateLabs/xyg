"""Named-section container codec for GraphForge compositions.

The ``XYGQ`` request and ``XYGF`` document share one framing
(spec/design/graphforge-compositions.md §5): a 32-byte header, 40-byte entries,
names, then 8-byte-aligned little-endian payloads. Pure framing; the sections'
meaning is Rust's. Node ``graphforge-container.js`` and the browser
``49_wasm_graphforge.ts`` are the same codec and produce the same bytes.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Iterable
from typing import Any

import numpy as np

__all__ = [
    "CONTAINER_VERSION",
    "DOCUMENT_MAGIC",
    "DTYPE",
    "REQUEST_MAGIC",
    "decode_container",
    "encode_container",
]

CONTAINER_VERSION = 1
REQUEST_MAGIC = "XYGQ"
DOCUMENT_MAGIC = "XYGF"
_HEADER = 32
_ENTRY = 40
_MAX_ENTRIES = 8192
_NAME = re.compile(r"^[a-z0-9._]{1,64}$")


class DTYPE:
    U8 = 1
    U32 = 2
    U64 = 3
    I64 = 4
    F64 = 5
    BYTES = 6
    UUID = 7
    UTF8 = 8
    TEXTS = 9


_NUMERIC = {DTYPE.U8: "<u1", DTYPE.U32: "<u4", DTYPE.U64: "<u8", DTYPE.I64: "<i8", DTYPE.F64: "<f8"}
_WIDTH = {DTYPE.U8: 1, DTYPE.U32: 4, DTYPE.U64: 8, DTYPE.I64: 8, DTYPE.F64: 8, DTYPE.BYTES: 1}
_WIDTH.update({DTYPE.UUID: 16, DTYPE.UTF8: 1})


def _align8(n: int) -> int:
    return (n + 7) & ~7


def _payload(name: str, dtype: int, values: Any) -> tuple[bytes, int]:
    if dtype in _NUMERIC:
        array = np.asarray(list(values) if not isinstance(values, np.ndarray) else values)
        packed = np.ascontiguousarray(array, dtype=_NUMERIC[dtype]).reshape(-1)
        return packed.tobytes(), int(packed.size)
    if dtype == DTYPE.BYTES:
        data = bytes(values)
        return data, len(data)
    if dtype == DTYPE.UUID:
        data = bytes(values)
        if len(data) % 16:
            raise ValueError(f"{name} must hold 16-byte UUIDs")
        return data, len(data) // 16
    if dtype == DTYPE.UTF8:
        data = str(values).encode("utf-8")
        return data, len(data)
    if dtype == DTYPE.TEXTS:
        parts = [str(v).encode("utf-8") for v in values]
        offsets = [0]
        for part in parts:
            offsets.append(offsets[-1] + len(part))
        head = struct.pack(f"<{len(offsets)}Q", *offsets)
        return head + b"".join(parts), len(parts)
    raise ValueError(f"unknown dtype {dtype}")


def encode_container(magic: str, sections: Iterable[tuple[str, int, int, Any]]) -> bytes:
    """Frame ``(name, index, dtype, values)`` sections into one container."""
    prepared = []
    for name, index, dtype, values in sections:
        if not _NAME.match(name):
            raise ValueError(f"invalid section name {name!r}")
        if not 0 <= int(index) <= 0xFFFFFFFF:
            raise ValueError("section index must be u32")
        payload, count = _payload(name, dtype, values)
        prepared.append((name.encode("utf-8"), int(index), dtype, count, payload))
    if len(prepared) > _MAX_ENTRIES:
        raise ValueError("too many container sections")
    names = sum(len(p[0]) for p in prepared)
    names_start = _HEADER + len(prepared) * _ENTRY
    cursor = _align8(names_start + names)
    offsets = []
    for p in prepared:
        offsets.append(cursor)
        cursor = _align8(cursor + len(p[4]))
    out = bytearray(cursor)
    struct.pack_into(
        "<4sIIIQ", out, 0, magic.encode("ascii"), CONTAINER_VERSION, len(prepared), names, cursor
    )
    name_at = 0
    for i, (name, index, dtype, count, payload) in enumerate(prepared):
        struct.pack_into(
            "<IIIIQQQ",
            out,
            _HEADER + i * _ENTRY,
            name_at,
            len(name),
            dtype,
            index,
            offsets[i],
            count,
            len(payload),
        )
        out[names_start + name_at : names_start + name_at + len(name)] = name
        name_at += len(name)
        out[offsets[i] : offsets[i] + len(payload)] = payload
    return bytes(out)


def decode_container(data: bytes, magic: str) -> dict[tuple[str, int], Any]:
    """``{(name, index): value}``: numeric sections as little-endian numpy
    arrays (copies), ``utf8`` as ``str``, ``texts`` as ``list[str]``, and
    ``uuid``/``bytes`` as ``bytes``. Raises ``ValueError`` on malformed bytes."""
    view = memoryview(bytes(data))

    def fail(reason: str) -> None:
        raise ValueError(f"malformed {magic} container: {reason}")

    if len(view) < _HEADER or bytes(view[:4]) != magic.encode("ascii"):
        fail("magic")
    _, version, count, names, total = struct.unpack_from("<4sIIIQ", view, 0)
    if version != CONTAINER_VERSION:
        fail("version")
    if count > _MAX_ENTRIES or total != len(view):
        fail("header")
    names_start = _HEADER + count * _ENTRY
    payload_start = _align8(names_start + names)
    if payload_start > len(view):
        fail("names")
    sections: dict[tuple[str, int], Any] = {}
    for i in range(count):
        name_off, name_len, dtype, index, offset, n, length = struct.unpack_from(
            "<IIIIQQQ", view, _HEADER + i * _ENTRY
        )
        if name_off + name_len > names:
            fail("name range")
        name = bytes(view[names_start + name_off : names_start + name_off + name_len]).decode(
            "utf-8"
        )
        if not _NAME.match(name):
            fail("name")
        if offset % 8 or offset < payload_start or offset + length > len(view):
            fail("section range")
        payload = view[offset : offset + length]
        value: Any
        if dtype == DTYPE.TEXTS:
            head = (n + 1) * 8
            if length < head:
                fail("texts")
            offs = struct.unpack_from(f"<{n + 1}Q", payload, 0)
            text = bytes(payload[head:])
            value = []
            for k in range(n):
                start, end = offs[k], offs[k + 1]
                if end < start or end > len(text):
                    fail("text offsets")
                value.append(text[start:end].decode("utf-8"))
        else:
            width = _WIDTH.get(dtype)
            if width is None or n * width != length:
                fail("section size")
            if dtype in _NUMERIC:
                value = np.frombuffer(bytes(payload), dtype=_NUMERIC[dtype]).copy()
            elif dtype == DTYPE.UTF8:
                value = bytes(payload).decode("utf-8")
            else:
                value = bytes(payload)
        if (name, index) in sections:
            fail("duplicate section")
        sections[(name, index)] = value
    return sections
