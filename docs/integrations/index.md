---
title: Integrations
description: Use GraphForge results with XYG in Python, Node, browser WASM, notebooks, and Matplotlib-shaped workflows.
---

# Integrations

XYG's shared Rust engine has Python, Node-native, and browser WASM hosts.
[Choose a host](/docs/xy/overview/installation/#node-and-browser-wasm) for native
chart composition or the bounded direct browser Worker API.

- [Use with GraphForge](/docs/xy/integrations/graphforge/) covers canonical
  Arrow results, analytical layers, graph identity, and VS Code webviews.
  GraphForge computes; XYG composes and renders.
- [Notebooks](/docs/xy/integrations/notebooks/) covers Jupyter, JupyterLab,
  VS Code, Colab, and Marimo through one bundled `anywidget` implementation.
- [Matplotlib (`xyg.pyplot`)](/docs/xy/integrations/matplotlib/) covers the
  compatibility boundary and migration to XYG's declarative API.

The native Python and Node hosts share one C ABI. Direct-browser WASM runs the
same Rust engine in a Worker with bounded feature coverage. Read
[Rust engine and host parity](/docs/xy/core-concepts/rust-engine-and-host-parity/)
for the common behavior and remaining boundaries.
