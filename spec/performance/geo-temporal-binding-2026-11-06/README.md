# Automatic retained geographic temporal binding — partial #50/#39

Accepted base: `c3152d97bdb3a1efd61686b21d84385ee0f8de9e`.
Normal no-commit merge: `043c3dba1a1352228519b5d06a1d4dcd11348462`,
whose tree equals accepted main. The two stale-parent conflicts were resolved
with accepted-main scheduling prose and generated API inventory, preserving
accepted historical receipts. Full-worktree hooks, Ruff check and format check
passed before committing that merge. No reset, rebase, push or tracker mutation.
The reviewed PR1102 temporal-graph commit is not a dependency of this slice.

The public browser retained Point/MultiPoint chart now binds directly to the
public Rust/WASM temporal controller. Cursor and range modes copy exact signed
fields into the existing geographic predicates. The existing Rust session owns
time-before-projection/LOD, cache admission, direct identities, aggregate cells
and paged provenance. The host schedules one running automatic update and one
pending latest intent; explicit viewport updates inherit current bound time.
No Rust, C ABI, WASM export, arena, package cap or threshold changes.

The existing strict-CSP/offline retained smoke now proves real Worker temporal
commands (including received events), direct full-u64 identity, 32,769-point
aggregate counts and paged membership, half-open range exclusion, rapid
cursor/viewport replacement across an unsettled read, failed-read recovery,
selection-only no-op delivery, and disposal in either direction. Its inherited
five small views, sidecar/cache recovery, resource-admission controls and frozen
snapshot checks still run. Those inherited checks are not a five-view temporal
or massive-scale claim. Native/WASM parity adds three exact semantic packet
comparisons (excluded instant, included range, included instant with viewport
change) through the same canonical session, retaining all existing byte oracles.

The first parity harness incorrectly attempted newer predicates with revisions
below its original full-u64 revision fixture; Rust correctly rejected them.
The retained initial failure log is diagnostic, not product failure evidence.
The final temporal cases use an additional low-revision fixture, preserving the
original full-u64 revision assertions. Existing index parity remains unchanged.
A later browser test attempted a second temporal controller in one Worker; the
existing single-controller guard correctly rejected it. The final disposal race
uses a separate caller-owned Worker, retaining that guard without modification.

Reproduce from this candidate with Node22.23.4 and Rust1.96.0:

```sh
npm ci
npm ci --prefix packages/xy-node
cargo build --release
node js/build.mjs
cargo build --release --target wasm32-unknown-unknown -p xyg-wasm
node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" uv run pytest tests/test_geo_retained.py tests/test_graphforge_contract_corpus.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/temporal-controller.test.mjs packages/xy-node/test/geo-scale-wasm-parity.test.mjs
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/geo_retained_wasm_smoke.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Fresh native/WASM builds, client build, 13 Python tests, 10 native temporal
controller tests, the native/WASM packet suite and actual public browser smoke
passed. Raw logs, browser environment/results and artifact/source hashes are
adjacent. Actual optimized WASM is 1,926,555 raw / 785,542 gzip6 bytes, below the
unchanged 1,927,168 / 786,432 limits. Generated assets remain ignored. No latency,
competitor lead, publication or independent-review claim is made here.

## Remaining acceptance

#50/#39 and M6 remain open. This slice does not establish:

- Automatic Python/Node/native notebook/application/VS Code temporal binding;
  complete linked brush/selection/playback, mixed-layer/tile automatic routing,
  final overview refinement or all-host/accessibility conformance.
- Complete deterministic inherited HTML/PNG/SVG/file export with jointly frozen
  viewport, time, layer/membership and attribution, plus offline reopening.
- Massive interaction CPU/memory/upload/cache budgets, cancellation/recovery
  across every source/tile profile, full geometry simplification/tessellation,
  all required geographic fixtures/projections and all-host provenance journeys.
- Small/medium/large/massive and 1B-class ingestion, memory, first paint, filtering,
  pan/zoom, pick p95, update, payload/export and five-view evidence, or comparable
  Matplotlib/Seaborn/Plotly/Bokeh/Altair/Datashader/HoloViews/hvPlot results.
  Use existing scheduled/manual infrastructure for large runs; no new workflow
  and no local/ordinary-CI 100M allocation was added.

Parent owns completed independent final-diff review and delivery. Integration
risk is limited to the shared temporal snapshot subscription and retained browser
controller scheduling; there is no cross-work ABI/version collision. Other
hosts and GraphForge temporal-graph output publication are separate contracts.
