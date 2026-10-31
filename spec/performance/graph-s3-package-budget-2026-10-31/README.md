# S3 canonical outline admission and parent raw-only package decision

This is a new, separate implementation receipt for the remaining independent
geometry P2 and the parent's explicitly adopted candidate/budget decision.
It does not replace the historical [S3 local](../graph-s3-local-2026-10-31/README.md)
or [S3 review repair](../graph-s3-review-repair-2026-10-31/README.md) receipts.
All prior S1/S2/S3 receipts, fixtures and ABI manifests remain byte-unchanged.
The whole integrated S3 still requires final independent re-review and CI before
a PR. This is not geometry approval or #36, M4, #108, S4–S7, hardware or release
completion. No remote, registry, hardware or paid-capacity action was taken.

## History and scope

The isolated `t3/fix-graph-clip-overflow` checkout normally merged
`80af7df777562605b7ce0bea240c3538a7ebfca7` without rebase, force or history
rewriting. Merge `91345354905348592effad4eaecb493b4a72fee7` has parents
`1440bec94202129eea25751c3d51ee7cd1620130` and that repair commit. Full-worktree
hooks and Ruff passed before the merge commit; their exact logs are retained.
The parent owns later accepted-S2 ancestry integration; this receipt makes no
claim about that history-only merge or its pending CI.

The only incremental product/build files over `80af7df7` are:

- `graphforge/interaction/paint.rs`: local canonical outline arithmetic admission;
- `graphforge/interaction/tests/pick.rs`: two negative publication regressions
  and positive circle/square/diamond controls;
- `coordination.rs`: **only** `#[inline]` on the existing `validate` helper;
- `js/package-wasm.mjs`: **only** the authorized raw constant and decision comment.

Coordination/update logic, guard order, atomicity, public semantics, profiles,
dependencies, toolchain, compiler flags, ABI declarations and exports are
unchanged. There is no third size candidate or speculative optimization.
Current graph-interaction, graph-mark, browser-wasm and dossier contracts are
updated separately from historical evidence. The release inventory is
regenerated only after the final specification text; existing classifications,
acceptance wording and release gaps are retained, with no freeze claim.

## Independent clip finding and before/after proof

`reviewer-repro.rs` is the exact supplied
`/tmp/xyg-s3-pick-review-recheck.rs`, compiled against this checkout's engine
rlib before production changes. Its directed persisted edge carries
`edge.status=[1]`. `(0,0) → (100,0)` has a filled head; `(0,0) → (1e80,0)`
has finite mapped endpoints, deltas and computed length, yet canonical circle
`node_shape_span` returns a non-finite span. The old clip comparisons silently
publish one shaft with no required head. `baseline-repro.txt.gz` records this
failure; the original `1e155`/camera length repair still rejects as expected.
The unchanged repro after rebuilding the repaired engine
(`fixed-repro.txt.gz`) retains the normal headed edge and rejects `1e80`,
`1e100`, `1e150` and `1e155` with `Invalid`.

`regression-before-compiled.txt.gz` captures **two failing new negative tests
and 22 passing controls** against unchanged production code. After repair,
all **24 pick tests** pass within the final 101 interaction tests. The negative
contracts are externally observable session behavior, not a test of an invented
replacement clipper:

- A directed circle edge at `1e80` in either axis must reject with no publication,
  camera or revision advance; an ordinary 100-unit directed edge keeps its head.
- A linked session first publishes valid camera/paint and has an edge selection,
  node focus, pending outbound snapshot and operation retry state. A camera
  mapping the chord to `1e80` must reject. The complete old publication (including
  index, paint, node/edge membership), both revisions, camera, state, pending
  snapshot, outbound sequence and last operation remain equal. The old stamp
  still selects the persisted edge and advances outbound sequence exactly once.

The narrow repair is S3 admission in `paint.rs`. Before canonical clipping,
`admit_outline_span` checks the arithmetic in the existing circle quadratic
(`qa`, `qb`, `qc`, discriminant, denominator and returned span) and the
square/diamond half-plane offsets, slopes and divisions. It then uses the
unchanged canonical kernel; it produces no alternative span or geometry.
The polygon audit covers offset subtraction, diamond half-plane addition and
ratio overflow, including canonical comparisons that can mask invalid results.
The circle audit includes negative-infinite discriminants otherwise returned
as `None`, as well as `Some((NaN,NaN))`.

