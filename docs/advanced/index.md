---
title: XYG Architecture
description: See how the shared Rust core owns processing and chart policy across Python, Node, and browser WASM, while the browser paints derived buffers.
---

# XYG Architecture

XYG separates source data, derived render data, and presentation. Python and
Node offer idiomatic authoring APIs; the shared Rust core owns data processing
and product policy. Browser WASM runs that engine in a Worker through a bounded
API, and the browser painter draws the resulting representation.

Native hosts support notebooks, applications, and supported HTML, PNG, SVG,
and PDF exports. Direct browser authoring and export coverage remain bounded;
see [Rust engine and host parity](/docs/xy/core-concepts/rust-engine-and-host-parity/).

## System overview

~~~text
Python / Node authoring or bounded browser WASM input
        |
        v
Shared Rust engine (native C ABI or WASM Worker)
(validation, GraphForge composition, layout, LOD, geometry, ticks, export)
        |
        v
Scene metadata + typed binary paint buffers
        |
        v
WebGL2 marks + canvas axes + DOM labels and controls
        |
        +---- supported refinement ----> native host or Rust WASM Worker
~~~

| Layer | Responsibility |
| --- | --- |
| Python / Node | Idiomatic authoring, input packing, callbacks, transport, and host lifecycle |
| Rust | Processing and policy: validation, graph composition/layout, LOD, statistics, geometry, encodings, ticks, selection, and supported static output |
| Browser WASM | Bounded Worker calls into the same Rust engine; explicit memory and feature limits |
| Browser | Drawing, picking, pan and zoom, tooltips, controls, and immediate interaction |

Standalone HTML has no live native-host connection. Notebook widgets can
communicate with Python, applications can route events to their native host,
and supported direct-browser operations use the Rust WASM Worker. Refinement
and exact readout depend on the active representation and available compute host.

## From source data to pixels

### 1. Compile and compute

Chart components are validated and compiled into a framework-independent
scene through Rust. In the Python native host, exact numeric and time values
remain in a figure-owned `ColumnStore` as contiguous `float64` columns. Other
hosts supply their admitted source buffers to the same engine; their memory
and input contracts are explicit rather than copies of Python policy.

Rust then prepares either exact visible points or a smaller render
representation. Long lines use M4 reduction, while dense scatter can use a
density grid plus a deterministic sample. These render buffers are disposable;
the exact columns remain the source of truth.

### 2. Send a compact payload

Chart structure, styles, and column references travel in a small JSON spec.
Numeric data travels separately in typed binary buffers rather than large JSON
number arrays.

| Representation | Used for | Browser receives |
| --- | --- | --- |
| Direct | Small traces | Exact visible marks |
| Decimated | Long lines and areas | Viewport-sized extrema |
| Density | Dense scatter overviews | A fixed-size grid and sample |
| Refined | A narrower live view | A recomputed aggregate or exact points |

Geometry is offset-encoded to `float32` for efficient GPU upload while keeping
visible differences in large values such as timestamps.

### 3. Draw and interact

The browser uses WebGL2 for marks and density textures, a 2D canvas for grid
lines and axis rules, and the DOM for labels, legends, tooltips, controls, and
accessible chart chrome.

Pan and zoom update locally first. When a live host is available, the browser
can request a refined view or resolve selections against exact source rows.
Sequence numbers prevent late replies from replacing a newer view.

CSS and Tailwind style DOM elements. Validated mark, axis, and theme styles have
renderer-specific coverage for WebGL, SVG, and native PNG; arbitrary browser
CSS does not carry into native exports. See
[Customize Each Part](/docs/xy/styling/customize/).

## Why it stays fast

~~~text
Conventional path: O(N) encode + transfer + parse + draw
XYG tiered path:    O(N) ingest/reduce + O(P) transfer + draw

N = source rows
P = detail useful at the current pixel resolution
~~~

XYG still has to inspect source data. Its advantage is that every source row
does not automatically become a browser object:

- Native columnar kernels avoid Python object loops for data-heavy work.
- Binary buffers avoid formatting and parsing large numeric JSON payloads.
- Line reduction and density grids avoid drawing detail the screen cannot show.
- Retained GPU buffers and local interaction avoid rebuilding the chart on
  every pointer movement.

This focused design is the foundation for making every chart faster. The
[benchmark snapshot](/docs/xy/overview/benchmarks/) publishes those contracts
and records when XYG uses a reduced representation.

## Runtime and output choices

| Target | Behavior |
| --- | --- |
| Notebook or native application | Live host callbacks and supported view refinement |
| Standalone HTML | Embedded browser client and initial data; no Python server |
| Native PNG | Browser-free Rust rasterization |
| Chromium PNG | Browser rendering when CSS and WebGL fidelity matter |
| SVG | Vector output for supported marks and chart chrome |

The chart definition stays the same; only the renderer and live capabilities
change. See [Runtime and Deployment](/docs/xy/advanced/runtime-and-deployment/)
for the full decision guide.

## Key boundaries

- Exact columns are authoritative; render and GPU buffers are replaceable.
- Numeric columns use binary transport; JSON describes structure and metadata.
- Reduced traces are identified as reduced and never presented as exact marks.
- Render work is bounded by the visible result, but ingest can still scale with
  source-data size.
- Rust owns processing and decisions that change shipped geometry, LOD,
  encodings, layout, ticks, or recorded outcomes. Python and Node pack inputs
  and manage host lifecycle; browser WASM invokes that same engine, and the
  browser painter owns drawing and immediate interaction.
- The core chart API stays independent of notebooks and application frameworks.

For public callback contracts, continue to
[Events and Callbacks](/docs/xy/api-reference/events-and-callbacks/). For APIs
still changing before 1.0, see
[Limitations and Alpha Status](/docs/xy/api-reference/limitations-and-alpha-status/).
