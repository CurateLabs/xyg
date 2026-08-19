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

The direct-browser foundation requires callers to provide both an explicit
static worker URL and an explicit local WASM URL, `WebAssembly.Module`, or byte
buffer. It never creates a Blob worker, guesses an asset path, imports from a
CDN, or silently runs chart algorithms in JavaScript. The worker currently
proves bounded memory/lifecycle handling and exact canonical Scene v3
compatibility; complete browser-side chart compilation remains tracked by
[#59](https://github.com/CurateLabs/xyg/issues/59).

The Node host (`packages/xy-node`, published later as `@curatelabs/xyg-node`)
must not import this module as a runtime WebGL graph — it **inlines**
`standalone.js` as text. This package must not import `koffi` or `node:fs`.
