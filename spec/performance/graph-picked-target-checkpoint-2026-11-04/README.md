# #36 picked-target / typed Hover Leave: early production gate failure

The Rust-only candidate is **blocked by both unchanged package limits**. No
browser feature expansion, integration, publication, push, PR or GitHub mutation
followed the failure. No budget/profile/compiler/optimizer/dependency/export/
validation or arena change was attempted. This receipt records an unaccepted
checkpoint, not #36, M4, #108 or release acceptance. The 685 API preparation gaps
remain frozen and unaccepted. Historical receipts are unchanged.

## Exact source and handoff state

- Worktree: `/home/ubuntu/.t3/worktrees/xyg/t3-12512ccd`
- Branch: `t3/rust-hover-pick-receipt`
- Base and final HEAD: `207ebdbdaa2ec8b0360c571683eb0fa6165e02c0`
- No commit was made. The seven candidate source/spec paths were restored to
  the base after measurement. The only untracked work is this receipt directory;
  the index and tracked worktree are clean (`baseline-status.txt`). Parent/root
  worktrees were not changed.
- `full-nonreceipt.patch` SHA-256:
  `fa6d5ecdae3c404694bca4a944304647fc4246bd307fa82270ba645f2e6ee388`
- `source-inputs.json` hashes every changed candidate input and the build/guard
  inputs. `unchanged-boundaries.json` also hashes native/WASM ABI manifests,
  entry files and the existing semantic decoder. Candidate bytes matched those
  hashes before restoration; `git apply --check full-nonreceipt.patch` passed
  against the restored baseline (see `restore-baseline.*`).
- Ignored native and raw WASM binaries under `target/` still contain the rejected
  candidate, with hashes below. They are **not builds of the restored baseline**;
  rebuild from the desired source before using them. No shipping WASM assets
  were emitted. Dependencies/client build outputs remain local and ignored.

## Measured result

The actual unchanged production command `node js/package-wasm.mjs` exits 1:

```
Error: xyg-wasm gzip is 785926 bytes, over the 783360-byte budget
```

The packager stops at its gzip check, before the raw-size and export/signature/
version checks. Those guards were not bypassed and their success is not claimed.
`measure.mjs` then ran the same repository `optimizeWasm` helper with the exact
same compiled input and normal `-O3 --all-features` arguments. It reproduced the
packager's gzip count and retained the optimized bytes as
`rejected-module.wasm.gz`; this separate measurement publishes no assets.

| Measurement | Actual bytes | Unchanged strict limit | Over limit |
| --- | ---: | ---: | ---: |
| Optimized WASM | 1,927,577 | 1,923,072 (1,878 KiB) | 4,505 |
| Node 22 gzip level 6 | 785,926 | 783,360 (765 KiB) | 2,566 |

Compared with the parent-supplied baseline of 1,922,723 / 783,181 bytes, the
candidate grows 4,854 raw / 2,745 gzip bytes. That baseline was supplied by the
parent, not rebuilt here. Neither limit changes.

Exact SHA-256 values (`artifacts.json`):

- Optimized WASM, 1,927,577 bytes:
  `ffd6e057ce05d36f36dd82827017c48945c1f52a4a5150c2159279c61265f252`
- Retained gzip6, 785,926 bytes:
  `7c5ccb7b5565871dda85d48d727ae11c3da1f5fc76c7ecb8e6b279767b1a853c`
- Compiled pre-Binaryen WASM, 2,125,719 bytes:
  `3f69d51fa7667c6c54535102e6b0e823a0c59e5fd7a8258b5979949746139ded`
- Native core, 6,119,528 bytes:
  `391b6545d05c18206bc04e32da91547ce4985210fb3127640c26bdf2c33e5851`

The normal `python3 scripts/verify_wasm_assets.py` exits 1 because both destination
sets lack the WASM module, inline copy and manifest. No rejected module was
staged as shipping output to make that check pass. Full CSP foundation, semantic
decoder browser execution and native/WASM full-byte receipt parity were not run
without qualifying production assets.

## Candidate boundary and limitations

The saved patch captures the single original `RenderOutput::point` result in a
query-scoped `OpOutcome` receipt, before mutation. It carries the real
`PickTarget`, request stamp, member count and optional exact source index/ref.
Direct/EdgeSample nodes use the actual source mapping used by paint; the same
publication's `focus_node` array is its real visible representative in those
tiers. Aggregate node/edge targets never expose a keyboard/source stand-in,
including singleton groups. Serializer code never repicks or derives the target
from selection, focus or flags. A collapsed Direct node retains its actual UUID
and full member count.

