"""Bounded harness transport proofs; no benchmark timings or large datasets."""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("tornado", reason="optional UX host dependency")
import tornado.httpserver
import tornado.netutil
import tornado.web
import tornado.websocket
from benchmarks import _ux_live_host as host

import xyg
from xyg.channel import decode_frame, encode_frame, handle_message

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "python/xyg/static/index.js"


def inventory(count=0):
    return struct.pack("<4sIQdiI", b"XYDC", 1, 7, 0.75, 2, count) + bytes(count * 12)


def density_request(**extra):
    return {
        "type": "density_view",
        "trace": 0,
        "x0": 0.0,
        "x1": 7.0,
        "y0": 0.0,
        "y1": 7.0,
        "w": 16,
        "h": 16,
        "seq": 9,
        **extra,
    }


def small_figure():
    values = np.arange(8, dtype=np.float64)
    return xyg.scatter_chart(xyg.scatter(x=values, y=values, density=True)).figure()


def test_python_roundtrip_dispatches_binary_control_and_legacy_json(monkeypatch):
    fig = small_figure()
    calls = []
    original = fig.density_view

    def observed(*args, **kwargs):
        calls.append(kwargs["tile_cache"])
        return original(*args, **kwargs)

    monkeypatch.setattr(fig, "density_view", observed)
    for count in (0, 256):
        raw = inventory(count)
        wire = encode_frame(density_request(tile_cache=True), [raw])
        content, buffers = host.decode_request(wire)
        assert buffers[0].obj is wire
        reply = handle_message(fig, content, buffers)
        assert reply is not None
        received = decode_frame(host.encode_frame(reply[0], reply[1] or []))
        assert received.message["type"] == "density_update"
        assert received.message["seq"] == 9
        assert [bytes(b) for b in received.buffers] == [bytes(b) for b in reply[1]]
        assert bytes(calls[-1]) == raw
    content, buffers = host.decode_request(json.dumps(density_request()))
    assert buffers == []
    assert handle_message(fig, content, buffers) is not None
    assert calls[-1] is None
    # A no-buffer binary envelope also remains valid.
    assert host.decode_request(encode_frame({"type": "unknown"}, [])) == ({"type": "unknown"}, [])


@pytest.mark.parametrize(
    ("content", "buffers"),
    [
        (density_request(tile_cache=True), []),
        (density_request(tile_cache=True), [inventory(), inventory()]),
        (density_request(tile_cache=False), [inventory()]),
        (density_request(), [inventory()]),
        (density_request(tile_cache=True), [b""]),
        (density_request(tile_cache=True), [b"XYDC"]),
        (density_request(tile_cache=True), [b"oops" + inventory()[4:]]),
        (
            density_request(tile_cache=True),
            [inventory()[:4] + struct.pack("<I", 2) + inventory()[8:]],
        ),
        (density_request(tile_cache=True), [inventory(1)[:-1]]),
        (density_request(tile_cache=True), [inventory(256) + b"x"]),
        (density_request(tile_cache=True), [inventory(257)]),
    ],
)
def test_density_control_fails_before_channel_dispatch(content, buffers):
    with pytest.raises(ValueError):
        host.decode_request(encode_frame(content, buffers))


def malformed_frames():
    good = encode_frame({"type": "unknown"}, [b"abc"])
    cases = [b"", good[:23], good[:-1], good + b"x", b"x" * 65537]
    for offset, fmt, value in (
        (0, "4s", b"nope"),
        (4, "B", 2),
        (5, "B", 1),
        (6, "H", 16),
        (8, "I", 16385),
        (12, "I", 17),
        (16, "Q", 2**63),
    ):
        bad = bytearray(good)
        struct.pack_into("<" + fmt, bad, offset, value)
        cases.append(bytes(bad))
    metadata_end = 24 + struct.unpack_from("<I", good, 8)[0]
    buffer_offset = (metadata_end + 7) // 8 * 8
    bad = bytearray(good)
    struct.pack_into("<Q", bad, buffer_offset, 65537)
    cases.append(bytes(bad))
    bad = bytearray(good)
    bad[-1] = 1  # nonzero attachment padding
    cases.append(bytes(bad))
    bad = bytearray(good)
    bad[metadata_end] = 1  # nonzero metadata padding
    cases.append(bytes(bad))
    return cases


@pytest.mark.parametrize("wire", malformed_frames(), ids=lambda b: f"frame-{len(b)}")
def test_invalid_frames_fail_closed(wire):
    with pytest.raises(ValueError):
        host.decode_request(wire)


