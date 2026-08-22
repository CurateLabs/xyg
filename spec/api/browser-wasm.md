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

Cancellation, supersession, and disposal clear bounded staging and suppress
late paint. Compile work runs in an isolated same-origin module Worker so
termination can interrupt Rust expansion, Scene encoding, or painter lowering
without disposing the caller's lifecycle Worker. Rust remains authoritative for identities, defaults, domains,
geometry, canonical Scene encoding, and painter lowering; TypeScript only
frames transferable columns and schedules lifecycle checkpoints.
