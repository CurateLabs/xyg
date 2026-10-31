# Local #36 S1 / PR #1022 recovery

S1 is recovered locally with its existing history. **The combined package gate
fails. #36 and milestone 4 are not complete.** The parent owns independent final
review, actual dependency integration, and any later update to the existing PR.
No push, force update, new PR, issue closure, publishing, tag, paid/hardware run,
secret change, or unrelated repair is part of this preparation.

## History and compatibility

Starting branch: `t3/recover-milestone4-s1`, isolated worktree
`/home/ubuntu/.t3/worktrees/xyg/t3-252e5f17`, rooted at `1440bec9`.
First fast-forward to validated combined commit
`465ec0a0acc16340947ea599fee7e0486f12b6d0` (tree
`04b437686f5e858bb68fc72379f7ce47064e8ca1`), then normal merge of existing PR head
`95c9f804c2f615038c3669ae78295bab5adb8c4e` from
`feat/36-s1-graph-session`. Both histories remain ancestors. The recovered tree
before this evidence and final inventory refresh is
`39d5d42980289b996224797d26be55361c5832d2`.

The source manifest hashes every tracked build input under `crates/` and
`.cargo/`, plus workspace Cargo, toolchain, npm, optimizer and packager inputs.
Its SHA-256 is
`e6a15c901d516844b460626932f0cb9999a23d96b437ee008739ff16d4debd2f`.
[results.json](results.json) binds environment, artifacts and raw validation logs.

Composition v2 adds optional document hierarchy planes. Generic Python/Node
document readers retain their existing transport behavior; the new Rust session
accepts only successful graph documents at v2. No session ABI or host API is
added. Native ABI stays **396 / 529 symbols**; generated declarations are
unchanged (`gen_abi_manifest.py --check`). WASM ABI/Scene/painter remain 34/34/17.
Rollback is restoration of the integration-base code, client artifacts and v1
fixture hashes together; no persisted data migration or remote rollout occurred.

Merge resolutions retain the current property caption precedence, visible
arrowhead geometry, synthetic property fixture manifest producer, CoSE portable
trigonometry, #1078 worker lifecycle, #922 annotations and current geographic/
temporal contracts. There is no S2 controller, rendering or ABI work and no #1038
expansion. Both synthetic fixture producers run in the integrated script.

`cross_host.json` was regenerated from the combined native library: the 101
existing request hashes are unchanged and all 101 document hashes change with
composition v2, including error documents. Semantic Scene/painter/SVG/raster/PNG
hashes were regenerated and remain unchanged from the integration base. Core
compatibility manifest digests were recomputed and still match the declaration
(`results`: `9f50ce9d…`; `results-0.6.0-rc.5`: `5cfec9ad…`; full hashes in
results.json). The API inventory was regenerated; it still reports 679 existing
classification/review gaps and does not claim an API freeze.

## S1 acceptance and prior review findings

| Contract | Recovery evidence |
|---|---|
| Composition hierarchy | Flat `parent_uuid` resolves to a forest; malformed unknown/self/cycle inputs fail atomically. Composed `node.parent` / `.valid` are authoritative, including hidden-parent reattachment decisions. Rust tests and added native/WASM parity test pass. |
| Tri-state declarations | Undeclared, explicit null root and parented declarations remain distinct. `a_root_and_a_parent_declaration_for_one_node_conflict_in_either_order` passes, as do both orders through actual WASM. |
| Linear ancestor resolution | 200 random forests match the walking definition; a 100,000-deep shared hidden chain plus 100,000 children asserts at most `2n` parent-link visits, independent of wall time. |
| Identity | Node/edge kind disambiguation, persisted UUID round trips, derived pair row keys, overlay steps, forced hash collisions and exact result-id replacement tests pass. Aggregates fail stale before S2 publication. |
| Fail-closed result ids | Mistyped and invalid-UTF-8 `layer.result_id` both reject session creation; absent ids remain supported. |
| One state owner | Bound session and temporal frame see one `GraphInteractionState`; mismatched planes reject, disposal yields unbound, unbind resets owned state, dropping the session preserves temporal state. |
| Atomic cap | Selection and each highlight plane count node + edge + derived refs; 10,000 accepted, 10,001 rejected without mutation across modes. Temporal setter returns -16. |
| Session operations | Create/load validation, select/clear/focus, destination stamps, unconsumed rejected operation sequences and cached idempotent retry tests pass. S1 render revision stays zero. |
| Core version assertion | `xyg-core` expects composition version 2; the ABI version test and full workspace suite pass. |

