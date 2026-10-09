# Geographic index observations, 2026-10-09

This is native cold sidecar-build and warm CPU query evidence, plus a separate
actual packaged-WASM browser correctness proof. It does not measure interaction
p95, GPU upload/paint, network startup, competitor speedups, or billion-row
execution. Concurrent development load was uncontrolled; each timing is one
observation, not a statistically paired comparison.

The fixture is deterministic uniform EPSG:4326 Point data, full-u64 IDs, 65,536
rows per canonical chunk, no nulls and no temporal intervals. Canonical chunks
are regenerated on reads; their generation/validation cost is included in the
canonical reference, and their external storage is not measured. Sidecar leaf
files are explicit caller-owned local storage, separate from the live ledger.
Cold manifest/build times include source generation and actual sidecar writes.
Warm queries read local files with an uncontrolled warm OS file cache.

| Rows | Grid | Build ms | Narrow zoom ms | Narrow pan ms | Whole-world ms |
| --- | --- | --- | --- | --- | --- |
| 100k | 16 | 38.978 | 0.714 | 0.696 | 42.187 |
| 1M | 16 | 320.740 | 9.407 | 8.994 | 507.550 |
| 10M | 16 | 3,805 | 82.285 | 81.487 | 5,246 |
| 100M | 16 | 53,612 | 1,231.380 | 788.277 | 89,928 |
| 1M | 32 | 378.787 | 2.168 | 2.157 | Explicit frontier fallback; not timed |
| 10M | 32 | 2,851 | 18.372 | 17.756 | Explicit frontier fallback; not timed |
| 100M | 32 | 46,892 | 315.856 | 192.491 | Explicit frontier fallback; not timed |

The raw JSONL is authoritative for exact values. `final-1k.jsonl` and
`final-1m.jsonl` are bounded reruns after adding product protocol work caps;
`environment.json` binds their engine/harness source hashes. Older large runs
used checkpoint `7cc5d692`; the six measured engine source files are preserved
beside the outputs. Later optional protocol work-cap and estimate APIs do not
change the uncapped benchmark constructor; the large runs were not repeated.
The checked-in harness adds an explicit grid argument and reports the grid-32
frontier fallback without timing it. It never silently labels fallback as an
indexed result.

Exact compiled Scene bytes are compared against the canonical Rust result for
runs of at most 1M rows. Large results have shared-engine unit/protocol coverage,
but no full canonical large-run byte comparison is inferred. Product protocol
queries additionally enforce cumulative decoded-record, leaf-read and byte
limits. The 100M world run uses the direct engine API without those optional
work caps; its 244,722 leaf reads exceed the product default 65,536-read cap.
Consequently it is a scaling-gap observation, not proof that default browser
or native host options admit that world query.

At 100M, grid 16 uses 8,007,831,104 bytes of external leaf files and 11,709,480
bytes of charged directory storage. Its narrow query reads 274,405,184 bytes;
maximum observed process RSS is 56,393,728 bytes. Grid 32 uses 8,007,850,112
external bytes; its narrow query reads 69,964,160 bytes, with maximum observed
RSS 116,015,104 bytes. Neither RSS observation is a proof of the entire 512 MiB
live binary ledger or JS/GPU/DOM/IPC memory. A spatial/temporal aggregate pyramid
and whole-world interactive latency remain open #50 requirements.

Reproduce from this branch (an empty output directory is required):

```sh
cargo build -p xyg-engine --release --example geo_index_bench
/usr/bin/time -l target/release/examples/geo_index_bench 100000000 /tmp/xyg-index-grid16 16 > grid16.jsonl 2> grid16-resource.txt
/usr/bin/time -l target/release/examples/geo_index_bench 100000000 /tmp/xyg-index-grid32 32 > grid32.jsonl 2> grid32-resource.txt
```

Run the same command with 1,000, 100,000, 1,000,000 and 10,000,000 rows for the
other scales. `geo_index_bench.rs` is the complete fixture and output contract.
Do not reuse an existing leaf directory. A 100M run writes approximately 8 GB.

`browser.json` records the exact packaged artifact SHA256, raw/gzip gate sizes,
environment and strict-CSP proof. It executes real Rust/WASM build/read/write
ACK, indexes an authenticated source, compares exact canonical/indexed Scene
bytes, preserves accepted paint after corrupt leaf reads, recovers, waits for an unsettled cancelled write before its ACK, keeps the
previous accepted index, and retains
full-u64 pick and original-row paging. It also covers existing five-view shared
Worker ownership, signed-i64 filters, context restoration and 63 malformed
controls. This four-row correctness fixture is not a browser scale benchmark.

```sh
cargo build -p xyg-core --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node --test packages/xy-node/test/geo-scale-wasm-parity.test.mjs
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' XYG_GEO_RETAINED_REPORT=browser.json node scripts/geo_retained_wasm_smoke.mjs
```

The native/WASM parity test compares indexed SceneData, original row pages,
query statistics and frozen XYGX bytes through the actual shared protocol.
