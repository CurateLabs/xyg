# #36 R2: one bounded source reuse experiment — still blocked

**R2 still fails both unchanged production size limits. Stop condition reached.**
The one authorized candidate reuses the counted selection CSR projection for an
optional picked source and borrows its exact ref for encoding. It saves 1,022
raw / 380 gzip6 bytes versus R1, but remains 3,483 raw / 2,186 gzip6 bytes over
the hard limits. No further source experiment, representation change, budget
increase, browser phase, integration, publication, PR, push or GitHub mutation
followed. No commit was made.

The **685 preparation gaps remain; the baseline freeze remains UNACCEPTED**.
Neither the parent's deliberate permission for this experiment nor its reported
two independent read-only R1 reviews supplies integration or R2 qualification.
Functional qualification remains unfinished. Final independent review is parent
owned, before any PR/integration. This receipt makes no #36/M4/#108/release,
competitor or runtime-performance acceptance claim.

## Source identity and final worktree state

- Isolated worktree: `/home/ubuntu/.t3/worktrees/xyg/t3-12512ccd`
- Branch: `t3/rust-hover-pick-receipt`
- Base and final HEAD: `207ebdbdaa2ec8b0360c571683eb0fa6165e02c0`
- Full R2 non-receipt patch SHA-256:
  `c0e230f8a1d1bf79a27c4bd31ce41f41963a8023d7d74518e7ab48946c5ef839`
- `full-nonreceipt.patch` includes R1 plus the sole R2 source reuse, the focused
  tests and updated design contracts. `source-inputs.json` lists every changed
  path and its exact hash, plus unchanged build/guard inputs. It excludes both
  receipt directories. The source was frozen before the production build and
  verified unchanged through the failed package attempt.
- All eight candidate source/spec paths were restored to the exact base after
  measurement. Tracked worktree and index are clean. The R1 and new R2 receipts
  remain untracked (`baseline-status.txt`). `git apply --check` of the full R2
  patch passes on that restored baseline (`restore-baseline.*`).
- Ignored `target/release/libxyg_core.so` and
  `target/wasm32-unknown-unknown/release/xyg_wasm.wasm` still contain the **rejected
  R2 candidate**, not the restored baseline. Their hashes are below. Rebuild the
  desired source before using them. Local dependency/client outputs remain
  ignored. No shipping WASM asset sets were generated.

## R1 preservation

The original R1 patch remains exactly
`fa6d5ecdae3c404694bca4a944304647fc4246bd307fa82270ba645f2e6ee388`.
Its entire original receipt, including README, archive, artifacts, command
records and raw logs, was checked against its recorded manifest before applying
that patch. `r1-files-before.json` snapshots every file, including the manifest
itself, for a second byte-exact check after R2. No R1 receipt file was rewritten.
The old failure and its historical wording remain historical evidence; the
UNACCEPTED baseline-freeze wording above applies to this new handoff.

## Exact bounded change

The optional source `ElementIndex` is appended **after** all resolved selected
indices, including a duplicate when it is already selected. Deterministic work
admission counts the combined target count and both sparse passes before
allocating combined resolved-index and borrowed-plane scratch. Indices reserve
that target count, offsets reserve count+1, and layer/row arrays reserve the
exact counted mappings. The single CSR pass emits:

- unchanged selection prefix slices: selected indices, the selected N+1
  offsets, and the layer/row prefix ending at that selected boundary;
- the optional picked-source layer/row suffix, with no second provenance pass.

Empty selection, no source, miss, leave and group all keep valid empty slices.
The extra provenance target is not a selected ref and does not raise the 10,000
selection cap. A borrowed `std::slice::from_ref` or empty slice replaces the
one-element `pick_refs` Vec/ref clone. Existing R1 fixed/per-plane reservations
remain in place, accounting for combined scratch plus builder/final/cache
copies. They remain conservative; no arena or runtime limit increases.

All five receipt sections, header discriminants, request stamps, exact UTF-8
identity and absent-vs-present-empty semantics remain byte-compatible with R1.
No Arc/Box representation, receipt/source identity lowering or source operation
signature was changed. No C/WASM signature, ABI399/538-symbol manifest,
WASM35/GPU-v1/Scene34/painter17 declaration, compiler/profile/toolchain,
optimizer/dependency/export/validation/tolerance or package limit changed.
No TypeScript product interface/runtime, controller hover, scheduler/coalescing,
public event, tooltip, linking or legacy replacement was added.

## Focused proof before the one production candidate

`rust-reuse`: **3 passed**, zero failures/ignores. The new test-only R1 projector
is copied from the original candidate with only naming/formatting changes. It
is excluded from production compilation, not a second runtime implementation.

1. Thirty complete projection-container byte comparisons cover empty/partial/
   complete small selections, absent receipt, miss, leave, node/edge group,
   node source already selected or unselected, and derived edge refs with absent,
   present-empty and Unicode result IDs. Selection dtype/count/payload prefixes
   are also compared independently against the no-pick publication.
2. Exactly 10,000 selected refs plus a duplicate picked source match R1 bytes.
   Selection refs/indices/offset counts stay 10,000/10,000/10,001; picked rows
   retain their own suffix. Adding an actual 10,001st selected ref still refuses
   and leaves the selection unchanged.