@pytest.mark.parametrize("text", ["{", "[]", "null", '{"x":NaN}', '{"x":Infinity}', " " * 16385])
def test_invalid_json_fails_closed(text):
    with pytest.raises(ValueError):
        host.decode_request(text)


def run_node(script):
    if shutil.which("node") is None:
        pytest.skip("Node is required for the browser encoder proof")
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def test_page_comm_encoder_preserves_typedarray_subview_and_dataview_bytes():
    # Execute the actual page: the ChartView stub exposes only its comm. The
    # shipped production decoder consumes Python frames unchanged in Node.
    if not CLIENT.is_file():
        pytest.skip("build client once with node js/build.mjs")
    page = host.PAGE.split('<script type="module">', 1)[1].split("</script>", 1)[0]
    page = page.replace('import { ChartView, decodeFrame } from "/static/index.js";', "")
    initial = encode_frame({"type": "init", "spec": {}}, [b"initial"])
    response = encode_frame({"type": "reply", "label": "東京"}, [b"\x00\xff\x01"])
    script = f"""
import {{ decodeFrame }} from {CLIENT.as_uri()!r};
globalThis.window = {{}};
globalThis.document = {{getElementById: () => ({{}})}};
globalThis.location = {{host: "127.0.0.1"}};
let socket;
class WebSocket {{
  constructor() {{ socket = this; this.sent = []; this.closed = []; }}
  send(value) {{ this.sent.push(value); }}
  close(code) {{ this.closed.push(code); }}
}}
class ChartView {{ constructor(element, spec, buffers, comm) {{
  this.comm = comm; this.buffers = buffers;
}} }}
{page}
const from64 = s => Uint8Array.from(Buffer.from(s, "base64")).buffer;
const to64 = b => Buffer.from(b).toString("base64");
socket.onmessage({{data: from64({base64.b64encode(initial).decode()!r})}});
const backing = Uint8Array.from([99, 0, 1, 2, 3, 4, 5, 88]);
const words = new Uint16Array([0x1234, 0xabcd, 0x4321]);
const floats = new Float64Array([1.25, -2.5]);
const spans = [backing.subarray(2, 6), new DataView(backing.buffer, 1, 5),
  words.subarray(1, 2), floats, backing.buffer, new Uint8Array(0)];
window.__view.comm.send({{type: "test", label: "東京"}}, spans);
window.__view.comm.send({{type: "legacy", label: "東京"}});
const inv = from64({base64.b64encode(inventory()).decode()!r});
window.__view.comm.send({{type: "density_view", tile_cache: true}}, [new DataView(inv)]);
let delivered;
window.__view.comm.onMessage((content, buffers) => {{
  delivered = {{content, buffers: buffers.map(b => to64(byteSpan(b)))}};
}});
socket.onmessage({{data: from64({base64.b64encode(response).decode()!r})}});
const before = window.__arm.applicationBytes();
const invalid = [new ArrayBuffer(0), new ArrayBuffer(3105)];
let rejected = 0;
for (const b of invalid) {{
  try {{ window.__view.comm.send({{type: "density_view", tile_cache: true}}, [b]); }}
  catch (_) {{ rejected++; }}
}}
for (const buffers of [Array(17).fill(new Uint8Array(0)), [new Uint8Array(65537)],
    [new Uint8Array(33000), new Uint8Array(33000)]]) {{
  try {{ window.__view.comm.send({{type: "test"}}, buffers); }} catch (_) {{ rejected++; }}
}}
try {{ window.__view.comm.send({{type: "test", text: "x".repeat(16385)}}); }}
catch (_) {{ rejected++; }}
const snapshot = window.__arm.applicationBytes();
snapshot.to_host.json_bytes = -1; // snapshots cannot mutate the live counters
const malformed = [new ArrayBuffer(2)];
for (const field of ["metadata", "buffer", "total"]) {{
  const frame = from64({base64.b64encode(response).decode()!r});
  const d = new DataView(frame);
  if (field === "metadata") d.setUint32(8, 8 * 1024 * 1024 + 1, true);
  if (field === "total") d.setBigUint64(16, 2n ** 63n, true);
  if (field === "buffer") {{
    const off = Math.ceil((24 + d.getUint32(8, true)) / 8) * 8;
    d.setBigUint64(off, 256n * 1024n * 1024n + 1n, true);
  }}
  malformed.push(frame);
}}
for (const frame of malformed) {{
  try {{ socket.onmessage({{data: frame}}); }} catch (_) {{}}
}}
"""
    script += """
process.stdout.write(JSON.stringify({
  sent: socket.sent.map(b => typeof b === "string" ? b : to64(b)),
  expected: spans.map(b => to64(byteSpan(b))), delivered, rejected, before,
  after: window.__arm.applicationBytes(), closed: socket.closed,
}));
"""
    result = run_node(script)
    sent = result["sent"]
    content, buffers = host.decode_request(base64.b64decode(sent[0]))
    assert content == {"type": "test", "label": "東京"}
    assert base64.b64decode(sent[0]) == encode_frame(content, buffers)
    assert [bytes(b) for b in buffers] == [base64.b64decode(b) for b in result["expected"]]
    assert host.decode_request(sent[1]) == ({"type": "legacy", "label": "東京"}, [])
    assert bytes(host.decode_request(base64.b64decode(sent[2]))[1][0]) == inventory()
    assert result["delivered"] == {
        "content": {"type": "reply", "label": "東京"},
        "buffers": [base64.b64encode(b"\x00\xff\x01").decode()],
    }
    assert result["rejected"] == 6
    assert len(sent) == 3
    assert result["closed"] == [1007] * 4
    counts = host.ApplicationBytes()
    for wire in (base64.b64decode(sent[0]), sent[1], base64.b64decode(sent[2])):
        counts.record("to_host", wire)
    for wire in (initial, response):
        counts.record("from_host", wire)
    assert result["before"] == counts.snapshot()
    counts.record("from_host", b"xx")
    for _ in range(3):
        counts.record("from_host", response)
    assert result["after"] == counts.snapshot()


