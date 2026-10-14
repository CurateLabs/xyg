---
title: Graph Visualization and Charting for Python, Node, and WASM
description: XYG is a Rust-powered graph visualization and charting engine for Python, Node.js, and browser WebAssembly, built for GraphForge's billion-scale graph goal.
---

# What is XYG?

XYG is a graph visualization and charting engine for **Python, Node.js, and
browser WebAssembly**, powered by a shared Rust core.

We forked [XY](https://github.com/reflex-dev/xy) because
[GraphForge](https://github.com/CurateLabs/graphforge) needed billion-scale graph
visualization. Graph visualization leads the product, with everyday charts,
custom application visuals, and large-data exploration alongside it. Two ideas
shape the engine:

- **Responsive views across data scales.** Small Cartesian scatter charts draw
  individual points; large scatter overviews can aggregate and long lines can
  decimate. Refinement depends on the active representation and host. Ingest and
  preparation still depend on the source data size.
- **Control over your chart's design.** Python and Node author charts over the
  shared native engine; browser WASM exposes a bounded Worker API.
  Style browser titles, legends, tooltips, and controls with CSS or Tailwind.
  Validated mark styles and theme tokens have their own export coverage; the
  [Capability Matrix](/docs/xy/styling/capabilities/) documents each mechanism.

~~~python demo-only exec
from xyg_examples import build_sdf_plots

sdf_plots = build_sdf_plots().reading_order
~~~

All four interactive charts are live — drag to pan and scroll to zoom.
They show the same XYG-shaped probability field as binned scatter, heatmap,
contours, and individual points.
[View the customizable Python source](https://github.com/CurateLabs/xyg/blob/main/docs/app/scripts/xyg_examples.py).

~~~md alert warning
**Early alpha.** XYG is pre-1.0. The declarative composition model is stabilizing, but callback
payloads, host coverage, chart breadth, and adaptive-rendering thresholds
may change. See [Limitations and alpha status](/docs/xy/api-reference/limitations-and-alpha-status/)
before committing to a long-lived integration.
~~~

## Start here

- Browse the [visual gallery](/docs/xy/overview/gallery/) to see the chart
  families available today.
- [Install XYG](/docs/xy/overview/installation/) and build
  [your first Python chart](/docs/xy/overview/first-chart/).
- [Use XYG with GraphForge](/docs/xy/integrations/graphforge/) or explore
  [graph visualization](/docs/xy/charts/graph/),
  or choose the [Node or browser WASM host](/docs/xy/overview/installation/#node-and-browser-wasm).
- Learn the [composition model](/docs/xy/core-concepts/) and how the
  [shared Rust engine](/docs/xy/core-concepts/rust-engine-and-host-parity/) keeps
  behavior consistent across hosts.
- Read the [benchmark evidence guide](/docs/xy/overview/benchmarks/) with its output
  contracts and measurement caveats.
- Follow the [styling overview](/docs/xy/styling/) for CSS, Tailwind, theme
  tokens, and rendered-mark styles.

## Why XYG

GraphForge owns graph data and analysis; XYG turns those results into
visualizations. Python and Node offer native chart composition, while direct
browser WASM runs the Rust engine in a Worker. Host coverage is explicit, and
the browser authoring surface remains bounded.

Build a node-link graph, an ordinary line, bar, or distribution chart, compose
multiple marks, or explore a dense scatter. XYG brings design and data-scale
controls together so you can choose the representation that fits your workflow.

The fork moved data processing and visual-output policy from Python into Rust:
graph composition and layout, LOD choices, binning, decimation, geometry,
encodings, and tick resolution. Python and Node call one native ABI;
browser WASM compiles the same engine for a Worker. Hosts package inputs and
manage application state; they do not maintain independent algorithms.
[Read the parity contracts and their limits](/docs/xy/core-concepts/rust-engine-and-host-parity/).

Rust kernels prepare data, binary transport carries numeric buffers,
and a WebGL2 client draws the resulting representation. Reduced views can bound
transport and drawing work by the viewport; initial scans and preparation still
scale with source data. Exact readout and refinement depend on the active
representation and available compute host.

Billion-scale graph visualization is the goal behind the fork. The
[benchmark evidence guide](/docs/xy/overview/benchmarks/) separates executed
graph-scale measurements from LOD policy checks and scatter-density capacity.

Browser CSS and Tailwind style chart chrome. Mark, axis, and theme styling
have explicit renderer contracts, so check export coverage when matching
notebook, application, PNG, SVG, and PDF output.

Browse the [chart gallery](/docs/xy/overview/gallery/), inspect
[benchmark evidence and measurement scopes](/docs/xy/overview/benchmarks/), or
build [your first chart](/docs/xy/overview/first-chart/). The docs describe the
current source; see [installation](/docs/xy/overview/installation/) for the
published alpha and source-build requirements.
