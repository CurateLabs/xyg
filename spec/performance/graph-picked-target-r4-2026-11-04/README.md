# #36 R4: retained R2 correctness, diagnostic parity only

**Scoped R4 correctness validation passes. Production packaging remains blocked.**
The exact R2 inline `Option<PickReceipt>` product is retained as the candidate;
R3 Arc ownership is rejected. There is no new size experiment, product repair,
gate/profile/compiler/optimizer/dependency/export/arena/validator/tolerance
change, browser coalescing or public hover API in this round.

- **152 Rust interaction tests pass**, zero failures/ignores.
- **9 actual C ABI/WASM diagnostic cases pass**, **468 recorded steps**, zero
  failures/skips. All **430 successful post-Open publications** compare complete
  native/WASM/Rust-engine XYGR bytes, including all five receipt sections.
- The unchanged **756,232-byte frozen R2 transcript** also passes exactly.
- Native release identity is the actual R2 core; the WASM input is the actual
  archived rejected R2 optimized module, used only in a new isolated `target/`
  directory. No rejected module was staged into either shipping asset set.
- Full-worktree pre-commit, Ruff check and Ruff format check all pass. No commit,
  PR, push, publication, GitHub mutation or root/pointer-child import occurred.

The **685 preparation gaps remain; baseline freeze remains UNACCEPTED**.
This is diagnostic correctness, **not production package, browser CSP,
old-controller, release or integration acceptance**. Independent parent review
of source/tests/policy remains required before integration.

## Exact source, preservation and final state

- Isolated worktree: `/home/ubuntu/.t3/worktrees/xyg/t3-12512ccd`
- Branch: `t3/rust-hover-pick-receipt`
- Base/final HEAD: `207ebdbdaa2ec8b0360c571683eb0fa6165e02c0`
- Full R4 source/test/spec patch SHA-256:
  `5383a32d4077dea01d8b9342068c1f20c0eaff6d5a7d7b5e4ef3580a637d3ef8`
- `full-nonreceipt.patch` includes R2 plus R4 test-only probes, correctness/replay
  tests, shared test helper extraction and current specifications. It excludes
  all receipt directories. `source-inputs.json` hashes every changed file and
  relevant build/guard inputs, the frozen R2 transcript and replay archive.
- All 14 candidate source/test/spec paths were restored to `207` after evidence
  capture. Tracked worktree and index are clean; only R1/R2/R3/R4 receipts remain
  untracked (`baseline-status.txt`). `git apply --check` of the full R4 patch
  passes on that baseline (`restore-baseline.*`). Apply the full R4 patch alone.
- Original R1/R2/R3 receipt trees, including manifests themselves, were verified
  before/after in `prior-receipts-before.json` / `prior-receipts-after.json`.
  No old patch, README, artifact archive, log or command record was rewritten.
  R2's original full patch remains
  `c0e230f8a1d1bf79a27c4bd31ce41f41963a8023d7d74518e7ab48946c5ef839`.

R4 first applied the exact R2 patch and verified all recorded input hashes.
Only `cfg(test)` probes touch the two product source files afterward. Removing
those probes recovers the exact original R2 source hashes
(`product-identity.json`). They preserve existing product source locations, and
the normal native rebuild **with the test-only source present** produces the
exact same R2 binary. The production core remains inline, with no R3 Arc-only
product code or lifetime test. The R3 receipt's original **pre-Arc R2** full-wire
transcript is read-only and was never regenerated.

Ignored binaries are intentionally labelled, not mistaken for restored HEAD:

| Path | Classification | SHA-256 |
| --- | --- | --- |
| `target/release/libxyg_core.so` | exact R2 native, **not HEAD** | `0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880` |
| `target/task-tmp/graph-picked-target-r4-diagnostic/rejected-r2.wasm` | archived rejected R2, **diagnostic only** | `e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96` |
| `target/wasm32-unknown-unknown/release/xyg_wasm.wasm` | leftover rejected **R3 raw**, **not used** | `efd99dc7040ac06e3adc084105eb10812282fd46fc9cf6e4dbd32e6e7c3d2b0b` |

Rebuild from the desired source before using default binary paths. The six
shipping module/inline/manifest paths remain absent; R4 did not create them.

## Actual-query correctness and resource proofs

`picked_checkpoint.rs` exercises real `WireSession` operations over:

- Direct, Aggregate and EdgeSample publications; Aggregate node **and edge**
  groups with both singleton and multiple-source membership. Singleton groups
  have no canonical UUID, source ref, source provenance or keyboard stand-in.
- A collapsed Direct representative at source index **2**, behind lower-index
  children, with three members. Its receipt must carry real UUID `id(3)`,
  source index 2 and full member count, rather than first-member UUID `id(1)`.
- Parallel edges, reverse lanes, a three-piece self-loop and exact derived refs;
  absent, present-empty and Unicode IDs; original u64 rows above `2^60`;
  ascending sparse layer indices and omitted existing absent-row sentinels.