def test_real_small_websocket_roundtrip_and_rejection_before_dispatch(monkeypatch):
    async def scenario():
        fig = small_figure()
        accounting = host.ApplicationBytes()
        dispatched = []

        def dispatch(fig, content, buffers):
            dispatched.append((content, [bytes(b) for b in buffers]))
            return handle_message(fig, content, buffers)

        monkeypatch.setattr(host, "handle_message", dispatch)
        app = tornado.web.Application(
            [
                (
                    r"/ws",
                    host.WSHandler,
                    {"fig": fig, "spec": {}, "buffers": [b"init"], "accounting": accounting},
                )
            ],
            websocket_max_message_size=host.REQUEST_LIMITS.max_frame_bytes,
        )
        sockets = tornado.netutil.bind_sockets(0, "127.0.0.1")
        server = tornado.httpserver.HTTPServer(app)
        server.add_sockets(sockets)
        url = f"ws://127.0.0.1:{sockets[0].getsockname()[1]}/ws"
        client = None
        expected = host.ApplicationBytes()
        try:
            client = await tornado.websocket.websocket_connect(url)
            init = await client.read_message()
            expected.record("from_host", init)
            assert bytes(decode_frame(init).buffers[0]) == b"init"
            wire = encode_frame(density_request(tile_cache=True), [inventory()])
            await client.write_message(wire, binary=True)
            reply = await client.read_message()
            expected.record("to_host", wire)
            expected.record("from_host", reply)
            assert decode_frame(reply).message["type"] == "density_update"
            assert dispatched[-1][1] == [inventory()]
            legacy = json.dumps(
                {"type": "pick", "trace": 0, "index": 1, "label": "東京"}, ensure_ascii=False
            )
            await client.write_message(legacy)
            reply = await client.read_message()
            expected.record("to_host", legacy)
            expected.record("from_host", reply)
            assert decode_frame(reply).message["type"] == "pick_result"
            assert dispatched[-1][1] == []
            assert accounting.snapshot() == expected.snapshot()
            # A structurally valid outer frame with an oversized XYDC never
            # reaches channel.handle_message, even if Rust would ignore it.
            bad = encode_frame(density_request(tile_cache=True), [inventory(256) + b"x"])
            await client.write_message(bad, binary=True)
            assert await client.read_message() is None
            assert client.close_code == 1007
            expected.record("to_host", bad)
            assert accounting.snapshot() == expected.snapshot()
            assert len(dispatched) == 2
            client.close()
            client = await tornado.websocket.websocket_connect(url)
            expected.record("from_host", await client.read_message())
            await client.write_message(b"x" * 65537, binary=True)
            assert await client.read_message() is None
            assert client.close_code == 1009
            assert accounting.snapshot() == expected.snapshot()
            assert len(dispatched) == 2
        finally:
            if client is not None:
                client.close()
            server.stop()
            await server.close_all_connections()

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))
