# xy browser interaction benchmark

Repetitions per gesture: `12`.
Repeated tooltip samples per eligible row: `8`.

## Benchmark Categories

| id | category | status | primary metrics | current/planned harness | goal |
|---|---|---|---|---|---|
| graph_render_pipeline | Graph render pipeline | tracked | UUID ingest, layout ticks, render-graph build, payload/export bytes, first paint and frame pacing | benchmarks/test_codspeed_graph_render.py; benchmarks/bench_dual_host_graph.py; benchmarks/bench_interaction.py; benchmarks/bench_graph_scale.py | Keep native graph work attributable and browser-visible geometry bounded at every scale tier. |
| small_data_startup | Small-data startup | tracked | TTFR, JS/payload size, Python overhead | benchmarks/bench_vs.py --ttfr at 1k-100k; benchmarks/test_codspeed_kernels.py::test_first_payload_scatter_small | Beat Plotly/Bokeh/Altair on first interactive paint for common charts. |
| install_footprint_import_budget | Install footprint and import budget | tracked | cold import time, installed distribution bytes, file count | benchmarks/bench_install.py | Keep xy lightweight at import and smaller to install than broad plotting stacks. |
| medium_direct_scatter | Medium direct scatter | tracked | FPS, TTFR, memory, bytes/point, hover latency | benchmarks/bench_vs.py at 100k-200k; benchmarks/bench_interaction.py; benchmarks/test_codspeed_kernels.py::test_first_payload_scatter_medium | Smooth exact WebGL scatter with bounded bytes/point and no JSON-number payload cliff. |
| huge_scatter_overview | Huge scatter overview | tracked | ingest/bin time, density payload size, peak memory, TTFR | benchmarks/bench_scatter_native.py, benchmarks/bench_vs.py, benchmarks/test_codspeed_kernels.py::test_first_payload_density_large, example app assets | Keep resident/render payload flat in N while showing truthful density summaries. |
| adaptive_scatter_drilldown | Adaptive scatter drilldown | tracked | visible-query latency, tier-switch latency, exact-point recovery, badge accuracy | benchmarks/test_codspeed_kernels.py::test_adaptive_drilldown_cycle and ::test_adaptive_drilldown_cycle_mean_color (channel-bearing: per-request cost must exclude full-column color work) | Exact points when visible count is under budget; sampled/density with explicit counts otherwise. |
| huge_line_time_series | Huge line/time series | tracked | decimation time, zoom re-decimation latency, TTFR, extrema preservation | benchmarks/bench.py, benchmarks/bench_native.py, benchmarks/bench_interaction.py, benchmarks/test_codspeed_kernels.py::test_decimate_view | Screen-bounded line payloads with extrema-preserving decimation and fast zoom refresh. |
| many_chart_dashboards | Many-chart dashboards | tracked | payload prep, navigation readiness, per-chart setup/first draw, shader compiles/program links, startup long tasks, JS heap, redraw submission, scroll visibility, context loss/restore, stable chart-count ceiling | benchmarks/bench_dashboard.py | Measure the 10-60 chart scaling curve and expose LRU context eviction without discarding partial-row metrics. |
| interaction_smoothness | Interaction smoothness | tracked | pan/zoom FPS, wheel latency, hover latency, tooltip stability, selection latency, frame color delta | benchmarks/bench_interaction.py; benchmarks/bench_transport.py | Stay responsive during interaction, avoid blank/flickering frames, then refine view after interaction settles. |
| payload_export_size | Payload/export size | tracked | standalone HTML bytes, binary payload bytes, bundle bytes | benchmarks/bench_vs.py, benchmarks/bench_scatter_native.py, benchmarks/bench_transport.py, benchmarks/test_codspeed_transport.py, benchmarks/test_codspeed_kernels.py::test_first_payload_density_large, benchmarks/test_codspeed_kernels.py::test_memory_report_density_medium, example app asset sizes | Keep data payloads binary and screen-bounded where possible; warn when exact export would be huge. |
| core_2d_chart_breadth | Core 2D chart breadth | tracked | payload-prep time, payload bytes, standalone HTML bytes, TTFR | benchmarks/bench_2d_charts.py vs Plotly/Seaborn; benchmarks/bench_pyplot_vs_matplotlib.py; benchmarks/bench_interaction.py; CodSpeed core_2d rows | Beat Plotly on user-visible first paint for common 2D charts while tracking Seaborn raster baselines where applicable. |
| input_ingestion | Input ingestion | tracked | ingest latency, copies, peak Python memory | benchmarks/bench_workflows.py ingestion rows | Keep zero-copy inputs cheap and make unavoidable conversions visible. |
| streaming_updates | Streaming updates | tracked | append latency, refresh bytes, incremental pyramid update latency, domain-growth rebuild latency | benchmarks/bench_workflows.py streaming rows; benchmarks/bench_transport.py append diagnostics | Keep stable-domain appends proportional to the batch and expose unavoidable domain-growth rebuilds. |
| log_autorange | Log autorange | tracked | range latency, positive-domain correctness, peak Python memory | benchmarks/bench_workflows.py log autorange row; tests/test_figure.py | Compute correct positive log domains from zone statistics with cost proportional to chunks, not points. |
| polar_coordinate_system | Polar coordinate system | tracked | payload-prep time, wedge flattening cost, SVG/PNG export latency, inverse-raster latency | benchmarks/test_codspeed_polar.py | Keep polar payload prep bounded by composition size rather than observation count, and keep wedge subdivision proportional to each wedge's own angular span. |
| static_export | Static export | tracked | export latency, output bytes, peak Python memory | benchmarks/bench_workflows.py export rows; benchmarks/bench_pyplot_vs_matplotlib.py matched PNG rows | Track each export target independently without mixing payload preparation and browser startup. |