- Real Hover/SelectAt Replace/Add/Toggle, already-selected query sources,
  miss, active-hover Leave, repeat Leave and empty graphs. Presence discriminants
  distinguish valid source index zero from absent scalar slots; no new sentinel.
- Same-revision publication and retained focus/highlights/pins/canonical layout
  geometry. Style/emphasis may update as designed. Hover does not change
  selection; Leave clears only transient hover and never queries.
- Exactly 10,000 selected refs plus a separate query-provenance target. Selection
  refs/indices/offset counts remain 10,000/10,000/10,001. Adding a new 10,001st
  selected source refuses SelectionTooLarge atomically, and the same sequence
  remains available for a valid Leave.

Test-only thread-local counters instrument `RenderOutput::point` itself: each
actual point operation increments once, Leave/retries increment zero times,
and stale/invalid/pre-candidate budget refusals increment zero times. A Leave
with manually seeded transient hover and **no publication** also proves zero
queries and no publication creation. The test hook is absent from release code.

Projection probes count admitted targets, a single borrowed-plane invocation,
both sparse passes and output-vector construction phases. Every successful
receipt publication checks exactly **2 × combined targets × layers** row probes,
one borrow and one output phase. R2's three frozen reuse tests remain unchanged,
including exact selection-prefix / optional query-suffix byte comparisons.

A 200-layer actual-query test admits the selection-only publication but refuses
the optional extra-source projection at the unchanged work ceiling. The point
query happens once, while combined projection admission/borrow/output phases
remain unentered. Selection, focus, transient hover, last typed outcome,
publication/paint/pick value, outbound event and retry bytes remain unchanged;
a valid Leave at the same sequence succeeds. Pre-candidate byte refusals for
Hover/SelectAt/Leave preserve the same state and perform zero point queries.
These are admission/phase and state-atomicity proofs, **not a general allocator
trace or measured RSS**. Earlier container/ref work retains existing accounting.

The frozen 756,232-byte R2 transcript checks real node/derived-edge Hover and
SelectAt, miss/Leave, same-revision updates, exact IDs/rows, identical retry,
stale/malformed requests and budget refusals. R4 keeps that transcript and
removes the Arc-only ownership test.

## Full-byte diagnostic C/WASM replay

The Rust actual-query fixture generator records requests, expected statuses and
complete engine replies in a versioned binary `XYQ2` corpus. The final corpus
has **9 cases / 468 steps**, including **430 successful post-Open publications**,
9 Open acknowledgments and 29 stale/invalid/selection-cap refusals. The complete
request/reply bytes are retained compressed, not merely response hashes.

The explicit diagnostic runner uses existing actual native-capacity and WASM
arena helpers. Their function bodies are unchanged
(`helper-guard-preservation.json`); extracting them changes tests only. It does
not drop sections, relax validators or normalize mismatched output. For every
successful publication it compares complete native, archived-WASM and engine
bytes. Native zero/short/exact-capacity calls retain byte-identical replies and
leave short caller buffers filled with the unchanged poison pattern. WASM
retries return the same complete bytes. Capacity here is the existing
**applied-success/copy-refusal** contract, not rollback.

For negative requests the expected statuses are exact (`-1`, `-3`, `-8`). Native
out_len is zero and both hosts retain the preceding successful **session retry
bytes**, checked by replaying that last request. Arena resize intentionally
clears the WASM instance's observable output before staging a new request; the
test distinguishes this from the retained session cache. Byte/work Budget
refusals are covered by the Rust tests, not claimed as cross-host corpus cases.

Eight small cases use the **existing 16 MiB** WASM allowance. The 10,000-selection
case uses the **existing 384 MiB maximum**, explicitly recorded per case. No
arena default, maximum or product policy is increased and no default-arena
massive-scale claim is made. Native/WASM hashes are hard assertions in this
explicit diagnostic test. The module path is outside shipping directories.

Final records:

- `diagnostic-native-wasm-handoff.*`: **9 passed**, zero failures/skips.
- `diagnostic-parity-handoff.json`: per-step operation, status, request/reply
  lengths and hashes, explicit input paths, Node version, case budgets and
  `DIAGNOSTIC_CORRECTNESS_ONLY` classification. SHA-256:
  `5cc885907f96b489d46d5b55a5ca67fafd2a8fc0395f9211f69c3d2960d975b5`.
- `diagnostic-parity-handoff.json.corpus.gz`: complete `XYQ2` corpus,
  2,161,156 gzip bytes. SHA-256:
  `178501f14ce0c15d90e263d38609594ff2a4c17d96a08ca2c0f7ff49b7909dba`.
- `diagnostic-summary.json`: counts, statuses, budgets and artifact identities.

The diagnostic runner is an explicitly invoked `.mjs` test, outside the normal
`*.test.mjs` glob; it requires the diagnostic module/corpus/report selectors.
It establishes no shipping/module-startup/browser qualification.

