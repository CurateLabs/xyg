# PR1104 small-chunk cache lookup

Correction base `caeffd14a43b9d57686c25e253b0df10ee8fc336`. Greptile
comment 4497709946 correctly identified a resident-wide linear scan on misses
and queue shifts on hits. A valid file can contain many four-row slabs within
the unchanged 8 MiB raw cache cap. The prior cache therefore incurred quadratic
lookup work while filling or traversing interior overlaps.

Rust now keys entries by canonical chunk ID in a standard hash table. Stored
previous/next chunk IDs maintain deterministic LRU order; no production lookup
or recency update iterates the table. Lookup, removal and insertion have expected
amortized constant cost. Trimming costs work proportional to entries evicted.
Raw slab ownership remains serialized, and taking a hit removes its accounting
before cancellation/decode, as before. Failed or cancelled work cannot publish
partial results. Admission/page boundaries, oversized bypass, provenance and
structural validation are unchanged. No ABI, dependency, cap or host policy change.
Hash-table capacity and link bookkeeping are additional to raw retained bytes,
not a total RSS bound; the normative residency contract remains explicit.

The normal Rust test suite adds 32,768 four-row chunks (131,072 rows; 2 MiB raw
slabs), checks exact cold/warm rows and misses, interior overlap, all link/order
invariants, budget shrink and complete eviction order. It retains every prior
cancellation, failure, concurrency and admission test. Timings are printed as
diagnostics, with no fragile wall-time assertion. The same semantic test passes
before and after; it does not by itself guard asymptotic complexity. The source
architecture and preserved measurements establish this specific repair.

Before/after debug-profile measurements on this VM are in checks.json and raw
logs. They compare this cache workload only, under uncontrolled concurrent
development load, without warmup/statistical or release-profile qualification.
They are not chart latency, massive-data, memory/RSS, or competitor claims.
The before source plus test is retained losslessly. An initial test-only compile
error (a u64 range lacks ExactSizeIterator) is separately preserved and excluded
from passing results.

Fresh checks: 18 Rust tests; 9 Python tests; 6 Node22 tests with zero skips;
release native build; strict engine all-target Clippy; required full-worktree
hooks and Ruff. Native artifact/source and compressed/raw logs are bound below.
No browser/WASM cache path is qualified by this local-native correction.

Reproduce from this tree (Rust1.96, Node22, explicit rebuilt native):

```sh
cargo test -p xyg-engine chunked_columns -- --nocapture
cargo build --release -p xyg-core
cargo clippy -p xyg-engine --all-targets -- -D warnings
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" uv run pytest tests/test_chunked_columns.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/chunked-columns.test.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Prior cache/history receipts remain unchanged. Independent correction review,
current-head CI, and delivery after parent PR1101 remain required. Larger-than-
RAM rendering/navigation, browser/WASM and full-host cache integration, measured
RSS budgets, accelerated100M evidence, #111/#112/#113 and complete #110/M7
acceptance remain open.
