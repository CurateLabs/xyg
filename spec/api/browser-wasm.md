# Direct-browser WASM API

`createXygWasmWorker` owns one bounded Rust/WASM engine instance. Low-level
compile methods return an `XygWasmTask`: await `task.result`, or call
`task.cancel()` to reject it with `XygWasmError.code === "XYG_WASM_CANCELLED"`.
Sequences are monotonic; newer work supersedes older work and stale work cannot
publish painter bytes.

`renderWasmChart` returns an `XygWasmChartHandle`. `update(chart)` starts a
checkpointed `XYTS` compile, `cancel()` cancels the active update without
disposing a borrowed Worker, and `dispose()` cancels work and releases painter
resources. A handle created with `workerOwnership: "own"` also disposes its
Worker. Caller arrays remain attached unless `dataOwnership: "transfer"` is
selected explicitly.

```js
const worker = createXygWasmWorker({ workerUrl, wasm, maxArenaBytes });
const chart = await renderWasmChart({ el, worker, chart: initialChart });
const update = chart.update(nextChart);
chart.cancel();
await update; // rejects with XYG_WASM_CANCELLED
await chart.dispose();
await worker.dispose(); // required for the default borrowed ownership
```

Every Worker-reported `XygWasmError` after the Rust instance initializes
carries a read-only `diagnostics` snapshot. Locally rejected argument,
messaging, cancellation, and initialization errors use `null`. The snapshot
exposes Rust's cumulative staging `copyCount`, split-u64
`copyBytesLo` / `copyBytesHi`, arena and linear-memory high-water bytes, and
the last Scene record/style counts without exposing source values. This makes
resource-limit failures inspectable without logging user data. Callers must
null-check `diagnostics`; initialization, messaging, or pre-Worker argument
failures have no authoritative Rust snapshot.

Cancellation, supersession, and disposal clear bounded staging and suppress
late paint. Compile work runs in an isolated same-origin module Worker so
termination can interrupt Rust expansion, Scene encoding, or painter lowering
without disposing the caller's lifecycle Worker. Rust remains authoritative for identities, defaults, domains,
geometry, canonical Scene encoding, and painter lowering; TypeScript only
frames transferable columns and schedules lifecycle checkpoints.

## Opt-in ChartView density refinement

`attachWasmDensity(view, { worker, input })` attaches the Rust `XYAG` to
`XYAO` aggregate seam to explicitly sourced already-painted Cartesian density
scatters. It is
explicit: standalone and kernel-backed ChartViews retain their existing routes
until an application attaches a handle. Once attached, it intercepts the
normal viewport refinement before a kernel `density_view` fallback is sent. The source
columns are canonical `Float64Array` values owned by the caller; an optional
`Uint8Array` supplies four straight-alpha RGBA8 bytes per point. Rust owns
binning, mean-color aggregation, aggregate bounds, and all resource counters.

```js
const density = await attachWasmDensity(view, {
  worker,
  input: { traceId: 0, x, y, rgba },
  // Borrowed by default: dispose `worker` separately.
  workerOwnership: "borrow",
});

// ChartView calls this on its normal viewport refinement path.
// An application may request a specific view explicitly as well.
density.schedule({ ranges: { x: [xmin, xmax], y: [ymin, ymax] } });
const metrics = density.diagnostics();
await density.dispose();
```

Each scheduled viewport cancels the preceding aggregate and only a result with
the current viewport sequence may upload a grid. The existing density surface
remains visible during the request; stale, destroyed, or lost-context results
never paint. `dispose()` clears pending work and, with
`workerOwnership: "own"`, disposes the dedicated Worker. `diagnostics()`
returns the current successful sequence plus Rust-owned `copyCount`, split-u64
copy bytes, arena bytes/high-water, and linear-memory bytes/high-water; it
returns `null` before a successful aggregate or after a failure.

Worker-reported failures dispatch a bubbling `xy:wasm_density_error`
`CustomEvent` on the ChartView root. Its detail is `{ code, message,
diagnostics, traceId }`, where `code` is the stable `XygWasmError` code and diagnostics
is either the Rust snapshot or `null`. `traceId` identifies the failed explicit
source. It never includes source values. The
supported contract accepts either `input` for one trace or `inputs` for
distinct trace ids. A single WASM instance deliberately processes those inputs
in order: each remains a separate Rust-owned request and therefore retains its
own axis scale without TypeScript aggregation. A newer viewport cancels the
active request and prevents the remaining old viewport inputs from publishing.
`diagnostics()` identifies the trace that produced its latest snapshot.
While automatic source provisioning, fallback deletion, and claims of full-product
density parity remain outside this API.

## Cross-host fixture contract

Regenerate `tests/fixtures/xyts_cross_host.json` with
`cargo run -p xyg-wasm --bin xyts_conformance`; use `-- --check` in validation.
The JSON carries canonical XYTS requests plus exact Scene v20 and painter v13
bytes. Browser tests submit the requests to a real Worker/WASM instance. Native
Python, native Node, and Pyodide validate the resulting Scene through their
Rust consumers, because XYTS itself is browser-only ingress. Consumers must
not copy its default, identity, overflow, or bar-width policy.

The strict-CSP direct-browser smoke also hydrates the checked-in
`tests/fixtures/authored_scene_v20.json` fixture through that same Worker. The
fixture is byte-for-byte output of the public Python `Figure` workload and
carries the supported Cartesian authored-chrome subset together: chart/plot
backgrounds, axes, primary legend, literal banded colorbar with Rust-resolved
major/minor ticks, and a fixed-background callout. The smoke asserts the
browser's structural and computed-style projection under `default-src 'none'`
and same-origin `script-src`/`worker-src`; it is not evidence for polar,
custom-font, CSS/class, or richer annotation semantics.