Tracked in this run: `graph_render_pipeline`, `medium_direct_scatter`, `huge_scatter_overview`, `huge_line_time_series`, `core_2d_chart_breadth`, `interaction_smoothness`

## Budgets

| metric | p95 budget |
|---|---:|
| `wheel_zoom_p95_ms` | 600.0 ms |
| `pan_p95_ms` | 300.0 ms |
| `crosshair_p95_ms` | 300.0 ms |
| `hover_p95_ms` | 350.0 ms |
| `box_zoom_p95_ms` | 300.0 ms |
| `brush_select_p95_ms` | 200.0 ms |

| visual invariant | budget |
|---|---:|
| `max_frame_color_delta` | <= 0.85 |
| `min_interaction_lit_pixels` | >= 64.00 |

## Results

| scenario | points | tier | payload | first paint | teardown | wheel p95 | pan p95 | hover p95 | crosshair p95 | box p95 | brush p95 | box zoom | brush select | blank frames | tick overlaps | color delta | tooltip | status |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|
| direct_scatter_interaction | 10,000 | direct | 79 KB | 481.3 | 3.8 | 12.1 | 10.8 | 41.5 | 18.5 | 10.6 | 13.6 | ok | 9966 | 0 | 0 | 0.022 | ok | ok |
| density_scatter_interaction | 250,000 | density | 258 KB | 459.6 | 9.9 | 23.5 | 22.1 | 11.5 | 12.4 | 81.1 | 11.1 | ok | n/a | 0 | 0 | 0.009 | ok | ok |
| graph_2000_interaction | 2,000 | direct | 173 KB | 846.8 | 4.7 | 58.1 | 55.6 | 211.8 | 60.9 | 54.1 | 57.2 | ok | 2560 | 0 | 0 | 0.135 | ok | ok |
| line_120k_interaction | 120,000 | decimated | 26 KB | 644.5 | 45.2 | 78.3 | 50.9 | 47.5 | 47.5 | 48.1 | 37.9 | ok | 2469 | 0 | 0 | 0.000 | ok | ok |
| histogram_120k_interaction | 120,000 | direct | 4 KB | 638.7 | 10.8 | 31.7 | 13.8 | 14.4 | 12.5 | 13.9 | 7.9 | ok | n/a | 0 | 0 | 0.000 | ok | ok |
| bar_1200_interaction | 1,200 | direct | 29 KB | 630.5 | 22.8 | 55.4 | 36.3 | 30.7 | 31.1 | 35.4 | 22.2 | ok | 898 | 0 | 0 | 0.174 | ok | ok |
| heatmap_39600_interaction | 39,600 | direct | 156 KB | 529.3 | 12.4 | 31.6 | 16.9 | 14.5 | 15.0 | 15.0 | 17.1 | ok | n/a | 0 | 0 | 0.004 | ok | ok |

Notes:

- Timed gestures enter through DOM events, flush queued wheel/animation state, draw, and perform a WebGL readback before the sample stops.
- Scope is standalone client input-to-GPU-finish; widget/backend LOD work is measured by native and workflow rows.
- `nonblank` is a WebGL readback sanity check over the rendered chart canvas.
- Budget verification rejects blank canvases, blank interaction frames, missing view changes, missing crosshair chrome, box zoom that does not narrow/restore the viewport, brush selection that does not select/clear eligible marks, overlapping tick labels, unstable tooltips, oversized frame color jumps, and p95 values over the listed limits.
- Scatter rows sweep the requested sizes; graph, line, histogram, bar, and heatmap rows are fixed core-family probes so interaction regressions are not scatter-only.
- The density rows measure client interaction over the current density surface; backend drilldown switching is tracked separately in CodSpeed.