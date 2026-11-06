# #36 R3: one immutable Arc representation experiment — failed gates

**R3 fails both unchanged production limits and is not integrated.** The sole
representation experiment uses `Option<Arc<PickReceipt>>`, sharing original
immutable query facts through outcome/candidate/retry clones and borrowing them
for serialization. Native `OpOutcome` shrinks from 272 to 160 bytes, but the real
optimized WASM grows **1,768 raw / 55 gzip6 bytes versus R2**. It measures
**1,928,323 raw / 785,601 gzip6 bytes**, exceeding the hard limits by
**5,251 / 2,241 bytes**. No further representation or source experiment followed.

The **685 preparation gaps remain; baseline freeze remains UNACCEPTED**.
This deliberate experiment authorization is not integration approval. Functional
qualification is unfinished; final independent review remains parent owned.
No #36/M4/#108/release/competitor/runtime-performance acceptance is claimed.
No PR, push, GitHub mutation, publication, credential operation, root-worktree
change or pointer-child/main import occurred. No commit was made.

## Exact source and safe handoff

- Worktree: `/home/ubuntu/.t3/worktrees/xyg/t3-12512ccd`
- Branch: `t3/rust-hover-pick-receipt`
- Base and final HEAD: `207ebdbdaa2ec8b0360c571683eb0fa6165e02c0`
- Full R3 non-receipt patch SHA-256:
  `f008a9ee82d461c84cfaec838d1a6cc7949485682c4434431649ce79c433b2c5`
- `full-nonreceipt.patch` includes R1, R2 and this sole R3 experiment with tests
  and relevant design contracts. `source-inputs.json` hashes every changed path,
  build/guard inputs and the separate R2 transcript test artifact. This source
  was frozen before release builds and checked unchanged through package failure.
- All nine changed source/spec paths were restored to exact `207`. The tracked
  worktree and index are clean; only R1/R2/R3 receipt directories remain untracked
  (`baseline-status.txt`). `git apply --check` of the full R3 patch passes on the
  restored baseline (`restore-baseline.*`). Apply R3 alone, not on top of R2.
- Ignored native/raw WASM binaries in `target/` contain the **rejected R3
  candidate**, not HEAD. Their exact hashes are below. Rebuild the desired source
  before using those paths. Local dependency/client outputs remain ignored.
  No shipping WASM assets were emitted.
- The golden transcript is a test dependency retained inside this receipt:
  `r2-wire-transcript.bin`, 756,232 bytes, SHA-256
  `26833b00743ba689888483ada900d90ba6f3b3e27b5294e99242a60efc5d7842`.
  Keep it alongside the patch; do not regenerate it under R3 source.

R1's original patch remains
`fa6d5ecdae3c404694bca4a944304647fc4246bd307fa82270ba645f2e6ee388`;
R2's remains
`c0e230f8a1d1bf79a27c4bd31ce41f41963a8023d7d74518e7ab48946c5ef839`.
Their entire receipt trees were verified against their manifests before applying
R2, then snapshotted (including manifests themselves) in
`prior-receipts-before.json` and checked byte-exact afterward. Their README,
failed commands, archives, artifacts and logs were not rewritten. Their original
failed statuses remain failures.

## Representation and allocation accounting

The original pre-mutation receipt is captured exactly once and moved into one
`Arc::new` allocation. Its actual target, stamp, source/group identity and
provenance remain unchanged. Deriving `Clone` for `OpOutcome` now clones the
Arc, not the receipt's owned canonical string. Serialization uses `as_deref`;
R2's combined projection and borrowed-ref path are unchanged. No extra cache,
interior mutability, RefCell, source identity lowering, operation signature or
C/WASM signature was introduced. Typed Leave creates its receipt after existing
stamp/retry checks and **before** clearing transient hover; it performs no query.

The already charged extra **4,096-byte fixed receipt reserve** remains exactly
unchanged. R3 names that reserve instead of leaving it inside literal 8,192
(the preceding selection reserve is still 4,096). It is admitted by
`WireSession::execute` before candidate cloning and typed application, for point
Hover, SelectAt and typed Leave alike. Owner-state admission still precedes
candidate application too. No admission allowance or byte/arena limit increases.

