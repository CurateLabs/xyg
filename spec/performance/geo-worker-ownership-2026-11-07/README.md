# Geographic worker ownership and captured coordination delivery

PR1112 review identified an ownership gap when cancelling a binding pump awaiting a synchronous reader: `to_thread` continued, but its unpublished returned frame had no recipient. Close could complete before that worker. The pump now owns an executor Future independently of the event loop task cancellation sweep, drains it through repeated cancellation, and retires any unpublished private frame. Close drains terminal pump completion before releasing the accepted owner and source registration. A newly cancelled close caller receives CancelledError after teardown; previously handled cancellation does not prevent cleanup. Reader-originated cancellation remains an operation failure retaining accepted snapshots. A non-returning synchronous reader still prevents drain; no timeout is introduced.

Native Node coordination captures the observer-handle set once before delivery. Unsubscribe/resubscribe cannot extend its live Map iterator, and observers added by a callback receive future coordination delivery only. The ordinary controller subscription and terminal pass contracts are unchanged.

Reproductions include five explicit pump/close cancellation orders and real asyncio.run task shutdown with a blocked synchronous reader released during shutdown. All six fail against the exact prior binding module loaded into an otherwise unchanged test environment; all pass after repair. Earlier exploratory runs include a shutdown-fixture setup error and are retained without treating that error as evidence of a product failure. Additional Future tests cover reader-raised CancelledError, completed cancelled Futures, repeated waiter cancellation, and result/cancellation races. Python/Node focused gates and types passed. Current Core provenance and real Git CRLF checkout checks run against successor bindings; prior producer evidence remains immutable.

Reproduction from this worktree, with the explicit existing native artifact:

```sh
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
uv run --no-sync pytest -q tests/test_geo_temporal_binding.py tests/test_geoscale.py tests/test_temporal_controller.py tests/test_geo_frame_leases.py tests/test_geo_spatial.py tests/test_geo_host.py tests/test_geo_rows.py
node --test packages/xy-node/test/geo-temporal-binding.test.mjs packages/xy-node/test/temporal-controller.test.mjs packages/xy-node/test/geo-frame-leases.test.mjs packages/xy-node/test/temporal-graph-publication.test.mjs
uv run --no-sync pytest -q tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py
uv run --no-sync ty check
```

The Python focused command passed 108 tests; Node 22 passed 41 tests, zero skips. Native/WASM/browser artifacts are reused by digest and not rebuilt; this correction changes no Rust, ABI, browser source, or size limit. No fresh browser capture or whole milestone acceptance is claimed. Mounted notebook/VS Code replacement, indexed/hierarchy automatic binding, mixed tiles, all-host frozen exports, accessibility, massive-scale/five-view/competitor acceptance, and #50/#39/M6 remain open. Independent final re-review, current-head CI and merge queue acceptance remain required.
