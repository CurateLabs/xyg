# `@curatelabs/xyg`

Host-neutral WebGL2 **paint client** for XYG. One TypeScript source tree
(`js/src`) builds this package; Python copies the same bundles into the
wheel so notebooks / `to_html()` / Reflex need no Node.

```bash
npm install @curatelabs/xyg
```

Registry publish is blocked on the `@curatelabs` npm org ([#13](https://github.com/CurateLabs/xyg/issues/13)).
Until then this package is in-repo: build with `npm ci && node js/build.mjs`
from the repository root.

| Export | Format | Use |
| --- | --- | --- |
| `.` (`dist/index.js`) | ESM | `render` / `renderStandalone` for bundlers and anywidget |
| `./standalone` (`dist/standalone.js`) | IIFE `window.xy` | Inline HTML (`toHtml` / `to_html`) and VS Code webviews |
| `./wasm-worker` (`dist/wasm-worker.js`) | Static module Worker | Explicit direct-browser Rust/WASM lifecycle foundation (#59) |
| `./xyg-wasm.wasm` (`dist/xyg-wasm.wasm`) | Raw WebAssembly | Same safe `xyg-engine`, compiled without native raster/PNG |

The raw WASM artifact is not produced by `js/build.mjs`. Build it with
`npm run build:wasm`, which compiles `xyg-wasm` for `wasm32-unknown-unknown`
and packages the validated bytes into `dist/xyg-wasm.wasm`.

Release tarballs also include `ASSET-MANIFEST.json`: it records the exact
SHA-256 and byte length of all four assets plus their wire protocol, WASM ABI,
Scene, and painter versions. Treat that manifest as the local/offline asset
contract; deploy all four files from one package version and never mix assets
across releases.

The direct-browser foundation requires callers to provide both an explicit
static worker URL and an explicit local WASM URL, `WebAssembly.Module`, or byte
buffer. It never creates a Blob worker, guesses an asset path, imports from a
CDN, or silently runs chart algorithms in JavaScript. The worker currently
proves bounded memory/lifecycle handling, Scene validate/paint, packed
typed-column (`XYCC`) compile for scatter/polyline/rect/band, and packed
progressive CoSE (`XYGL`/`XYGO`) with cancellation, revisions, pins, compounds,
and explicit scheduler bounds. `attachWasmTicks(view, { worker })` additionally
cuts automatic primary Cartesian linear/log/symlog ChartView ticks to the
Rust-owned `XYTK`/`XYTO` lane. Category/time/polar, secondary axes, colorbars,
authored ticks, and self-contained hosts remain compatibility/follow-up paths.
`encodeWasmCose` plus
`XygWasmWorker.layoutCose` keep every force tick in Rust inside the Worker;
remaining all-host cutovers and hosted evidence stay tracked by
[#59](https://github.com/CurateLabs/xyg/issues/59).

The Node host (`packages/xy-node`, published later as `@curatelabs/xyg-node`)
must not import this module as a runtime WebGL graph — it **inlines**
`standalone.js` as text. This package must not import `koffi` or `node:fs`.
