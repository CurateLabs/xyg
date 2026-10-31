---
title: Serving, CSP, and Offline Use
description: Serve bundled XYG assets under CSP and operate without a CDN or network access.
---

# Serving, CSP, and Offline Use

Published XYG wheels contain the Python package, native core, and versioned
JavaScript/WebGL client. Notebook display and standalone export do not load
XYG from a CDN.

## Offline Environments

Once the required wheels are installed, normal chart construction, notebook
display, native PNG, SVG, and standalone HTML export need no network access.
Prepare compatible platform wheels in advance for an air-gapped installation;
a source build still requires the Rust toolchain.

Chromium PNG export needs a supported browser installed locally, but does not
fetch one. The default native PNG engine has no browser requirement.

## Standalone HTML Policy

`chart.to_html()` creates one portable file containing its data, styles, and
render client. The document emits a defensive `Content-Security-Policy` that
blocks external connections, objects, forms, and base-URL changes. Density
refinement can start a worker from the bundled source, so the policy allows
`worker-src blob:`; it does not allow an external worker script.

Two `data:` allowances keep the file self-contained: `img-src data:` for
embedded raster content, and `font-src data:` so a `custom_css` `@font-face`
can carry a brand face inline. Neither permits a network origin, so a
standalone chart still loads nothing from the network.

Portable single-file output necessarily uses inline script and style blocks.
Its policy therefore includes `script-src 'unsafe-inline'` and
`style-src 'unsafe-inline'`. `custom_css=` is added to that inline author
stylesheet.

~~~md alert warning
### Strict Nonce or Hash Policies

Do not embed standalone HTML unchanged in a host that forbids inline scripts
or styles. A nonce/hash-only deployment needs an application wrapper that
serves the bundled JavaScript separately and injects chart data and styles
through the host's nonce- or hash-aware path.
~~~

## GraphForge applications and webviews

Compose GraphForge results in a native Python or Node host, then serve the
local XYG painter and typed binary payload. In a Node extension host, use
`await graphforgeWebviewPayload(owner, input, options)` with one
`GraphForgeLayoutController` per view. Relay picks to
`graphforgePick(payload, composition, hit)` and await `owner.dispose()` during
teardown. Keep full source positions and pick membership at the Node host;
only the spec and binary painter buffer go to the webview. The webview owns
display rather than graph computation.

The direct browser WASM path serves a module Worker and matching WASM asset at
explicit same-origin URLs. Strict hosting needs `wasm-unsafe-eval` for WASM
compilation and a Worker directive for the local Worker. VS Code webviews use
their local resource origin and documented Blob-Worker setup. Follow
[Use with GraphForge](/docs/xy/integrations/graphforge/) for the supported
paths and size bounds, and test the application's complete policy.

## Self-Contained Does Not Mean Live

A standalone HTML file remains interactive in its browser, but it is a
snapshot. It cannot call Python event handlers or receive future
`chart.append(...)` calls. Use a notebook widget or framework adapter when the
browser must communicate with a Python process.
