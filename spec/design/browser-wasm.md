# Direct-browser Rust/WASM boundary

**Status:** bounded lifecycle/toolchain foundation, **not** a complete direct-browser
chart host. Tracking: [#59](https://github.com/CurateLabs/xyg/issues/59).
Canonical scene dependency: [Scene v3](scene-ir.md).

## Runtime taxonomy

Direct-browser WASM is the safe `xyg-engine` compiled for
`wasm32-unknown-unknown` and hosted in a static module Worker. It is distinct
from both:

- the native Python/Node C ABI (`xyg-core`); and
- the Pyodide/PyEmscripten Python wheel, which runs CPython in the browser.

There is no separate “WASM implementation.” Rust owns engine decisions, the
Worker adapter owns memory/lifecycle/status transport, and the existing
TypeScript/WebGL client retains paint, pick, gestures, accessibility, and DOM
chrome.

## Foundation artifacts

| Artifact | Role |
| --- | --- |
| `crates/xyg-wasm` | Minimal raw-export adapter over `xyg-engine`; no `wasm-bindgen`, browser framework, renderer, or host algorithm |
| `spec/wasm/abi.json` | Versioned raw-export/status manifest |
| `js/src/wasm_abi_generated.ts` | Generated export validator and typed declarations |
| `js/src/wasm_worker.ts` | Static strict-CSP module Worker |
| `js/src/47_wasm.ts` | Main-thread lifecycle proxy; requires explicit worker and WASM assets |
| `dist/xyg-wasm.wasm` | Separately built direct-browser engine adapter; never copied into the Python static tree |

The WASM adapter disables `xyg-engine`'s default `raster` feature. Native
SVG/PNG/PDF export remains a native-host concern; browser output reuses the
shared painter. The raw module must request no ambient WebAssembly imports.

## Memory and copy contract

An ordinary JavaScript `ArrayBuffer` cannot alias wasm32 linear memory. The
default contract is therefore:

1. Canonical typed source stays in JavaScript-owned buffers.
2. Moving a buffer to the Worker uses `postMessage` transfer by default, so it
   does not clone the payload between main thread and Worker.
3. The Worker copies only the bounded operation slice into a reusable WASM
   staging arena. The Rust adapter enforces the per-instance logical bound and
   a 64 MiB compile-time ceiling.
4. Rust validates or computes from that slice. Outputs remain bounded scene/LOD
   records and are copied or transferred back as their contracts require.
5. The arena's logical length returns to zero. wasm32 pages may remain reserved
   because WebAssembly memory cannot shrink; the budget prevents unbounded
   ratcheting.

Future full-data algorithms must stream bounded chunks through the arena or use
an explicitly measured alternative. They must not claim zero-copy JS→WASM
aliasing. `SharedArrayBuffer` is an optional future optimization that requires
an isolated context; this foundation rejects it explicitly rather than
silently cloning or changing ownership.

The foundation diagnostics report copy count, split-u64 copied bytes, current
logical arena length, scene record/style counts, ABI version, and scene version.
The Worker normalizes semantically unsigned wasm32 results before exposing
them, so a set high bit in either copied-byte half remains a non-negative u32.
They never log user values.

## Version and scene contract

`WASM_ABI_VERSION` starts at 1. `SCENE_VERSION` remains independently versioned
at 3. `scripts/gen_wasm_abi.py --check` rejects parameter/result drift among
the manifest, raw Rust exports, generated TypeScript declarations, and the Rust
scene constant. `js/package-wasm.mjs` parses the compiled module's type,
function, and export sections and rejects artifact-level signature drift.

The only scene operation in this slice is allocation-free validation of an
already canonical Scene v3 batch. That establishes exact integration without
inventing a provisional browser chart schema. It does **not** compile a public
chart specification or satisfy #59's scatter/line/bar acceptance criteria.

## Lifecycle and failure model

- Instance handles carry a generation and fail closed after disposal; stale
  handles cannot access a reused slot.
- At most 64 instances exist per module. Each instance has an explicit arena
  budget no greater than 64 MiB.
- Sequence zero is reserved. Lower/repeated sequences fail as stale. Cancelled
  sequences fail with a stable cancelled status. The Worker defers queued work
  one task turn so already-posted cancellation can suppress it; future long
  Rust operations must add cooperative checkpoints.
- Traps invalidate and dispose the Worker-side Rust instance. Callers must
  create a fresh Worker rather than continue with uncertain engine state.
- Invalid sources fail before Worker allocation. Initialization-send failures
  and unreadable Worker messages terminate immediately; disposal waits at most
  one second for cooperative cleanup before terminating the Worker.
- Unsupported operations, incompatible versions, malformed scenes, invalid
  ranges, and resource bounds return stable error codes. There is no silent
  JavaScript algorithm or remote-service fallback.

## CSP, offline, and asset loading

Both assets are explicit:

```js
const engine = createXygWasmWorker({
  workerUrl: new URL("./wasm-worker.js", import.meta.url),
  wasm: compiledModule, // or explicit local URL / bytes
});
```

The library never uses `Blob`, `eval`, a CDN, default URL, or path probing.
URL-based WASM loading performs one non-redirecting fetch of the exact
caller-provided URL; redirects fail initialization rather than changing the
asset authority. `Module`/bytes loading performs no WASM fetch. A strict policy needs
`script-src 'self' 'wasm-unsafe-eval'`, `worker-src 'self'`, and
`connect-src 'self'` when a local WASM URL is used. `wasm-unsafe-eval` permits
WebAssembly compilation; it does not permit JavaScript `eval`.

`scripts/wasm_foundation_smoke.mjs` serves an allowlisted local-only asset set
under that CSP and tests explicit Module/bytes/URL loading, transfer and copy
diagnostics, lifecycle, cancellation, stale sequence, malformed module/scene,
resource bounds, redirect rejection, a real runtime trap, and disposal. It
also verifies unsigned split-u64 accounting across the `0x80000000` boundary
and that an invalid source is rejected before a Worker is allocated.

## Build and evidence

The repository pins Rust 1.88.0 and CI installs the
`wasm32-unknown-unknown` target explicitly:

```bash
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
node scripts/wasm_foundation_smoke.mjs
```

The CI artifact is compile- and runtime-verified. This slice makes no startup,
throughput, memory, or bundle-size win claim. Those budgets and comparisons
must be established through the repository's hosted CodSpeed workflow before
#59 can close; raw local timings are not performance evidence.

## Remaining #59 work

- typed column and chart-spec ingest;
- Rust Scene v3 production for the first scatter/line/bar/aggregate slice;
- integration with the existing WebGL painter and export path;
- native Python/Node/WASM/Pyodide conformance fixtures;
- cooperative cancellation inside long Rust operations;
- small-through-massive CodSpeed and browser budget evidence; and
- replacement (not expansion) of `46_worker.ts` only after WASM covers its
  density contract without regression.
