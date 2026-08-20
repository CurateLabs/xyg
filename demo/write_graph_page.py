"""Shared HTML page writer for the force-graph demos."""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = (ROOT / "graph_page_template.html").read_text(encoding="utf-8")
CLIENT_JS = (ROOT.parent / "python" / "xyg" / "static" / "standalone.js").read_text(
    encoding="utf-8"
)


def write_graph_page(
    *,
    path: Path,
    title: str,
    host: str,
    spec: dict,
    blob: bytes,
    meta: dict,
) -> None:
    # Escape </script> breakouts in the inlined client / JSON.
    client = CLIENT_JS.replace("</", "<\\/")
    spec_js = json.dumps(spec, separators=(",", ":")).replace("<", "\\u003c")
    meta_js = json.dumps(meta, separators=(",", ":")).replace("<", "\\u003c")
    html = (
        TEMPLATE.replace("__TITLE__", title)
        .replace("__HOST__", host)
        .replace("__CLIENT_JS__", client)
        .replace("__SPEC__", spec_js)
        .replace("__META__", meta_js)
        .replace("__B64__", base64.b64encode(blob).decode("ascii"))
    )
    path.write_text(html, encoding="utf-8")
