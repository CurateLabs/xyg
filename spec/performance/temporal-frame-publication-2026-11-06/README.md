# Temporal frame output publication

Focused implementation candidate for #45, related to #50's temporal-before-LOD
ordering. Accepted main base: c3152d97bdb3a1efd61686b21d84385ee0f8de9e.
Normal sync merge: 4e00fa09. No source graph or canonical identity changes.

Previously the WASM adapter called `TemporalGraph::frame` (committing visibility
and revision) before rejecting an oversized XYTF output. Bound sessions could
therefore observe a rejected frame and the same revision could not be retried.
The engine now prepares immutable candidate output before the cancellation-aware
publication gate. WASM exact output-size arithmetic and complete serialization
run there. Rejected output leaves the last applied revision/visibility and its
frozen provenance unchanged. The native frame seam delegates to the same engine
path. No ABI or wire signature, arena, work, or package budget changes.

Engine regression: validity intervals and persistent selection/focus/pins cross
the half-open boundary at 20. An output rejection and cancellation after output
construction each preserve revision 1, visibility and frozen state; revision 2
then succeeds and a repeated successful revision is stale. WASM-host regression:
one-byte-under output cap fails without publication, exact cap succeeds with the
same revision and matches native engine frame bytes. Real wasm32 regression:
a bounded 4096-node graph exceeds its reply cap; repeated revisions remain
ResourceLimit, with empty replies, rather than becoming StaleRevision. Real
native/wasm32 replay compares visibility, UUID membership and remapped topology
at eight boundary instants using the existing temporal graph test fixture.

Commands (Cargo is /home/ubuntu/.cargo/bin; Node v22.23.4 is on PATH):

```sh
cargo test -p xyg-engine --lib temporal_graph
cargo test -p xyg-wasm --lib temporal_graph
cargo clippy -p xyg-engine -p xyg-wasm --lib --tests -- -D warnings
cargo build --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
uv run python scripts/verify_wasm_assets.py
uv run pytest tests/test_temporal_graph_native.py tests/test_temporal_controller.py tests/test_graphforge_contract_corpus.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/temporal-graph.test.mjs packages/xy-node/test/temporal-controller.test.mjs packages/xy-node/test/temporal-graph-publication.test.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

`results.json` records environment, source/artifact hashes and log hashes.
Source hashes describe Linux producing bytes; no new portable checkout binding
or rewrite of historical producer evidence is introduced. Prior current-bindings
receipts and pointers are untouched. Initial failed Python collection (native
library not built yet) and Node lookup (explicit development library missing)
are retained beside subsequent successful runs.

## Remaining acceptance

This is failure atomicity and bounded frame proof, not issue closure or a speed
claim. #45 still needs controller/composition integration, real GraphForge
assertion/event-history coverage, aggregate graph LOD membership, rendered frozen
HTML/PNG/SVG attachment, and the remaining scale/accessibility/parity matrix.
#50/#39 retain automatic linked brush/playback, final spatial refinement,
unknown-allocation recovery, mixed routing, attributed export and massive
five-view/per-phase/competitor evidence. #46's six named compositions, streaming,
accessible journeys and scale catalog remain open; #38 closure is not required
for implementing #50. The normative application-consumers spec replaces retired
Reflex presentation wording with the supported host matrix without waiving it.
No comparison against Matplotlib, Seaborn, Plotly, Bokeh, Altair, Datashader,
HoloViews/hvPlot or emerging competitors is claimed by these correctness checks.
The parent owns independent review, delivery, issue disposition and closures.
