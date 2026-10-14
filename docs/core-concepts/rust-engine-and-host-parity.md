---
title: Rust Engine and Host Parity
description: Why XYG moved processing and visual-output policy from Python into Rust, and what parity means across Python, Node, and browser WASM.
---

# Rust engine and host parity

XYG began as a fork of upstream XY for GraphForge's billion-scale graph visualization
needs. The inherited architecture placed chart decisions in Python. We moved
data processing and decisions that affect visual output into the Rust core so
Python, Node, and browser WASM can use one implementation.

Moving only slow loops would leave each host choosing different domains,
budgets, layouts, encodings, or defaults. XYG's placement rule covers those
decisions too: **Rust owns behavior that changes buffers, layout, encodings,
level of detail, or recorded outcomes.** Hosts own idiomatic authoring,
input packaging, transport, display integration, and application lifecycle.

## What moved into Rust

The migration includes row scans and policy across graph and chart families:

| Concern | Shared engine responsibility |
| --- | --- |
| GraphForge results | Arrow schema recognition, UUID joins, generation checks, provenance, composition planes, and diagnostic codes |
| Graph visualization | Display layout, force ticks, graph LOD budgets, edge membership, and semantic geometry |
| Large data | Range/filter indices, density binning, line decimation, pyramid/tile operations, and representation choices |
| Chart geometry and statistics | Histogram and distribution reductions, triangulation, contours, curves, and supported mark expansion |
| Numeric precision and paint buffers | Canonical f64 handling, finite-value validation, offset-f32 lowering, color/channel encoding, and buffer budgets |
| Axes and static output | Shared packed tick generation/formatting, supported Scene layout/lowering, and static-document export policy |

These are examples of the current engine's responsibilities, not a guarantee
that every public authoring or export feature is available on all hosts.
The [ownership audit](https://github.com/CurateLabs/xyg/blob/main/spec/design/ownership-audit.md)
records remaining compatibility and presentation code, and its destination.

## One engine, three hosts

Python loads `libxyg_core` through `ctypes`; Node loads the same native C ABI
through `koffi`. The ABI declarations are generated from Rust and versioned
with the library. Neither host silently falls back to a separate numerical
engine when the core cannot load.

Browser WASM compiles `xyg-engine` through `xyg-wasm` and runs it in a Worker.
TypeScript frames typed requests and transfers buffers; Rust validates and
lowers them to the painter contract. The browser client owns WebGL2 drawing,
picking, gestures, DOM chrome, accessibility, transitions, caches, and request
scheduling. It does not maintain a second layout or aggregation algorithm.

A notebook, standalone document, and VS Code webview can all use the same
painter. They differ in where compute runs and whether a live host is
available. A native Node extension host requires no Python installation.

## What parity proves

Parity is a tested output contract. Identical admitted inputs should produce
the same Rust decisions and typed outputs across hosts; it is more precise
than making three APIs look alike.

- Python and Node GraphForge fixtures pin request and document digests.
  Native/WASM tests compare GraphForge documents and portable-layout Scenes
  byte for byte, including selection identity and coded failures.
- Packed tick fixtures compare native Python, native Node, and real-browser
  WASM outputs, including positions, labels, and authored provenance.
- The admitted Python/Node static-export registry compares Scene, SVG,
  raster-command, and PNG bytes, and checks decoded PNG pixels.

These proofs apply to the fixture contracts. They do not establish universal
pixel identity across browser font engines, identical performance on native
and WASM targets, or complete authoring-feature parity.

## Current boundaries

Python and Node provide native chart and GraphForge composition. Direct
browser WASM is a bounded host with supported compile, Scene, density, graph,
and tick operations; broader aggregate production and complete native-host
feature coverage remain in progress. Its rendered GraphForge Scene currently
has a 1,024-composed-node ceiling and a primitive budget. Native graph LOD is
the path for larger graph views.

Native hosts can use native threads and disk-backed paths where supported;
a browser Worker has different memory, staging, and filesystem constraints.
Using the same Rust source does not remove those constraints or make ingestion
independent of source size. Reduced drawing and transport can be bounded by
the viewport while preparation still scans source rows.

Browser CSS/Tailwind chrome and arbitrary DOM content do not automatically
carry into PNG, SVG, or PDF. The
[capability matrix](/docs/xy/styling/capabilities/) and
[export guide](/docs/xy/guides/display-and-export/) describe the supported
styling contracts. Compatibility paths remain explicitly recorded while their
shared Rust counterparts grow.

For implementation details and reproduction gates, read the
[host-parity specification](https://github.com/CurateLabs/xyg/blob/main/spec/design/host-parity.md),
[Rust placement rule](https://github.com/CurateLabs/xyg/blob/main/spec/design/rust-engine.md#1-the-placement-rule),
and [browser WASM boundary](https://github.com/CurateLabs/xyg/blob/main/spec/design/browser-wasm.md).
For a practical workflow, continue with
[Use with GraphForge](/docs/xy/integrations/graphforge/).
