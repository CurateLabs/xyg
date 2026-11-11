"""Text schema inference preserves late-value validation and complete wire planes."""

from __future__ import annotations

import struct
import uuid

import numpy as np
import pytest

from test_tooltip_columns_cross_host import U1, _Recorder
from xyg._tooltip_columns import encode_tooltip_rows


def _encode(rows):
    recorder = _Recorder()
    entry = encode_tooltip_rows(rows, recorder)
    # Observe every writer call even when inference refuses typed columns.
    return {"tooltip_columns": entry, "shipped": recorder.columns}


class _Label(str):
    pass


class _IntegerText(str):
    @property
    def __class__(self):
        return int


class _BooleanText(str):
    @property
    def __class__(self):
        return bool


@pytest.mark.parametrize("count", [2, 4097])
@pytest.mark.parametrize("first", ["alpha", U1], ids=["ordinary", "uuid"])
@pytest.mark.parametrize(
    ("late", "kind"),
    [
        pytest.param("naïve ☃", "text", id="builtin"),
        pytest.param(np.str_("label"), "text", id="numpy-text"),
        pytest.param(_Label("label"), "text", id="text-subclass"),
        pytest.param(np.str_(U1), "uuid", id="late-numpy-uuid"),
        pytest.param(None, "null", id="null"),
        pytest.param(0, None, id="integer"),
        pytest.param(True, None, id="boolean"),
        pytest.param(np.int64(1), None, id="numpy-integer"),
        pytest.param(2**54, None, id="unsafe-integer"),
        pytest.param(np.uint64(2**64 - 1), None, id="unsafe-numpy-integer"),
        pytest.param(float("inf"), None, id="nonfinite"),
        pytest.param([], None, id="nested"),
        pytest.param(_IntegerText("7"), None, id="integer-subclass-identity"),
        pytest.param(_BooleanText("1"), None, id="boolean-subclass-identity"),
    ],
)
def test_late_text_values_preserve_scalar_refusal_and_full_bytes(count, first, late, kind):
    rows = [{"text": first} for _ in range(count - 1)] + [{"text": late}]
    before = repr(rows)
    encoded = _encode(rows)
    assert repr(rows) == before and rows[-1]["text"] is late
    if kind is None:
        assert encoded == {"tooltip_columns": None, "shipped": []}
        return

    # This fixture has only one declared UUID and at most two dictionary values;
    # build its exact expected bytes without the production classifier or regex.
    is_uuid = first == U1 or kind == "uuid"
    dtype = "u8" if is_uuid else "u32"
    dictionary, parts, flags = [], [], []
    for value in [first] * (count - 1) + [late]:
        if value is None:
            flags.append(1)
            parts.append(bytes(16 if is_uuid else 4))
        elif is_uuid and value == U1:
            flags.append(2)
            parts.append(uuid.UUID(U1).bytes)
        else:
            text = str(value)
            if text not in dictionary:
                dictionary.append(text)
            flags.append(3 if is_uuid else 2)
            parts.append(
                struct.pack("<I", dictionary.index(text)) + (bytes(12) if is_uuid else b"")
            )
    raw = b"".join(parts)
    presence = None if all(flag == 2 for flag in flags) else bytes(flags)
    shipped = [] if presence is None else [{"dtype": "u8", "hex": presence.hex()}]
    shipped.append({"dtype": dtype, "hex": raw.hex()})
    assert encoded == {
        "tooltip_columns": {
            "n": count,
            "keys": ["text"],
            "kinds": ["uuid" if is_uuid else "text"],
            "data": [0 if presence is None else 1],
            "present": [None if presence is None else 0],
            "dict": dictionary,
        },
        "shipped": shipped,
    }


def test_row_mutation_revalidates_schema_on_each_encode():
    rows = [{"id": U1}, {"id": U1}]
    assert _encode(rows)["tooltip_columns"]["kinds"] == ["uuid"]
    rows[1]["id"] = 2**54
    assert _encode(rows) == {"tooltip_columns": None, "shipped": []}
    rows[0]["id"], rows[1]["id"] = False, True
    assert _encode(rows) == {
        "tooltip_columns": {
            "n": 2,
            "keys": ["id"],
            "kinds": ["bool"],
            "data": [0],
            "present": [None],
            "dict": [],
        },
        "shipped": [{"dtype": "u8", "hex": "0001"}],
    }


@pytest.mark.parametrize("count", [2, 4097])
def test_uuid_classification_cannot_bypass_a_later_numeric_column(count):
    rows = [{"id": U1, "value": 1} for _ in range(count)]
    assert _encode(rows)["tooltip_columns"]["kinds"] == ["uuid", "f64"]
    rows[-1]["value"] = np.uint64(2**64 - 1)
    assert _encode(rows) == {"tooltip_columns": None, "shipped": []}
