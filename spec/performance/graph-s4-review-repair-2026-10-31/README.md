# S4 independent-review repair, 2026-10-31

Local repair over `dee3ea37540a7126c3082ae59624bb02881bb00f` only. The parent
owns independent re-review, package policy, remote PR/queue/issues and M4/#36
acceptance before #108 publication. This receipt does not claim shipping,
milestone completion, S5/S6/S7 delivery or a competitor performance win.
Historical S1–S4 receipts, including old FAIL and diagnostic records, are unchanged.

The inherited canonical binary/full-index S4 diff against `bd57eb7` is
`8b7b36df21bcaefb9d3f37eb4f77a4b68c6470fdfba7d3d796ccd5efc07e7480`.
This round has its own source/artifact inventory and final diff hash.

## Repair decisions

- XYGR carries the complete retained `RenderOutput.paint` in eight named
  sections: exact styles/layers, mapped centers, clipped routed pieces, dash
  origins, terminal heads, frame bands and canonical order/flags. Rust decoding
  reconstructs it without semantic/layout/route policy. These are resolved CPU
  records; subsequent generic GPU lowering remains Rust-owned, offset-f32/u8.
  Same-revision style/emphasis operations refresh them. No second Scene or
  host policy, S5 shader/controller, DOM or ARIA implementation is introduced.
- Successful XYGF reader identity remains arbitrary exact UTF-8, including
  absent versus present-empty, Unicode, spaces and more than 128 bytes.
  XYGQ authoring grammar is unchanged. Borrowed validation precedes ID clones;
  present-empty uses the actual pool cursor, absence `0xffffffff/0`.
