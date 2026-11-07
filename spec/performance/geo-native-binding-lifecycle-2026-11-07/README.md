# Native temporal geographic binding lifecycle repair

This correction preserves candidate `bfb7aaec` and its earlier evidence. It fixes
three independently reported review findings: controller notifications from a
foreign thread now dispatch to the binding's owning event loop before intent or
task mutation; source-triggered cancellation becomes an operation error while
retaining the last accepted snapshot and permitting explicit cleanup; stale Node
unsubscribe closures cannot remove a replacement subscription set.

The retained source increments its cancellation generation only when it cancels
another active task. Binding waits remain shielded from caller cancellation.
Async source close still drains the active storage callback, and binding close
releases private owners and registration. Independent caller frame leases survive.
The async reader fixture acknowledges its read after cancellation begins; it does
not assume storage callbacks terminate instantly. No geographic filtering,
projection, membership, LOD, layout or export policy moves into either host.

Reproduce with explicit `XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so`:

```sh
uv run pytest tests/test_geo_temporal_binding.py tests/test_geo_retained.py tests/test_geo_retained_components.py tests/test_temporal_controller.py -q
node --test packages/xy-node/test/geo-temporal-binding.test.mjs packages/xy-node/test/temporal-controller.test.mjs packages/xy-node/test/geo-frame-leases.test.mjs
uv run pytest tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py -q
uv run python scripts/abi_smoke.py
uv run ty check
```

`checks.json` binds commands, artifacts and lossless logs. Original-method negative
controls reproduce the three Python failures; the prior Node unsubscribe fails
its resubscription regression. Initial cancellation fixtures that never released
the storage callback were interrupted, not passes; their partial output is
preserved. Mistyped module paths collected no tests and receive no pass credit.
System Python differs from the project's test interpreter; both are recorded.
Rust and client producer inputs are unchanged and their artifacts are reused by
verified digest. No browser run, rebuild, scale or WASM execution is claimed.

This is not issue or milestone acceptance. Mounted native notebook/VS Code
replacement, mixed tiles, all-host exports/accessibility, massive-scale and the
broader #50/#39/M6 requirements remain open. The candidate still needs accepted
current-main integration, independent final review, fresh CI and queue delivery.

Fresh correction validation passes 66 Python tests, 19 Node tests, 33 Core
binding/inventory tests and 673 ABI checks. Type checking fails with ten
diagnostics, independently reproduced against an immutable archive of the
original bfb candidate (four missing private-publication override parameters
and six heterogeneous-query inference errors). This is a delivery blocker,
not a waiver or pass; it remains to repair before final candidate delivery.
The interrupted initial fixture runs and mistyped paths are not credited.