These verify the old composition assertion, null-root conflict, quadratic walk,
and malformed-result-id findings using the fixes already in `95c9f804`; this is
implementation validation, not a substitute for the parent's independent review.

## #36 acceptance criteria and remaining S2–S7 work

| Issue acceptance criterion | S1 result and remaining debt |
|---|---|
| IDs round-trip between tables and selected elements | Rust identity/state proof passes. Live session transport, table integration and cross-session result-id fixture proof remain S3/S6/S7. |
| Routed/self-loop/parallel/compound/aggregate interaction | Hierarchy and identity seams pass. Render publication, bounded picking, disclosure and aggregate membership remain S2; no new live behavior is claimed. |
| Keyboard reachability and screen-reader semantics | Design is recorded; browser controller, companion, focus/emphasis paint, reduced motion and accessibility proof remain S4/S5/S7. |
| Views isolated unless linked | Instance stamps reject stale local events. CoordinationGate extraction, ApplyRemote, linked-view delivery/isolation and reload proof remain S2/S6/S7. |
| Interaction latency scale ladder | Not run or claimed by this foundation recovery; S7 needs the benchmark and raw ladder evidence. Existing CoSE evidence is retained without reinterpretation. |
| Equivalent Python/Node/browser events | Existing composition bytes and CoSE remain native/WASM equivalent. Session ABI is S3, host/channel/VS Code exposure S6 and event parity proof S7. |

S2 also owns temporal visibility in publication, emphasis planes, pin/move/
relayout, `session_update` and traversal. S3 owns numeric status/wire layout and
capacity retry through native/WASM. Static exports continue to show explicit
selected state only. No core mutation/editor scope is added.

## Validation and failures

Passing: workspace Rust **1,830** tests; release native/WASM compile; strict
Clippy; focused Python **600 passed / 11 skipped**; graph/CoSE/worker/temporal Node
**156 passed**; ABI smoke **673** checks; browser render and streaming smokes;
client build/typecheck/shader lint; ownership (483 sources); ABI generator check;
fixture regeneration checks; full pre-commit, Ruff check and format check; `ty`.
The entire multi-hour Python suite and release installation cohort were not run.

The broader diagnostic Node run reports **720 tests: 703 passed, 15 failed,
1 cancelled, 1 skipped**. Its geographic hierarchy fixture has 13 assertion
failures plus the 20-second cancellation of `cancel after real44 publication
cleans candidate before accepted paint changes`; subsequent cases are also
affected by retained failed-fixture resources. Geometry tests fail on
`constantMarkColor uses color_ch.constant only like Python` (`#3987e5` vs null)
and `sceneScatterPaintChannelAdmit matches host table` (true vs false).
All 15 failures and the cancellation reproduce using the validated integration
base's native library with unchanged JS/tests; see `node-baseline-live.txt.gz` and
`node-baseline-geom.txt.gz`. No geographic or geometry source/test was changed.
The one Node skip is the existing `parsed identity failure drops packet storage
before Data disposal` test. No broad-suite PASS is claimed.

`cargo fmt --all --check` fails on **the same 90 files** in both this recovery
and a disposable archive of `465ec0a0`. This pre-existing formatting debt was
not expanded into unrelated cleanup; both full outputs are retained. Mandatory
pre-commit and Ruff checks pass independently.