3. A 200-layer case admits selected-target work but refuses the combined extra
   target. A malformed borrowed row plane produces Invalid without the extra
   source, but Budget with it; combined work refuses before projection
   descriptors/output are built, and the output builder stays empty. Source
   order also places combined resolved-index allocation after that admission;
   this is not a counting-allocator claim about all earlier container/ref work.
   Wire-level pre-candidate byte admission continues to cover that earlier work.

`rust-focused`: all **138 existing R1 interaction tests pass**, zero failures/
ignores (1,691 filtered out). No source was adjusted after these tests to search
for a smaller module. `git diff --check` also passes.

These are internal projection/interaction proofs. Broader actual-query Direct/
Aggregate/EdgeSample, collapsed/singleton, parallel/self-loop, no-query-on-leave
instrumentation, complete preservation/capacity/allocation atomicity,
native/WASM full-byte new-receipt parity, fresh full unfiltered strict-CSP
foundation and actual old-controller compatibility remain unfinished. The
package failure stopped that broader qualification as instructed.

## Actual production result

The normal `node js/package-wasm.mjs` command exits **1** with:

```
Error: xyg-wasm gzip is 785546 bytes, over the 783360-byte budget
```

The producer stops at its unchanged gzip check before its raw-size/export/
signature/version checks. Success of those later guards is not claimed.
The separate `same-input-measurement` invokes the exact existing repository
`optimizeWasm` helper on the same compiled bytes, with normal Binaryen arguments,
reproduces that gzip count, and archives the rejected optimized module. It is
an archive/measurement of the same single source candidate, not another size
experiment or alternate packaging profile. No shipping output is staged.

| Candidate | Optimized raw bytes | Node 22 gzip6 bytes |
| --- | ---: | ---: |
| Parent-supplied baseline (not rebuilt here) | 1,922,723 | 783,181 |
| Preserved R1 actual failed measurement | 1,927,577 | 785,926 |
| R2 actual | 1,926,555 | 785,546 |
| R2 minus R1 | −1,022 | −380 |
| R2 minus supplied baseline | +3,832 | +2,365 |
| Strict unchanged limit | 1,923,072 (1,878 KiB) | 783,360 (765 KiB) |
| R2 over limit | **3,483** | **2,186** |

`artifacts.json` records exact hashes:

- Optimized module, 1,926,555 bytes:
  `e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96`
- Retained gzip6 archive, 785,546 bytes:
  `0975dbd54304597999f505eb23cb561399aa65b10935da9c1d0f462b8bbd87db`
- Pre-Binaryen compiled WASM, 2,124,514 bytes:
  `f66281328c0ffa9a53db8ab4728ab9ed3d88f2f3ca8b58ecc6ac3db212e08231`
- Native core, 6,118,472 bytes:
  `0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880`

The normal paired-asset verifier exits **1** because both destination sets lack
WASM module/inline/manifest assets. It was not made green by staging rejected
bytes. No full CSP foundation, new-receipt native/WASM parity or browser decoder/
controller qualification ran after the failed gate. No second source/size
experiment, Arc follow-up or automatic budget decision is authorized by this
result.

## Commands, environment and reproduction

Each `*.command.json` preserves actual argv, cwd, selected environment, UTC
timestamps, exit status and SHA-256 of its unmodified combined raw `*.log`.
`run.py` refuses overwriting. Native and WASM release builds, normal client
build, three reuse tests, all 138 focused tests, full-worktree pre-commit hooks,
Ruff check and Ruff format check pass. Production package and paired assets
fail exactly as recorded. There was no commit or full Python suite.

Environment (`environment.*`): Linux x86_64, Python 3.12.15, Rust/Cargo 1.96.0,
LLVM 22.1.2, Node v22.23.4, Binaryen 132.0.0, uv 0.12.22. Repository release fat
LTO/one codegen unit/strip and WASM inline threshold 100 remain unchanged;
RUSTFLAGS and CARGO_TARGET_DIR overrides are absent. Cargo serialized the native
and WASM builds with its normal lock. Chromium was not invoked after failure.

The patch is currently saved, **not applied**. Reproduce in this isolated
worktree or a separate checkout at the exact base, retaining both receipt
directories. Apply the R2 full patch alone (it already includes R1):

```bash
export PATH=/home/ubuntu/.cargo/bin:/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
git apply --check spec/performance/graph-picked-target-r2-2026-11-04/full-nonreceipt.patch
git apply spec/performance/graph-picked-target-r2-2026-11-04/full-nonreceipt.patch
npm ci
uv sync --group dev
cargo test -p xyg-engine graphforge::interaction::wire::projection_reuse_tests --lib
cargo test -p xyg-engine graphforge::interaction::tests --lib
cargo build --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
# Expected exit 1 at unchanged gzip gate; raw independent measurement also fails.
python3 scripts/verify_wasm_assets.py
# Expected exit 1: no WASM asset sets emitted.
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The archive/manifest writers intentionally refuse existing outputs; reproduce
`measure.mjs` in a fresh receipt directory copy after applying/building R2.
The retained gzip archive can be independently decompressed and hashed without
any source change. A separate parent decision is required for further work.
