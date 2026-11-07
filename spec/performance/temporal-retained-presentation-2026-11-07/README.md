# Retained temporal presentation: bounded #45 candidate

This continues `2c799612191793cd2392b597dbdf9050a24e1cee` on
`t3/temporal-graph-controller`, preserving that commit and its evidence. It
implements the previously missing connection to the existing retained graph
presentation. No producer branch was changed or imported; accepted main
`80e841542462eaf5509ac90e1f17a80cae974164` remains in the preserved history.

## Implemented public journey

`attachWasmGraphSession({el, worker, instanceId, document, load, camera,
temporal: {controller, binding, budget}})` now subscribes to complete Rust
controller snapshots. A separate controller Worker drives the same retained
graph Worker, Rust session, GPU painter and native canvas picking. There is no
application frame pump, alternate layout/renderer, JS graph filtering or topology
reconstruction. Internal named temporal create/frame messages share the existing
exclusive serialized lane and its sequence/lifetime/byte/watchdog checks.

Initial request capture verifies OPEN → temporal create → temporal frame → Rust
Bind → render. Publishing the initial frame before Bind is required because
Bind itself renders in Rust. Subsequent time changes apply membership before
Rust render/pick/layout; the existing progressive continuation is reused.
The scheduler retains one active operation and one latest pending intent.
Late replies never paint; real frame/render refusals retain the preceding
picture and snapshot. Acknowledged session revisions and the last accepted
membership allow a matching refresh without stale interaction admission.
`whenIdle()` drains admitted work without polling; `pinFocused(boolean)` uses
the single eligible ref issued by Rust. Selection, focus and pins remain UUID
state across hidden/reappearing membership. Disposing the controller closes its
view; disposing the view unsubscribes and drains before releasing the lane.

Bind adopts the temporal owner's empty initial interaction state. Nonzero
`load.pinned` with temporal binding is explicitly refused; pin after ready.
Borrowed Worker ownership is unchanged: close the attachment before disposing
an owned Worker. Rust temporal storage stays with that Worker until replacement
or Worker disposal. The standalone coordinator from the prior commit remains
available for explicit frame/layout consumers.

## Final checked evidence

`checked-exits.json` records eight commands, actual exit codes and raw logs:

- Client build/typecheck, packaged-asset verification, official ownership and
  API inventory checks: all passed. The inventory retains the existing 685
  preparation/classification gaps.
- Existing native/WASM GraphSession wire command: **8 tests passed, 0 failed,
  0 skipped**. The added shared history case compares complete retained XYGR
  bytes, including GPU, membership, selection, focus and pin facts at every
  shared fixture frame and re-entry. Capacity/exact-byte retry assertions remain
  active; no section or tolerance is waived.
- Focused Python command: **116 passed, 0 failed**, covering temporal controller,
  native graph, inventory, capability registry and packaged-asset verification.
- Full source-dist foundation command: passed, then executed **9 retained
  temporal browser cases** through the existing command. This is now normal CI
  coverage, not an optional new gate. `ci-foundation.json` binds the production
  assets; `ci-foundation.json.retained-temporal.json` records actual snapshots,
  initial/boundary PNGs, exact render membership and native no-hit picking.
  Its `.wire.json.gz` retains raw issued requests and actual received replies,
  including held replies and actual Rust failures.
- Existing graph browser command: **69 cases passed, 0 skipped**, under strict
  CSP with zero page errors/violations. `ci-existing.json.gz` and its raw log
  retain the established pointer, keyboard, ownership, failure, publication and
  lifetime tests.

The retained cases prove initial pixels, all seven shared validity/history
frames plus re-entry, canonical visible UUIDs and matching Rust render members,
native node picking and hidden-node no-hit, persistent selected/focused/pinned
UUID state, remote snapshots without a local revision bump, scrub/step/play/
pause, actual Rust frame-budget refusal and render-camera refusal, last-good
pixels/snapshots and refresh, bounded held-reply coalescing, disposal, and
supersession of an in-flight progressive checkpoint. The canonical document
bytes stay identical; one OPEN and no UPDATE occur. Companion rows intentionally
list canonical entities, including hidden ones; render buffers and pixels are
the visibility oracle.

Final hooks and full-worktree Ruff checks are recorded separately before the
commit. `inputs-artifacts.json` binds exact sources, raw evidence, environment,
archived production client/Worker/WASM/native artifacts and paired assets.
Archives preserve exact raw bytes using gzip level 9; they are not shipping size
measurements. Actual Node22 gzip6 WASM size remains **786,115 bytes**, with
**1,927,032 raw bytes**. Unchanged caps are 768 KiB gzip6 / 1,882 KiB raw.
`node js/package-wasm.mjs` refreshed paired manifests/inline assets and passed.
No Rust source, ABI, export, validator, runtime arena or package cap changed.
Every Rust producer input and both native/WASM artifact digests are checked
against the prior receipt before reusing those binaries.

Development failures remain appended: the first browser assertion incorrectly
assumed the canonical companion was visible-only; the next used the existing
f64 test reader on u64 membership. Both test assumptions were corrected without
changing Rust policy. A richer ownership rationale was refused by the official
fixed-policy validator; the unchanged valid machine classification was restored
and the detailed ownership contract was updated in the human ledger. Earlier
passing development captures are retained as intermediate runs. Final
qualification uses the `checked-*` logs and `ci-*` reports.

## Reproduction

Use Node22 from
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`,
Cargo from `/home/ubuntu/.cargo/bin`, `CARGO_BUILD_JOBS=2`, the project `uv` env,
and Chromium at
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
The project Python is 3.12.15; system Python is separately recorded and is not
the test interpreter. Build native/WASM normally if producer hashes differ.

```bash
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH
export CARGO_BUILD_JOBS=2
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
export XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so
node js/build.mjs
node js/package-wasm.mjs
uv run python scripts/verify_wasm_assets.py
uv run python scripts/verify_ownership.py
uv run python scripts/check_release_inventory.py
node --test packages/xy-node/test/graph-session-wire.test.mjs
uv run pytest -q tests/test_temporal_controller.py tests/test_temporal_graph_native.py tests/test_release_inventory.py tests/test_capability_registry.py tests/test_verify_wasm_assets.py
node scripts/wasm_foundation_smoke.mjs
node scripts/graph_session_controller_wasm_smoke.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

`verify.py` is the exact bounded command/log producer; `capture.py` binds source,
artifacts and reuse. Preserve this receipt when reproducing: use a fresh evidence
copy/output directory rather than replacing these recorded files.

## Remaining acceptance

This is a three-node/two-edge direct-tier browser fixture, not issue #45/#38,
M4–M7 or release completion. Full GraphForge payload fixtures, aggregate LOD
membership, temporal HTML/PNG/SVG freezing, large/massive playback, supported
host parity, complete accessibility/reduced-motion journeys, timezone
presentation, broader authoring state ingress and comparative performance still
need acceptance. The UTC controller has no timezone setter. No competitor win,
performance claim, independent review completion, publication or GitHub action
is claimed. Parent owns review and delivery.
