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

## Cross-host fixture contract

Regenerate `tests/fixtures/xyts_cross_host.json` with
`cargo run -p xyg-wasm --bin xyts_conformance`; use `-- --check` in validation.
The JSON carries canonical XYTS requests plus exact Scene v14 and painter v11
bytes. Browser tests submit the requests to a real Worker/WASM instance. Native
Python, native Node, and Pyodide validate the resulting Scene through their
Rust consumers, because XYTS itself is browser-only ingress. Consumers must
not copy its default, identity, overflow, or bar-width policy.
