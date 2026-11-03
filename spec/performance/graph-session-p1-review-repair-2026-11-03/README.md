# P1 review repair — four blocking findings addressed

Base: `ec3b738eda52c8d55c27989bdcf8d6017d320bed`.
Worktree `/home/ubuntu/.t3/worktrees/xyg/t3-47e5e75b`, branch
`t3/rust-graph-session-p1`. This is new append-only review-repair evidence;
all earlier P1/S5a receipts remain unchanged. Independent final re-review and
parent integration are still required.

1. **Shared owner, different derived overlays.** `selection.*` is the complete
   resolvable per-composition projection, using existing `GraphIdentity::refs_of`
   omission of foreign derived keys. The erroneous equality between local refs
   and global owner selection size is removed. Valid hidden local refs remain;
   the owner is not edited. Global `outcome.selected` semantics remain unchanged.
   A/B tests bind identical canonical UUID planes to one owner with different
   overlay IDs, then verify Render, fresh bind, same-owner rebind, exact retry
   bytes, hidden local refs and byte-independent owner-state equality. Normal
   no-op outcomes verify that the global selected count can exceed local refs.
2. **Quadratic result-ID projection.** Borrowed IDs and optional node/edge row
   planes now share one per-layer descriptor pass over document sections.
   Projection admits `sections + layers*(2*resolvable_selected+1)` work units.
   No per-layer `Container::get` remains in this projection. A 4,000-layer
   interleaved-schema/ID document within the existing 8,192-section bound verifies
   exact sparse rows and complete IDs, absence versus empty, Unicode, checked
   work arithmetic, plus strict type/UTF-8/out-of-range and duplicate rejection.
   There is no new layer cap. Generic container decoding and the pre-existing
   identity reader are not refactored or claimed linear by this change.
3. **Empty progressive layouts never settling.** Retained reporting now treats
   zero active nodes as done while preserving alpha and zero actual ticks. Step
   replies use that same reporter. Tests cover empty documents, empty bound
   owners, initial all-hidden owners and visibility-to-empty, including steps
   and exact byte retries. No invented force ticks or alpha changes are used.
4. **Move before first Render seeded 300 ticks in progressive mode.** The local
   seed helper honors one progressive tick or legacy absent/zero 300 ticks.
   Progressive seed work admission occurs before layout allocation for both
   render and move entry paths. Preview/Commit still invalidate continuation.
   Tests compare exact native one-tick/300-tick source positions plus delta,
   verify cancel restores seeded coordinates and commit pins/restarts on the
   next step, and prove rejected pre-camera moves and post-apply publication
   failures preserve positions, pins, force state, work, reply and sequence.

Production changes are confined to `graphforge/composed.rs`,
`interaction/wire.rs` and `interaction/layout.rs`. Regression cases extend the
already-classified `interaction/tests/wire/p1.rs`. Normative semantics are updated
in `spec/design/graph-interaction.md` and `graphforge-node-scheduling.md`.
No new production file or ownership-policy entry is needed.

| Check | Final result | Evidence |
|---|---|---|
| Focused P1 regressions | 14 passed | [argv/result](focused-corrected.json), [log](focused-corrected.log) |
| Full GraphForge engine scope | 218 passed | [argv/result](graphforge.json), [log](graphforge.log) |
| Core and WASM native adapter tests | 67 + 73 passed | [argv/result](core-wasm.json), [log](core-wasm.log) |
| Workspace Clippy/all targets/warnings denied | PASS | [argv/result](clippy.json), [log](clippy.log) |
| Rebuilt actual native C ABI regression | PASS | [argv/result](actual-native.json), [checkpoints/native hash](actual-native.log) |
| Python seams after release rebuild | 60 passed | [argv/result](python.json), [log](python.log) |
| Native ABI smoke + generated declarations | ABI398, 537 signatures current | [smoke](abi-smoke.json), [declarations](abi-declarations.json) |
| WASM generated declarations | ABI35 unchanged | [argv/result](wasm-declarations.json) |
| Ownership inventory | PASS | [argv/result](ownership.json) |
| Required pre-commit/full-worktree Ruff | PASS | `hooks.json`, `ruff-check.json`, `ruff-format.json` and matching raw logs |

`native-regression.mjs` reuses unchanged fixture/transport/capacity helpers from
`packages/xy-node/test/graph-session-wire.test.mjs`, with no host product-policy
implementation. Against the freshly rebuilt native library, A selects an A-only
derived overlay; B Render, B rebind and a fresh B bind all succeed with empty
local projections; A's later publication still carries its selected identity.
An actual native no-op reports the full owner selected count. Zero/short/exact
capacity and same-sequence byte retries run through the existing helper on every
operation. Native empty first paint and step replies report done=1, alpha=1,
steps=0. No WASM module, cached shipping asset or new package producer was used.
The initial focused test compilation used UUID pins as if they were flag bytes;
that test fixture error was corrected and its failed receipt is retained.

[Source/native hashes](source-and-native-hashes.json) identify the repaired
implementation, tests, contracts, native binary and unchanged shipping inputs.
Every command JSON records exact argv/cwd/environment, result, duration and
raw-log SHA256. The final canonical `git diff --binary --full-index BASE HEAD`
SHA256 is returned with the commit because it cannot hash itself inside its diff.

Reproduction (Rust 1.96.0 and Node22 on PATH, existing dependencies installed):

```sh
export CARGO_TARGET_DIR=target/task-tmp/p1
cargo test -p xyg-engine graphforge --lib
cargo test --offline -p xyg-core -p xyg-wasm --lib -- --test-threads=1
cargo clippy --offline --workspace --all-targets -- -D warnings
cargo build -p xyg-core --release
export XYG_NATIVE_LIB="$PWD/target/task-tmp/p1/release/libxyg_core.so"
node spec/performance/graph-session-p1-review-repair-2026-11-03/native-regression.mjs
uv run pytest -q tests/test_graph_session_abi.py tests/test_graphforge.py tests/test_gen_wasm_abi.py tests/test_verify_ownership.py
python3 scripts/abi_smoke.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The parent bind-count repair `e91fe2f7531cc808987d0af0868c321c55e51066` is not
present on this isolated base and is not duplicated here. The bind path is
untouched by this repair; parent integration must preserve its calculation of
the adopted owner's full selection count under the destination-world lock and
its existing regressions. The new tests assert projection on bind/rebind and
global count on normal outcomes without codifying the old bind-count bug.
Parent API-inventory refresh remains parent-owned.

No push, PR, remote job, parent worktree write, package-budget, ABI/export,
dependency or optimizer/profile change occurred. As requested, expensive WASM
packaging and full browser qualification were not repeated. The previous
[shipping FAIL](../graph-session-p1-2026-11-03/artifacts.json) remains unresolved;
its byte sizes describe ec3, not a fresh measurement of this repaired source.
The existing 384 MiB admission/scale limitation remains; no scale acceptance is
claimed. This evidence repairs source correctness and does not waive shipping.