At most one old and one new distinct engine-owned receipt coexist in a wire
transaction; outcome/candidate/retry copies share each receipt. A conservative
**1,024-byte subreserve** within the existing fixed 4,096 explicitly covers both
receipt bodies, Arc counters and alignment slack. Compile-time guards enforce:

```
align_of::<PickReceipt>() <= 2 * size_of::<usize>()
2 * (size_of::<PickReceipt>() + 4 * size_of::<usize>()) <= 1024
```

Both native and actual WASM release builds pass these target-specific guards.
On native, measured `PickReceipt` size/alignment is 120/8, giving a **304-byte
logical bound** for the pair under this formula. That is an accounting allowance,
not an allocator trace. The remaining 3,072 fixed bytes plus existing per-row,
text and cache envelopes keep covering receipt metadata, combined scratch and
encoded/builder/final/cache copies. `accounting.json` records these facts and
limits. Existing direct internal typed methods retain their work/stamp contract;
the byte-budget guarantee belongs to the admitted wire product boundary.

There is no instrumented claim that all request/ref/outcome work avoids
allocation: container decoding, changed-ref Vec cloning and other existing
allocations retain their existing accounting. The lifetime probe observes strong
counts 2/4/1 and loss of upgrade when the retained outcome is replaced. Its Weak
probe keeps the old control block allocated until the probe drops; loss of
upgrade proves data/strong ownership ended, not that this probe's control block
was already freed. Caller-retained typed outcomes are caller-owned lifetimes.
No new correctness or accounting defect was observed by this scoped proof.

## Minimum proof completed before measurement

With exact saved R2 product source applied, the test-only transcript fixture was
captured **before** the Arc change (`r2-transcript-capture-fixed.*`). It records
complete real requests and XYGR replies for point Hover, SelectAt, actual derived
edge hits, miss, typed Leave and repeat Leave; each success is retried with exact
request bytes. Source provenance includes node row 42 and derived edge row 13,
with absent, present-empty and Unicode exact result IDs.

It also exercises stale Leave, malformed Leave-with-coordinates, and pre-candidate
budget refusals for point Hover, SelectAt and typed Leave. Refusals explicitly
preserve retained reply, selection, focus, transient hover, last typed outcome,
published geometry/flags and outbound event; valid same-sequence work succeeds
after refusals. All requests, statuses and cached responses are retained in the
transcript. R3 compares the complete **756,232 bytes**, including selection and
all five receipt sections, exactly against that R2 artifact. This is more than
Arc pointer equality or an inferred semantic equivalence.

A second test checks original query association, returned/cloned/cached outcome
facts, Arc sharing, release after replacement, stale Leave preservation and
cached Leave identity. Its pointer checks supplement the full byte comparison.
It prints native layout and the logical two-Arc allowance.

`rust-checkpoint`: **149 passed**, 0 failed/ignored, 1,682 filtered out. This
includes all unchanged 138 original interaction tests, all three unchanged R2
reuse tests, both R3 tests and six other existing interaction validations.
`r3-wire-comparison` separately passes the full transcript comparison. The first
new capture harness compilation failed on test private-field access; that raw
failure is preserved as `r2-transcript-capture.*`. It was corrected to use the
existing session accessor before capturing R2; no product policy was changed to
fix the test. No source was adjusted after freezing to search for a smaller size.

Broader actual-query Direct/Aggregate/EdgeSample, collapsed/singleton,
parallel/self-loop, complete capacity/allocation atomicity, stronger no-query
Leave instrumentation, actual new-receipt native/WASM full-byte parity, fresh
unfiltered full CSP and old-controller/browser compatibility qualification remain
unfinished. The failed early gate stopped that broader work as instructed.

## Actual production failure and deltas

The one normal `node js/package-wasm.mjs` attempt exits **1**:

```
Error: xyg-wasm gzip is 785601 bytes, over the 783360-byte budget
```

It stops at the unchanged gzip check before raw-size/export/signature/version
checks, so success of those later checks is not claimed. The separate
`same-input-measurement` invokes the exact existing `optimizeWasm` helper on the
same compiled input with normal Binaryen arguments, reproduces the producer's
gzip count and archives its rejected optimized bytes. This is the same single
candidate, not another source experiment or alternate profile. No rejected bytes
were staged as shipping output.

