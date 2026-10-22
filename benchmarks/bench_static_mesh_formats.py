"""Bounded public mesh export/admission evidence for #1042 (dossier §28).

Run with ``uv run --with matplotlib==3.11.0 python
benchmarks/bench_static_mesh_formats.py --matplotlib --output <report.json>``.
Times include public export compilation and encoding, but exclude chart setup.
This is local diagnostic evidence, not a replacement or relaxation of a gate.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import subprocess
import time
from pathlib import Path

import numpy as np

import xyg
from xyg import _native
from xyg._scene_v3 import scene_export_support_reason
from xyg._static_document import UnsupportedStaticExport


def columns(n: int, overlap: bool) -> tuple[np.ndarray, ...]:
    zeros = np.zeros(n)
    if overlap:
        return zeros, zeros, zeros + 1, zeros, zeros, zeros + 1
    angle = np.arange(n + 1) * (2 * np.pi / n)
    return (
        zeros,
        zeros,
        np.cos(angle[:-1]),
        np.sin(angle[:-1]),
        np.cos(angle[1:]),
        np.sin(angle[1:]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matplotlib", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    report = {
        "issue": 1042,
        "environment": {
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "cpu_model": next(
                (
                    line.split(":", 1)[1].strip()
                    for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")
                ),
                platform.machine(),
            )
            if Path("/proc/cpuinfo").exists()
            else platform.processor(),
            "native_library_sha256": hashlib.sha256(
                Path(_native._lib._name).read_bytes()
            ).hexdigest(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "native_abi": _native.ABI_VERSION,
            "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        },
        "contract": {
            "viewport_css_px": [640, 420],
            "png_scale": 1,
            "vector_face_ceiling": 50_000,
            "raster_work_plots": 64,
            "raster_reason": "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD",
            "timing": "public export; construction excluded; no timing gate",
        },
        "rows": [],
    }
    if args.matplotlib:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        from matplotlib.collections import PolyCollection

        report["environment"]["matplotlib"] = matplotlib.__version__
    for name, n, overlap in [
        ("fan", 1_024, False),
        ("fan", 5_000, False),
        ("fan", 50_000, False),
        ("fan", 50_001, False),
        ("overlap", 1_100, True),
    ]:
        x0, y0, x1, y1, x2, y2 = columns(n, overlap)
        figure = xyg.chart(
            xyg.triangle_mesh(x0=x0, y0=y0, x1=x1, y1=y1, x2=x2, y2=y2, color="#1e78c8"),
            xyg.x_axis(domain=(-1, 1)),
            xyg.y_axis(domain=(-1, 1)),
            width=640,
            height=420,
        ).figure()
        for format in ("svg", "pdf", "png"):
            reason = scene_export_support_reason(figure, format=format)
            elapsed = []
            encoded = b""
            for _ in range(args.repeats):
                started = time.perf_counter()
                try:
                    encoded = figure.to_image(format, scale=1)
                    assert reason is None
                except UnsupportedStaticExport as exc:
                    assert str(exc) == reason == "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"
                elapsed.append(time.perf_counter() - started)
            report["rows"].append(
                {
                    "engine": "xyg",
                    "fixture": name,
                    "faces": n,
                    "format": format,
                    "seconds": elapsed,
                    "reason": reason,
                    "bytes": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest() if encoded else None,
                }
            )
        if args.matplotlib and n != 50_001:
            mpl_figure, ax = plt.subplots(figsize=(6.4, 4.2), dpi=100)
            vertices = np.stack(
                [np.column_stack([x0, y0]), np.column_stack([x1, y1]), np.column_stack([x2, y2])],
                axis=1,
            )
            ax.add_collection(PolyCollection(vertices, facecolors="#1e78c8", edgecolors="none"))
            ax.set(xlim=(-1, 1), ylim=(-1, 1))
            for format in ("svg", "pdf", "png"):
                elapsed = []
                for _ in range(args.repeats):
                    output = io.BytesIO()
                    started = time.perf_counter()
                    mpl_figure.savefig(output, format=format, dpi=100)
                    elapsed.append(time.perf_counter() - started)
                report["rows"].append(
                    {
                        "engine": "matplotlib",
                        "fixture": name,
                        "faces": n,
                        "format": format,
                        "seconds": elapsed,
                        "reason": None,
                        "bytes": len(output.getvalue()),
                    }
                )
            plt.close(mpl_figure)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
