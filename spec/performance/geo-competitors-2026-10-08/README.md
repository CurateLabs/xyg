# Geographic point build/export evidence, 2026-10-08

This directory measures eight Python libraries at1k,100k and1M geographic points.
Every case completed in a fresh bounded subprocess. These are descriptive local
build/export measurements, not a speedup claim, browser render benchmark or #50
closure. Local date is2026-10-08; UTC timestamps fall on2026-10-09.

Reproduce from the repository root with Python3.13:

```sh
uv venv --python 3.13 /tmp/xyg-geo-competitors-repro
uv pip install --python /tmp/xyg-geo-competitors-repro/bin/python -r spec/performance/geo-competitors-2026-10-08/requirements.txt
python3 scripts/bench_geo_competitors.py --python /tmp/xyg-geo-competitors-repro/bin/python --out /tmp/xyg-geo-competitors-repro-results
uv run ruff check scripts/bench_geo_competitors.py
uv run ruff format --check scripts/bench_geo_competitors.py
```

`environment.json` pins all dependencies, Python, hardware/OS, source/script SHA,
working-tree state and safety limits. `requirements.txt` is the exact environment
used by all measured children. The initial supplied environment had HoloViews1.14.9,
hvPlot0.8.1 and Panel0.10.3 alongside Bokeh3.10.0; imports failed because old
Panel imported removed `bokeh.models.Box`. Updating the three HoloViz packages
resolved their supported dependencies (including Bokeh3.9.2); the lock captures
the resulting measured versions, not the failed environment.

Each `<library>-<rows>-r1.json` records the exact child command, stage timings,
per-stage RSS high-water readings, total child maximum RSS, parent RSS safety
samples, output size/type/SHA256 and deterministic dataset fingerprint. Matching
stdout/stderr files preserve the actual raw observations. `summary.json` collects
all24 cases; `validation.json` independently checks completion, per-scale source
identity, export bounds and measured output contracts. Temporary exported PNG,
HTML and Vega-Lite JSON files were generated, validated, hashed and discarded;
large bundled runtimes/data are not committed. HTML document/model IDs may vary,
so output SHA values are provenance, not future golden assertions.

## Dataset and safety

Original row `r` has longitude
`((r*48271+17)%1000003)/1000003*340-170` and latitude
`((r*69621+31)%1000033)/1000033*120-60`. These are the exact formulas in
[`geo_scale_bench.rs`](../../../crates/xyg-engine/src/bin/geo_scale_bench.rs),
covering longitude[-170,170) and latitude[-60,60) in unordered source order.
The benchmark generates `u64MAX-r` IDs, but does not attach them to competitor
glyphs or claim full-ID picking parity. All rows are valid; no temporal predicate,
source style/state attachments, polygons or network providers are measured.

Every child materializes lon/lat and explicit spherical Web Mercator x/y using
R6378137, plus a pandas frame and source ID array. Native Plotly/Altair geographic
encodings consume lon/lat; other measured paths receive projected x/y. Keeping
both representations standardizes fixture preparation but overstates their
minimum possible memory. No geographic policy code is added to XYG hosts.

Outputs target800×600. Projected baselines cover the full Mercator world;
Plotly has a white map style, center0/0,zoom0. These have different margins,
marker units and camera fitting from XYG's zoom0 world inside an800×600 Scene.
Datashader log shading and HoloViz defaults are not the same as XYG count-color
and cluster rules. Equal input does not imply pixel-equal output.

The safety contract is at most1M materialized rows,180 seconds per child,
1.5GiB sampled RSS and128MiB final payload. A100ms parent watchdog kills the
whole child process group on timeout or RSS breach and records an explicit
failure; it does not silently subsample. Finished-child RSS comes from
`getrusage`, in bytes on macOS or converted from KiB on Linux. The sampled
watchdog is a safety check, not a strict allocation ledger. No limit was hit.
Larger competitor workloads are unmeasured rather than extrapolated.

One run per case supplies no confidence interval. The host was shared with
ongoing development/build/browser work; load average is recorded and no quiet
host is claimed. BLAS/OpenMP/Numba thread limits are explicitly1. Fresh children
have no in-process warmup, but persistent font/Numba disk caches were not cleared.

## What each measured output means

| Library/version | Measured product path | Important boundary |
| --- | --- | --- |
| Matplotlib3.11.2 | Agg scatter of preprojected x/y → actual PNG | Static draw/export; geographic CRS/camera adapter and Cartopy are not exercised |
| Seaborn0.13.2 | `scatterplot` on projected pandas frame → Matplotlib PNG | Same static renderer, with Seaborn authoring overhead; no geographic adapter |
| Plotly7.1.0 | Native `Scattermap(lon,lat)` → self-contained JS HTML | All rows serialized; MapLibre draw/hover/GPU work happens later and is unmeasured |
| Bokeh3.9.2 | Mercator axes + projected `ColumnDataSource` → inlined HTML | All rows serialized; WebGL is requested but never executed by this harness |
| Altair6.3.0 | longitude/latitude encodings + Mercator projection → Vega-Lite JSON |5000-row guard explicitly disabled; JSON is a specification, not a rendered map |
| Datashader0.19.1 | Explicit800×600 `Canvas.points(count)` → shaded PNG | Exact count sum equals source rows; fixed raster has no individual source IDs |
| HoloViews1.23.2 | Eager `datashade(Points,dynamic=False)` → inlined Bokeh HTML | Fixed raster; standalone output does not provide a live Python reaggregation server |
| hvPlot0.12.2 | `points(datashade=True,dynamic=False)` → inlined Bokeh HTML | Same explicit preprojection/raster contract; GeoViews/Cartopy/geo=True and live callbacks unmeasured |

