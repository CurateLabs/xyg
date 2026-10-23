#!/usr/bin/env python3
"""Live XYG chart host for the UX benchmark: production client, production wire.

Runs as a child process. Serves one page whose JS imports `ChartView` from the
shipped ESM bundle and connects it to this process over a real WebSocket. The
bridge is `channel.handle_message` — the same dispatcher the widget and live
application hosts use — so deep zoom drills to exact rows exactly as a live chart does.
This is the interactive XYG chart; the standalone HTML export is not measured.

Wire framing: production XYBF v1 in both directions when buffers ride;
legacy no-buffer requests remain JSON text. Requests are bounded before dispatch.
Application-byte totals count UTF-8 JSON text and complete binary frames (including
framing/padding), not WebSocket headers, HTTP, TLS, TCP/IP or network-stack bytes.

Also serves:
    /transport_metrics  cumulative WebSocket application-message byte totals
    /static/*   the installed XYG client bundle
    /oracle     ?x0=&x1=&y0=&y1= -> {"count": rows in window}  (ground truth
                for the drill check, computed on the exact source arrays)

On startup prints one line:  META {"port": ..., "n": ..., "sentinels": [...]}
then serves until killed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import tornado.httpserver
import tornado.netutil
import tornado.web
import tornado.websocket

import xyg
from xyg.channel import FrameLimits, decode_frame, encode_frame, handle_message

SEED = 20260713
# Sentinels sit in the far Gaussian tail: guaranteed sparse (drillable), and
# they stretch the autoscaled home domain so their home-view pixels are
# interior, not clipped at the frame edge.
SENTINELS = [(4.6, 2.2), (4.9, 2.45), (4.75, 2.05), (5.0, 2.3), (4.55, 2.5)]


def make_data(n: int) -> tuple[np.ndarray, np.ndarray]:
    """The ceiling workload plus planted sentinel rows (replacing, not
    appending, so every arm still receives exactly n rows)."""
    rng = np.random.default_rng(SEED)
    x = rng.standard_normal(n, dtype=np.float32)
    y = rng.standard_normal(n, dtype=np.float32)
    y *= np.float32(1.2)
    y += x
    y *= np.float32(0.5)
    for i, (sx, sy) in enumerate(SENTINELS):
        x[i] = np.float32(sx)
        y[i] = np.float32(sy)
    return x, y


# Control ingress stays small even when first paint or replies are much larger.
REQUEST_LIMITS = FrameLimits(
    max_frame_bytes=64 * 1024,
    max_metadata_bytes=16 * 1024,
    max_buffers=16,
    max_buffer_bytes=64 * 1024,
)
XYDC_MAX_BYTES = 3104
APPLICATION_BYTE_LAYER = "websocket_application_messages"


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def decode_request(message: str | bytes) -> tuple[dict[str, Any], list[memoryview]]:
    """Validate the envelope and XYDC attachment shape before channel dispatch.

    Inventory semantics/keys remain Rust-owned; this checks only the bounded
    binary control document's identity, version and declared extent.
    """
    if isinstance(message, bytes):
        frame = decode_frame(message, limits=REQUEST_LIMITS)
        content, buffers = frame.message, list(frame.buffers)
    else:
        if len(message.encode("utf-8")) > REQUEST_LIMITS.max_metadata_bytes:
            raise ValueError("JSON control exceeds metadata limit")
        content = json.loads(message, parse_constant=_reject_constant)
        buffers = []
    if not isinstance(content, dict):
        raise ValueError("control must be a JSON object")
    if content.get("type") == "density_view":
        if content.get("tile_cache") is not None:
            if content["tile_cache"] is not True or len(buffers) != 1:
                raise ValueError("tile_cache requires one XYDC attachment")
            raw = buffers[0]
            if not 32 <= len(raw) <= XYDC_MAX_BYTES or raw[:4] != b"XYDC":
                raise ValueError("invalid bounded XYDC attachment")
            version = struct.unpack_from("<I", raw, 4)[0]
            count = struct.unpack_from("<I", raw, 28)[0]
            if version != 1 or count > 256 or len(raw) != 32 + count * 12:
                raise ValueError("invalid XYDC version or extent")
        elif buffers:
            raise ValueError("density_view attachments require tile_cache: true")
    return content, buffers


@dataclass
class ApplicationBytes:
    """Cumulative socket-message bodies at the application layer, both directions."""

    to_host: dict[str, int] = field(
        default_factory=lambda: {"json_bytes": 0, "binary_frame_bytes": 0}
    )
    from_host: dict[str, int] = field(
        default_factory=lambda: {"json_bytes": 0, "binary_frame_bytes": 0}
    )

    def record(self, direction: str, message: str | bytes) -> None:
        counts = getattr(self, direction)
        key = "json_bytes" if isinstance(message, str) else "binary_frame_bytes"
        counts[key] += len(message.encode("utf-8")) if isinstance(message, str) else len(message)

    def snapshot(self) -> dict[str, Any]:
        result: dict[str, Any] = {"layer": APPLICATION_BYTE_LAYER}
        for direction in ("to_host", "from_host"):
            counts = dict(getattr(self, direction))
            result[direction] = {**counts, "total_bytes": sum(counts.values())}
        result["total_bytes"] = (
            result["to_host"]["total_bytes"] + result["from_host"]["total_bytes"]
        )
        return result


# Executed unchanged by the page and the bounded Node transport regression tests.
TRANSPORT_JS = """
const REQUEST_LIMITS = {maxFrameBytes: 65536, maxMetadataBytes: 16384,
  maxBuffers: 16, maxBufferBytes: 65536};
