"""Shared browser probes for xy benchmark pages.

The regular TTFR helper in ``_browser.py`` answers "when did a page first
paint?". These helpers are for richer xy-specific pages that need the
``ChartView`` object, WebGL readback, and structured JSON results from
headless Chromium.
"""

from __future__ import annotations

import html as html_lib
import http.server
import json
import re
import subprocess
import tempfile
import threading
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import quote

from _browser import chromium_gl_flags, find_chromium
from xyg import export as _xy_export


def json_bytes(obj: Any) -> int:
    return len(json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8"))


def inline_json(obj: Any) -> str:
    """JSON safe enough for generated benchmark data inside a script tag."""
    return json.dumps(obj, separators=(",", ":"), default=str).replace("</", "<\\/")


def _standalone_js() -> str:
    import xyg

    path = Path(xyg.__file__).resolve().parent / "static" / "standalone.js"
    return path.read_text(encoding="utf-8")


def chart_payload(id: str, spec: dict[str, Any], blob: bytes) -> dict[str, Any]:
    # Chunked base64 (same §29 fallback as the product export): no single JS
    # string near the V8 length cliff, so probe pages scale to 25M+ points.
    return {
        "id": id,
        "spec": spec,
        "chunks": _xy_export._base64_chunks(blob),
        "n": len(blob),
    }


def page_for_charts(
    charts: list[dict[str, Any]],
    probe_js: str,
    *,
    title: str,
    body_css: str = "",
) -> str:
    payloads = inline_json(charts)
    css = body_css or (
        "html,body{margin:0;background:#fff;font-family:system-ui,sans-serif;}#root{padding:0;}"
    )
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html_lib.escape(title)}</title>
<style>{css}</style>
</head>
<body>
<div id="root"></div>
<script>{_standalone_js()}</script>
<script>
const XY_CHARTS = {payloads};
{_xy_export._DECODE_B64_JS}
function xyBytesFromPayload(payload) {{
  return xyDecodeB64(payload.chunks, payload.n);
}}
function xyReport(marker, payload) {{
  document.body.setAttribute("data-xy-benchmark-probe", "ok");
  document.title = marker + " " + JSON.stringify(payload);
}}
function xyFail(marker, err) {{
  const msg = (err && (err.stack || err.message)) ? (err.stack || err.message) : String(err);
  document.body.setAttribute("data-xy-benchmark-probe-error", msg.slice(0, 480));
  document.title = "XY_ERROR " + marker + " " + msg.slice(0, 480);
}}
function xyRaf() {{
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}}
function xyPercentile(values, p) {{
  if (!values.length) return null;
  const sorted = values.slice().sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[idx];
}}
function xyStats(values) {{
  return {{
    min_ms: xyPercentile(values, 0),
    median_ms: xyPercentile(values, 50),
    p95_ms: xyPercentile(values, 95),
    p99_ms: xyPercentile(values, 99),
    max_ms: xyPercentile(values, 100),
    reps: values.length,
  }};
}}
function xyNonblankPixels(view) {{
  const gl = view.gl;
  view._drawNow();
  const w = Math.max(1, Math.min(64, view.canvas.width));
  const h = Math.max(1, Math.min(64, view.canvas.height));
  const x = Math.max(0, Math.floor((view.canvas.width - w) / 2));
  const y = Math.max(0, Math.floor((view.canvas.height - h) / 2));
  const pixels = new Uint8Array(w * h * 4);
  gl.readPixels(x, y, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
  let count = 0;
  for (let i = 0; i < pixels.length; i += 4) {{
    if (pixels[i] || pixels[i + 1] || pixels[i + 2] || pixels[i + 3]) count++;
  }}
  return count;
}}
{probe_js}
</script>
</body>
</html>"""


def run_json_probe(
    html: str,
    *,
    marker: str,
    chromium: str | None,
    virtual_time_ms: int | None = 15_000,
    timeout_s: int = 180,
    hosted: bool = False,
    wasm_ticks: bool = False,
) -> dict[str, Any]:
    exe = find_chromium(chromium)
    if not exe:
        return {"status": "skipped(no chromium)"}

    with tempfile.TemporaryDirectory() as td:
        page = Path(td) / "probe.html"
        page.write_text(html, encoding="utf-8")
        server: http.server.ThreadingHTTPServer | None = None
        thread: threading.Thread | None = None
        try:
            if wasm_ticks:
                _xy_export.copy_wasm_tick_assets(page.parent)
                hosted = True
            if hosted:

                class QuietHandler(http.server.SimpleHTTPRequestHandler):
                    def log_message(self, format: str, *args: object) -> None:
                        del format, args

                    def end_headers(self) -> None:
                        self.send_header(
                            "Content-Security-Policy",
                            "default-src 'none'; script-src 'unsafe-inline' "
                            "'wasm-unsafe-eval'; style-src 'unsafe-inline'; "
                            "worker-src 'self'; connect-src 'self'; object-src 'none'; "
                            "base-uri 'none'",
                        )
                        self.send_header("Cache-Control", "no-store")
                        super().end_headers()

                handler = partial(QuietHandler, directory=str(page.parent))
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                url = f"http://127.0.0.1:{server.server_port}/{quote(page.name)}"
                command = [
                    "node",
                    str(Path(__file__).resolve().parents[1] / "scripts" / "browser_probe_dump.mjs"),
                    exe,
                    url,
                    "data-xy-benchmark-probe",
                    f"--xyg-probe-timeout-ms={timeout_s * 1000}",
                    *chromium_gl_flags(),
                    "--hide-scrollbars",
                    "--enable-precise-memory-info",
                    "--window-size=900,420",
                ]
            else:
                command = [
                    exe,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    *chromium_gl_flags(),
                    "--hide-scrollbars",
                    "--enable-precise-memory-info",
                ]
                if virtual_time_ms is not None:
                    command.append(f"--virtual-time-budget={virtual_time_ms}")
                command.extend(["--dump-dom", page.as_uri()])
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_s + (15 if hosted else 0),
            )
        except subprocess.TimeoutExpired:
            return {"status": "failed(timeout)"}
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=5)

    match = re.search(r"<title>(.*?)</title>", completed.stdout, flags=re.IGNORECASE | re.S)
    title_text = html_lib.unescape(match.group(1).strip()) if match else ""
    prefix = f"{marker} "
    if title_text.startswith(prefix):
        try:
            payload = json.loads(title_text[len(prefix) :])
        except json.JSONDecodeError as exc:
            return {"status": f"failed(bad probe JSON: {exc})"}
        payload.setdefault("status", "ok")
        return payload
    if title_text.startswith("XY_ERROR "):
        return {"status": f"failed({title_text[:220]})"}
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout).strip().splitlines()
        return {"status": f"failed(chromium exit {completed.returncode}: {err[:1]})"}
    return {"status": "failed(no probe title)"}