| Candidate / comparison | Optimized raw bytes | Node 22 gzip6 bytes |
| --- | ---: | ---: |
| Parent-supplied baseline (not rebuilt here) | 1,922,723 | 783,181 |
| Preserved R1 | 1,927,577 | 785,926 |
| Preserved R2 | 1,926,555 | 785,546 |
| R3 actual | 1,928,323 | 785,601 |
| R3 minus R2 | +1,768 | +55 |
| R3 minus R1 | +746 | −325 |
| R3 minus supplied baseline | +5,600 | +2,420 |
| Strict unchanged limit | 1,923,072 (1,878 KiB) | 783,360 (765 KiB) |
| R3 over limit | **5,251** | **2,241** |

A smaller native outcome layout did not produce a smaller WASM artifact.
No finer component attribution or runtime-speed measurement is claimed.
`artifacts.json` gives exact SHA-256 values:

- Optimized WASM, 1,928,323 bytes:
  `165eaae5341c31c68ad83d178219242ac406185f413d39935ad700156f63a5e6`
- Retained gzip6 archive, 785,601 bytes:
  `99ed6705112fdda3bf9c9775e0b81864dcc4d389c029f700a5103fa044107ab3`
- Compiled pre-Binaryen WASM, 2,126,290 bytes:
  `efd99dc7040ac06e3adc084105eb10812282fd46fc9cf6e4dbd32e6e7c3d2b0b`
- Native core, 6,116,312 bytes:
  `1574d281e525fbb7595143759bcdd59df6058386bed5c248485934da3a4479f1`

The normal paired-asset verifier exits **1** because both destinations lack WASM
module/inline/manifest assets. It was not bypassed. CSP, new-receipt native/WASM
parity and controller qualifications did not run on staged rejected output.
No Box, inline-attribute, profile, budget or other representation follow-up was
attempted. Further work requires a separate parent functionality decision.

## Build environment, raw commands and reproduction

`run.py` records exact argv, cwd, selected environment, UTC start/end, exit code
and SHA-256 of unmodified combined raw output, refusing overwrites. Actual native
and WASM release builds and normal client build pass. Full-worktree pre-commit,
Ruff check and Ruff format check pass; `git diff --check` passes. Production
package and paired assets fail. No commit or full Python suite followed.

Environment (`environment.*`): Linux x86_64, Python 3.12.15, Rust/Cargo 1.96.0,
LLVM 22.1.2, Node v22.23.4, Binaryen 132.0.0, uv 0.12.22. Fat LTO, one codegen
unit, strip and WASM inline threshold 100 remain unchanged. RUSTFLAGS and
CARGO_TARGET_DIR overrides are absent; Cargo serialized native/WASM builds with
its normal lock. ABI399/538-symbol manifest, WASM35, GPU-v1, Scene34 and painter17
declarations remain unchanged. No dependency/export/validation/tolerance,
compiler/profile/optimizer, arena or runtime-cap adjustment. No Chromium run
followed the failed package gate.

The saved patch is currently **not applied**. Retain this receipt and its golden
transcript at the indicated path, then reproduce from exact base `207`:

```bash
export PATH=/home/ubuntu/.cargo/bin:/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
git apply --check spec/performance/graph-picked-target-r3-2026-11-04/full-nonreceipt.patch
git apply spec/performance/graph-picked-target-r3-2026-11-04/full-nonreceipt.patch
npm ci
uv sync --group dev
env -u XYG_CAPTURE_R2_RECEIPTS cargo test -p xyg-engine graphforge::interaction --lib -- --nocapture
cargo build --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
# Expected exit 1 at unchanged gzip gate; independent raw measurement also fails.
python3 scripts/verify_wasm_assets.py
# Expected exit 1: producer emitted no WASM asset sets.
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Never regenerate the R2 golden fixture using R3 source. The fixture capture
option was used only on saved R2 before changing its representation and refuses
existing output. Evidence archive/manifest writers also refuse overwrites; use a
fresh receipt directory copy to reproduce `measure.mjs`. The archived module
can be decompressed and hashed without changing source or any gate.
