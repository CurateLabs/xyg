# Automatic temporal graph controller coordinator

This is a committed implementation candidate for a bounded part of #45, not
issue or milestone completion. Accepted main `80e841542462eaf5509ac90e1f17a80cae974164`
was merged normally into the stale parent, preserving both histories, as
`1408b146`. The resulting merge tree exactly equals accepted main. Hooks and
both full-worktree Ruff commands passed before that merge commit.

The public `XygWasmTemporalGraph.attachController` consumes initial and changed
Rust controller snapshots automatically. It holds one active membership/layout
and one latest pending intent, cancels CoSE on replacement, and suppresses stale
publication. No JS topology, identity, validity or LOD policy was added.

## Fresh validation

- `npm ci`, `node js/build.mjs`, and `CARGO_BUILD_JOBS=2 npm run build:wasm`
  passed with the Node 22 path below. The final type-only rebuild produced
  byte-identical index, standalone, Worker and WASM assets to the full foundation
  run. The shipping module remains 1,927,032 raw / 786,115 Node22 gzip6 bytes;
  the unchanged caps remain 1,882 KiB raw / 768 KiB gzip6.
- `CARGO_BUILD_JOBS=2 cargo build --release -p xyg-core` passed before host tests.
- `uv run pytest -q tests/test_temporal_graph_native.py`: 6 passed.
- `uv run pytest -q tests/test_temporal_controller.py tests/test_temporal_graph_native.py tests/test_release_inventory.py tests/test_capability_registry.py`:
  80 passed, zero failed. The six-test run is included in this count.
- `uv run python scripts/check_release_inventory.py`: declarations match;
  existing classification/acceptance gaps remain explicit.
- Full `node scripts/wasm_foundation_smoke.mjs`: passed under strict CSP with
  local requests only, using actual packaged Workers. `foundation.json` retains
  seven exact membership/range results from the shared assertion-history fixture.
  Other assertions cover automatic initial state, rapid scrub, step/play/pause,
  received events whose local revision does not change, immutable source,
  defensive observer/snapshot buffers, disposal, and Worker-failure retention.
- Full pre-commit, Ruff check and Ruff format check passed; raw logs retained.

Three development foundation failures are retained: a duplicate lexical test
name prevented module startup (manifest request timeout), then two runs exposed
and diagnosed test command ordering. Rust `setCursor` correctly recenters the
window; the final fixture sets cursor before range and asserts the exact final
range. Native fixture goldens and production range policy were unchanged.

`inputs-artifacts.json` records actual source/artifact hashes, native library,
Node22 gzip measurement, raw logs and environment. `capture.py` reproduces that
capture. Project Python is 3.12.15; system Python is separately recorded and was
not used for host tests. Old receipts/captures/generators were preserved.

## Reproduction

```bash
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH
export CARGO_BUILD_JOBS=2
npm ci
node js/build.mjs
npm run build:wasm
cargo build --release -p xyg-core
uv run pytest -q tests/test_temporal_controller.py tests/test_temporal_graph_native.py tests/test_release_inventory.py tests/test_capability_registry.py
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome XYG_WASM_FOUNDATION_REPORT=/tmp/temporal-controller-foundation.json node scripts/wasm_foundation_smoke.mjs
uv run python scripts/check_release_inventory.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
uv run python spec/performance/temporal-graph-controller-2026-11-07/capture.py
```

## Remaining acceptance and cross-lane dependency

The retained `attachWasmGraphSession` owns an exclusive Worker lane. Its public
API lacks temporal create/bind/frame operations, and its byte encoder excludes
Rust operation 18. Public temporal commands are rejected while it owns that
Worker. This candidate does not bypass that boundary or edit the M4-owned
`63_graph_controller.ts`. M4 must provide a narrow serialized temporal hook
that commits temporal membership before retained render/pick/layout, preserves
shared UUID interaction state, and keeps last-good presentation after failure.
The coordinator delivered here operates on its existing standalone temporal
Worker and Rust CoSE, without claiming retained presentation attachment.

Browser selected/focused/pinned UUID persistence, retained cancellation,
timezone presentation, complete GraphForge fixtures, aggregate membership,
HTML/PNG/SVG freezes, accessibility, large/massive playback, full host parity
and competitor comparisons remain open. Native persistent UUID assertions do
not prove the browser journey. No performance win, gate waiver, ABI change,
independent-review completion, GitHub mutation or delivery is claimed.