## Preserved exploratory failures and separate finding

All failed raw runs remain unchanged. Initial Rust harness compilation omitted
an enum import; this was corrected only in the test. Unit-scale fixture sampling
landed on occluded overlapping strokes; the established nonidentity Y camera
separates actual published lanes. Product geometry/picking was not changed.
The first diagnostic harness assumed observable output survived arena resize;
its failed run is preserved, and the corrected test checks the existing
retained-session retry contract described above.

**Separate existing Node Buffer-decoder defect, reported to parent and unfixed:**
`packages/xy-node/src/graphforge-container.js:38` uses
`new Array_(payload.slice().buffer)`. With a Buffer view, `slice()` retains the
larger backing buffer instead of copying the payload range. A byte-identical
valid container can therefore fail numeric decoding with RangeError.
`node-buffer-finding.mjs` reproduces this against unchanged product code;
`separate-node-buffer-finding.*` records the result and source hash. The replay
harness supplies byte-identical plain Uint8Array copies, as the existing replay
helpers do. No product decoder fix or wire guard bypass was introduced. This
finding needs separate parent triage before any broader host acceptance.

## Strict remaining production blocker

The actual R2 optimized module remains **1,926,555 raw / 785,546 Node 22 gzip6
bytes**. The unchanged gates are **1,923,072 / 783,360 bytes** (1,878/765 KiB), so
R2 remains **3,483 / 2,186 bytes over**. These are preserved R2 production
measurements, with identical module identity verified here; R4 did not rerun the
known-failing normal packager or claim a new package result.

The parent's 1,882/768-KiB functionality policy proposal is **not authorized or
adopted here**. No gate/configuration changes occur. Fresh normal production
packaging, paired assets, full unfiltered CSP foundation and old-controller
compatibility remain mandatory **after** a separate approved policy decision.
R4 supplies no browser release/acceptance claim and does not stage rejected
bytes to manufacture that proof. Independent parent source/test/policy review
precedes integration.

## Environment, status and reproduction

`run.py` records actual argv, cwd, selected environment, UTC timing, exit code
and SHA-256 of unmodified combined output. Earlier diagnostic command argv
explicitly contains all selectors; later runner records also include them in
the selected-environment fields. It refuses record overwrites.

Environment (`environment.*`): Rust/Cargo 1.96.0, LLVM 22.1.2, Node v22.23.4,
Python 3.12.15, uv 0.12.22; koffi version is recorded. Binaryen 132.0.0 remains
installed but **was not run** in R4. Repository release fat LTO/one codegen
unit/strip and inline threshold 100 remain unchanged. ABI399/538-symbol
manifest, WASM35, GPU-v1, Scene34 and painter17 declarations are unchanged.
No profile/optimizer/dependency/export/arena/guard/tolerance adjustments.
No full Python suite or browser/CSP run. Final hooks and Ruff checks all pass.

The full patch is currently saved, **not applied**. In this same isolated
worktree, retain all receipt directories (including the immutable R2 transcript
inside R3), then reproduce using a fresh diagnostic output directory:

```bash
export PATH=/home/ubuntu/.cargo/bin:/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
git apply --check spec/performance/graph-picked-target-r4-2026-11-04/full-nonreceipt.patch
git apply spec/performance/graph-picked-target-r4-2026-11-04/full-nonreceipt.patch
uv sync --group dev
npm ci --prefix packages/xy-node
cargo build --release
python3 - <<'PYTHON'
import gzip, hashlib
from pathlib import Path
p = Path('target/task-tmp/graph-picked-target-r4-replay')
p.mkdir(parents=True, exist_ok=False)
b = gzip.decompress(Path('spec/performance/graph-picked-target-r2-2026-11-04/rejected-module.wasm.gz').read_bytes())
assert hashlib.sha256(b).hexdigest() == 'e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96'
(p / 'rejected-r2.wasm').write_bytes(b)
PYTHON
env -u XYG_PICK_CORPUS cargo test -p xyg-engine graphforge::interaction --lib -- --nocapture
env XYG_PICK_CORPUS="$PWD/target/task-tmp/graph-picked-target-r4-replay/corpus.bin" cargo test -p xyg-engine picked_checkpoint --lib -- --nocapture
env XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" XYG_SESSION_WASM="$PWD/target/task-tmp/graph-picked-target-r4-replay/rejected-r2.wasm" XYG_PICK_CORPUS="$PWD/target/task-tmp/graph-picked-target-r4-replay/corpus.bin" XYG_PICK_REPORT="$PWD/target/task-tmp/graph-picked-target-r4-replay/report.json" node --test packages/xy-node/test/graph-picked-receipt-diagnostic.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Diagnostic outputs refuse existing immutable corpus files; choose a fresh
output directory for another replay. Never copy the rejected module into
`packages/xy-client/dist/` or `python/xyg/static/`. Normal producer/gate/browser
qualification remains separate and unaccepted.
