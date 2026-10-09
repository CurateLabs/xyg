#!/usr/bin/env python3
"""Bounded offline geographic build/export evidence; no browser or speedup claim.

Each library/scale uses a fresh Python child, materializing all lon/lat rows.
The Rust retained-source benchmark is a separate output/ownership contract.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import resource
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "spec/performance/geo-competitors-2026-10-08"
FAMILIES = (
    "matplotlib",
    "seaborn",
    "plotly",
    "bokeh",
    "altair",
    "datashader",
    "holoviews",
    "hvplot",
)
WIDTH, HEIGHT = 800, 600
WORLD = 20037508.342789244


def rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def child(family: str, rows: int, artifact: Path) -> int:
    began = time.perf_counter()
    metrics: dict[str, Any] = {"library": family, "rows": rows, "status": "started"}
    try:
        import numpy as np
        import pandas as pd

        if family in ("matplotlib", "seaborn"):
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            if family == "seaborn":
                import seaborn as sns
        elif family == "plotly":
            import plotly.graph_objects as go
        elif family == "bokeh":
            from bokeh.embed import file_html
            from bokeh.models import ColumnDataSource, HoverTool
            from bokeh.plotting import figure
            from bokeh.resources import INLINE
        elif family == "altair":
            import altair as alt
        elif family == "datashader":
            import datashader as ds
            import datashader.transfer_functions as tf
        else:
            import holoviews as hv
            from bokeh.resources import INLINE
            from holoviews.operation.datashader import datashade

            hv.extension("bokeh")
            if family == "hvplot":
                import hvplot.pandas  # noqa: F401
        metrics["startup_import_ms"] = (time.perf_counter() - began) * 1000
        metrics["startup_max_rss_bytes"] = rss_bytes()
        start = time.perf_counter()
        row = np.arange(rows, dtype=np.uint64)
        lon = ((row * 48271 + 17) % 1000003).astype(np.float64) / 1000003.0 * 340.0 - 170.0
        lat = ((row * 69621 + 31) % 1000033).astype(np.float64) / 1000033.0 * 120.0 - 60.0
        ids = np.uint64(2**64 - 1) - row
        # Native geographic encodings consume lon/lat. Other baselines get
        # explicitly preprojected Web Mercator, never an implied map adapter.
        x = np.deg2rad(lon) * 6378137.0
        y = np.log(np.tan(np.pi / 4.0 + np.deg2rad(lat) / 2.0)) * 6378137.0
        frame = pd.DataFrame({"lon": lon, "lat": lat, "x": x, "y": y})
        coord_digest = hashlib.sha256(
            np.column_stack((lon, lat)).astype("<f8").tobytes()
        ).hexdigest()
        metrics.update(dataset_sha256=coord_digest, dataset_ms=(time.perf_counter() - start) * 1000)
        metrics["dataset_array_bytes"] = sum(a.nbytes for a in (row, lon, lat, ids, x, y))
        metrics["dataset_max_rss_bytes"] = rss_bytes()
        assert len(frame) == rows and np.all(np.isfinite(x)) and np.all(np.isfinite(y))
        assert np.max(np.abs(x)) < WORLD and np.max(np.abs(y)) < WORLD
        start = time.perf_counter()
        if family in ("matplotlib", "seaborn"):
            fig, ax = plt.subplots(figsize=(8, 6), dpi=100)
            if family == "matplotlib":
                points = ax.scatter(x, y, s=4, c="#2166ac", linewidths=0)
            else:
                sns.scatterplot(
                    data=frame, x="x", y="y", s=4, color="#2166ac", linewidth=0, legend=False, ax=ax
                )
                points = ax.collections[0]
            ax.set(
                xlim=(-WORLD, WORLD),
                ylim=(-WORLD, WORLD),
                xlabel="Web Mercator easting",
                ylabel="Web Mercator northing",
            )
            assert len(points.get_offsets()) == rows
            contract, ext = "static_png_all_projected_points", "png"
        elif family == "plotly":
            fig = go.Figure(
                go.Scattermap(
                    lon=lon, lat=lat, mode="markers", marker={"size": 2, "color": "#2166ac"}
                )
            )
            fig.update_layout(
                map={"style": "white-bg", "center": {"lon": 0, "lat": 0}, "zoom": 0},
                width=WIDTH,
                height=HEIGHT,
                margin={"l": 0, "r": 0, "t": 0, "b": 0},
            )
            assert len(fig.data[0].lon) == rows and len(fig.data[0].lat) == rows
            contract, ext = "standalone_html_native_scattermap_all_lonlat", "html"
        elif family == "bokeh":
            source = ColumnDataSource(data={"x": x, "y": y})
            fig = figure(
                width=WIDTH,
                height=HEIGHT,
                x_range=(-WORLD, WORLD),
                y_range=(-WORLD, WORLD),
                x_axis_type="mercator",
                y_axis_type="mercator",
                output_backend="webgl",
                tools="pan,wheel_zoom,reset",
            )
            fig.scatter("x", "y", source=source, size=2, color="#2166ac", line_color=None)
            fig.add_tools(HoverTool(tooltips=[("easting", "@x"), ("northing", "@y")]))
            assert len(source.data["x"]) == rows
            contract, ext = (
                "standalone_html_all_projected_points_webgl_requested_not_executed",
                "html",
            )
        elif family == "altair":
            alt.data_transformers.disable_max_rows()
            fig = (
                alt.Chart(frame[["lon", "lat"]])
                .mark_circle(size=4, color="#2166ac")
                .encode(longitude="lon:Q", latitude="lat:Q")
                .project(type="mercator")
                .properties(width=WIDTH, height=HEIGHT)
            )
            contract, ext = (
                "vega_lite_json_native_geographic_all_lonlat_maxrows_explicitly_disabled",
                "json",
            )
        elif family == "datashader":
            canvas = ds.Canvas(
                plot_width=WIDTH,
                plot_height=HEIGHT,
                x_range=(-WORLD, WORLD),
                y_range=(-WORLD, WORLD),
            )
            counts = canvas.points(frame, "x", "y", agg=ds.count())
            assert int(counts.sum()) == rows
            fig = tf.shade(counts, cmap=["#deebf7", "#2166ac"], how="log")
            metrics.update(
                aggregate_total=int(counts.sum()),
                occupied_cells=int(np.count_nonzero(counts.values)),
            )
            contract, ext = "static_png_fixed_800x600_exact_counts_no_individual_ids", "png"
        elif family == "holoviews":
            fig = datashade(
                hv.Points(frame, kdims=["x", "y"]),
                dynamic=False,
                width=WIDTH,
                height=HEIGHT,
                x_range=(-WORLD, WORLD),
                y_range=(-WORLD, WORLD),
            ).opts(width=WIDTH, height=HEIGHT)
            contract, ext = "standalone_html_static_datashaded_800x600_no_individual_ids", "html"
        else:
            fig = frame.hvplot.points(
                "x",
                "y",
                datashade=True,
                dynamic=False,
                width=WIDTH,
                height=HEIGHT,
                xlim=(-WORLD, WORLD),
                ylim=(-WORLD, WORLD),
                color="#2166ac",
            )
            contract, ext = "standalone_html_static_datashaded_800x600_no_individual_ids", "html"
        metrics.update(
            build_ms=(time.perf_counter() - start) * 1000,
            build_max_rss_bytes=rss_bytes(),
            output_contract=contract,
        )
        start = time.perf_counter()
        if family in ("matplotlib", "seaborn"):
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=100)
            payload = buf.getvalue()
            plt.close(fig)
        elif family == "plotly":
            payload = fig.to_html(full_html=True, include_plotlyjs=True).encode()
        elif family == "bokeh":
            payload = file_html(fig, INLINE, "Geographic points").encode()
        elif family == "altair":
            payload = fig.to_json(indent=None, sort_keys=False).encode()
        elif family == "datashader":
            buf = io.BytesIO()
            fig.to_pil().save(buf, format="PNG")
            payload = buf.getvalue()
        else:
            hv.save(fig, artifact, fmt="html", resources=INLINE)
            payload = artifact.read_bytes()
        metrics.update(
            export_ms=(time.perf_counter() - start) * 1000, export_max_rss_bytes=rss_bytes()
        )
        verification_start = time.perf_counter()
        if family == "altair":
            parsed = json.loads(payload)
            assert sum(len(v) for v in parsed["datasets"].values()) == rows
        if len(payload) > 128 << 20:
            raise RuntimeError("explicit128MiB output ceiling exceeded")
        if ext == "png":
            from PIL import Image

            image = Image.open(io.BytesIO(payload))
            assert image.size == (WIDTH, HEIGHT)
            metrics["image_dimensions"] = list(image.size)
        elif ext == "html":
            assert b"<html" in payload.lower() and b"<script" in payload.lower()
        if family not in ("holoviews", "hvplot"):
            artifact.write_bytes(payload)
        metrics.update(
            status="complete",
            verify_and_write_ms=(time.perf_counter() - verification_start) * 1000,
            payload_bytes=len(payload),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            file_type=ext,
            maximum_resident_bytes=rss_bytes(),
            total_child_ms=(time.perf_counter() - began) * 1000,
        )
    except Exception as exc:
        metrics.update(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            maximum_resident_bytes=rss_bytes(),
            total_child_ms=(time.perf_counter() - began) * 1000,
        )
        traceback.print_exc(file=sys.stderr)
    print(json.dumps(metrics, sort_keys=True), flush=True)
    return 0 if metrics["status"] == "complete" else 3


def run(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    if args.rows and (min(args.rows) < 1 or max(args.rows) > 1_000_000):
        raise SystemExit("Measured rows must be1..1M; larger materialized sources are not admitted")
    versions = subprocess.check_output(
        [
            args.python,
            "-c",
            "import importlib.metadata as m,json; print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()},sort_keys=True))",
        ],
        text=True,
    )
    environment = dict(
        schema_version=1,
        recorded_at=datetime.now(UTC).isoformat(),
        python_command=args.python,
        python=subprocess.check_output([args.python, "-VV"], text=True).strip(),
        platform=platform.platform(),
        cpu=subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        if sys.platform == "darwin"
        else platform.processor(),
        memory_bytes=int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))
        if sys.platform == "darwin"
        else None,
        git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        git_status=subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True),
        dataset_authority_sha256=hashlib.sha256(
            (ROOT / "crates/xyg-engine/src/bin/geo_scale_bench.rs").read_bytes()
        ).hexdigest(),
        machine=platform.machine(),
        logical_cpus=os.cpu_count(),
        load_average=os.getloadavg(),
        versions=json.loads(versions),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        row_ceiling=1_000_000,
        timeout_seconds=args.timeout,
        rss_watchdog_bytes=args.max_rss_mib << 20,
        output_ceiling_bytes=128 << 20,
        rss_method="completed child resource.getrusage maximum RSS; parent samples ps RSS every100ms for safety",
        repetitions=args.repeat,
        dataset=dict(
            longitude="((row*48271+17)%1000003)/1000003*340-170",
            latitude="((row*69621+31)%1000033)/1000033*120-60",
            feature_id="u64MAX-row (generated for dataset equality; not attached to competitor glyphs)",
            source_order="unordered modular sequence",
            projection="explicit spherical Web Mercator R6378137 for projected baselines; Plotly/Altair native lonlat",
            frame=[WIDTH, HEIGHT],
            bounds=[-WORLD, WORLD, -WORLD, WORLD],
        ),
        caveats=[
            "Materializes entire source, projected arrays and pandas frame in every child",
            "Shared fixture keeps both lonlat and Mercator arrays even for native geographic encodings; this is not a minimum-memory implementation",
            "Overall child RSS includes output validation; export_max_rss_bytes excludes final payload parsing/writing verification",
            "Dataset generates fullu64 IDs but glyph payloads do not attach them; exact source-ID picking is unmeasured",
            "Fresh child has no in-process warmup; persistent font/Numba disk caches are not cleared",
            "One run per case by default; no confidence interval or quiet-host guarantee",
            "No browser/GPU draw, hover, FPS, full-u64 picking, temporal filtering, network tiles or out-of-core interaction measured",
            "Fixed count rasters do not retain per-point IDs; direct vector serialization and fixed-raster outputs are different contracts",
            "XYG retained-source protocol evidence is a separate workload, never a derived speedup ratio",
        ],
    )
    (args.out / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    (args.out / "requirements.txt").write_text(
        "\n".join(
            f"{name}=={value}"
            for name, value in sorted(environment["versions"].items(), key=lambda kv: kv[0].lower())
        )
        + "\n"
    )
    results = []
    for family in args.libraries:
        for rows in args.rows:
            for iteration in range(1, args.repeat + 1):
                stem = f"{family}-{rows}-r{iteration}"
                with tempfile.TemporaryDirectory(prefix="xyg-geo-competitor-") as scratch:
                    artifact = Path(scratch) / "output.html"
                    cmd = [
                        args.python,
                        str(Path(__file__).resolve()),
                        "--child",
                        family,
                        "--child-rows",
                        str(rows),
                        "--artifact",
                        str(artifact),
                    ]
                    start = time.perf_counter()
                    with (
                        (args.out / f"{stem}.stdout.txt").open("w") as stdout,
                        (args.out / f"{stem}.stderr.txt").open("w") as stderr,
                    ):
                        proc = subprocess.Popen(
                            cmd,
                            stdout=stdout,
                            stderr=stderr,
                            start_new_session=True,
                            env={
                                **os.environ,
                                "MPLBACKEND": "Agg",
                                "OPENBLAS_NUM_THREADS": "1",
                                "OMP_NUM_THREADS": "1",
                                "MKL_NUM_THREADS": "1",
                                "NUMBA_NUM_THREADS": "1",
                            },
                        )
                        safety = None
                        sampled = 0
                        while proc.poll() is None:
                            if time.perf_counter() - start > args.timeout:
                                safety = "timeout"
                            try:
                                ps = subprocess.check_output(
                                    ["ps", "-o", "rss=", "-p", str(proc.pid)], text=True
                                ).strip()
                                resident = int(ps or "0") * 1024
                                sampled = max(sampled, resident)
                                if resident > args.max_rss_mib << 20:
                                    safety = "rss_watchdog"
                            except (subprocess.CalledProcessError, ValueError):
                                pass
                            if safety:
                                os.killpg(proc.pid, signal.SIGKILL)
                                proc.wait()
                                break
                            time.sleep(0.1)
                    raw = (args.out / f"{stem}.stdout.txt").read_text().strip()
                    try:
                        value = json.loads(raw)
                    except json.JSONDecodeError:
                        value = dict(
                            library=family,
                            rows=rows,
                            status="failed",
                            error=safety or "child exited without metrics",
                        )
                    value.update(
                        iteration=iteration,
                        command=cmd,
                        subprocess_elapsed_ms=(time.perf_counter() - start) * 1000,
                        returncode=proc.returncode,
                        safety_stop=safety,
                        sampled_max_rss_bytes=sampled,
                    )
                    (args.out / f"{stem}.json").write_text(json.dumps(value, indent=2) + "\n")
                    results.append(value)
                    print(
                        f"{stem}: {value['status']} elapsed={value['subprocess_elapsed_ms']:.1f}ms payload={value.get('payload_bytes')} peakRSS={value.get('maximum_resident_bytes', sampled)}",
                        flush=True,
                    )
    complete = all(
        r["status"] == "complete" and r["returncode"] == 0 and r["safety_stop"] is None
        for r in results
    )
    (args.out / "summary.json").write_text(
        json.dumps(dict(schema_version=1, results=results, all_complete=complete), indent=2) + "\n"
    )
    if complete:
        fingerprints = {
            str(rows): sorted({r["dataset_sha256"] for r in results if r["rows"] == rows})
            for rows in args.rows
        }
        checks = {
            "all_libraries_share_per_scale_dataset": all(
                len(v) == 1 for v in fingerprints.values()
            ),
            "all_payloads_within_128MiB": all(r["payload_bytes"] <= 128 << 20 for r in results),
            "all_finished_child_max_rss_within_admitted_limit": all(
                r["maximum_resident_bytes"] <= args.max_rss_mib << 20 for r in results
            ),
            "datashader_exact_count_sums_match_source_rows": all(
                r["aggregate_total"] == r["rows"] for r in results if r["library"] == "datashader"
            ),
            "all_png_dimensions_match_frame": all(
                r["image_dimensions"] == [WIDTH, HEIGHT] for r in results if r["file_type"] == "png"
            ),
            "script_sha256_matches": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            == environment["script_sha256"],
        }
        validation = dict(
            schema_version=1,
            completed_cases=len(results),
            all_complete=True,
            checks=checks,
            per_scale_dataset_sha256=fingerprints,
            largest_payload_bytes=max(r["payload_bytes"] for r in results),
            largest_finished_child_rss_bytes=max(r["maximum_resident_bytes"] for r in results),
            source_fingerprint="little-endian f64 interleaved original lonlat SHA256; not projected/output/identity digest",
            verification="Direct input counts, Altair serialized dataset row count, Datashader aggregate total, PNG dimensions/HTML structure; GPU/browser render unmeasured",
        )
        (args.out / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
        complete = all(checks.values())
    return 0 if complete else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--rows", type=int, nargs="+", default=[1000, 100000, 1000000])
    parser.add_argument("--libraries", choices=FAMILIES, nargs="+", default=list(FAMILIES))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--max-rss-mib", type=int, default=1536)
    parser.add_argument("--child", choices=FAMILIES)
    parser.add_argument("--child-rows", type=int)
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args()
    if args.child:
        if (
            args.child_rows is None
            or not 1 <= args.child_rows <= 1_000_000
            or args.artifact is None
        ):
            raise SystemExit("bounded child rows and artifact path required")
        return child(args.child, args.child_rows, args.artifact)
    if (
        not 1 <= args.repeat <= 3
        or not 1 <= args.timeout <= 600
        or not 128 <= args.max_rss_mib <= 2048
    ):
        raise SystemExit("repeat1..3/timeout1..600s/RSS128..2048MiB required")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
