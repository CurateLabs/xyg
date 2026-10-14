---
title: Choosing a Runtime and Deployment Mode
description: Choose Python, native Node, or bounded browser WASM for GraphForge views, notebooks, applications, and static output.
---

# Choosing a runtime and deployment mode

Choose where the data and application already live. XYG has Python, Node-native,
and browser WASM hosts over one Rust engine. It is a visualization engine, not
an application framework. Your application owns UI, state, deployment, and
message routing.

| Workflow | Compute host | Display and output |
| --- | --- | --- |
| Python analysis | Python with the native Rust core | Notebook widget, standalone HTML, supported static export |
| GraphForge editor or Node application | Native Node with the same Rust C ABI | Local browser client/webview, HTML, supported static export |
| Results already in a browser | Bounded Rust/WASM Worker | Shared browser painter and supported Scene operations |
| Published snapshot | Compute in a supported authoring host before publication | Self-contained HTML or PNG/SVG/PDF within renderer coverage |

## Use with GraphForge

GraphForge Core runs queries and algorithms natively. Send its canonical Arrow
results, source generation, and explicit visualization intent to XYG. For the
GraphForge editor, compose in the Node extension host and paint in the
webview; this keeps large graph compute near the data and avoids requiring
Python. Browser WASM is available for browser contexts within its current
bounds, including the 1,024-composed-node rendered GraphForge Scene limit.

See [Use with GraphForge](/docs/xy/integrations/graphforge/) for both native
webview and direct-WASM workflows. XYG does not execute GraphForge Core in a
browser or on the Hub.

## Live compute versus snapshots

A notebook widget can call a live Python kernel for exact selection and
supported refinement. A Node application can retain its native figure and
route browser events back to it. Direct browser WASM performs only the
operations admitted by its bounded API.

Standalone HTML remains interactive locally but is a snapshot: it cannot call
Python handlers or receive subsequent `chart.append(...)` calls. Static images
have no live interaction. CSS, fonts, mark styling, and export coverage also
differ by renderer; use the [capability matrix](/docs/xy/styling/capabilities/)
when you need the same design in several outputs.

## Deployment setup

Python wheels carry the native library and a prebuilt browser client. Source
checkouts need both built before export or notebook display. Node uses its
native platform package or an explicit development library path; `toHtml()`
uses the host-neutral client, not Python's static directory.

Direct WASM deployments serve the client, module Worker, and WASM from the
same build at explicit local asset URLs. Respect the host's CSP and Worker
restrictions, especially in a VS Code webview. See
[Installation](/docs/xy/overview/installation/),
[Serving, CSP, and offline use](/docs/xy/guides/serving-csp-and-offline-use/), and
[Deployment recipes](/docs/xy/guides/deployment-recipes/).

Native and WASM hosts share engine behavior on supported contracts, while
feature coverage and resource limits remain explicit. Read
[Rust engine and host parity](/docs/xy/core-concepts/rust-engine-and-host-parity/)
before choosing a browser-only deployment for a native workload.
