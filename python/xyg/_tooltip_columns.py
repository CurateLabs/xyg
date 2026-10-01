"""Typed wire encoding for semantic hover rows (graph-mark.md §2, "Tooltip columns").

Hosts keep ``trace.tooltip_rows`` as row dicts. On the wire, a trace's rows ship
as typed planes instead of one JSON object per element: each key becomes one
column of a single kind, all as ``u8``/``u32`` payload columns:

- ``uuid``: canonical lowercase UUID text, 16 bytes per row; a column holding
  any UUID uses this kind, and its other strings (for example synthetic ids of
  derived edges) are dictionary text stored in the slot's first four bytes;
- ``f64``: numbers, 8 little-endian bytes per row (u8 column: packed blobs are
  only 4-byte aligned);
- ``bool``: one byte per row;
- ``text``: ``u32`` index into the entry's string dictionary.

All text columns share one dictionary per entry (``dict``), so a name repeated
across keys ships once. An optional ``u8`` presence plane per key records an
absent key (0), a null value (1), a value (2), or, in a ``uuid`` column, a
dictionary string (3); it is omitted when every row has a value. Non-finite
numbers ship as null, as JSON would. Rows whose keys do not follow one shared
order, whose values are not scalars of one kind per key, or that hold an
integer beyond ±2**53 (which f64 would round) keep the JSON ``tooltip_rows``
form. Node ``tooltip-columns.js`` is the same encoding byte for
byte; the browser materializes one row per hover.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

import numpy as np

__all__ = ["decode_tooltip_rows", "encode_tooltip_rows"]

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ABSENT, _NULL, _VALUE, _TEXT = 0, 1, 2, 3
_EXACT_INT = 2**53  # integers beyond this lose digits as f64


def _kind(value: Any) -> str | None:
    if value is None:
        return "null"
    if isinstance(value, (bool, np.bool_)):
        return "bool"
    if isinstance(value, (int, np.integer)) and abs(int(value)) > _EXACT_INT:
        return None  # an integer f64 cannot hold exactly: keep JSON rows
    if isinstance(value, (int, float, np.integer, np.floating)):
        return "f64"
    if isinstance(value, str):
        return "text"
    return None


def encode_tooltip_rows(rows: Sequence[dict[str, Any]], pw: Any) -> dict[str, Any] | None:
    """Ship ``rows`` as typed columns through ``pw`` (rows are only read).

    Returns the ``tooltip_columns`` entry, or ``None`` to keep JSON rows.
    """
    n = len(rows)
    if n == 0:
        return None
    keys: list[str] = []
    position: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        last = -1
        for key in row:
            if not isinstance(key, str):
                return None
            at = position.get(key)
            if at is None:
                at = position[key] = len(keys)
                keys.append(key)
            if at <= last:
                return None  # rows disagree on key order
            last = at
    kinds: list[str] = []
    for key in keys:
        kind = "null"
        any_uuid = False
        for row in rows:
            if key not in row:
                continue
            value = row[key]
            k = _kind(value)
            if k is None:
                return None
            if k == "null":
                continue
            if kind not in ("null", k):
                return None
            kind = k
            if k == "text" and not any_uuid and _UUID.match(value):
                any_uuid = True
        kinds.append("bool" if kind == "null" else "uuid" if any_uuid else kind)

    data: list[int] = []
    present: list[int | None] = []
    dictionary: list[str] = []
    lookup: dict[str, int] = {}

    def intern(text: str) -> int:
        index = lookup.get(text)
        if index is None:
            index = lookup[text] = len(dictionary)
            dictionary.append(text)
        return index

    for key, kind in zip(keys, kinds, strict=True):
        presence = np.full(n, _VALUE, dtype=np.uint8)
        if kind == "uuid":
            plane = np.zeros(n * 16, dtype=np.uint8)
        elif kind == "f64":
            numbers = np.zeros(n, dtype="<f8")
        elif kind == "bool":
            plane = np.zeros(n, dtype=np.uint8)
        else:
            indices = np.zeros(n, dtype="<u4")
        for i, row in enumerate(rows):
            if key not in row:
                presence[i] = _ABSENT
                continue
            value = row[key]
            if value is None or (kind == "f64" and not math.isfinite(float(value))):
                presence[i] = _NULL
            elif kind == "uuid":
                if _UUID.match(value):
                    plane[i * 16 : i * 16 + 16] = np.frombuffer(
                        bytes.fromhex(value.replace("-", "")), dtype=np.uint8
                    )
                else:
                    presence[i] = _TEXT
                    plane[i * 16 : i * 16 + 4] = np.frombuffer(
                        intern(value).to_bytes(4, "little"), dtype=np.uint8
                    )
            elif kind == "f64":
                numbers[i] = float(value)
            elif kind == "bool":
                plane[i] = 1 if value else 0
            else:
                indices[i] = intern(value)
        present.append(None if bool(np.all(presence == _VALUE)) else pw.ship_u8(presence))
        if kind == "f64":
            data.append(pw.ship_u8(numbers.view(np.uint8)))
        elif kind == "text":
            data.append(pw.ship_u32(indices))
        else:
            data.append(pw.ship_u8(plane))
    return {
        "n": n,
        "keys": keys,
        "kinds": kinds,
        "data": data,
        "present": present,
        "dict": dictionary,
    }


def _column_bytes(spec: dict[str, Any], payload: Any, index: int) -> memoryview:
    meta = spec["columns"][index]
    width = {"u8": 1, "u32": 4, "f64": 8}.get(meta.get("dtype"), 4)
    source = payload[meta["buf"]] if "buf" in meta else payload
    view = memoryview(source).cast("B")
    start = int(meta["byte_offset"])
    return view[start : start + int(meta["len"]) * width]


def decode_tooltip_rows(
    spec: dict[str, Any], payload: Any, entry: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """The rows a trace entry carries, from either wire form (tests, hosts)."""
    if "tooltip_rows" in entry:
        return entry["tooltip_rows"]
    cols = entry.get("tooltip_columns")
    if cols is None:
        return None
    n = int(cols["n"])
    dictionary = cols["dict"]
    rows: list[dict[str, Any]] = [{} for _ in range(n)]
    for key, kind, data, present in zip(
        cols["keys"], cols["kinds"], cols["data"], cols["present"], strict=True
    ):
        raw = _column_bytes(spec, payload, data)
        flags = _column_bytes(spec, payload, present) if present is not None else None
        for i in range(n):
            state = flags[i] if flags is not None else _VALUE
            if state == _ABSENT:
                continue
            if state == _NULL:
                rows[i][key] = None
            elif state == _TEXT:
                rows[i][key] = dictionary[int.from_bytes(raw[i * 16 : i * 16 + 4], "little")]
            elif kind == "uuid":
                h = bytes(raw[i * 16 : i * 16 + 16]).hex()
                rows[i][key] = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
            elif kind == "f64":
                rows[i][key] = float(np.frombuffer(raw[i * 8 : i * 8 + 8], dtype="<f8")[0])
            elif kind == "bool":
                rows[i][key] = bool(raw[i])
            else:
                rows[i][key] = dictionary[int.from_bytes(raw[i * 4 : i * 4 + 4], "little")]
    return rows