Finite canonical misses stay valid, including terminal misses that retain heads.
Disabled outlines and canonical early misses remain valid. Polygon ±infinity
bounds are legitimate unbounded sentinels for slopes below the existing parallel
tolerance; they remain admitted for tiny occluded chords. Tests retain ordinary
headed edges, coincident nodes, tiny/ordinary fully occluded chords across all
three canonical outlines, loops/parallel routes, and fully culled graphs. The
original `1e155`, squared-length camera overflow and opposite-`MAX` routing-delta
controls remain unchanged and pass. No coordinate cutoff, clamp, robust alternate
algorithm, custom shape, fallback chord, shared legacy renderer change or ABI
change is introduced. Existing final-coordinate and frame checks remain intact.

## Parent retention and raw-only budget decision

The previous child measured exactly two annotations and reverted both. Its
historical rejection and old failing gates remain unchanged. Independent policy
review `m4_s1_size_policy_review` verified that candidate 1 was attribute-only
and recommended retaining it as a Pareto improvement. The parent adopted that
recommendation for this round; this implementation follows that decision.

Historical Node 22 measurements, **not fresh final-source acceptance**:

| Source | Raw | gzip6 | Disposition at that checkpoint |
|---|---:|---:|---|
| S2 | 1,547,779 | 640,527 | S2 packaged baseline |
| S3 repair baseline | 1,548,509 | 640,755 | old raw gate fails by 221 |
| Candidate 1, `#[inline]` | 1,548,390 | 640,709 | child rejected: old raw gate still fails by 102 |
| Candidate 2, `#[inline(never)]` | 1,548,509 | 640,755 | child rejected: zero improvement |

Historical baseline SHA-256 is
`1ba9fcc8c8bef3b2acc9b87f6b740e5c57bd4f7b8f94335da8f7f3c674f52019`;
candidate 1 is
`db698663bb9db02e50001af58e45c538cbdd9644c778d52ae82aebd6a3baa61a`.
Candidate 1 historically saves **119 raw / 46 gzip bytes**. Parent retention
changes the earlier disposition; it does not rewrite an old failure as a pass.

The parent authorized only the smallest next-KiB **raw** limit:
**1513 KiB = 1,549,312 bytes**. Gzip remains **626 KiB = 641,024 bytes**.
Fresh source must still fail if either is exceeded; no further raise is
permitted. Reachable shared coordination-gate extraction adds **611 raw /
182 gzip bytes** over S2 after retaining the hint. The typed session is not
WASM-exported. This is attribution of functionality bytes, not a performance win.

## Fresh real package and provenance

`wasm-build` and `native-build` rebuild the final geometry and retained hint.
`package-wasm` invokes the real producer with actual Node **v22.23.4**, unchanged
release O3/fat LTO/codegen1/strip, inline threshold 100, pinned Binaryen **132**
`-O3 --all-features`, and Node `gzipSync` default level 6. Packaging exits **0**.

| Fresh final artifact | Measured bytes | Gate | Headroom |
|---|---:|---:|---:|
| Optimized WASM | **1,548,390** | 1,549,312 | **922** |
| Node gzip6 | **640,709** | 641,024 | **315** |

Fresh optimized SHA-256:
`db698663bb9db02e50001af58e45c538cbdd9644c778d52ae82aebd6a3baa61a`.
Fresh gzip6 SHA-256:
`2ffb1209c2475fba0d33fb82475b5a0018eafe5d830b46ffb66e61aa252d24ad`.
Fresh pre-optimizer source SHA-256:
`57faf55aa486343112f251d195149fd3a245f9a053dd4b1b23158001e465a74c`.
The final geometry source differs from the historical candidate, so the match
is a fresh measured result, not an assumed inherited package acceptance.

`artifact.json` binds the actual producer's browser/Python WASM, inline script
and manifests; `packaged-wasm.manifest.json` retains the actual metadata. Each
paired file is byte-identical. `verify_wasm_assets.py` passes. The module has
**0 ambient imports, 60 exact function exports, WASM ABI 34, Scene 34, painter 17**.
Generated shipping files remain ignored, not committed as product source.
No diagnostic WASM copy is used for any acceptance run.

The native core is rebuilt **before** Python/Node checks. `environment.json`
records the tools, Python, native backend, local TMPDIR, profiles/locks and
binary hashes. `node-module-provenance.json` records actual Node executable,
checkout-local `@curatelabs/xyg-node` module, loaded Linux koffi binary and the
actual native-library path/SHA. This is local Node-module provenance, not wheel,
registry, cross-platform or publication acceptance.

