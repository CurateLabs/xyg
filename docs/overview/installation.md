---
title: Installation
description: Install the published XYG alpha or build the current source, with explicit platform and integration requirements.
---

# Installation

XYG has Python, Node-native, and direct browser WASM hosts. These docs describe the current source
checkout, which may contain features ahead of the published alpha.
The Python host supports Python 3.11 and newer. As verified on 2026-10-14,
PyPI contains **0.0.1a2**. Install that release
with your preferred package manager:

~~~~md tabs
## uv

~~~bash
uv add "xyg==0.0.1a2"
~~~

## pip

~~~bash
python -m pip install "xyg==0.0.1a2"
~~~
~~~~

The host-neutral browser client (`@curatelabs/xyg`) and Node host
(`@curatelabs/xyg-node`) are source-checkout packages. Neither is published to
npm as of the verification date above. See the
[Node package guide](https://github.com/CurateLabs/xyg/tree/main/packages/xy-node)
for source setup.

Confirm the package imports from the environment where your code will run:

~~~bash
python -c "import xyg; print(xyg.__version__)"
~~~

Compiling a chart also requires the native core; a successful lazy import alone
is not a native-backend check.

## Supported platforms and published artifacts

The source build and release pipeline target the platforms below. The PyPI
column describes the actual **0.0.1a2** artifacts, rather than inferring
publication from a successful build or release rehearsal.

| Platform | Source/release target | Architectures | PyPI 0.0.1a2 wheel |
| --- | --- | --- | --- |
| macOS | macOS 10.12+ on Intel; macOS 11+ on Apple silicon | `x86_64`, `arm64` | Not published |
| Linux | glibc native builds | `x86_64`, `aarch64`, `armv7l` | `manylinux_2_39_x86_64` only (glibc 2.39+) |
| Linux | musl builds, including Alpine | `x86_64`, `aarch64`, `armv7l` | Not published |
| Windows | Native Windows | `x86_64`, `x86`, `arm64` | Not published |
| WebAssembly | Pyodide 314 (Emscripten, PEP 783) | `wasm32` | Not published |

PyPI also contains `xyg-0.0.1a2.tar.gz`. On targets without a compatible wheel,
installing that release requires Rust and the platform-specific toolchain.
The published source archive includes the prebuilt browser client, so it does
not require Node unless you rebuild that client. Windows requires Rust MSVC.
Inspect the [PyPI release files](https://pypi.org/project/xyg/#files) before
choosing a deployment platform.

The source pipeline builds and runtime-verifies a WebAssembly wheel targeting
PEP 783's `pyemscripten_2026_0_wasm32` platform. That wheel is not in the
verified PyPI release. In-browser Python requires an exact compatible built
wheel URL; package-name installation does not currently provide that target.
See [Notebooks](/docs/xy/integrations/notebooks/) for display behavior and
live-kernel boundaries after installing a compatible build.

## What the package includes

The regular `xyg` dependency installs NumPy and anywidget. You can author charts
with lists without creating NumPy arrays yourself. Native wheels carry the
Python package, browser client, and Rust core. Installing a compatible wheel
does not require Rust, Node, npm, or a CDN.

The current source supports notebook display and HTML, PNG, SVG, and PDF
export without separate `notebooks` or `export` extras. Renderer coverage is
listed in [Display and export](/docs/xy/guides/display-and-export/); source
capabilities are not a claim about every feature in the published alpha.

## Node and browser WASM

**Node.js** uses `@curatelabs/xyg-node`: native chart and GraphForge composition
over the same Rust C ABI as Python. It serves Node applications and VS Code
extension hosts without a Python runtime. Follow the
[Node setup guide](https://github.com/CurateLabs/xyg/tree/main/packages/xy-node)
to build/stage the native library and install the package's dependencies.
Build the host-neutral client for `toHtml()` and webview output.

**Direct browser WASM** uses the Worker API in `@curatelabs/xyg`, including
`createXygWasmWorker` and `renderWasmChart`. It runs the shared Rust engine in a
browser Worker without a Python or Node server. Its current compile, graph,
density, and tick operations have explicit bounds; it is not yet a complete
authoring host for every native chart feature. See the
[browser WASM contract](https://github.com/CurateLabs/xyg/blob/main/spec/api/browser-wasm.md)
and [client setup guide](https://github.com/CurateLabs/xyg/tree/main/packages/xy-client).

From a source checkout, install the Rust `wasm32-unknown-unknown` target,
build the browser client, and build/package the WASM module:

~~~bash
rustup target add wasm32-unknown-unknown
npm ci
node js/build.mjs
npm run build:wasm
~~~

Serve the static module Worker and WASM assets at explicit same-origin URLs
from the same build. This direct browser host is separate from running the
Python package inside Pyodide. Both npm packages remain unpublished in the
registry snapshot above.

## Building the current source

A source checkout requires Rust (`cargo` and `rustc`), Node/npm, and the
platform toolchain. Build the core and browser client before using charts:

~~~bash
git clone https://github.com/CurateLabs/xyg.git
cd xyg
cargo build --release
npm ci
node js/build.mjs
uv venv
uv pip install .
~~~

The browser build writes `packages/xy-client/dist` and copies the client into
`python/xyg/static`. Those generated bundles are not committed. The packaging
hook builds and includes the core and client in distributions.
Pin a reviewed XYG commit when deploying from source. Bare `v0.0.1` tags belong
to upstream history, not the XYG release line, whose tags begin with `xyg-v`.
A missing native core raises when a chart first needs compute; there is no
NumPy fallback.

## Optional tools and integrations

- Install `pyarrow` separately when you want Arrow-backed input:

  ~~~bash
  uv add pyarrow
  ~~~

- For GraphForge results, use XYG's built-in composition helpers. They accept
  canonical Arrow IPC bytes without importing GraphForge or requiring
  `pyarrow`. Run GraphForge Core in its native Python, Node, or CLI host,
  then pass its results to XYG. See
  [Use with GraphForge](/docs/xy/integrations/graphforge/).

- Native PNG is the default static raster path and does not launch a browser.
  Chromium-based PNG export is optional and discovers Chrome, Chromium, Edge,
  or `chrome-headless-shell` on the machine; set `XYG_BROWSER` to an executable
  path when automatic discovery is not appropriate.

Next, build [your first chart](/docs/xy/overview/first-chart/).