The five additive `pick.*` sections and typed operation-0/action-1 Leave are
specified inside the saved patch. `kind` explicitly controls presence of the
render index, and `form` explicitly controls presence of the source index;
absent slots have canonical zero values, while valid index zero remains valid.
There is no ambiguous zero sentinel. Source provenance shares the existing exact
layer-ID/validity table and borrows projection planes once. It counts both sparse
passes before allocating row output, with additional conservative admission
reserves; the runtime caps stay fixed. Leave forbids all coordinates and clears
only private transient hover, without invoking the point query.

The existing TypeScript semantic decoder's named-section reader permits additive
sections; it does not interpret or expose these new receipts. No TypeScript
runtime/interface change, pointer mapper change, public hover event, scheduler,
coalescing, tooltip, linking, controller hover or legacy replacement was made.
ABI399 / 538 native symbols, WASM35, GPU-v1, Scene34 and painter17 declarations
remain unchanged. No C/WASM signature change required a generated ABI update.

Only the minimum proof required to reach the early gate was completed. The
additional Direct/Aggregate/EdgeSample, collapsed/singleton, parallel/self-loop,
absent/empty UTF-8 provenance, no-query instrumentation, full preservation and
allocation-atomicity cases requested for a passing checkpoint remain unfinished.
New-receipt full-byte native/WASM parity, fresh unfiltered CSP foundation,
integrated decoder compatibility and independent final review are still needed
before any subsequent browser phase. No performance or competitor win is claimed.
The blocker needs a separate parent decision; this task attempted no size repair
or alternate profile.

## Actual checks and environment

`run.py` records exact argv, cwd, selected environment, UTC timestamps, exit code
and SHA-256 of unmodified combined output, refusing to overwrite existing records.

- `rust-focused`: **138 passed**, 0 failed, 0 ignored; 1,688 filtered out.
  This is the existing 137 interaction tests plus one new exact-node/retry/
  same-revision/miss/typed-leave/malformed-frame/stale/budget regression.
- `native-release`, `wasm-release`, `client-build`: pass, using actual release
  builds and normal `node js/build.mjs`.
- `production-package`: **FAIL**, exit 1; the actual failed producer log is kept.
- `same-input-measurement`: pass as a measurement, **not** package qualification.
- `paired-assets`: **FAIL**, exit 1; missing assets are recorded unchanged.
- `hooks`, `ruff-check`, `ruff-format-check`: all pass across the full worktree.
  No commit followed. `git diff --check` passed too.
- `initial-path-failure.log` retains the first shell failure (`cargo` absent from
  login PATH; exit 127). `initial-rust-137.log` retains the corrected absolute-path
  run before the new focused test. Those two exploratory logs predate the
  timestamped runner and do not have runner-generated timing metadata.

Build environment (`environment.*`): Linux x86_64, Rust/Cargo 1.96.0, LLVM 22.1.2,
Node v22.23.4, Binaryen 132.0.0, uv 0.12.22, Python 3.12.15. Cargo release fat LTO,
one codegen unit, strip enabled; unchanged target inline threshold 100. No
RUSTFLAGS/CARGO_TARGET_DIR override. The native and WASM production builds ran
from the exact saved candidate (Cargo serialized them under its build lock).
Chromium was not invoked after the package failure. No full Python suite ran.

## Reproduce without changing limits

Run in this isolated worktree or another checkout at the exact base, with the
receipt directory retained. The saved patch is uncommitted and is not currently
applied:

```bash
export PATH=/home/ubuntu/.cargo/bin:/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
git apply --check spec/performance/graph-picked-target-checkpoint-2026-11-04/full-nonreceipt.patch
git apply spec/performance/graph-picked-target-checkpoint-2026-11-04/full-nonreceipt.patch
npm ci
uv sync --group dev
cargo test -p xyg-engine graphforge::interaction::tests --lib
cargo build --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
# Expected exit 1 at the unchanged 783360-byte gzip gate.
python3 scripts/verify_wasm_assets.py
# Expected exit 1: package failure emitted no WASM asset sets.
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

`measure.mjs` is a one-shot evidence writer and refuses existing output files;
use a fresh copy of the receipt directory to reproduce that measurement. The
retained gzip archive can be decompressed and hashed independently without
rebuilding or changing source.
