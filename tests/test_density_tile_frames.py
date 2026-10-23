"""Rust-owned keyed painter framing, host controls and deterministic reuse (#10)."""

from __future__ import annotations

import hashlib
import struct

import numpy as np
import pytest

from xyg import kernels


def decode_frame(raw: bytes) -> dict:
    assert raw[:4] == b"XYDT"
    level, flags, count, active, missing = struct.unpack_from("<5I", raw, 8)
    rows = []
    for i in range(count):
        fields = struct.unpack_from("<8I8d", raw, 128 + 96 * i)
        rows.append(
            {
                "key": list(fields[:3]),
                "w": fields[3],
                "h": fields[4],
                "offset": fields[5],
                "size": fields[6],
                "active": fields[7],
                "ranges": fields[8:],
                "pixels": raw[fields[5] : fields[5] + fields[6]],
            }
        )
    return {
        "level": level,
        "flags": flags,
        "active": active,
        "missing": missing,
        "generation": struct.unpack_from("<Q", raw, 32)[0],
        "max": struct.unpack_from("<d", raw, 40)[0],
        "log_max": struct.unpack_from("<d", raw, 48)[0],
        "budget": struct.unpack_from("<I", raw, 64)[0],
        "gpu_bytes": struct.unpack_from("<I", raw, 68)[0],
        "rows": rows,
    }


def observations(frame: dict) -> dict:
    return {
        "known_generation": frame["generation"],
        "previous_level": frame["level"],
        "known_keys": [r["key"] for r in frame["rows"]],
    }


@pytest.fixture
def store():
    n = 32768
    i = np.arange(n, dtype=np.float64)
    x, y = (i * 17 % n) / n, (i * 31 % n) / n
    pyr = kernels.pyramid_build(x, y, 0, 1, 0, 1, 1024)
    handle = kernels.pyramid_spill(pyr)
    kernels.pyramid_free(pyr)
    assert handle
    yield handle
    kernels.tile_store_free(handle)


def test_keyed_pan_sends_only_edges_with_identical_uncached_source_bytes(store):
    a = decode_frame(kernels.tile_store_paint(store, 0, 0.5, 0, 0.5, 256, 256))
    b = decode_frame(
        kernels.tile_store_paint(store, 0.25, 0.75, 0, 0.5, 256, 256, **observations(a))
    )
    uncached = decode_frame(kernels.tile_store_paint(store, 0.25, 0.75, 0, 0.5, 256, 256))
    assert (a["level"], a["active"], a["missing"]) == (1, 1, 1)
    assert (b["level"], b["active"], b["missing"]) == (1, 2, 1)
    assert uncached["missing"] == 2
    assert (
        hashlib.sha256(b"".join(r["pixels"] for r in uncached["rows"])).hexdigest()
        == "410965db6e34b2143ebcb668edd99c35af3dd7caaade3e3eace7566cdb5486dd"
    )
    assert (b["max"], b["log_max"]) == (uncached["max"], uncached["log_max"])
    cache = {tuple(r["key"]): r["pixels"] for r in a["rows"]}
    cache.update({tuple(r["key"]): r["pixels"] for r in b["rows"] if r["size"]})
    for row in uncached["rows"]:
        assert cache[tuple(row["key"])] == row["pixels"]
    assert b["gpu_bytes"] <= b["budget"] == 256 * 256 * 8
    zoom = decode_frame(
        kernels.tile_store_paint(store, 0.25, 0.5, 0, 0.25, 256, 256, **observations(b))
    )
    assert abs(zoom["level"] - b["level"]) == 1
    assert any(r["key"][0] == b["level"] for r in zoom["rows"])


def test_resource_coarsening_is_explicit_and_invalid_controls_are_bounded(store):
    tiny = decode_frame(kernels.tile_store_paint(store, 0, 1, 0, 1, 16, 16))
    assert tiny["gpu_bytes"] <= tiny["budget"] == 2048
    for keys in ([[0, -1, 0]], [[0, 0]], [[0, 0, 0]] * 257, "invalid"):
        with pytest.raises(ValueError, match="known tile"):
            kernels.tile_store_paint(store, 0, 1, 0, 1, 256, 256, known_keys=keys)
    for args in ({"known_generation": -1}, {"known_generation": 2**64}, {"previous_level": 32}):
        with pytest.raises(ValueError, match="generation or level"):
            kernels.tile_store_paint(store, 0, 1, 0, 1, 256, 256, **args)
    assert kernels.tile_store_paint(store, 0, 0, 0, 1, 256, 256) is None


def test_binary_inventory_decoder_and_channel_forwarding(store):
    import xyg
    from xyg.channel import handle_message

    control = struct.pack("<4sIQdiI", b"XYDC", 1, 0, -1.0, -1, 0)
    frame = kernels.tile_store_paint(store, 0, 0.5, 0, 0.5, 256, 256, control=control)
    assert decode_frame(frame)["missing"] == 1
    malformed = [
        b"XYDC",
        control + b"\0",
        b"WRNG" + control[4:],
        control[:28] + struct.pack("<I", 257),
        control[:16] + struct.pack("<d", float("nan")) + control[24:],
    ]
    for raw in malformed:
        with pytest.raises(ValueError, match="tile painter frame"):
            kernels.tile_store_paint(store, 0, 0.5, 0, 0.5, 256, 256, control=raw)
    fig = xyg.scatter_chart(xyg.scatter([0.1, 0.2], [0.2, 0.3], density=True)).figure()
    trace = fig.traces[0]
    trace._tile_store = store
    message = {
        "type": "density_view",
        "seq": 7,
        "trace": trace.id,
        "x0": 0.0,
        "x1": 0.5,
        "y0": 0.0,
        "y1": 0.5,
        "w": 256,
        "h": 256,
        "tile_cache": True,
    }
    reply, buffers = handle_message(fig, message, [control])
    assert reply["seq"] == 7
    assert reply["traces"][0]["density"]["tile_frame"] == 0
    assert decode_frame(buffers[0])["missing"] == 1
    for attachments in ([], [control, control], [malformed[0]], ["not binary"]):
        assert handle_message(fig, message, attachments) is None
    assert handle_message(fig, {**message, "tile_cache": {"keys": [[0, 0, 0]]}}, [control]) is None
    trace._tile_store = None