`source-final-build.json` binds the 244-source build-time snapshot, including
its then-current specification text. Later edits are specification/receipt and
inventory only; `source-final.json` records the completed current specification
snapshot as well. Production/build inputs match both snapshots. Neither
snapshot hashes itself. `history-before.json` binds 2,003 historical files;
`verify-receipt.py` checks them, command/log pairs, source bindings, actual
assets, scope, original foundation harness, six PNGs and inventory preservation.

## Full original foundation and meaningful validation

`browser-foundation` runs the **unchanged original full**
`scripts/wasm_foundation_smoke.mjs`, not its density-only selector. It explicitly
unsets the selector, staged-package override and release-commit override.
`browser-foundation.json` is a real report: **passed**, **full-foundation**,
**source-dist**, **artifactCommit null**, Node v22.23.4, Chromium 156.0.8078.4,
strict local-only CSP and **zero external requests**. It binds the real packaged
WASM/client/worker and original harness hashes, plus **six PNGs** (three cases
through each ESM/IIFE entry) with framebuffer and screenshot hashes. Source was
uncommitted when measured, so the merge SHA is only `harnessCommit`; it is not
misrepresented as the artifact commit.

The full foundation includes actual packaged-WASM temporal state/selection,
cross-worker event delivery, atomic selection, stale-revision and self-echo
refusals, exact bigint state, playback/disposal and temporal graph lifecycle.
Native temporal regressions execute the actual C ABI through Python/Node;
they are not merely host scalar-validation tests.

| Final check | Result |
|---|---|
| Full Rust workspace | **1,782 engine + 58 core + 65 WASM + 5 integration** passed |
| Graph interaction | **101** passed, including 24 pick tests and 3 new outline arithmetic audit tests |
| Temporal controller engine | **13** passed |
| Clippy | full workspace, all targets, `-D warnings`, passed |
| Native and wasm32 builds | passed |
| Client typecheck/shader lint/bundle | passed |
| Real package, paired assets and artifact measurement | passed |
| Packaged Node graph/CoSE parity, cross-host and force lifecycle | **51**, none skipped |
| Native Node graph/composition/temporal seams | **136**, none skipped |
| Focused Python native graph/style/temporal seams | **134**, 4 browser cases deliberately deselected |
| ABI generation/parity | **529 symbols, v396**, unchanged |
| ABI smoke | **673** checks |
| Semantic + cross-host goldens | passed, fixtures unchanged |
| Non-NumPy render + append smokes | passed, explicit cached Chromium |
| Original full strict-CSP local-only foundation | passed, actual report + 6 PNGs |
| Python type check | passed |
| Final inventory, touched Rust format, full hooks + Ruff | exact command logs retained |

All commands, exits, timings, decompressed-log SHA-256 and compressed-log SHA-256
are indexed in `results.json` and `*.command.json`; logs are deterministic gzip
with `mtime=0`. Intermediate mistakes are retained transparently: the first
repro link ran before the baseline rlib existed; the first regression draft used
two wrong test API names; the first shape audit mistakenly called an unbounded
circle line through its center a miss (corrected its input to a true offset
miss); the first environment capture preceded WASM build completion. None is
claimed as a behavioral regression or final pass. The corrected failing-before
and successful-after runs have distinct names. Assertions were not relaxed to
admit non-finite results.

## Environment and reproduction

From this checkout, use the exact argv vectors in `*.command.json` with
`uv run python spec/performance/graph-s3-package-budget-2026-10-31/run.py NEW-NAME COMMAND ...`.
Use a **fresh receipt directory** for a full rerun; this runner refuses to
replace an existing command/log name. Never run an older receipt's `run.py`
against its historical output directory. The local runner prepends actual
Node 22 at
`/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin`,
then `$HOME/.cargo/bin`; uses Python via uv and existing offline caches;
sets checkout-local `target/task-tmp` as TMPDIR and the rebuilt native core
through `XYG_NATIVE_LIB`. Create that temp directory first.

The required browser is explicitly
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
These are documented repository smoke workflows with software rendering, not
hardware/performance evidence. The multi-hour full Python suite, unrelated geo
diagnostic experiments, blanket formatting of the existing Rust backlog and
new benchmark/speed claims are out of scope. No new chart family or competitive
performance lead is claimed. Independent **whole integrated S3** review and CI
remain required before a parent-owned PR; later interaction and release gaps
are unchanged.
