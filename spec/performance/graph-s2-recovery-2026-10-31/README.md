# Bounded GraphSession S2 recovery (#1038)

This receipt covers Rust-only retained session rendering and structural state
on the reviewed S1 tip `9a52123156ef87ef8ed30a22db3d577be5ae8925`.
The existing PR head `b72b1af07cf41dfd52509d79f681bc4070f1f1ce` is
preserved as a normal merge parent. No force push, rebase, cherry-pick, PR
update, issue closure, or publication was performed. The combined prerequisite
base `465ec0a0acc16340947ea599fee7e0486f12b6d0` is already in S1;
accepted-main integration and #1029's queue remain the parent's responsibility.

This is not #36 or milestone 4 completion. Final independent parent review of
the complete final diff is required. The old Greptile review is evidence of
findings, not approval of this recovered tree. CodeRabbit skipped its review.

## Scope and slice numbering

The original S1 table bundled render, pick, coordination and update into S2.
The retained #1038 body and slice table split that work explicitly: this S2 is
render publication, emphasis, current-revision aggregate refs, transient hover,
highlights, focus state walks, disclosure, pin/move/relayout, revisions and bound
temporal visibility. Pick/admission/degraded mode, CoordinationGate/ApplyRemote
and session_update remain S3; the native/WASM session ABI is S4. Browser
controller/accessibility/painter work and Python/Node hosts remain later slices.
No broader phase acceptance is inferred from the narrower recovery.

No C ABI symbol, ABI/Scene/painter version, browser controller, host, keyboard
binding, compiler profile, dependency or budget was added or changed. Rust
focus walks are state operations. Composition v2 and S1's shared temporal
interaction state and nearest-visible-ancestor memo (`<=2n` link visits) remain
intact. #1078 worker ACK/cancel semantics are unchanged. Authored style flags
stay 7-bit (127); session emphasis only widens compound collapse's accepted
flags. All historical S1 evidence remains byte-for-byte unchanged.

## Findings and disposition

Fresh read-only GitHub captures retain the entire PR body and every available
review, inline comment and issue comment: `pr.json.gz`, `reviews.json.gz`, and
`review-comments.json.gz`. The five Greptile findings were all valid:

1. **Shared stale pin masks:** already fixed in the retained head. The force
   state tracks its authoritative pins/active nodes and drops on bind/unbind.
   Existing tests exercise direct temporal mutation and changed pin authority.
2. **Split frame stamp/visibility:** already fixed in the retained head.
   `TemporalGraph::world_parts` and `GraphSession::locked` hold one registry
   lock through validation, mutation and render publication. Hooked-lock tests
   advance a frame at the lock boundary and reject any second lock.
3. **First relayout exceeds budget:** fixed here. Admission includes 300 seed
   steps when positions are absent, plus requested steps, over visible nodes
   and edges. A fresh 70,000-node one-step request rejects before force work;
   the same graph with loaded positions accepts one step. A small fresh graph
   demonstrates admitted seed work.
4. **Collapsed hover misses neighbors:** fixed here. Hover resolves the current
   collapse representatives and traverses visible rerouted edges before LOD.
   Tests cover representative and hidden-member refs, disclosure changes, and
   absence of spurious neighbors after expansion.
5. **Rejected moves seed positions:** fixed here. Delta/camera/cancel/origin
   validation precedes initialization, and new positions stay local until the
   operation succeeds. Invalid requests leave positions, pins, revision and
   op sequence unchanged; the same sequence then accepts a valid commit.

The seven prior round-1 blocker categories are preserved and covered:
temporal masking before hierarchy collapse; visible-subgraph layout; one
locked world; shared pin authority; bounded aggregate expansion; whole-stop
focus selection; and explicit revision exhaustion. The retained tests cover
expired collapsed ancestors, layout without invisible forces, atomic frame
interleavings, external pins, repeated/oversized aggregates, whole aggregate
and collapsed-group selection, and exhaustion across every structural path.

Recovery additionally fixes **aggregate union admission**: an explicit node ref
inside a selected aggregate no longer counts twice against the exact 10,000-ref
cap. Admission subtracts overlaps using membership before expansion; oversized
groups still reject without expansion. Selection and highlight both exercise
the exact-cap overlap case.

The original three new review regressions fail against the retained code
(`regressions-before.txt.gz`); the aggregate-union test fails before its repair
(`aggregate-before.txt.gz`). These are negative controls, not green tests
silently added after the fix. `retained-engine.patch.gz` records the staged
engine merge before these repairs. The prior PR's 21 mutation checks remain
historical claims, not newly executed controls in this recovery.

## Validation

See `results.json` for exact commands, exits, environment and hashes, and
`source.json` for the producer file hashes. Raw output is retained losslessly as
`*.txt.gz` (`gzip -dc FILE` to inspect). Generated artifacts are ignored and are
not committed. No full multi-hour pytest, broad Node geo/geometry suite,
hardware benchmark, paid service or external capacity was used. S1's broad
Node stale geometry and geo-fixture failures remain baseline evidence, not a
reason to change unrelated code.