const align8 = (n) => Math.ceil(n / 8) * 8;
const byteSpan = (b) => {
  if (b instanceof ArrayBuffer) return new Uint8Array(b);
  if (ArrayBuffer.isView(b)) return new Uint8Array(b.buffer, b.byteOffset, b.byteLength);
  throw new TypeError("attachment must be an ArrayBuffer or view");
};
function validateDensityControl(msg, buffers) {
  if (msg.type !== "density_view") return;
  if (msg.tile_cache != null) {
    if (msg.tile_cache !== true || buffers.length !== 1)
      throw new RangeError("tile_cache requires one XYDC attachment");
    const b = byteSpan(buffers[0]);
    if (b.byteLength < 32 || b.byteLength > 3104 ||
        b[0] !== 88 || b[1] !== 89 || b[2] !== 68 || b[3] !== 67)
      throw new RangeError("invalid bounded XYDC attachment");
    const d = new DataView(b.buffer, b.byteOffset, b.byteLength);
    const count = d.getUint32(28, true);
    if (d.getUint32(4, true) !== 1 || count > 256 || b.byteLength !== 32 + count * 12)
      throw new RangeError("invalid XYDC version or extent");
  } else if (buffers.length) {
    throw new RangeError("density_view attachments require tile_cache: true");
  }
}
function encodeFrame(content, buffers = []) {
  if (!content || typeof content !== "object" || Array.isArray(content))
    throw new TypeError("frame metadata must be an object");
  if (buffers.length > REQUEST_LIMITS.maxBuffers) throw new RangeError("too many attachments");
  validateDensityControl(content, buffers);
  const metadata = new TextEncoder().encode(JSON.stringify(content));
  if (metadata.byteLength > REQUEST_LIMITS.maxMetadataBytes)
    throw new RangeError("metadata exceeds limit");
  const spans = buffers.map(byteSpan);
  let total = align8(24 + metadata.byteLength);
  for (const b of spans) {
    if (b.byteLength > REQUEST_LIMITS.maxBufferBytes) throw new RangeError("attachment exceeds limit");
    total = align8(total + 8 + b.byteLength);
    if (total > REQUEST_LIMITS.maxFrameBytes) throw new RangeError("frame exceeds limit");
  }
  const result = new Uint8Array(total);
  const view = new DataView(result.buffer);
  result.set([88, 89, 66, 70, 1, 0]); // XYBF v1, flags=0
  view.setUint16(6, 24, true);
  view.setUint32(8, metadata.byteLength, true);
  view.setUint32(12, spans.length, true);
  view.setBigUint64(16, BigInt(total), true);
  result.set(metadata, 24);
  let off = align8(24 + metadata.byteLength);
  for (const b of spans) {
    view.setBigUint64(off, BigInt(b.byteLength), true);
    result.set(b, off + 8);
    off = align8(off + 8 + b.byteLength);
  }
  return result.buffer;
}
const applicationBytes = {
  layer: "websocket_application_messages",
  to_host: {json_bytes: 0, binary_frame_bytes: 0},
  from_host: {json_bytes: 0, binary_frame_bytes: 0},
};
function recordBytes(direction, message) {
  const key = typeof message === "string" ? "json_bytes" : "binary_frame_bytes";
  applicationBytes[direction][key] += typeof message === "string"
    ? new TextEncoder().encode(message).byteLength : message.byteLength;
}
function applicationBytesSnapshot() {
  const snapshot = {layer: applicationBytes.layer, total_bytes: 0};
  for (const direction of ["to_host", "from_host"]) {
    const counts = applicationBytes[direction];
    snapshot[direction] = {...counts, total_bytes: counts.json_bytes + counts.binary_frame_bytes};
    snapshot.total_bytes += snapshot[direction].total_bytes;
  }
  return snapshot;
}
function sendMessage(socket, msg, buffers = []) {
  validateDensityControl(msg, buffers);
  const message = buffers.length ? encodeFrame(msg, buffers) : JSON.stringify(msg);
  if (typeof message === "string" &&
      new TextEncoder().encode(message).byteLength > REQUEST_LIMITS.maxMetadataBytes)
    throw new RangeError("JSON control exceeds metadata limit");
  socket.send(message);
  recordBytes("to_host", message);
}
"""

PAGE = (
    """<!doctype html>
