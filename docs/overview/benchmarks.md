---
title: Benchmarks
description: Inspect versioned charting evidence, measurement scopes, competitor coverage, and reproduction commands.
---

# Benchmarks

XYG's benchmark program covers graph visualization, ordinary charts, large-data exploration,
interaction, static export, and dashboards. A useful result identifies the
source version, environment, representation, measurement scope, and correctness
oracle. Chart breadth and customization also need visual examples and the
[Capability Matrix](/docs/xy/styling/capabilities/).

## Evidence available today

The [competitive results specification](https://github.com/CurateLabs/xyg/blob/main/spec/benchmarks/results.md)
records scoped measurements and their limitations. The
[archived launch baselines](https://github.com/CurateLabs/xyg/tree/main/benchmarks/launch_baselines)
include raw JSON, dependency locks, environment records, and manifests.
These are historical, versioned evidence, including upstream XY runs; they are
not measurements of every capability in the current XYG source.

The fork was motivated by GraphForge's need for billion-scale graph
visualization. The archived
[graph-scale diagnostic](https://github.com/CurateLabs/xyg/blob/main/spec/benchmarks/results.md#graph-scale-evidence-33-local-diagnostic)
executes through 1M source nodes, with explicit node/edge reduction budgets.
The 10M, 100M, and 1B graph rows evaluate Rust LOD policy without executing
those graphs. Graph-scale, scatter-density, and cross-host evidence are
separate contracts; a billion-row scatter run does not establish billion-node
graph visualization across Python, Node, and WASM.

The previously displayed 10k–100M interactive UX table and chart have no
committed raw run record supporting their values. They are withdrawn from the
public performance summary until a versioned run with its environment and
complete competitor results is archived. This also means there is no supported
current-source 177× speedup claim from that table.

## What the measurements mean

| Measurement | Scope |
| --- | --- |
| Preparation | Source ingest, figure construction, aggregation, and payload preparation; scope must be recorded per harness |
| Browser navigation time | Navigation to the correct, stable canvas after the host has prepared its chart; excludes earlier preparation |
| End-to-end time to first render | Build, serialization, and browser rendering where the harness explicitly includes all three |
| Interaction | Input-to-pixels and final settle time; whether live refinement is exercised must be recorded |
| Memory | Python and browser process trees reported separately; a Python-only number is not total application memory |

The UX summarizer's `visible_complete_ms` is the browser-navigation measurement.
Its correctness and stability probes check expected sentinel pixels and wait
for 10 byte-identical frames. This is not a measurement of complete source
loading or figure preparation.

Source-row work still grows with data size. Density aggregation and line
decimation can bound the resulting transport and drawing work by the viewport.
A density surface and one-marker-per-row geometry answer different output
contracts; both need disclosure and correctness checks.

## Compare relevant alternatives

Exact-marker comparisons include Matplotlib and Plotly. Aggregated views also
need aggregation-capable peers, including Datashader with HoloViews/hvPlot and
Bokeh. The UX runner includes a live Datashader arm, but no comparable archived
UX values are available to present here. Its omission is not evidence of a win.
The broader benchmark harness covers Seaborn, Altair, and other relevant tools.

One scatter workload cannot establish performance for every chart family,
platform, export path, or multi-chart application. Small everyday charts and
large-data views both belong in the evidence. Keep hardware WebGL and
SwiftShader software-GL results separate.

## Inspect and reproduce

- [Benchmark runbook](https://github.com/CurateLabs/xyg/blob/main/benchmarks/README.md)
- [Measurement methodology](https://github.com/CurateLabs/xyg/blob/main/spec/benchmarks/methodology.md)
- [Interactive UX harness](https://github.com/CurateLabs/xyg/blob/main/benchmarks/bench_ux.py)
- [Full ladder runner](https://github.com/CurateLabs/xyg/blob/main/benchmarks/run_ux_suite.sh)
- [Result summarizer](https://github.com/CurateLabs/xyg/blob/main/benchmarks/summarize_ux.py)

After completing the runbook setup, set `CHROME` to your browser executable and
run the ladder. It includes default density and exact-marker XYG, Plotly,
Matplotlib, and Datashader:

```bash
export CHROME="/path/to/chrome"
./benchmarks/run_ux_suite.sh /path/to/xyg-ux-suite
uv run python benchmarks/summarize_ux.py /path/to/xyg-ux-suite
uv run python benchmarks/plot_ux.py /path/to/xyg-ux-suite --out-dir charts
```

Archive the raw results, source commit, environment, failures, and output
contracts before publishing numbers. The runbook explains how to produce
artifacts; it does not imply that every generated run has been committed.
See [Large data and performance](/docs/xy/core-concepts/large-data-and-performance/)
for the representation and refinement boundaries.
