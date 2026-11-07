"""Typed framing only for Rust's exact temporal Scene compiler."""

from __future__ import annotations

import base64
import ctypes
import html as _html
import struct

from . import _native, export

MAX_BYTES = 64 * 1024 * 1024
KINDS = {"event": 0, "interval": 1, "gantt": 2, "line": 3, "bar": 4, "scatter": 5}


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
):
    lo, hi = (integer(v) for v in domain)
    zone = timezone.encode("utf-8")
    heading = (title or "").encode("utf-8")
    count = len(rows)
    if 128 + len(zone) + len(heading) + count * 40 > MAX_BYTES:
        raise ValueError("temporal request exceeds framing budget")
    out = bytearray(128)
    struct.pack_into(
        "<4sIII2d3qIII",
        out,
        0,
        b"XYTM",
        1,
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
window.temporalView=xy.hydrateWasmPainter(document.getElementById('chart'), {{painter:b.buffer,memoryBytes:0}});
</script></body></html>'''
    if path is not None:
        export._atomic_write_text(path, document)
    return document