<meta charset="utf-8">
<title>xy live</title>
<style>html,body{margin:0;background:#fff}#chart{width:900px;height:420px}</style>
<div id="chart"></div>
<script type="module">
import { ChartView, decodeFrame } from "/static/index.js";
"""
    + TRANSPORT_JS
    + """

const ws = new WebSocket(`ws://${location.host}/ws`);
ws.binaryType = "arraybuffer";
const handlers = [];
ws.onmessage = (ev) => {
  recordBytes("from_host", ev.data);
  let content, buffers;
  try {
    if (typeof ev.data === "string") {
      content = JSON.parse(ev.data);
      buffers = [];
    } else {
      ({ message: content, buffers } = decodeFrame(ev.data));
    }
    if (!content || typeof content !== "object" || Array.isArray(content))
      throw new TypeError("message metadata must be an object");
  } catch (error) {
    ws.close(1007, "invalid application frame");
    throw error;
  }
  if (content.type === "init") {
    const comm = {
      send: (msg, buffers = []) => sendMessage(ws, msg, buffers),
      wantsViewChange: () => false,
      onMessage: (cb) => { handlers.push(cb); return () => {}; },
    };
    window.__view = new ChartView(
      document.getElementById("chart"), content.spec, buffers, comm);
    window.__wireReady = true;
  } else {
    for (const cb of handlers) cb(content, buffers);
  }
};

window.__arm = {
  applicationBytes: applicationBytesSnapshot,
  ready: () => !!window.__view && !!window.__view.gl,
  domain: () => {
    const v = window.__view && window.__view.view;
    return v ? { x0: v.x0, x1: v.x1, y0: v.y0, y1: v.y1 } : null;
  },
  project: (x, y) => {
    const view = window.__view;
    const v = view.view;
    const r = view.canvas.getBoundingClientRect();
    if (x < v.x0 || x > v.x1 || y < v.y0 || y > v.y1) return null;
    return {
      px: ((x - v.x0) / (v.x1 - v.x0)) * r.width,
      py: (1 - (y - v.y0) / (v.y1 - v.y0)) * r.height,
    };
  },
  readbacks: () => {
    const view = window.__view;
    view._drawNow();
    const gl = view.gl;
    gl.finish();
    const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
    const data = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, data);
    const r = view.canvas.getBoundingClientRect();
    return [{ data, w, h, topDown: false, cssW: r.width, cssH: r.height }];
  },
  zoomInput: (fx, fy, dir) => {
    const view = window.__view;
    const r = view.canvas.getBoundingClientRect();
    view.canvas.dispatchEvent(new WheelEvent("wheel", {
      bubbles: true, cancelable: true,
      clientX: r.left + r.width * fx,
      clientY: r.top + r.height * fy,
      deltaY: dir > 0 ? -120 : 120,
      deltaMode: 0,
    }));
  },
};
</script>
"""
)


class WSHandler(tornado.websocket.WebSocketHandler):
    def initialize(self, fig, spec, buffers, accounting: ApplicationBytes) -> None:
        self.fig, self.spec, self.buffers = fig, spec, buffers
        self.accounting = accounting

    def send_frame(self, content, buffers) -> None:
        frame = encode_frame(content, buffers or [])
        self.write_message(frame, binary=True)
        self.accounting.record("from_host", frame)

    def open(self) -> None:
        self.send_frame({"type": "init", "spec": self.spec}, self.buffers)

    def on_message(self, message: str | bytes) -> None:
        # Count delivered application bytes, including rejected control bodies.
        self.accounting.record("to_host", message)
        try:
            content, buffers = decode_request(message)
        except (ValueError, RecursionError):
            self.close(1007, "invalid application frame")
            return
        reply = handle_message(self.fig, content, buffers)
        if reply is not None:
            self.send_frame(*reply)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--density", choices=("auto", "off"), default="auto")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    x, y = make_data(args.n)
    mark = xyg.scatter(x=x, y=y, density=False) if args.density == "off" else xyg.scatter(x=x, y=y)
    fig = xyg.scatter_chart(mark, width=900, height=420).figure()
    spec, bufs = fig.build_payload_split()

    static_dir = Path(xyg.__file__).resolve().parent / "static"

    class PageHandler(tornado.web.RequestHandler):
        def get(self) -> None:
            self.set_header("Content-Type", "text/html")
            self.write(PAGE)

    class OracleHandler(tornado.web.RequestHandler):
        def get(self) -> None:
            q = {k: float(self.get_argument(k)) for k in ("x0", "x1", "y0", "y1")}
            inside = (x >= q["x0"]) & (x <= q["x1"]) & (y >= q["y0"]) & (y <= q["y1"])
            self.write({"count": int(np.count_nonzero(inside))})

    accounting = ApplicationBytes()

    class MetricsHandler(tornado.web.RequestHandler):
        def get(self) -> None:
            self.write(accounting.snapshot())

    async def serve() -> None:
        # The server must be created inside the running loop so its handlers
        # are scheduled on it — created outside, the socket binds but accepted
        # connections are never serviced.
        app = tornado.web.Application(
            [
                (r"/", PageHandler),
                (
                    r"/ws",
                    WSHandler,
                    {"fig": fig, "spec": spec, "buffers": bufs, "accounting": accounting},
                ),
                (r"/transport_metrics", MetricsHandler),
                (r"/oracle", OracleHandler),
                (
                    r"/static/(.*)",
                    tornado.web.StaticFileHandler,
                    {"path": str(static_dir)},
                ),
            ],
            websocket_max_message_size=REQUEST_LIMITS.max_frame_bytes,
        )
        sockets = tornado.netutil.bind_sockets(args.port, "127.0.0.1")
        server = tornado.httpserver.HTTPServer(app)
        server.add_sockets(sockets)
        port = sockets[0].getsockname()[1]
        print(
            "META "
            + json.dumps(
                {
                    "port": port,
                    "n": args.n,
                    "sentinels": [list(s) for s in SENTINELS],
                    "mode": "density" if fig.traces[0].use_density() else "direct",
                }
            ),
            flush=True,
        )
        await asyncio.Event().wait()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
