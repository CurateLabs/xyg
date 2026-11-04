# Bounded P1 result — functional PASS, shipping FAIL

Base: `5840b4790660d8bafa59e9b5308b450c51f55713`. Worktree:
`/home/ubuntu/.t3/worktrees/xyg/t3-47e5e75b`; branch `t3/rust-graph-session-p1`.
Slice 1 commit: `5cbef0afe860f35739047486cca3c84afc03f006`.
Slice 2 contains the retained progressive seed, exact step counts, final sparse
projection descriptors/work admission, tests and evidence. No remote mutations,
PR, issue closure, optimizer/profile/dependency/export/runtime guard or package
budget changes are part of this work.

Complete canonical selection and exact original result rows are now available
in index-0 `selection.*` sections on every successful publication, independent
of changed refs and coordination. Projection resolves only selected elements,
borrows row planes, builds per-layer descriptors in one section pass, counts
actual mapped entries before allocating tables, and admits both row probes
against the existing work ceiling. Conservative table/scratch/reply reservations
precede candidate cloning. Type/count errors, invalid row-layer indices,
remap failures and resource refusals remain inside the existing transaction.
UPDATE serializes against its replacement document.

`load.progressive.u8=[1]` publishes one configured native CoSE tick and retains
that same force state for opcode 15; absent/zero keeps legacy 300-step seeding.
Authored positions paint directly; unauthored pins anchor after the first seed.
Options, document hierarchy and UUID pins reach the existing native engine.
`relayout.steps.u64` counts actual native ticks, including convergence/empty-state
behavior, rather than requested chunks or host callbacks. Selection, hover and
camera preserve continuation; pin, move preview/commit/cancel, temporal visibility,
binding and replacement retain existing invalidation semantics.

