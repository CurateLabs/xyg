# Node Buffer numeric container copy repair

Base: `c3d2e4aa19bcfbf9940775819f03c71cc0934472` (#1093 published head).
This is an independent Node codec correctness repair, not M4, #108, release,
scale or competitor-performance acceptance. All earlier receipts, including
the 1k first-paint evidence and its failed instrumentation bytes, are retained.
The separate R4 finding and the parallel #1093 evidence-harness repair are
not modified or incorporated here.

## Defect and repair

`decodeContainer` explicitly accepts Node `Buffer`. On little-endian hosts,
`unpackLittleEndian` previously constructed typed arrays over
`payload.slice().buffer`. Unlike `Uint8Array.slice()`, `Buffer.slice()` aliases
the backing allocation: its length can be indivisible by the numeric width,
or its contents can include the header, neighboring sections and unrelated
prefix/suffix bytes. This violates the existing copied/aligned/detached numeric
output contract. Text-list offsets use this same helper.

The fix copies the exact payload with `Uint8Array.from(payload)` before making
the numeric view. It preserves the DataView endian branch, validation,
wire bytes, versions, signatures and all Rust-owned policy. The browser twin
is unchanged: browser `Uint8Array.slice()` already copies the actual span.
No ABI, WASM, controller, Worker, point mapper, dependency or package changes
are part of this repair. Other dtype copy semantics are unchanged.

## Raw reproduction and results

`before.json` and `after.json` record the same 112-byte `XYGI` input, its full
hex bytes and SHA-256, in a `Buffer.alloc(113).subarray(0,112)`. The valid
`header.u64#0` is `[7n,9n,1n]`. Plain Uint8Array passes before and after;
Buffer throws `RangeError: byte length of BigUint64Array should be a multiple
of 8` before and decodes exactly three values after.

Original codec SHA-256:
`57e2250967df1322e0a5d449774a073f4687e01d45ef563e17b736d42e998a6a`.
Repaired codec SHA-256:
`0506d4e907b553742c042514c69efd824cc95cffb10417e077a3d84ef4f92aec`.

The new pure codec test file fails 13/25 tests against the original source
and passes 25/25 after the repair (`codec-after.tap`). It checks u32, u64,
i64 and f64 exact counts/values, empty sections, zero indices, BigInts beyond
Number precision, bidirectional mutation isolation, nonfinite f64 framing,
ASCII/multibyte/empty text lists, and malformed framing/offset rejection.
Inputs cover ordinary Uint8Array, ArrayBuffer, offset unaligned Uint8Array
and DataView, pooled Buffer, odd backing length and aligned/unaligned Buffer
views with prefix/suffix sentinels. The existing GraphForge test entry imports
these tests so the normal Node test command also runs them, without changing
package scripts. They also run independently without loading a native core.

`compositions-layout.tap`: **82/82 pass**, including those 25 codec tests and
the existing GraphForge composition, layout and general composition tests.
`session-wire.tap`: **7/7 pass**, including full native/WASM GraphSession byte
replays. No tests were skipped. `api-inventory-write.log` and
`api-inventory-check.log` record official regeneration/check; only provenance
and the codec source hash change. The 685 review gaps and contract facts stay
unchanged. The inventory Markdown is unaffected.

`context.json` records exact toolchain/artifact provenance and unchanged
browser source hashes. Integration tests use only the verified baseline
native library copied from `t3-1b0dd836` (SHA-256
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`)
and its existing WASM bytes via `XYG_SESSION_WASM`; no native or WASM build
was performed. Ordinary browser bundles were built locally for the scoped
tests and remain ignored generated artifacts. Initial environment setup
overlapped two npm installs and failed; after npm completed, bundle generation
and `uv sync --group dev` succeeded. This setup failure is not product evidence.

## Reproduce

From this worktree, use the supplied Node 22.23.4 binary on PATH:

```bash
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
mkdir -p target/task-tmp
git show c3d2e4aa19bcfbf9940775819f03c71cc0934472:packages/xy-node/src/graphforge-container.js > target/task-tmp/graphforge-container.before.mjs
node spec/performance/node-buffer-codec-2026-11-04/reproduce.mjs target/task-tmp/graphforge-container.before.mjs
# Expected exit 1 before; expected exit 0 for the current codec below.
node spec/performance/node-buffer-codec-2026-11-04/reproduce.mjs
node --test packages/xy-node/test/graphforge-container.test.mjs
export XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so
node --test packages/xy-node/test/graphforge.test.mjs packages/xy-node/test/graphforge-layout.test.mjs packages/xy-node/test/composition.test.mjs
XYG_SESSION_WASM=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/packages/xy-client/dist/xyg-wasm.wasm node --test packages/xy-node/test/graph-session-wire.test.mjs
uv run python scripts/check_release_inventory.py --write
uv run python scripts/check_release_inventory.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The three mandatory pre-commit commands have individual raw logs in this
directory. The parent must obtain independent final review before any PR or
integration. No push, PR, issue mutation, publication or main synchronization
was performed here.

## Remaining acceptance boundaries

The existing 1k receipt's remaining acceptance boundaries continue to apply:
this repair proves no additional host, workload size, performance budget,
full interactive journey or package-install cohort. M4/open issues and #108
require their own final acceptance and publishing evidence. The separate
R4/native product-path finding and #1093 evidence-harness repair remain
parent-owned work; neither is resolved by this codec fix. Full Python and
repository-wide Node/browser suites and competitor benchmarks were not run.
Big-endian execution was not available; its DataView branch is unchanged.
