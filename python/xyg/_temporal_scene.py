"""Typed framing only for Rust's exact temporal Scene compiler."""

from __future__ import annotations

import base64
import ctypes
import html as _html
import struct
from contextlib import suppress

from . import _native, export

MAX_BYTES = 64 * 1024 * 1024
KINDS = {"event": 0, "interval": 1, "gantt": 2, "line": 3, "bar": 4, "scatter": 5}


def _row_capacity(timezone, title):
    size = 128 + len(timezone.encode("utf-8")) + len((title or "").encode("utf-8"))
    if size > MAX_BYTES:
        raise ValueError("temporal request exceeds framing budget")
    return (MAX_BYTES - size) // 40


def snapshot_rows(rows, timezone, title):
    """Bound the wire envelope before retaining caller-owned source rows."""
    capacity = _row_capacity(timezone, title)
    try:
        count = len(rows)
    except TypeError:
        count = None
    if count is not None and count > capacity:
        raise ValueError("temporal request exceeds framing budget")
    snapshot = []
    for row in rows:
        # Also bound unsized iterables and sources with an understated length.
        if len(snapshot) >= capacity:
            raise ValueError("temporal request exceeds framing budget")
        snapshot.append(tuple(row))
    return tuple(snapshot)


def integer(value, bits=64, signed=True):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("temporal times and identities require exact integers")
    low = -(1 << (bits - 1)) if signed else 0
    if not low <= value < (1 << (bits - int(signed))):
        raise ValueError("integer outside temporal wire width")
    return value


def request(
    kind,
    rows,
    *,
    domain,
    timezone,
    precision,
    title,
    width,
    height,
    cursor,
    color,
    stroke,
    stroke_width,
    dense=False,
    operation=0,
    cell=0,
    offset=0,
    limit=0,
):
    lo, hi = (integer(v) for v in domain)
    zone = timezone.encode("utf-8")
    heading = (title or "").encode("utf-8")
    count = len(rows)
    if count > _row_capacity(timezone, title):
        raise ValueError("temporal request exceeds framing budget")
    out = bytearray(128)
    struct.pack_into(
        "<4sIII2d3qIII",
        out,
        0,
        b"XYTM",
        2 if dense else 1,
        KINDS[kind],
        count,
        width,
        height,
        lo,
        hi,
        integer(cursor),
        len(zone),
        len(heading),
        precision,
    )
    if dense:
        struct.pack_into("<4I", out, 88, operation, cell, offset, limit)
    out[72:76] = bytes(color)
    out[76:80] = bytes(stroke)
    if len(color) != 4 or len(stroke) != 4:
        raise ValueError("paint requires four RGBA8 bytes")
    struct.pack_into("<d", out, 80, stroke_width)
    out.extend(zone)
    out.extend(heading)
    for start, end, value, row_id in rows:
        out.extend(
            struct.pack(
                "<qqdQBB6x",
                0 if start is None else integer(start),
                0 if end is None else integer(end),
                value,
                integer(row_id, signed=False),
                start is not None,
                end is not None,
            )
        )
    return bytes(out)


def compile_request(packet, budget):
    function = _native._lib.xyg_temporal_scene_compile
    source = ctypes.create_string_buffer(packet)
    length = ctypes.c_size_t()
    status = function(source, len(packet), budget, None, 0, ctypes.byref(length))
    if status:
        raise ValueError(f"temporal Scene rejected ({status})")
    out = (ctypes.c_uint8 * length.value)()
    status = function(source, len(packet), budget, out, length.value, ctypes.byref(length))
    if status:
        raise ValueError(f"temporal Scene rejected ({status})")
    return bytes(out)


def html(figure, path=None, *, custom_css=None):
    css = export._custom_css_block(custom_css)
    script = export._javascript_for_inline_script(export._bundled_js("standalone"))
    csp = export._standalone_csp(wasm_ticks=False, density=False)
    title = _html.escape(figure.title or "xy")
    scene = figure.to_scene()
    painter = base64.b64encode(_native.scene_browser_painter(scene)).decode("ascii")
    # Existing painter hydration and ChartView; no temporal geometry in the host.
    document = f'''<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<title>{title}</title>{css}</head><body><div id="chart"></div><script>{script}</script><script>
const b=Uint8Array.from(atob("{painter}"), c=>c.charCodeAt(0));
const {{hydrateWasmPainter}}=window.xy;
window.temporalView=hydrateWasmPainter(document.getElementById('chart'), {{painter:b.buffer,memoryBytes:0}});
</script></body></html>'''
    if path is not None:
        export._atomic_write_text(path, document)
    return document


class TemporalOperation:
    """One revision of a retained Rust temporal session; steps and cancel are native."""

    def __init__(self, session, revision):
        self.session = session
        self.revision = revision
        self.ready = False

    def step(self):
        ack = self.session._command(2, self.revision)
        self.ready = struct.unpack_from("<I", ack, 8)[0] == 1
        return ack

    def result(self):
        while not self.ready:
            self.step()
        return self.session._command(3, self.revision)

    async def result_async(self):
        """Yield between Rust steps and cancel this claim if its waiter is cancelled."""
        import asyncio

        try:
            while not self.ready:
                self.step()
                await asyncio.sleep(0)
            return self.session._command(3, self.revision)
        except BaseException:
            with suppress(Exception):
                self.cancel()
            raise

    def cancel(self):
        return self.session._command(4, self.revision)

    def close(self):
        self.cancel()


class TemporalSession:
    """Retain accepted Rust state until a complete replacement is published."""

    def __init__(self, budget=MAX_BYTES):
        self.budget = budget
        self.handle = 0
        self.revision = 0
        ack = self._command(0, 0)
        self.handle = struct.unpack_from("<Q", ack, 16)[0]

    def _command(self, op, revision, source=b""):
        if op and not self.handle:
            raise ValueError("temporal session disposed")
        header = bytearray(64)
        struct.pack_into(
            "<4sIIIQQ",
            header,
            0,
            b"XYTJ",
            1,
            op,
            0,
            0 if op == 6 else self.handle,
            0 if op == 5 else revision,
        )
        return compile_request(bytes(header) + source, self.budget)

    def preview(self, packet):
        size = 128 + sum(struct.unpack_from("<2I", packet, 56))
        return self._command(6, 0, packet[:size])

    def begin(self, packet):
        self.preview(packet)
        if self.revision >= (1 << 64) - 1:
            raise OverflowError("temporal revision exhausted")
        self.revision += 1
        self._command(1, self.revision, packet)
        return TemporalOperation(self, self.revision)

    def cancel(self):
        if self.handle and self.revision:
            return self._command(4, self.revision)

    def accepted(self, revision):
        return self._command(3, revision)

    def close(self):
        if self.handle:
            try:
                self._command(5, self.revision)
            finally:
                self.handle = 0

    def __del__(self):
        with suppress(Exception):
            self.close()