- Admission replaces unconditional 51,200,000 state bytes with source-reachable
  bounded state and explicit text charges. Actual shared owner state is charged
  under its lock, including foreign IDs absent from this document. Labels are
  charged after dictionary expansion (XYGF TextList stores each row's bytes).
  Repeated identity/result/escaping/cache peaks, old/new document, grid bands,
  staging and candidate copies are covered with checked arithmetic. Normative
  derivation and exact section layouts are in graph-interaction.md.
- Bind/Unbind validate destination stamp and current old-owner frame together
  immediately before installation. Same-owner binds commit under that one lock;
  cross-owner construction releases the target lock before checking/installing
  under the old owner's lock. No nested temporal locks. Native adapters expose
  their underlying lock identity; WASM retains its disposable owner generation.
  Disposed-owner unbind recovery remains explicit. Refusal preserves session,
  publication, owner, retry cache, sequence and outbound delivery.

Arena defaults/maxima remain 16 MiB browser / 384 MiB native/maximum. A real
small session open/render/select/focus succeeds at 16 MiB. The three-node,
three-edge Rust Open boundary is exactly 2,966,016 admitted bytes (one byte less
refuses); this is an accounting boundary, not RSS or an arbitrary source-size
promise. Pressure from long IDs, expanded labels and foreign bound-state text
refuses atomically. Existing selection/request/work caps remain.

Every wire command still speculatively clones/renders/serializes in
O(source + publication). This repair makes no runtime-speed or responsiveness
claim. S7 scale/latency evidence, broad cardinality and complete product-host
controller work remain gaps; this internal boundary repair adds no chart family
or change to competitor/capability/visual matrices.

## Reproduction and evidence

Use `uv run python .../run.py NEW-NAME COMMAND ...`; the runner refuses to
overwrite a command name and retains argv, exit, elapsed validation wall time,
raw/gzip logs and hashes. `before_proof.py` recreates the archived-parent Rust
regressions in diagnostic scratch. It does not modify working source or remotes.
The first archived extraction missed a compile-time spec include; that failure
is retained, and `paint-bind-failing-before-complete` is the actual failing-before
paint and live-owner proof. `failing-before` records UTF-8 Invalid and default
arena Budget on original source. New positive controls reconstruct exact paint,
retain empty identity through update, and test malformed/resource rollback.

Some initial test-driver attempts are retained transparently: smoke scripts take
a positional Chrome path, the IR command needs `--lib`, and the new result-ID test
helper must insert a missing section when changing absent to present-empty.
Corrected runs retain the original assertions. No historical runner/output path
is reused. GraphForge semantic/cross-host golden files stay unchanged; the five stale
native-ABI fixture labels refreshed later are documented below.

Actual Node22 optimized-WASM replay compares complete replies to the rebuilt
native ABI, covering all operations, local/linked UTF-8 identities, reordered
result tables, None/empty update invalidation, focus/changed/candidates/events,
style refresh, heads/loops/parallel routes/frames/aggregate singletons,
20,000-ref differences, 10,000 request cap, stale binds/unbinds, new owners,
frame advancement, disposed-owner recovery and unconsumed failed sequences.
Pressure refusal at the real 16 MiB WASM arena is followed by same-sequence recovery.

## Bounded size work

Correctness baseline: **1,860,323 raw / 759,045 gzip6**, optimized SHA256
`b6b3a6f1228e9cd1dd612b585be72e0709474a1be92783f4470bd3304bb21bd8`.
`baseline.artifact.json` binds source/compiler/optimized/gzip hashes. The actual
unchanged Node22 producer refuses the existing 1,513/626-KiB gates; baseline
excess is 311,011 raw / 118,021 gzip bytes. This is a new repaired baseline,
not the historical S4 artifact or its unapproved proposed ceilings.

Raw-body attribution has no function names because production stripping remains
unchanged. Diagnostic LLVM-IR emission (same release optimization, no profile or
optimizer edits) identifies the non-generic candidate boundary: 205 IR lines,
16,342 IR text bytes, called by two execute closures; GraphSession Clone has
2,680 IR lines / 232,761 IR text bytes. These are **IR text sizes, not attributable
WASM bytes**. Fat-LTO may inline these boundaries. This supports only a measured
outlining experiment; it does not establish a preexisting measured size cause.
The raw body inventory, IR source hash, candidate excerpt and complete relevant
function metrics are retained separately. Standard compiler-module bytes after
IR emission match the baseline raw module.

Only two isolated source candidates are authorized: A adds `#[inline(never)]`
to the existing candidate body; B replaces UUID formatting allocations with a
fixed nibble writer. Each starts from the repaired baseline. Every clone,
callback, owner guard, admission and rollback remains. The exact patches and
source/artifact hashes are retained. There is no combined unmeasured candidate,
compiler/profile/dependency/toolchain/optimizer/gate/export stripping change or
runtime-speed claim. Final disposition follows below.


### Final size disposition and package blocker

Exactly two candidates were built and measured independently with Node 22.23.4
and the unchanged production `optimizeWasm` pass and gzip6 behavior:

| Source | Raw bytes | Gzip6 bytes | Disposition |
|---|---:|---:|---|
| repaired correctness baseline | 1,860,323 | 759,045 | reference |
| A: candidate noinline | 1,860,323 | 759,044 | byte replay passes; removed in favor of B |
| B: UUID nibble writer | 1,860,250 | 759,008 | retained alone; raw -73, gzip -37 versus baseline |

A changes only 13 raw-module byte positions, with no raw-size reduction. The
one-byte gzip improvement does not demonstrate a meaningful outlining gain.
B improves both dimensions relative to A and baseline. No third/combined
candidate was tried. `experiment-{a,b}.patch`, `*.artifact.json` and
`size-disposition.json` retain exact patches/source/compiler/module/gzip hashes.
Both candidates pass native/actual optimized-WASM byte replay. UUID output stays
all 32 lowercase hex characters, including zero bytes.

Final optimized diagnostic module SHA256:
`25ee24fdf32ee8355598cff67da44e01556d0bb2914d5cc2d4ab4a3834c1769d`.
Gzip6 SHA256:
`5357262c8b2999858ffbf9953a7acd6cebc97d49440abbce1781ea860a1352f9`.
Compiler module: 2,051,907 bytes,
`c92331ab934390e8a67a539c9553339b6bcb3de8bd0fd647d2a10cc94ac6e401`.
Fresh native library:
`f31d05896b0ca7072f62d1b013be8d3812f559e1f844852afbe58445e1bf3be9`.

The fresh real producer `npm run build:wasm` **FAILS**, returning exit 1 on the
unchanged 641,024-byte gzip gate. Exact final size is **1,860,250 raw / 759,008
gzip6**, over the unchanged 1,549,312 / 641,024 gates by **310,938 / 117,984**.
Shipping WASM/inline/manifests are withheld in both dist/static locations;
the fresh shipping asset verifier consequently fails for missing assets.
This remains a real package-policy blocker for the parent, with no assumed
new ceiling, diagnostic promotion, publication or milestone acceptance.

`diagnostic_assets.mjs` runs the real packager with all signature/import/version/
worker checks, logs BOTH size refusals, and changes output paths only to
`target/task-tmp/s4-review-repair-diagnostic-assets`. The producer's ordinary
stdout word “packaged” therefore refers only to that explicitly nonshipping
root. Paired diagnostic assets verify. The original full strict-CSP foundation
passes on that root with its report and all six PNGs retained here; they remain
diagnostic, `artifactCommit:null`, and cannot establish shipping acceptance.
ABI/Scene/painter remain 35/34/17 in WASM, with 65 function exports and no imports.

### Parent-requested native ABI parameter-label repair

The parallel Node scheduling candidate exposed an inherited guard failure:
`document` inside the generated Koffi signature string matched the existing
browser-global guard. The original finding/log is copied here, and this checkout
reproduces the failure in `node-global-guard-before`. The Rust C-seam parameter
is now named `document_bytes`; `scripts/gen_abi_manifest.py --write` regenerated
all four declarations/metadata outputs. No generated file was edited manually,
and the guard is unchanged and passes in `node-global-guard-after`.

`abi-parameter-proof.json` compares all 537 symbols: parameter types/order,
returns and calling conventions are unchanged. Native ABI remains 397; this
is a parameter-label/metadata-digest update, not a binary function-type change.
The generated named-signature digest changes from
`68824381caf0f8a96852b75e33764e926af4416a566cebcc1bff1b2a26241a29` to
`11aaa11bd88b7c974284d88fd96295a938f0b17d811ce820132f0b22aeef7ffa`.
The native library is freshly rebuilt and all 67 core tests, generator checks,
Python ABI/session seams and complete native/optimized-WASM reply parity pass.
This native-only label change does not affect the measured WASM candidate.
The Node public API, runtime wrappers, scheduling work, shared Node docs,
checkpoint paragraph, smoke callers and API inventory remain parent-owned.

### Final verification scope

- Full Rust workspace: 1,946 unit/integration tests passed, zero ignored:
  67 core, 1,802 engine, 72 WASM and five integration tests. The final native
  parameter-label change additionally passes all 67 core tests. All-target
  workspace Clippy passes with warnings denied.
- Shared wire regression set: 18 pass, including failing-before controls,
  retained-paint reconstruction, malformed/resource rollback, UTF-8 identities,
  exact admission boundaries and foreign bound-state text pressure.
- Five complete native/actual optimized-WASM byte replay tests pass on the
  final rebuilt native library and final diagnostic module; no skips.
- Python broad seams: 185 pass, four browser-only cases deliberately deselected;
  final ABI/session subset rerun after parameter regeneration.
- Node broad native seam: 105 pass. The full existing package test list is run
  separately against an isolated diagnostic view with bounded file concurrency;
  its complete results are in `full-node-baseline-diagnostic`.
- Client type/shader/bundle, actual browser DT.u32 encoder, generated native/WASM
  ABI checks, exact ABI parity and 673-check ABI smoke pass. GraphForge semantic/cross-host
  payload golden files are unchanged. Render and append smokes pass on Chromium 156.
- Full original strict-CSP foundation and paired-asset checks pass ONLY on
  diagnostic staging. Real package producer and shipping assets remain FAIL.

`evidence.json` and `source.patch` bind nonreceipt source, generated native seams,
compiler/module/native/paint bundles, environment and command logs. Tests ran on
uncommitted source, hence `artifactCommit:null` is preserved. Final commit and
canonical complete binary/full-index diff SHA against dee3 are returned to the
parent after hooks/Ruff checks. Parent independently re-reviews before any PR.


### Full Node baseline follow-through

The complete package test list initially reports 1,001 pass / five fail / two
pre-existing skips. All five failures are the stale top-level `abi_version:396`
labels in density-emit, force-emit, geo, payload and series-palette fixtures;
all their actual payload comparisons pass, and the browser-global guard passes.
The original failing full run is retained. Each fixture is then regenerated
through its existing Python/Node producer. `abi-fixture-metadata-proof.json`
asserts byte-content equality of ALL other JSON data and records unchanged-data
hashes: only the five top-level ABI labels become 397. No semantic, geometry,
color, numerical payload, output hash or assertion is changed. This is the
justified exception to preserving cross-host goldens after S4's native ABI bump.
`refresh_abi_fixtures.py` refuses any broader regeneration change.

The full package list is rerun after that repair. Its existing skips are the
packet-storage identity-failure case and heatmap Scene fill-opacity (#889);
neither is newly skipped, waived, or included in the S4 proof. The standalone
S4 native/actual-WASM replay has five passes and zero skips. The full diagnostic
view links unchanged inputs while retaining explicit nonshipping WASM outputs;
production dist/static assets are never supplied by this diagnostic view.


Final full Node result (`full-node-baseline-correct`): **1,006 passed, zero failed,
two existing skips** across all 1,008 package test cases, including the unchanged
browser-global guard, scheduler lifecycle and temporal/geo regressions. The
corresponding Python fixture suite has **199 passes**. No fixture data changes
beyond those five ABI-version labels are admitted.
