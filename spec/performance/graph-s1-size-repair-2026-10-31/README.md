# Bounded S1 WASM size repair: partial savings, package gate FAIL

The retained repair saves **890 raw / 706 gzip6 bytes** relative to recovered S1,
but **does not repair the package gate**. The unchanged packager still measures
**1,546,708 raw / 639,531 gzip6 bytes**, **3,540 raw / 555 gzip bytes over budget**.
Four measured candidates exhausted this deliberately narrow attempt. No S2–S7
behavior, dependency, compiler/profile/optimizer change, gate increase, feature
removal, or unrelated geographic fix is included. #36 and milestone 4 remain
incomplete. The parent owns independent review and integration; this local
commit is not a release or a validated package.

## History and source binding

Worktree: `/home/ubuntu/.t3/worktrees/xyg/t3-cbd63022`, initially at `1440bec9`.
Fast-forward merge of recovered S1 `8878a151767e1f1092fca921117aa7a6d91e5471`
retains both existing histories. There is no remote update or history rewrite.
The [historical S1 failure receipt](../graph-s1-recovery-2026-10-31/README.md)
and all its raw logs remain unchanged.

[Source before](source-before.json) hashes tracked Rust, Cargo, toolchain,
optimizer, packager, npm and WASM ABI inputs at recovered S1. `source-after.json`
records the corresponding final inputs; `results.json` binds the manifests,
artifacts, fixture snapshots, candidate patches and raw logs by SHA-256.
The retained three-file implementation patch is [candidate-3.patch.gz](candidate-3.patch.gz),
decoded SHA-256 `6890e42a0ef239ee8c64b575e7cbb6ad1c4fa12db033552c9bf5ba3dab445668`.
Decode with `gzip -dc candidate-N.patch.gz | git apply`; all four patches
apply independently to recovered S1. Generated WASM/client
artifacts remain ignored and uncommitted.

## Diagnosis before editing and measured candidates

The local baseline exactly reproduced the historical compiler and optimized
artifact hashes. Optimized wasm32 engine LLVM IR showed `finish` and hierarchy
resolution inlined into `base::build`: **2,907 IR lines / 258,892 textual bytes**,
including the intermediate vector paths and inlined UUID resolver. `encode_graph`
contained the ancestor memo/conversion path. [diagnosis-before.json](diagnosis-before.json)
records the complete IR hash and counts; `base-build-before.ll.gz` retains the
exact selected function. These are pre-final-LTO IR diagnostics, **not shipped
function byte sizes**. `section-sizes.json` records actual WASM section sizes.

| Candidate | Optimized raw | gzip6 | Disposition |
|---|---:|---:|---|
| Recovered S1 | 1,547,598 | 640,237 | Exact baseline reproduction; gate FAIL |
| 1: `resolve_hierarchy` out of line | 1,547,781 | 640,278 | Reverted: both measures regress |
| 2: shared UUID validation; direct hierarchy resolution | 1,546,923 | 639,837 | Retained as part of 3 |
| 3: also compact ancestor memo | **1,546,708** | **639,531** | Retained; gate still FAIL |
| 4: also `finish` out of line | 1,546,653 | 639,653 | Reverted: only 55 raw bytes saved for 122 extra gzip bytes |
| Unchanged limit | 1,543,168 | 638,976 | Neither limit is met |

All builds use Rust **1.96.0**, workspace O3/fat LTO/one codegen unit/strip,
target inline threshold **100**, pinned Binaryen **132.0.0** and
`wasm-opt -O3 --all-features`. gzip is Node `gzipSync` default level 6.
[environment.json](environment.json) records the environment; individual size
JSON files include compiler/optimized/gzip hashes. No runtime speedup or benchmark
ladder result is claimed.

## Preservation boundary

The collector's `Option<Option<Uuid>>` declarations are unchanged: undeclared,
explicit root and parented remain distinct, and conflicts retain both-order
rejection. It now resolves declarations directly into the dense parent/validity
planes using the same per-parent UUID validation as `resolve_parents`, eliminating
intermediate UUID, input-validity and final root-conversion vectors. Public
`resolve_parents` retains its signature, length checks, row validity checks,
nil-before-lookup validation and row order. The collector resolves all UUIDs
before forest validation, then replaces roots in place. Unknown/self/cycle/nil
errors, their text/fields and precedence remain unchanged. `finish` and all
endpoint/empty-graph checks remain in their original order.

Ancestor memoization uses `COSE_NO_PARENT - 1` for unresolved and `COSE_NO_PARENT`
for a resolved root. Both lie outside the admitted dense index range. The first
walk finds an already-known answer or a root/visible proper parent; the second
walk writes that answer along the same unresolved chain. Each node is examined
at most once in each walk. Random forests and the 100,000-deep shared chain
retain exact ancestor results and the deterministic **<=2n** work bound.

Session identity, generation/staleness, error/op-sequence behavior, atomic
10,000-ref selection/highlight limits, caption precedence, arrow/annotation
behavior and geographic/temporal policy are untouched. ABI remains **396 / 529
symbols**; no host, WASM ABI, fixture, Scene or painter contract is changed.

## Verification and remaining blockers

Before and after each pass **1,830 Rust tests, 102 focused Python tests,
156 graph/CoSE/worker/temporal Node tests and 673 ABI smoke checks**, plus
cross-host/semantic goldens, ABI declarations and browser render/streaming smokes.
Strict Clippy and ownership verification pass. Full-worktree pre-commit, Ruff
check and Ruff format check pass. Final counts and command exit codes are
recorded in `results.json`, with lossless raw logs
(`gzip -dc <log>`). All tracked GraphForge fixture hashes match
[fixtures-before.json](fixtures-before.json); `fixtures-after.json` records the
same bytes. Node exercises actual optimized WASM, including hierarchy errors,
root/parent conflicts and native/WASM document byte equality. The unchanged
CoSE golden corpus also passes.

The packager fails before emitting a manifest/inline asset set. The optimized
module is copied only into ignored `dist/xyg-wasm.wasm` for functional parity;
this does not establish packaged-asset validation, installation-cohort readiness
or a release. Further narrow work must recover **at least 3,540 raw and 555 gzip
bytes** under the same toolchain and gates. This attempt stops at that concrete
blocker instead of expanding into unrelated engine optimization.

The historical broader Node **15 failures / 1 cancellation**, existing full-tree
Rust formatting debt and release/API inventory gaps retain the disposition in
the S1 recovery receipt. They were not repaired or reclassified. The multi-hour
full Python suite and release installation cohort were not run here. Mandatory
full-worktree pre-commit/Ruff gates run before the local commit. Independent
review, dependency integration, and all S2–S7 acceptance work remain with the
parent; no remote mutation, PR, issue closure, tag or publication occurred.

## Reproduction

[commands.txt](commands.txt) lists the exact build, unchanged package gate,
focused correctness/golden checks, browser paths and mandatory hooks.
[measure.mjs](measure.mjs) independently runs the shipped optimizer over the
compiler bytes and records raw/gzip6 sizes and hashes in a chosen output
directory. Reproduce the baseline in a separate checkout of `8878a151`, then
apply exactly one candidate patch and repeat the same commands. Do not use the
historical failed receipt as a passing package claim.