The explicit Node suite includes the worker lifecycle and composition tests;
it preserves real ACK/destruction/exit sequencing and public cancellation
semantics. Python/Node semantic goldens also cover the original PR's two CI
style-vocabulary failures. API/ABI manifests remain unchanged at ABI 396 /
529 symbols. Browser render/append smokes use the installed Chromium at the
explicit path in `results.json`; `/usr/bin/google-chrome-stable` is absent in
this environment. No dependency or browser installation is needed for those
smokes. Rustfmt checks only edited session files; the known 90 baseline
full-workspace formatting failures are not reformatted.

Package measurements and final validation totals are recorded below after the
real Node 22 package command. Package rejection, if any, remains a release
blocker and requires a separate deliberate budget decision; this recovery has
no authority to raise the accepted S1 gates.

## Actual package result: FAIL

Node **22.23.4**, Rust **1.96.0**, unchanged release O3/fat LTO/codegen1/strip,
inline threshold 100, pinned Binaryen 132 `-O3 --all-features`:

- Optimized module: **1,547,915 raw / 640,615 gzip6 bytes**.
- SHA-256: `544d97c615a96e31cdca66cac0d577b954ee337e50e2e589690dc348d7c852bc`.
- Accepted S1 limits: **1,547,264 raw / 640,000 gzip6 bytes** (1,511 / 625 KiB).
- Exceeded by **651 raw / 615 gzip bytes**. The real packager checks gzip
  first, exits 1, and publishes no artifact/manifest/inline payload.
- Compared with accepted S1's 1,546,708 / 639,531-byte module, this is
  **+1,207 raw / +1,084 gzip bytes**. S1 SHA-256 remains
  `2feaf15adfe770d5ae2f879e38b7495ae3490cd73a79ad6dcc334a66ec0a32c7`.

`package-wasm.txt.gz` retains the unmodified packager's failure.
`artifact.json` / `artifact-measure.txt.gz` independently record both sizes,
source and optimized hashes under the identical optimizer/profile. `measure.mjs`
is only a measurement script. Its raw optimized output is copied into the
ignored browser dist path solely to run diagnostic GraphForge/CoSE parity;
no manifest or inline assets are fabricated. Those results cannot establish
successful packaging or a packaged-browser foundation result. There is no
valid recovered S2 packaged asset set to pass `verify_wasm_assets.py` or the
packaged foundation smoke. Both package limits remain unresolved blockers;
a separate deliberate decision is required. No limits are raised here.

The session remains Rust-only and has no new WASM exports. Reachable shared
compound/temporal changes nevertheless affect the module. This result makes
no performance, startup, competitor, massive-source, UI or release-readiness
claim. No synthetic timing can substitute for later interaction evidence.

## Reproduce

Use a real Node 22 installation and the pinned Rust toolchain. All temporary
files go below the checkout to avoid `/tmp` quota pressure:

```bash
mkdir -p target/task-tmp
export TMPDIR="$PWD/target/task-tmp"
export PATH="/path/to/node22/bin:$HOME/.cargo/bin:$PATH"
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
uv sync --group dev
npm ci
npm ci --prefix packages/xy-node
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
cargo build --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs  # expected failure at the unchanged gzip gate
node spec/performance/graph-s2-recovery-2026-10-31/measure.mjs
```

Run the focused consumer and ABI commands in `commands.txt`. The diagnostic
Node parity step explicitly copies `target/task-tmp/s2-recovery/optimized.wasm`
to `packages/xy-client/dist/xyg-wasm.wasm` after the package refusal. A later
successful package decision must use the real packager and paired-asset and
packaged-browser checks; diagnostic copies are insufficient.

## Final functional results and remaining gates

- Rust workspace: **1,876 passed**, zero failures; 69 focused interaction
  tests pass separately. Workspace/all-target Clippy is clean with `-D warnings`.
- Focused Python: **134 passed**, four browser tests deliberately deselected;
  native backend reports `native`.
- Actual Node 22: **136 native + 33 diagnostic native/WASM parity tests passed**,
  zero failures or skips, including worker/composition lifecycle controls.
- ABI generator and host parity: passed, **396 / 529 symbols**;
  ABI smoke: **673 checks passed**.
- Cross-host composition and semantic goldens: passed unchanged.
- Ownership, Python type checking, edited-session rustfmt, render/append smokes,
  full-worktree hooks and both Ruff checks: passed.
- Real release WASM compilation: passed. Real packaging: **FAIL** at gzip gate;
  independent measurement also exceeds raw gate. No packaging acceptance.

The only recovered S2 release blockers are the two unchanged package size
limits and required independent final parent review. Later S3/S4/controller/
host/evidence work is explicitly deferred, not counted as recovered S2 delivery
or #36/M4 completion. The human author identity is used for the local merge.
No remote repository mutation was performed.

Setup diagnostics are also retained: the first `uv sync` ran before npm setup
finished and its client build failed; the retry with Node 22 succeeded. An
initial ownership command used a nonexistent script name (exit 2); the actual
repository gate `scripts/verify_ownership.py` passed. Neither is a product
failure or a waived check. The final gate log is `hooks-final.txt.gz`.

An independent diagnostic export-name/version check passes with zero ambient
imports and exactly the manifest's 60 function exports (WASM ABI 34). Its first
helper assertion incorrectly counted the compiler's two exported globals as
functions; the corrected check compares function exports and retains the
initial diagnostic separately. It is not the packager's full raw-signature or
paired-asset check and does not waive the size gates.
