"""Bounded local XYGC snapshot rendering proof; no larger-than-RAM claim."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import resource
import struct
import sys
import time
from pathlib import Path

from PIL import Image

from xyg import ChunkedColumns, scatter, scatter_chart
from xyg._chromium import ChromiumSession


def run(output: Path, chromium: str) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    rows = [(float(i), float((i * 7) % 31)) for i in range(512)]
    path = output / "source.xygc"
    chunks = [rows[i : i + 64] for i in range(0, len(rows), 64)]
    data_offset = 64 + len(chunks) * 48
    overview = list(range(0, 512, 16)) + [511]
    header = bytearray(64)
    struct.pack_into(
        "<4sIQIIQQI",
        header,
        0,
        b"XYGC",
        2,
        512,
        64,
        len(chunks),
        data_offset,
        data_offset + 512 * 16,
        len(overview),
    )
    with path.open("wb") as f:
        f.write(header)
        for i, chunk in enumerate(chunks):
            xs, ys = zip(*chunk, strict=True)
            f.write(struct.pack("<QII4d", i * 64, 64, 0, min(xs), max(xs), min(ys), max(ys)))
        for x, y in rows:
            f.write(struct.pack("<2d", x, y))
        for i in overview:
            f.write(struct.pack("<Q2d", i, *rows[i]))
    report = {
        "scope": "bounded programmatic Python snapshot navigation; native Rust selection",
        "python": sys.version,
        "platform": platform.platform(),
        "artifact_bytes": path.stat().st_size,
        "requests": [],
    }
    with ChunkedColumns(path) as source, ChromiumSession(chromium, sandbox=False) as browser:
        for generation, (name, bounds) in enumerate(
            [
                ("overview", None),
                ("viewport", (80, 240)),
                ("pan", (150, 310)),
                ("deepzoom", (160, 170)),
            ]
        ):
            start = time.perf_counter()
            chart = source.chart(bounds, budget_bytes=8192, page_bytes=4096, generation=generation)
            ids = (
                overview
                if bounds is None
                else [i for i, (x, _) in enumerate(rows) if bounds[0] <= x <= bounds[1]]
            )
            assert list(chart.source_row_ids) == ids
            oracle = scatter_chart(scatter([rows[i][0] for i in ids], [rows[i][1] for i in ids]))
            html = chart.to_html()
            (output / f"{name}.html").write_text(html)
            actual = browser.render_image(html, 900, 420, scale=1)
            expected = browser.render_image(oracle.to_html(), 900, 420, scale=1)
            actual_pixels = Image.open(io.BytesIO(actual)).convert("RGB")
            expected_pixels = Image.open(io.BytesIO(expected)).convert("RGB")
            assert actual_pixels.tobytes() == expected_pixels.tobytes(), name
            assert len(set(actual_pixels.getdata())) > 16, "blank screenshot"
            (output / f"{name}.png").write_bytes(actual)
            (output / f"{name}-oracle.png").write_bytes(expected)
            report["requests"].append(
                {
                    "name": name,
                    "range": bounds,
                    "row_ids": ids,
                    "provenance": chart.source_provenance,
                    "elapsed_including_two_renders_s": time.perf_counter() - start,
                    "pixel_sha256": hashlib.sha256(actual_pixels.tobytes()).hexdigest(),
                    "exact_pixel_match": True,
                }
            )
    report["host_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["rss_scope"] = (
        "Python process only; includes full bounded oracle fixture; excludes browser/GPU"
    )
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--chromium", required=True)
    args = parser.parse_args()
    run(args.output, args.chromium)