Normative contracts: [graph-interaction](../../design/graph-interaction.md#211-complete-selectionresult-row-publication-bounded-p1)
and [scheduling seam](../../design/graphforge-node-scheduling.md#bounded-retained-session-p1-seam-2026-11-03).
Rust source compatibility changes are explicit there: exhaustive `SessionLoad`
and `RelayoutReport` literals need new fields. C ABI398/WASM35/Scene34/painter17
and every C/WASM function signature remain unchanged.

| Final check | Result | Receipt / raw log |
|---|---|---|
| GraphForge engine incl. all interaction/identity tests | 212 passed | [argv/result](final-topology-and-invalidation.json), [log](final-topology-and-invalidation.log) |
| Core + WASM native adapter tests | 67 + 73 passed | [argv/result](core-wasm-release-candidate.json), [log](core-wasm-release-candidate.log) |
| Python seams after release rebuild | 60 passed | [argv/result](python-release-candidate.json), [log](python-release-candidate.log) |
| Workspace Clippy, all targets, warnings denied | PASS | [argv/result](clippy-release-candidate.json), [log](clippy-release-candidate.log) |
| Native ABI smoke | PASS, ABI398 | [argv/result](abi-release-candidate.json), [log](abi-release-candidate.log) |
| Generated native/WASM declarations | PASS, unchanged | [native](abi-declarations.json), [WASM](wasm-declarations-corrected.json) |
| Exact ownership inventory | PASS | [argv/result](ownership-final.json), [log](ownership-final.log) |
| Existing actual C ABI/WASM replay | PASS, diagnostic only | [argv/result](existing-wire-replay-release-candidate.json), [log](existing-wire-replay-release-candidate.log) |
| New P1 actual C ABI/WASM replay | PASS, diagnostic only | [argv/result](boundary-replay-release-candidate.json), [checkpoint hashes](boundary-replay-release-candidate.log) |
| Real production WASM packager | **FAIL** | [argv/result](package-release-candidate.json), [raw failure](package-release-candidate.log) |

New P1 Rust proofs cover Replace/Add/Toggle/Clear/no-op/unlinked snapshots,
shared node/edge UUIDs, persisted parallel/loop topology, exact multi-layer
node/edge/path/pair rows, None/empty/Unicode/long IDs, malformed present and
missing inapplicable planes, post-update serialization rollback and retry/resource
atomicity. Existing forced-collision identity and full 10k/20k delta proofs
remain green. Native CoSE checkpoint proofs cover 1+1/7/16/64 chunks bit-exactly,
nondefault options/bounds/hierarchy/pins, authored and seed-then-anchor positions,
first publication coordinates, selection/hover/camera preservation, convergence,
stale/resource/cancel/replacement/temporal-visibility/disposal cases. Native
capacity retries are exercised at zero, short and exact sizes on actual P1 replies.
The replay reuses the unchanged existing Node boundary harness as an oracle;
it implements no host product policy. Browser controller/paint integration,
full-foundation qualification and scale acceptance are not claimed.

The real packager uses unchanged Binaryen 132.0.0, `-O3 --all-features`, Node
22.22.1 and repository release profiles. It fails before publishing WASM assets.
After that failure only, `diagnostic.mjs` invokes the **same production optimizer**
and validates all 65 manifest signatures, zero imports, ABI35, Scene34 and
painter17. This diagnostic artifact is used for replay, never represented as a
shipped package. Final optimized sizes: **1,882,245 raw / 768,683 gzip-6 bytes**;
unchanged gates: 1,872,896 / 764,928; excess: **9,349 / 3,755 bytes**. No full
foundation waiver, budget raise or alternate optimization profile was applied.
Earlier attempts remain immutable alongside the final `*-release-candidate`
receipts; intermediate code changes corrected functionality/accounting, not size.

[Artifact hashes and sizes](artifacts.json) include the final native binary,
raw WASM, optimized diagnostic WASM and gzip hashes. [Source hashes](source-hashes.json)
identify the changed implementation/spec and unchanged shipping inputs. Each
command JSON records argv, cwd, environment, exit status, duration and raw-log SHA256.
The final canonical `git diff --binary --full-index BASE HEAD` hash is returned
with the commits (it cannot be included in its own hashed diff).

Reproduce from this isolated checkout with Rust 1.96.0 and Node22 on PATH:

```sh
export CARGO_TARGET_DIR=target/task-tmp/p1
cargo test -p xyg-engine graphforge --lib
cargo test --offline -p xyg-core -p xyg-wasm --lib -- --test-threads=1
cargo build -p xyg-core --release
export XYG_NATIVE_LIB="$PWD/target/task-tmp/p1/release/libxyg_core.so"
uv run pytest -q tests/test_graph_session_abi.py tests/test_graphforge.py tests/test_gen_wasm_abi.py tests/test_verify_ownership.py
node js/build.mjs
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/package-wasm.mjs target/task-tmp/p1/wasm32-unknown-unknown/release/xyg_wasm.wasm
# Only after the real producer FAIL above: diagnostic, never shipping acceptance.
node spec/performance/graph-session-p1-2026-11-03/diagnostic.mjs
export XYG_SESSION_WASM=target/task-tmp/p1-diagnostic.wasm
node --test packages/xy-node/test/graph-session-wire.test.mjs
node spec/performance/graph-session-p1-2026-11-03/boundary-replay.mjs
```

Remaining integration requirements:

- Parent owns API inventory refresh, independent final review and integration.
- Parent's reviewed bind-count repair `e91fe2f7531cc808987d0af0868c321c55e51066`
  is intentionally neither duplicated nor rebased into this branch. Preserve
  its `OpOutcome.selected = destination_state.selection().len()` calculation
  under the existing destination-world lock and its regression tests. P1 adds
  a document argument to `WireSession::finish`; combine that argument with the
  parent's repaired outcome at the bind call. Do not restore the old default
  outcome while resolving the overlap. Fresh combined package measurement is
  still required; the isolated P1 FAIL must not be waived or added arithmetically
  to the parent's measured binary.
- Python worker/P0 child files, widgets/channel, JS controller, public host APIs,
  browser full-foundation and scale proof remain out of scope. No issue closes.
- The existing `(n+m)*8192` charge alone is 2,457,600,000 bytes at 100k nodes /
  200k edges, exceeding the 384 MiB session cap before other charges. No scale
  acceptance or capacity increase is claimed. Conservative P1 reservations can
  additionally refuse sparse multi-layer documents; this is an explicit remaining
  admission limitation, not a reason to invent larger capacities.

Final pre-commit and full-worktree Ruff receipts are `commit-hooks`,
`commit-ruff-check` and `commit-ruff-format` (JSON argv/results plus raw logs).
