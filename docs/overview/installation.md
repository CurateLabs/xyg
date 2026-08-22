---
title: Installation
description: Install XY, understand its bundled runtime, and choose optional integrations.
---

# Installation

XY 0.0.1 supports Python 3.11 and newer. Install the released core package
from PyPI with your preferred package manager:

~~~~md tabs
## uv

~~~bash
uv add xyg
~~~

## pip

~~~bash
python -m pip install xyg
~~~
~~~~

JavaScript and browser users install the host-neutral paint client instead of
the Python wheel. The in-repo package name is `@curatelabs/xyg`; registry
publish waits on the `@curatelabs` npm org.

~~~bash
npm install @curatelabs/xyg
~~~

From a source checkout, build it once with `npm ci && node js/build.mjs`.
Node host bindings (`packages/xy-node`, `@curatelabs/xyg-node`) compose
charts and call `toHtml()` against that client — they do not read
`python/xyg/static`.

Confirm the Python package imports from the environment where your code will run:

~~~bash
python -c "import xyg; print(xy.__version__)"
~~~

## Supported platforms

XY supports the platforms below. The PyPI column describes only the files in
the current 0.0.1 upload, not whether XY supports the platform.

| Platform | Compatibility | Architectures | XY support | PyPI 0.0.1 wheel |
| --- | --- | --- | --- | --- |
| macOS | macOS 10.12+ on Intel; macOS 11+ on Apple silicon | `x86_64`, `arm64` | Supported | Included |
| Linux | glibc (`manylinux_2_17`) | `x86_64`, `aarch64`, `armv7l` | Supported | Included |
| Linux | musl (`musllinux_1_2`, including Alpine) | `x86_64`, `aarch64`, `armv7l` | Supported | Included |
| Windows | Native Windows | `x86_64`, `x86`, `arm64` | Supported | Not included |
| WebAssembly | Pyodide 314 (Emscripten, PEP 783) | `wasm32` | Supported | Not in 0.0.1 (on PyPI since 0.0.3) |

Windows is supported by XY's native core and release pipeline. The current
0.0.1 PyPI upload does not include Windows wheels or a source distribution, so
`uv add xyg` and `python -m pip install xyg` cannot install it directly on
Windows yet. Until a Windows wheel is published, install the tagged source
with a Rust MSVC toolchain as described below.

The runtime-verified WebAssembly wheel targets the standardized PEP 783
`pyemscripten_2026_0_wasm32` platform and, as of 0.0.3, is published to PyPI
alongside the native wheels. In-browser Python installs it by package name —
`micropip.install("xyg")`, or `%pip install xyg` in a JupyterLite notebook.
This target runs XY's Python and Rust core inside Pyodide; it is separate
from the JavaScript/WebGL client (`@curatelabs/xyg`, copied into every Python
wheel). See
[Notebooks](/docs/xy/integrations/notebooks/) for how charts display on WASM
kernels.

## What the package includes

The regular `xyg` dependency already includes NumPy and anywidget support.
Published platform wheels bundle the Python package, a **copy** of the
host-neutral browser client, and the native Rust compute core. Notebook
display and HTML, native PNG, and SVG export do not require separate
`notebooks` or `export` extras, Node, npm, or a CDN. JS/Node users install
`@curatelabs/xyg` (and the Node host) instead of the Python wheel.

## Installing from Git or source

Use the PyPI wheel when your platform is supported. A working source install
must compile the native compute core, so it requires a Rust toolchain with
`cargo` and `rustc`. The browser client is generated (`node js/build.mjs` →
`packages/xy-client/dist`, copied into `python/xyg/static`); published wheels
already carry the copy, so Node and npm are not required just to `pip install`
a wheel.

To reproduce the 0.0.1 release from Git with uv:

~~~bash
uv add "xyg @ git+https://github.com/CurateLabs/xyg.git@v0.0.1"
~~~

Or install the same tagged source with pip:

~~~bash
python -m pip install "xyg @ git+https://github.com/CurateLabs/xyg.git@v0.0.1"
~~~

A source build without Rust can finish installing, but it has no compute
backend and fails with an actionable error when a chart first needs native
compute. XY does not silently switch to a slower implementation. Building for
an unsupported operating system or architecture may also require target-specific
Rust tooling beyond the commands above.

## Optional tools and integrations

- Install `pyarrow` separately when you want Arrow-backed input:

  ~~~bash
  uv add pyarrow
  ~~~

- The bundled Reflex integration supports state-backed application charts and
  remains experimental. Install the extra to select a compatible Reflex
  version. With uv:

  ~~~bash
  uv add "xyg[reflex]"
  ~~~

  Or with pip:

  ~~~bash
  python -m pip install "xyg[reflex]"
  ~~~

  The `xyg` wheel already carries the `reflex_xy` integration; the extra adds
  only the supported Reflex dependency floor. Pin resolved versions for
  production deployments. Continue with the
  [Reflex integration guide](/docs/xy/integrations/reflex/) for its current
  limitations and setup.

- Native PNG is the default static raster path and does not launch a browser.
  Chromium-based PNG export is optional and discovers Chrome, Chromium, Edge,
  or `chrome-headless-shell` on the machine; set `XY_BROWSER` to an executable
  path when automatic discovery is not appropriate.

Next, build [your first chart](/docs/xy/overview/first-chart/).
