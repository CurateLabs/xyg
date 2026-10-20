#!/usr/bin/env python3
"""Static hexbin export evidence: XYG native Scene route vs Matplotlib (#887).

The cloud is the hexbin_demo.py gallery witness (100,000 rows,
seed 19680801, ``bins="log"``). Each (engine, gridsize, format) runs in a fresh
subprocess so peak RSS is attributable. An XYG export above the documented
cell ceiling records its stable fail-closed reason instead of timings.

    uv run python scripts/bench_hexbin_static.py --out results.json
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys

GRIDSIZES = (25, 50, 100, 200, 300, 400, 600)
FORMATS = ("svg", "png")
REPEATS = 3

WORKER = r"""
import io, json, resource, statistics, sys, time
engine, gridsize, fmt, repeats = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
import numpy as np
np.random.seed(19680801)
n = 100_000
x = np.random.standard_normal(n)
y = 2.0 + 3.0 * x + 4.0 * np.random.standard_normal(n)
if engine == "xyg":
    import xyg.pyplot as plt
else:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
times, size, cells, reason = [], 0, None, None
for _ in range(repeats):
    fig, ax = plt.subplots(figsize=(4.5, 4))
    h = ax.hexbin(x, y, gridsize=gridsize, bins="log", cmap="inferno")
    fig.colorbar(h, ax=ax, label="counts")
    if engine == "xyg":
        cells = len(fig._charts()[0].figure().traces[0].x.values)
    else:
        cells = len(h.get_offsets())
    buf = io.BytesIO()
    start = time.perf_counter()
    try:
        fig.savefig(buf, format=fmt)
    except Exception as error:
        reason = str(error)
        break
    times.append(time.perf_counter() - start)
    size = len(buf.getvalue())
    plt.close(fig)
print(json.dumps({
    "cells": cells,
    "reason": reason,
    "median_seconds": statistics.median(times) if times else None,
    "bytes": size if times else None,
    "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
}))
"""


def run(engine: str, gridsize: int, fmt: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", WORKER, engine, str(gridsize), fmt, str(REPEATS)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    import matplotlib
    import numpy

    import xyg

    rows = []
    for gridsize in GRIDSIZES:
        for fmt in FORMATS:
            for engine in ("xyg", "matplotlib"):
                result = run(engine, gridsize, fmt)
                rows.append({"engine": engine, "gridsize": gridsize, "format": fmt, **result})
                print(rows[-1], flush=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    document = {
        "schema": "xyg.bench-hexbin-static/v1",
        "issue": 887,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "numpy": numpy.__version__,
            "matplotlib": matplotlib.__version__,
            "xyg": xyg.__version__ if hasattr(xyg, "__version__") else None,
            "commit": commit,
            "repeats": REPEATS,
        },
        "rows": rows,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
