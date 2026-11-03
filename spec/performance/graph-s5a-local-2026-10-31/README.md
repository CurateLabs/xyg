# S5a Rust GPU publication and controller-result contract

Bounded implementation over parent local
`1044cdf2175d57dbed2c5088f747f812a982dc08`. **Shipping gates FAIL.**
This receipt does not complete S5, milestone 4, #36, all #108 acceptance, or a
release. No PyPI/npm publishing, push, PR, issue mutation, hardware change or
package-budget decision is part of this work. Historical receipts are unchanged.

## Contract and source

`graphforge/interaction/gpu.rs` lowers only already published `PaintGeometry`
and publication membership/emphasis into 33 additional version-1 XYGR GPU
sections. Coordinate columns are raw offset-f32; styles are existing resolved
f32/u8 records. X/y/dash-origin transforms remain binary f64 CPU metadata.
Frame → shaft → head → node order, clipped-piece edge references, dash origins,
head triangles, frame bands, RGBA/styles/layers and simultaneous state bits are
retained. No Scene, source style resolution, routing, layout or LOD is added.
The original seven CPU paint sections and f64 pick authority are unchanged.
Exact output layouts and error bounds are normative in
[graph-interaction.md](../../design/graph-interaction.md#s5a-rust-gpu-publication-and-controller-result-foundation).

The wire now serializes actual `OpOutcome.state_changed`, `selected` and the
existing `{node,collapsed}` disclosure report. Focused actions resolve the
displayed stop, reuse the existing disclosure reducer and read authoritative
pins. An Aggregate singleton is still a stamped AggregateRef with no singular
move/pin/disclosure capability. A Direct collapsed compound remains its source
representative; EdgeSample retains source-backed pin/move capability.

Pre-candidate admission adds `16,384 + 2,048n + 8,192m` bytes per source document
to the existing conservative source/text envelope, covering GPU scratch,
output/builders/caches and focused reducer work. Update admits the new envelope
while retaining the old one. Browser default 16 MiB, maximum 384 MiB, all caps,
retry/sequence/outbound and atomic owner/publication semantics are unchanged.
No native signature or WASM export/version changes are introduced by S5a.

## Actual package failure

Real Node 22.23.4 `npm run build:wasm` compiles the source with the unchanged
release O3/fat-LTO/codegen1/strip profile and production Binaryen 132 optimizer.
It fails the unchanged shipping gate, including after the final validator fix:

| Measurement | Actual | Hard limit | Excess |
|---|---:|---:|---:|
| Optimized raw | 1,872,537 | 1,860,608 (1,817 KiB) | 11,929 |
| Node gzip6 | 764,058 | 759,808 (742 KiB) | 4,250 |

Optimized SHA-256:
`4f27f5d20485ef5b63942c017ffb583191478fe74ecf78b9d94b1e7507f531a6`.
Gzip6 SHA-256:
`f18f0f6ea92ef78c19ed3bd9e495859bd255cf7be872a72a40714fcc450c9070`.
Compared with the accepted parent S4 module, this adds 12,287 raw / 5,050 gzip
bytes. There is no optimizer/profile/dependency/toolchain/export change, guard
removal, speculative size experiment or child budget increase.

`diagnostic.mjs` invokes the identical production optimizer and stores a
separately labelled module only under `target/task-tmp`. It checks exact actual
compiled signatures for all 65 manifest exports, zero imports, no start
function and WASM 35 / Scene 34 / painter manifest 17. Functional replay uses
that module explicitly with `diagnosticModule:true`. It is not a shipping asset.
The producer emits no S5a paired WASM assets. Full foundation is conditional on
successful shipping packaging and is not replaced with a diagnostic foundation.

## Proof and controls

The retained command JSON files contain actual argv, exits, times and raw/gzip
log hashes. Both successful and failed attempts remain available.

- 124 focused Rust interaction tests pass after the validator repair; additional
  focused GPU tests cover small deltas at 1e12 and extreme finite domains.
- 67 native C-ABI tests, two WASM session adapter tests, 33 focused Python
  session/generator tests and the actual native ABI smoke (673 checks) pass.
- Native and WASM ABI generators, all-target Clippy with warnings denied, and
  the client typecheck/shader-lint/build pass.
- Five actual C-ABI/optimized-WASM replay tests pass, zero skips. Every result
  compares complete bytes and independently inspects GPU columns against the
  same Rust CPU paint snapshot within the documented f32 bound. Coverage includes
  Direct, EdgeSample, Aggregate singleton/multiple, viewport/collapse, temporal
  visibility, exact derived UTF-8 IDs, all simultaneous focus/highlight and
  hover/selection bits, same-revision style/width refresh and default 16 MiB.
- Native zero/short/exact capacity and successful retry bytes, nonconsuming
  short Poll, malformed inputs, admission rollback, stale stamps, owner
  disposal/replacement, full 20,000 changed refs and unconsumed sequences remain
  exercised. GPU malformed views reject missing/wrong-type/count/index planes,
  bad flags/style tags/reserved fields, nonfinite values/transforms and invalid
  piece/head/frame references.
- `before_control.py` uses a separately built exact parent source archive and
  actual S5a C ABI. Render retains all 35 old sections byte-for-byte; selection
  at the same revision retains all 36 old sections byte-for-byte. Parent replies
  lack the 38 added GPU/fact sections. S5a adds them without replacing old
  geometry/state/pick inspection output (3,136→5,824 and 3,464→6,152 bytes).

The first replay's new test incorrectly expected state-only CPU shaft width to
stay unchanged. Existing semantic selection legitimately changes that width.
The repaired assertion checks unchanged source positions/piece identity and
requires fresh GPU shaft width at the same revision; every GPU/CPU geometry
comparison remains enabled. No product change followed that test correction.
An initial no-default-features engine test command was unsuitable for existing
native raster-only test modules; supported default-feature tests are used.

## Independent review and parent dependency

Independent reviewer `review_gpu` approved the production diff after its P2
finding was fixed: invalid shape/dash/arrow/state tags now fail GPU validation,
with four mutation cases. Reviewed production diff SHA-256:
`840b5b1c740ed97a94210d0182a9e428e4a896ec835364660bcce37f951d717a`.
Reviewed GPU source SHA-256:
`b9e096a9a3691c1d7c309f2f860df0ebf3aba02dcd521c60536828b76299b995`;
wire source:
`d97ec2d23276a4c7f83bcbca85fe809c8d01fb2f1494760f40861b4129246bb8`.
The reviewer inspected final code/tests/specs; independent test execution was
not duplicated while the implementing verification held Cargo locks. Parent
review of the final integrated diff remains required before any PR.

The parent separately owns the S4 standalone temporal-arena repair, native ABI
398 regeneration/fixture metadata and existing ownership-ledger omissions.
This child changes none of those paths. Its two new Rust paths use exact copies
of the existing `rust-engine` policy in the manifest and bounded human ledger.
Current ownership verification accepts both new paths but fails on seven
pre-existing parent paths (five S4 files plus two Node layout files); the real
repository verifier test fails for that same list, with eight other tests green.
No verifier exemption or responsibility weakening is added. The reviewed parent
dependency must be merged normally and relevant actual seams rerun when supplied.

S5b still owns session transport/controller, retained-view hydration, DOM/ARIA,
generic shader consumption and deletion of `58_graph.ts` hover policy. Visual,
scale/responsiveness and S6/S7/M4/#108 acceptance remain outstanding before
publishing. This is an internal foundation with no external competitor claim.

## Reproduction

Run from the repository root with the Node 22 path recorded by `run.py` and
`TMPDIR=$PWD/target/task-tmp`. Use a new receipt command name for each run;
the runner refuses overwrites. `XYG_RECEIPT_LOG_DIR` directs final hooks/Ruff
logs outside tracked files while checks run; copy them here only afterward.

```sh
python3 spec/performance/graph-s5a-local-2026-10-31/run.py repeat-engine cargo test --offline -p xyg-engine graphforge::interaction
python3 spec/performance/graph-s5a-local-2026-10-31/run.py repeat-native cargo build --offline -p xyg-core --release
python3 spec/performance/graph-s5a-local-2026-10-31/run.py repeat-shipping npm run build:wasm
# Only after the real shipping failure, for explicitly diagnostic functional proof:
python3 spec/performance/graph-s5a-local-2026-10-31/run.py repeat-diagnostic node spec/performance/graph-s5a-local-2026-10-31/diagnostic.mjs
python3 spec/performance/graph-s5a-local-2026-10-31/run.py repeat-replay env XYG_SESSION_WASM=target/task-tmp/s5a-diagnostic.wasm node --test packages/xy-node/test/graph-session-wire.test.mjs
```

For the before control, extract `git archive 1044cdf2175d57dbed2c5088f747f812a982dc08
Cargo.toml Cargo.lock rust-toolchain.toml .cargo crates` into
`target/task-tmp/s5a-parent-source`. Build with the exact `before-build.command.json`
argv, then run `uv run python spec/performance/graph-s5a-local-2026-10-31/before_control.py`.
`capture.py` records source/artifact/environment hashes and verifies every
historical receipt against the parent Git blobs. Its nonreceipt diff digest
avoids a self-referential receipt hash; the final canonical whole binary/full-index
diff digest versus the parent is reported with the committed handoff.

Final full-worktree pre-commit hooks, `uv run ruff check .` and
`uv run ruff format --check .` pass, with new sources staged first and logs
captured outside tracked files. All 2,597 historical receipt files match the
parent Git blobs. `final-checks.json` binds those checks to the nonreceipt diff.
