# Retained graph lifetime failures between commands

Greptile found that an idle Worker failure had no pending promise to reject, so the graph attachment never learned of it. A superseded temporal operation could also suppress the original transport cause and later report a generic disposed-lane error. The new idle regression fails against the approved predecessor bundle: whenIdle resolves rather than returning XYG_WASM_WORKER_TRAP.

The private graph lane now receives the Worker's failAll notification independently of command replies, captures its first failure once, and forwards it to the presenter before promise rejection/supersession. The presenter stops continuation, clears pending time, unsubscribes, settles idle waits and reports the first failure once. Later errors and disposed-lane refusals retain that cause. Superseded temporal work cannot suppress transport lifetime failure. No new public API, Rust/ABI/resource-cap change or replay of ambiguous commands occurs.

Four new real Worker cases cover idle and superseded temporal work, each with Worker error or messageerror. They require exact first cause/message, stable later idle rejection, zero subsequent graph commands, no late publications and unchanged accepted revision. All 14 retained temporal cases pass; the complete strict-CSP foundation, 69 existing attachment journeys, eight native/WASM wire tests, types, official inventory and assets pass. Normal foundation CI invokes these cases. Current source and Core/Git CRLF evidence are refreshed in successor bindings, with every predecessor receipt preserved.

Run with Node22, XYG_CHROMIUM pointing to the existing Chrome, XYG_NATIVE_LIB to the bound native library:

```sh
node js/build.mjs
XYG_GRAPH_TEMPORAL_ONLY=1 node scripts/graph_session_controller_wasm_smoke.mjs
node scripts/wasm_foundation_smoke.mjs
node scripts/graph_session_controller_wasm_smoke.mjs
node --test packages/xy-node/test/graph-session-wire.test.mjs
uv run --no-sync pytest -q tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py
uv run --no-sync ty check
```

The first browser launch used an overly long task TMPDIR socket path and failed before tests. It is retained without product-failure credit; the valid before/after use a short disk-backed task temp path. Native and shipping WASM are digest-reused, browser bundles rebuilt. No broad Python/Rust rebuild or competitor/scale result is claimed. Aggregate/exact membership, frozen exports, scale, full accessibility, timezones and broader authoring-state ingress remain open, as do #45/M5. Independent correction review, new-head CI and merge queue remain required.