Initial setup commands needed corrections: `cargo` required
`/home/ubuntu/.cargo/bin` on PATH; Node native tests required explicit
`XYG_NATIVE_LIB`; WASM functional tests required an artifact after the packaging
gate failed. Those incomplete invocations were superseded by the recorded runs.
The client build retains existing non-ESM `import.meta` warnings; WASM compile
retains seven existing unused/dead-code warnings. `npm ci` reports one high
development dependency audit finding; no dependency change was made.

## Unchanged WASM size gate: FAIL

Rust **1.96.0**, pinned Binaryen **132.0.0**, workspace release profile, target
inline threshold 100 and `wasm-opt -O3 --all-features` are unchanged.

| Artifact | Raw bytes | gzip6 bytes | SHA-256 |
|---|---:|---:|---|
| Compiler output | 1,706,762 | — | `6ad6e56e235701aebea5aa1e1f446f7efc9dd395e742f283dd20661d0ef738ce` |
| Optimized diagnostic | 1,547,598 | 640,237 | `a528de02966ec317d33af4c7473d6f3916181664668f755ef1be097ac6eca749` |
| Existing gate | 1,543,168 | 638,976 | — |
| Excess | **4,430** | **1,261** | — |

`node js/package-wasm.mjs` fails the gzip gate first and publishes no validated
asset set. The same optimizer produced `target/xyg-s1-diagnostic.wasm`, copied
only to ignored `packages/xy-client/dist/xyg-wasm.wasm` to exercise actual WASM
functionality. It is **not a passing package**; manifest/inline packaging,
release-cohort verification and publication are not asserted. No gate or
compiler profile was raised or changed.

Narrow sharing opportunities for the next size repair, not measured wins:

1. The new `base::finish` hierarchy resolution materializes UUID, validity and
   dense vectors around `projection::resolve_parents`. Investigate a shared
   non-generic internal resolver/forest adapter to reduce monomorphization while
   preserving projection's existing validation contract and stable error codes.
2. The new nearest-visible-ancestor helper stores `Option<u64>` and builds a
   second final vector. Investigate one sentinel-coded memo table, keeping the
   deterministic `<=2n` proof and all reattachment decisions intact.
3. Keep parent-plane gathering/validation in one shared Rust path; inspect
   optimized function-size output before adjusting inline boundaries. Retain
   caption, arrow, selected snapshot and geographic/temporal functionality.

The next concrete action is a narrowly reviewed sharing repair that recovers
at least 4,430 raw and 1,261 gzip bytes on this combined tree, followed by the
unchanged package gate and affected parity checks. Geographic/geometry baseline
failures need separate disposition. After dependencies land, the parent must
independently review the final diff and update the existing PR with normal
merges; no force push or milestone/issue completion is justified by S1 alone.

## Reproduction

```bash
export PATH=/home/ubuntu/.cargo/bin:$PATH
uv sync --group dev
npm ci
npm ci --prefix packages/xy-node
cargo test --workspace
cargo build --release
node js/build.mjs
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/package-wasm.mjs  # expected FAIL: 640237 > 638976 gzip bytes
uv run python scripts/gen_graphforge_ipc_fixtures.py
uv run python scripts/gen_graphforge_cross_host.py --check
uv run python scripts/gen_graphforge_semantic_fixture.py
python3 scripts/gen_abi_manifest.py --check
python3 scripts/abi_smoke.py
python3 scripts/verify_ownership.py
uv run python scripts/check_release_inventory.py
cargo clippy --workspace --all-targets -- -D warnings
cargo fmt --all --check  # existing failure; compare base-fmt.txt.gz
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

The focused pytest paths are all `tests/test_geo*.py`, the three temporal files,
the six GraphForge test files, `test_cose_native_parity.py`, and graph, compound,
edge identity/routes/ends, style, semantic mapping and static export files.
See [commands.txt](commands.txt) for exact invocations, including diagnostic
artifact preparation and baseline failure reproduction. Raw logs are retained
losslessly as `*.txt.gz` (`gzip -dc <log>`); results.json records their raw and
compressed hashes. `node-final.txt.gz` includes sparse NUL bytes from redirected
output after restarting an interrupted run.