Authoring/build time includes the eager aggregation where requested. Export time
includes PNG drawing/encoding or HTML/JSON serialization. Startup imports,
dataset/projection preparation and final output verification/write are separately
recorded. Final RSS includes verification; `export_max_rss_bytes` is the
high-water reading before the final payload validation. Altair's independent JSON
reparse occurs after export timing, so it does not inflate serializer time.

Primary documentation supports these boundaries:
[Matplotlib scatter](https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.scatter.html),
[Cartopy's separate geographic integration](https://cartopy.readthedocs.io/stable/matplotlib/intro.html),
[Seaborn scatterplot](https://seaborn.pydata.org/generated/seaborn.scatterplot.html),
[Plotly Scattermap](https://plotly.com/python-api-reference/generated/plotly.graph_objects.Scattermap.html),
[Bokeh geographical data](https://docs.bokeh.org/en/3.3.3/docs/user_guide/topics/geo.html),
[Altair geographic encodings](https://altair-viz.github.io/altair-tutorial/notebooks/09-Geographic-plots.html),
[Altair large-data guard and specification tradeoffs](https://altair-viz.github.io/user_guide/large_datasets.html),
[Datashader pipeline](https://datashader.org/getting_started/Pipeline.html),
[HoloViews static versus live rasterization](https://holoviews.org/user_guide/Large_Data.html),
and [hvPlot geographic options](https://hvplot.holoviz.org/en/docs/latest/ref/plotting_options/geographic.html).
Installed versions in the raw environment are authoritative for this run.

## XYG comparison boundary and remaining evidence

The neighboring [XYG retained scale evidence](../geo-scale-2026-10-08/README.md)
measures native Rust chunk authoring, authentication, time-first bounded queries,
LOD→Scene lowering, exact CPU picking, five leased views, and native SVG/PNG.
Its source is regenerated chunk by chunk through65536-row chunks rather than
materialized as a source-wide pandas frame. Above32768 vertices its first Scene
may represent bounded cluster cells and keep exact source membership accessible
through paged queries. Direct HTML/JSON containing every competitor point and a
fixed count raster are different output contracts from that retained Scene.

The recorded startup/build/export/RSS/payload columns identify concrete costs
and capabilities for this fixture; no ratio between them and XYG is labelled a
speedup. This evidence does not rank browser first paint, pan/zoom FPS, hover,
GPU picking, VRAM, full-u64 identity, temporal filtering, network tiles,
out-of-core interaction, multipolygon rendering or massive application latency.
Matched camera/style/output contracts, multiple repetitions on a quiet host and
actual browser/interactive measurements remain necessary for those comparisons.

## Measured results

Each entry is build/export milliseconds, pre-verification export-phase RSS high-water MiB, and payload MiB. Startup and fixture preparation are excluded from the two displayed timing columns but retained in raw results.

| Library | Rows | Build ms | Export ms | Export-phase peak MiB | Payload MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| matplotlib | 1,000 | 8.03 | 27.44 | 101.36 | 0.025 |
| matplotlib | 100,000 | 7.60 | 27.32 | 113.28 | 0.026 |
| matplotlib | 1,000,000 | 15.31 | 73.52 | 235.31 | 0.020 |
| seaborn | 1,000 | 33.53 | 19.87 | 163.86 | 0.025 |
| seaborn | 100,000 | 48.54 | 24.55 | 179.62 | 0.026 |
| seaborn | 1,000,000 | 188.22 | 70.24 | 376.84 | 0.020 |
| plotly | 1,000 | 38.12 | 7.80 | 139.61 | 4.622 |
| plotly | 100,000 | 28.53 | 18.09 | 167.89 | 6.752 |
| plotly | 1,000,000 | 30.57 | 125.99 | 487.44 | 26.127 |
| bokeh | 1,000 | 4.18 | 11.65 | 98.27 | 1.420 |
| bokeh | 100,000 | 4.24 | 50.47 | 127.61 | 3.354 |
| bokeh | 1,000,000 | 4.33 | 412.38 | 428.92 | 20.904 |
| altair | 1,000 | 2.80 | 10.13 | 107.95 | 0.054 |
| altair | 100,000 | 3.19 | 168.94 | 155.70 | 5.322 |
| altair | 1,000,000 | 2.90 | 1669.28 | 602.94 | 53.215 |
| datashader | 1,000 | 326.12 | 12.98 | 207.28 | 0.004 |
| datashader | 100,000 | 262.76 | 17.22 | 213.38 | 0.030 |
| datashader | 1,000,000 | 285.06 | 22.18 | 322.52 | 0.114 |
| holoviews | 1,000 | 349.18 | 51.13 | 268.44 | 2.842 |
| holoviews | 100,000 | 335.32 | 42.90 | 275.00 | 2.907 |
| holoviews | 1,000,000 | 300.78 | 37.89 | 379.55 | 2.971 |
| hvplot | 1,000 | 305.42 | 35.61 | 280.58 | 2.842 |
| hvplot | 100,000 | 300.24 | 35.93 | 287.72 | 2.907 |
| hvplot | 1,000,000 | 321.06 | 37.76 | 392.59 | 2.971 |

The largest measured payload was Altair’s 1M-row Vega-Lite specification (55,800,338 bytes). The largest completed-child RSS was 647,741,440 bytes, including output verification. Count-raster payloads are bounded by the frame while direct vector payloads grow with source rows. These observations do not imply equal interaction or source-identity capability.
