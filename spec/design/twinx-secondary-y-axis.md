# Native secondary y axis (`y2`, twinx) in the Rust Scene/static path

Authoritative design (r2 plus the final addendum, which overrides conflicting
text). Part of #1006 (twinx PRs 1–3). The *PR 1 implementation record* and the
*PRs 2+3 implementation record* at the end state where the shipped work refines
this text.

Closes Matplotlib corpus case 26 (`tests/pyplot/corpus/26_twinx_dual_axis.py`)
for #1006. Supersedes r1 (`.m4/design-twinx.md`); r1 §0 facts still hold unless
restated here. Builds on #1019 (`origin/fix/a-chrome-style-1004`, ABI 384);
citations marked (1019) are to that branch, all others to `t3/complete-milestone-4`.
Verified 2026-10-20.

## 1. Blocker resolution

| # | Sol finding (verified) | r2 resolution |
|---|---|---|
| 1 | Literal Scene version `32` in readers: `js/src/63_geo_source.ts:98`, `66_geo_mixed.ts:39`, `67_geo_overview.ts:54`, `74_geo_overview_snapshot.ts:109`; Node `geoscale.js:99`, `geo-mixed-wire.js:40`, `geo-overview.js:55`; Python `_geoscale.py:530`, `_geo_overview.py:132`, `_geo_mixed.py:111`. Generated/runtime constants already exist: `js/src/wasm_abi_generated.ts:5` (`XYG_WASM_SCENE_VERSION`), Node `scene.js:674` (`sceneVersion()` via `xyg_scene_version`), Python `_native.py:5121` (`scene_version()`). Fixtures embedding v32 bytes: `tests/fixtures/graphforge/scene32_refresh.json`, `graph_static_export_scene32_refresh.json`, `geo_cross_host.json`. | §5: every reader compares against the constant; fixtures regenerated; a source guard forbids `getUint32(4,true)!==<digits>` / `!= 32` version literals. All in PR 1. |
| 2 | WASM path drops y2: `crates/xyg-wasm/src/lib.rs:1099,1194,1307` call `to_browser_painter`; `scene.rs:15116-15160` resolves only x/y ticks; `js/src/48_wasm_scene.ts:346-348` rebuilds only x/y from XYPB (header 300 B, x block at 88, y at 176, text lengths at 264, reserved 276..280) and `:179` hard-codes `y_axis:"y"` per trace. | §4: XYPB v16 adds a y2 axis block, y2 tick run, y2 title, and a per-trace y-axis selector; TS emits `axes.y2` + `y_axis:"y2"`. Test through `renderWasmScene` in `tests/browser/wasm_foundation_page.mjs`. PR 1. |
| 3 | `python/xyg/_native.py:3302-3426` is a handwritten `xyg_scene_xycf_pack` wrapper; `_scene_unpack.py:161` and `scene.js:5990` reject XYAS ≠ v1; r1's PR A would break main. | §6: PR 1 is one atomic format PR (Rust + generated ABI + the two handwritten wrappers + every version reader + fixtures + bundles), with hosts still fail-closed on y2; PRs 2/3 add host policy only. XYAS stays v1 (§2.2), so the two unpackers do not change. |
| 4 | Metrics arrive after layout: (1019) `static_document.rs:573-585` decodes the laid-out Scene then `apply_static_chrome_metrics`; (1019) `scene.rs:11244-11266` only stores them; `widen_gutters` measures with literal `12.0` (`scene_encode_assembled.rs:612,633`). XYST panel record is full (1019 `PANEL_BYTES = 128`, `chrome_text_rgba` ends at 128, `static_document.rs:480-528`). | §3: y2 chrome metrics/paints/text flags are resolved by XYCO **before** Scene encode ((1019) `_static_document.py` `project_figure`: `resolve_chrome_style` precedes `_scene_v3._public_scene_or_reason`) and travel in the XYY2 sidecar → Rust lays out with them. No XYST record change for y2; compat floor preserved. |

## 2. Scene format v33

### 2.1 `XYGS` trailer

`SCENE_VERSION = 33` (`scene.rs:22`). Trailer byte 15 **bit 1 = `has_y2`**;
when set, a length-prefixed `XYY2` block follows the bit-0 extras block
(`scene.rs:3033,3096`) and precedes the text tables, so every existing offset
becomes `trailer + extras_len + y2_len`. `XYY2` carries, in this order:

- scale: `kind u32, lo f64, hi f64, constant f64, mask_nonpositive u8, pad[3]`;
- chrome: one `SceneAxisChromeStyle` record packed by the same writer/reader as
  the y record (`scene.rs:1380` region), side = right;
- **resolved metrics** (new, canonical for y2 only): `tick_label_size f64,
  label_size f64, tick_padding f64, text_flags u32` (two-bit italic/bold for
  tick labels and title, same encoding as XYCO), `tick_rgba [u8;4]`,
  `title_rgba [u8;4]`, `present u8` (bit 0 metrics, 1 tick paint, 2 title paint),
  `pad[3]`;
- ticks: `major_count u32 (u32::MAX = auto)`, `minor_count u32`, f64 values,
  `labels_len u32` + NUL-joined labels;
- text: `title_len u32` + UTF-8, `format_len u32` + grammar;
- policy: `tick_strategy u8, tick_anchor u8, anchor_authored u8, category u8,
  min_gap f64, angle f64 (NaN = none)`.

Bounds mirror y (`MAX_AXIS_TICKS`, `MAX_SCENE_TEXT_BYTES`,
`MAX_SCENE_CHROME_LENGTH`). The metrics live on the Scene because the XYST
panel record is full and because y2 has no legacy "static-only compat" to
preserve; x/y keep the #1019 overlay path unchanged.

### 2.2 Records

`SCENE_BATCH_RECORD_BYTES` stays 56. Each record gains a **`Y2_SCALE` bit** in
the existing flag/tag byte (implementer confirms the free bit against the
decoder's reserved-zero check; the `EncodedRecord` fields `scene.rs:9531-9540`
show `annotation_tag`/`symbol` as candidates). Set while `has_y2` is clear →
`SceneError::Length`. Decode, pick/hover inversion and the geographic rebuild
select the scale from this bit; encode→decode→encode is byte-identical.

The same bit rides the host-authored 56-byte XYAS rows (same record layout),
so **XYAS stays v1** and `_scene_unpack.py:161` / `scene.js:5990` are
untouched. Rust rejects the bit when XYCF has no `XYY2` sidecar
(`EncodeAssembledCode::Payload`). Fallback only if no bit is free: XYAS v2
with a trailing selector column, updating both unpackers in PR 1.

### 2.3 Ingress

- **XYCF v1**: header gains `has_y2` in a reserved u32 (`scene_xycf_pack.rs`
  header struct, offset confirmed by the implementer) plus an `XYY2` sidecar at
  the end of the concat order with exactly §2.1's facts (chrome record, resolved
  metrics/paints/flags, ticks, title, format, policy). `xyg_scene_xycf_pack`
  gains `y2_ptr, y2_len`; null/0 = no y2.
- **XYFS**: axis id **2 = y2** admitted when `side == right` and its key set ⊆
  y's (`scene_export.rs:1581-1597`); `n_axes ∈ {2,3}`; traces with `y_axis ==
  "y2"` no longer raise `XYFS_TRACE_NON_PRIMARY_AXIS` (`:1494,1711`).
- **XYCS/XYCO** (1019 `static_chrome_style.rs:369-466`): XYCS flag **bit 2 =
  has y2**, then a third `(style, minor_style)` pair after y. XYCO appends y2
  tick paint, y2 title paint, three y2 sizes, and two more consumed-key lists.
  `chrome_text` bits: title/x/y flags 0..9, paints 10..13 unchanged (1019 mask
  `0x3fff`); **y2 title flags 14..15, y2 tick flags 16..17, y2 tick paint 18,
  y2 title paint 19** (Sol's note that 14..17 are not paint bits is correct;
  r1's numbering was wrong). Hosts copy these into XYY2, not into XYST.

### 2.4 ABI

`xyg_scene_xycf_pack` (new args), `xyg_static_chrome_style` (longer XYCO),
`xyg_scene_figure_support_materialize` (axis-code docs) change: `ABI_VERSION`
385, `python3 scripts/gen_abi_manifest.py --write`, `BROWSER_PAINTER_VERSION`
16 / `BROWSER_PAINTER_HEADER_BYTES` regenerated into
`js/src/wasm_abi_generated.ts`. No hand edits to generated files.

## 3. Rust layout and painting (blocker 4)

Order on the static path, both hosts:

1. Host resolves chrome style through XYCO (already before Scene encode on
   #1019: `resolve_chrome_style` at `_static_document.py` `project_figure`
   precedes `_scene_v3._public_scene_or_reason`; Node mirrors in
   `figureChromeStyle`, `scene.js:2567`).
2. Host copies y2's XYCO outputs into the `XYY2` sidecar; x/y outputs keep
   riding the XYST panel record as today.
3. `encode_assembled` builds `y2_scale` with the shared vertical span and
   `widen_gutters` (`scene_encode_assembled.rs:595-636`) gains a y2 branch:
   `margin_right = max(margin_right, 8 + tick_out + tick_padding + widest
   visible y2 label advance at tick_label_size + (title ? gap + label_size ×
   1.25 : 0))`. Measurement uses `scene_text_advance` at the resolved size
   (fallback 12.0 as for y). Auto ticks are produced for measurement by the
   same `resolved_axis_ticks(scale, length, false, ...)` (`scene.rs:1640`)
   with `length = height - margins`, so measurement and paint see one ladder.
   `chrome.margin_right` arriving from `static_panel_chrome` already includes
   `compat_layout::right_y_room()` for `RIGHT_SECONDARY`
   (`static_panel_chrome.rs:238`, `compat_layout.rs:151`, 54/42 px); the
   `max` keeps it as the floor. No relayout after decode is needed.
4. Expansion picks the scale per record from `Y2_SCALE`.
5. Drawing: extract the y-axis emission in `SceneDocument::to_svg`
   (`scene.rs:13454` on 1019) and the raster display list into
   `emit_y_axis(scale, chrome, metrics, ticks, title, side)`; call for y (left)
   and y2 (right): spine at `layout.right`, ticks outward, labels anchored
   `start` at `right + tick_out + padding`, title rotated −90° (reads bottom to top, as the left title) in the right
   gutter, **no y2 grid** (Matplotlib default; recorded in §28). PDF follows
   SVG. y2 text uses the styled text command #1019 introduces, with XYY2's
   sizes/paints/flags.

Tick ownership (accurate): hosts never tick. Python `Figure._range()` already
calls Rust autorange (`python/xyg/_figure_autorange.py:65-67`); explicit
majors/labels pass through; auto majors are Rust f64 ticks via
`resolved_axis_ticks`, parameterized by axis, not copied. Live ticks are
Rust/WASM-owned and TypeScript fails closed without them
(`js/src/50_chartview.ts:1434-1466`); the §4 projection feeds that same slot
for y2.

## 4. XYPB v16 and the browser reader (blocker 2)

`to_browser_painter` (`scene.rs:15116`): after the y axis block (176..264)
insert an 88-byte **y2 axis block** of identical layout; shift the text-length
words, legend/colorbar/scene-label lengths and all later offsets by 88; use the
reserved word (old 276..280) as `y2_title_len`; add `y2_tick_count` beside the
x/y tick counts; the y2 tick run follows y's with pixel = `y2_scale.pixel`
(`browser_ticks(false, self.y2_scale, resolved y2 ticks)`); the y2 title is
`text[3]`. When `has_y2` is clear the block is zero, counts 0, title empty,
`axes.y2` omitted. Each 64-byte trace descriptor gains a `y_axis` byte
(0 = y, 1 = y2) in a byte the TS reader currently requires to be zero.

`js/src/48_wasm_scene.ts`: header check uses the regenerated constants
(`:33`); `axis("y2", [bottom, top], xTickCount + yTickCount, y2TickCount,
false, chrome + 200)` with `tick_sides` right, `label: text[3]`; traces get
`y_axis: "y2"` from the descriptor byte (`:179`); spec emits `y2_axis` and
`axes.y2` in the shape the live client already consumes
(`57_viewstate.ts:310,550`). `hydrateWasmPainter`'s borrowed-surface guard is
unchanged (y2 chrome on a geo surface is rejected by `padding !== 0` already).

## 5. Version readers and fixtures (blocker 1)

PR 1 replaces every version literal with the owning constant:
TS readers import `XYG_WASM_SCENE_VERSION`; Node readers call
`sceneVersion()`; Python readers use `_native.scene_version()`. Regenerate
`tests/fixtures/graphforge/scene32_refresh.json`,
`graph_static_export_scene32_refresh.json`, `geo_cross_host.json` and any
fixture the Rust `fixture refresh` tests write (`scene.rs:16771` pattern), via
their existing refresh scripts. Add a source guard test
(`tests/test_scene_version_literals.py`) grepping `js/src`, `packages/xy-node/src`,
`python/xyg` (excluding generated files) for `XYGS` checks against a numeric
literal. Spec: `spec/design/scene-ir.md` version table and the geo transport
pages that quote "Scene32" (`geo-mixed-transport.md`, `geo-frozen-export.md`,
`geo-spatial-index.md`, `geo-linked-state.md`) become "current Scene version".

## 6. PR sequence — every PR leaves `main` green (blocker 3)

Rebase onto `main` after #1019 lands; do not stack.

1. **PR 1 — atomic format PR.** Rust: v33 + `XYY2`, `Y2_SCALE`, XYCF `XYY2`
   sidecar, XYFS id 2, XYCS/XYCO y2, `widen_gutters`, `emit_y_axis`, XYPB v16,
   ABI 385 in the original draft (shipped as 387; see the implementation record) + generated manifests. Hosts, mechanical only: `_native.py:3302`
   wrapper passes `None, 0` for y2 (and reads the longer XYCO in
   `_static_document.py:626-662` / `scene.js figureChromeStyle`); all §5 version
   readers; fixtures; `48_wasm_scene.ts` reader; `node js/build.mjs`. Hosts
   still send no `XYY2`, so y2 figures keep failing closed with the existing
   reason. Specs: `scene-ir.md`, `static-chrome-style.md`, `host-parity.md`.
   Justification: the version bumps already force every reader, both wrappers
   and all fixtures to move together; splitting them is what broke r1. Size is
   bounded because no host policy is included.
2. **PR 2 — Python host.** `_scene_marshal.py` packs `XYY2` from
   `figure.axis_options["y2"]`, `_range("y2")`, tickers, title, format, and the
   XYCO y2 outputs; `_layout.py:1195` admits `{"y2"}`/right; XYAS rows set the
   bit from `trace.y_axis`; pyplot `twinx()` seeds `_axis["y2"]["style"]`
   through the function that seeds y (rc `ytick.*`, `axes.labelcolor`,
   `axes.edgecolor`); corpus 26 enabled; `compat.md`, `chart-grammar.md`.
3. **PR 3 — Node host + cross-host.** `scene.js` `packFigureSupport` (`:3991`,
   axis code 2), flag test (`:7085`), `packChromeAxis` (`:2458`) for y2,
   `XYY2` packer, XYAS bit, third XYCS pair; cross-host byte-identity test;
   `host-delegation-corpus.json`.

PRs 2 and 3 run in parallel worktrees after PR 1; PR 3's cross-host test is the
gate for the issue's "dual axes" line.

## 7. Tests (each fails on revert)

- **Rust**: y2 row expands with `y2_scale`; `Y2_SCALE` without `has_y2` →
  `Length`; bit in XYAS without `XYY2` → `Payload`; v32 bytes → `Version`;
  v33 round trip byte-identical; `widen_gutters` grows `margin_right` for
  (a) styled auto ticks at `tick_label_size = 20`, (b) explicit long labels
  (`"1,000,000 units"`), (c) padding 12, and never below the compat floor;
  SVG: right labels have `x > layout.right` and no label exceeds `width`;
  `to_browser_painter` on a twin scene has a non-zero y2 block, `y2_tick_count
  > 0`, descriptor byte 1 for y2 traces; XYCS bit 2 without entries →
  `_HEADER`; `chrome_text` y2 bits 14..19 round-trip.
- **Tick parity**: equal-domain y and y2 (same lo/hi, auto) produce identical
  tick values in SVG, raster display list, and XYPB y/y2 runs; and the
  WASM live result for `y2` equals the static ladder (same `resolved_axis_ticks`
  call).
- **Browser**: `tests/browser/wasm_foundation_page.mjs` renders a v33 twin
  scene through `renderWasmScene`; asserts `spec.axes.y2.range`, right-side
  tick labels in the chrome layer, one trace with `y_axis === "y2"`, and no
  console error; a v32 blob → `XYG_WASM_SCENE_VERSION` status (`lib.rs:1022`).
- **Geo readers**: existing geo conformance tests pass with regenerated
  fixtures; source-guard test for literals (§5).
- **Python**: `tests/test_static_dual_axis.py` — public `y_axis(id="y2",
  side="right")` + `line(..., y_axis="y2")` → SVG/PNG/PDF; left-side y2 and
  `x2` rejected with stable reasons; tampered native output changes bytes.
  Corpus 26 gains focused assertions beyond
  `tests/pyplot/test_reference_corpus.py:120-136` (ink fraction / bbox): left
  axis title pixel colour ≈ `tab:blue`, right title ≈ `tab:red`, y2 tick
  labels use default rc tick colour (not red), one shared x ladder, right
  labels fully inside the canvas.
- **Cross-host**: `tests/test_static_dual_axis_cross_host.py` +
  `packages/xy-node/scripts/static_dual_axis_cross_host.mjs`: byte-identical
  SVG/PNG/PDF, identical `XYY2`/XYCS bytes, identical reasons, no y2 table in
  either host.

## 8. Scope boundary

In: one right-side `y2`, linear/log/symlog, auto/explicit ticks, title,
format, chrome style and slots, static and WASM-live paint.
Out (fail-closed, stable reasons): `x2`/`twiny`, left-side `y2`, >1 extra y,
`secondary_yaxis()` conversions, y2 grid, y2 + colorbar on one panel
(`XYG_SCENE_UNSUPPORTED_Y2_COLORBAR`). Overlay-panel alternative remains
rejected for the r1 §5 reasons (hosts would need Rust's final margins).

---

## Final addendum — orchestrator resolution of Sol round-2 findings (2026-10-20)

Sol round 2 marked round-1 blockers 1, 3, 4 RESOLVED and left two blockers with precise resolutions. The orchestrator closes them here; these override conflicting text above.

**F1 — XYPB y2 chrome is complete, not an identical axis block.** XYPB v16 carries, after the 88-byte y2 axis block, a fixed y2 chrome-text record holding the resolved XYCO outputs for y2: tick-label size (f32), title size (f32), tick padding (f32), tick-label paint (RGBA u8×4), title paint (RGBA u8×4), text flags (u32: bold/italic per slot), with explicit presence bits; reserved bytes must be zero. `js/src/48_wasm_scene.ts` reads these into `axes.y2` and applies them, rather than reusing the shared `labelSize`/single paint. Tests through `renderWasmScene`: (a) red y2 title with default-colored y2 ticks renders distinct colors; (b) y2 tick size 20 / padding 12 changes measured label geometry; (c) primary-axis rendering unchanged (existing fixtures).

**F2 — Right-only admission is Rust-owned via an observed side.** `FigureSupportAxisObs` (crates/xyg-engine/src/scene_figure_support_materialize.rs:~100) gains the authored axis side; the XYFS axis header carries it in one of the three currently zero bytes (scene_figure_support_pack.rs:~47), with defined codes and the remaining bytes still zero. Rust admits axis id 2 only when side == right, and returns stable reasons for x2, left y2, multiple extras and tick-only secondary axes. Python `_layout.py:~1193` and Node `scene.js:~7085` do NOT add admission conditions: they translate axis id/side into the observation and surface Rust's reason. Allowed host work is limited to axis-code translation, XYCO copying, selector marshalling and pyplot rc seeding. Test: identical left-y2 and right-y2 inputs from Python and Node yield the same Rust decision and the same reason bytes.

**F3 — Selector bit reservation.** Bit `0x40` of byte 3 is reserved as the y2 selector in both XYAS rows (scene_pack.rs:~161) and XYGS records (scene.rs:~4080). It is preserved through Rust packing and expansion and masked off before every annotation-tag comparison (tags 0..6 and 0x80). Tests: an annotation-tagged record on y2 keeps both its tag and selector; a non-y2 record is unchanged.

**F4 — PR 1 hygiene (non-blocking from Sol, adopted).** PR 1 also updates literal-version test assertions (e.g. tests/test_scene_ir.py:~237, ~1010), not only the JSON fixtures. It regenerates WASM constants with `scripts/gen_wasm_abi.py` in addition to `scripts/gen_abi_manifest.py --write`.

**Sequencing:** implementation starts after PR #1019 (#1004) merges, because y2 reuses its XYCS/XYCO projection. PR 1 (atomic format) → PR 2 (Python marshal + pyplot) → PR 3 (Node marshal + cross-host byte identity). Each PR leaves main green.

---

## PR 1 implementation record (format PR)

PR 1 ships the atomic format and Rust policy with hosts still fail-closed for
y2: Scene v33, XYPB v16 (`WASM_ABI_VERSION` 34), `ABI_VERSION` 388, the browser
reader, every Scene-version reader, regenerated fixtures, and Rust-owned
admission. The normative wire layouts are in `scene-ir.md` (Secondary
right-hand y axis). Where the implementation refines this document:

- **Trailer flag.** `has_y2` is trailer byte 15 bit **5** (`0x20`). Bits 1–4 of
  that byte already carry the x/y collision category/anchor flags (§2.1 named
  bit 1).
- **Record selector.** Byte 3 bit `0x40` of XYGS records and XYAS rows (§2.2/F3);
  XYAS stays v1. Decoded records keep the masked annotation tag and a separate
  `y2` flag, so no annotation-tag comparison can see the selector.
- **`XYCF` ingress.** The reserved header word at 284..288 carries the *byte
  length* of the trailing `XYY2` sidecar (non-zero = present) so the sidecar is
  self-locating after the variable collision extras. `xyg_scene_xycf_pack` gains
  `y2_ptr, y2_len`; the bulk `xyg_scene_chrome_pack` that the hosts actually call
  gains the same pair so PRs 2 and 3 are host-only.
- **`format`.** The numeric-format grammar is part of the sidecar and the Scene
  block, but it is materialized into explicit ticks and labels at encode exactly
  as for y, so consumers never interpret it. Time-format y2 axes are not
  admitted (tick kind numeric only).
- **XYFS (F2).** Axis ids 2 = y2, 3 = x2; the second axis-header byte carries
  the authored side using the existing `XYEP` side codes; trace flag bit 13
  marks y2 traces, so "tick-only secondary" (a y2 axis with no trace) is
  detectable. `FigureSupportAxisObs` carries `side`; both bulk wrappers pass it.
  XYFS observation bit 10 and the materialize argument `has_colorbar` report a
  colorbar of any kind, so y2 + a supported colorbar is rejected by Rust
  (`_Y2_COLORBAR`) rather than looking like no colorbar.
- **XYPB v16 (F1).** Header 420 bytes; layout in `scene-ir.md`. The y2 chrome-text
  record stores sizes as f32 (the browser works in f32); the Scene keeps f64.
- **XYCS/XYCO.** The extended XYCO is emitted only when XYCS flag bit 2 is set,
  so host XYCO readers need no change until the hosts send a y2 pair (PRs 2/3).
- **Title direction.** PR 1 drew the y2 title clockwise; the host PR flips it to
  read bottom to top like the left title and Matplotlib's `twinx` label (rotation
  90° counter-clockwise). See the PRs 2+3 record.
- **Readers.** Every literal-32 Scene reader now uses its owning constant (TS
  `XYG_WASM_SCENE_VERSION`; the Node geo wire files, which the conformance pages also
  serve to browsers and so cannot import native bindings, carry the same value as a
  generated constant that `--check` regeneration keeps current; Python
  `scene_version()`), enforced by `tests/test_scene_version_literals.py`.

## PRs 2+3 implementation record (Python and Node hosts)

PRs 2 and 3 shipped as one host PR at `ABI_VERSION` 391. Hosts marshal facts and
surface Rust's reasons; no host adds admission or layout policy.

- **Per-trace selector needs a wire carrier (ABI 391).** PR 1 stamped the record
  selector (`0x40`) in XYGS records and XYAS rows, but the product pipeline
  (XYTC → XYTT → XYCL rows) had no way to say which trace is on y2, so every row
  was packed `y2 = false`. `XYCL` prefix byte 3 gains bit 1, `XYCL_Y2`
  (`scene_trace_rows.rs`): Rust stamps `PackedSceneRow.y2` on every row of a
  flagged trace; undefined bits stay rejected. Python (`_scene_sidecars.py`) and
  Node (`scene.js` `packXyCl`) set the bit from `trace.y_axis == "y2"`. This is
  the only Rust change; admission still reads the `XYFS` trace flag.
- **XYY2 is built by Rust (review round 1).** Hosts do not write the sidecar. They
  pass the authored y2 observation to `xyg_scene_chrome_pack` the way they pass
  the primary y: an `XygChromeY2In` struct (presence flags plus authored values:
  scale kind, domain, optional constant, nonpositive mask, the same chrome-axis
  and collision observations as y, title, format) and the `y2_major`,
  `y2_minor`, `y2_tick_labels` arrays, replacing the earlier `y2`/`y2_len` bytes
  (still ABI 391). `scene_chrome_pack.rs::pack_y2_sidecar` resolves the axis
  chrome record from the y2 style exactly as the y style resolves
  (`scene_style::resolve_chrome_style`, y record bytes 112..200) and writes the
  payload through `scene_y2::SceneY2Wire`, the one layout writer shared with
  `SceneY2Axis::encode`. The strategy/collision precedence and anchor code
  (`tick_strategy_code`, `tick_anchor_nibble`), the 4 px minimum label gap
  (`DEFAULT_Y_MIN_GAP`) and the scale constant default 1
  (`DEFAULT_SCALE_CONSTANT`) are Rust's; the y axis shares the same functions
  and constant. No host holds a default for a y2-specific `XYY2` field (scale
  constant, tick strategy/anchor, minimum gap, ticks, labels): an absent fact
  stays absent and an authored value (a zero constant, an infinite angle or
  domain) passes through untouched to Rust's scene validation. The shared chrome
  axis marshalling is unchanged and still resolves the side code and the
  tick/label side masks from the authored side and `tick_sides` /
  `tick_label_sides` before packing, for y and y2 alike. Python:
  `_scene_marshal._marshal_y2`; Node: `scene.js marshalY2`. A non-finite
  `tick_label_angle` is rejected; only NaN on the wire means "no angle".
- **XYCS/XYCO.** `resolve_chrome_style` / `resolveStaticChromeStyle` set XYCS flag
  bit 2 when `axis_options` carries `y2`, send the third `(style, minor_style)`
  pair, parse the y2 tail of XYCO, drop the consumed y2 style keys, and carry
  `Y2Chrome` (sizes, padding, flags, paints) to the sidecar. The XYST
  `chrome_text` word is masked to `0x3fff` so y2 bits (14..19) never reach a panel
  record. pyplot's own panel path (`pyplot/_grid.py`) threads the same `Y2Chrome`.
- **Axis codes.** `XYFS`/`XYEF` axis ids: `x` 0, `y` 1, `y2` 2, `x2` 3, else 255;
  the authored side was already marshalled. Rust returns `_Y2_SIDE`, `_X2`,
  `_EXTRA_AXES`, `_Y2_TICK_ONLY`, `_Y2_POLAR` and `_Y2_COLORBAR` to both hosts.
- **pyplot.** `Axes._seed_rc_axis_styles` seeds a twin's host `_axis["y2"]` with
  `_rc_axis_style("y")` / `_rc_minor_axis_style("y")`, the same functions that
  seed the left axis, on construction and on `clear()`. The seeded rc keys are
  exactly: `axes.linewidth`, `grid.linewidth`, `grid.alpha`, `grid.linestyle`,
  `ytick.major.size`, `ytick.major.pad`, `ytick.major.width`, `ytick.color`,
  `ytick.labelcolor`, `ytick.labelsize`, `axes.labelcolor`, `axes.labelsize`,
  `axes.labelweight`, `font.size`, and for the minor ticks `ytick.minor.size`,
  `ytick.minor.width`, `ytick.minor.pad`. `ytick.direction` (and every other
  `ytick.*` key) is not seeded: pyplot does not support it for the left axis
  either, so the twin does not either.
- **Node surface.** `Figure.setAxis` accepts `"y2"`; traces bind with `yAxis: "y2"`.
- **Tests.** `tests/test_static_dual_axis.py`, `tests/pyplot/test_twinx.py`,
  `tests/test_static_dual_axis_cross_host.py` with
  `packages/xy-node/scripts/static_dual_axis_cross_host.mjs`,
  `packages/xy-node/test/static-dual-axis.test.mjs`, and the Rust test
  `scene_trace_rows::y2_flag_selects_the_secondary_scale_for_that_trace_only`.
  Corpus case 26 passes (53/55 overall; the two open cases, 25 and 47, are the named
  gaps in `spec/matplotlib/compat.md`).
- **Title direction.** The y2 title now reads bottom to top: SVG/PDF
  `rotate(-90 …)` (`push_svg_chrome_text` path in `scene.rs`) and the styled
  raster text command angle −90°, like the left title. The title baseline
  swaps the roles of ascent and depth accordingly
  (`y2_title_baseline`: ink spans `[x − ascent, x + depth]`). Pinned by
  `y2_title_reads_bottom_to_top_like_the_y_title_in_svg_and_raster` (Rust) and
  `test_y2_title_reads_bottom_to_top_in_svg_pdf_and_raster` (Python). The
  browser client's default title rotation is a TypeScript default
  (`js/src/50_chartview.ts`, `_axisLabelCss` and `renderYTitle`; XYPB has no
  title-angle fact): both y and y2 titles now default to −90°, which changes the
  interactive y2 title from reading top to bottom to reading bottom to top.
  Pinned by the rendered-transform assertion in
  `tests/browser/wasm_foundation_page.mjs` (CI job `wasm_foundation`). An authored
  `label_angle` still wins.
- **Empty `tick_values` means automatic.** `xyg_scene_chrome_pack` has always
  treated a zero-length major list as "not authored" for the primary y and x axes
  (`scene_bulk_pack_ffi.rs`: `major_len == 0 → None`); y2 now follows the same
  rule, so an authored `tick_values=[]` gives automatic ticks, not "no ticks"
  (an earlier host-packed y2 sidecar encoded it as zero ticks). Labels follow
  suit (an empty `tick_labels` is automatic). To hide ticks, author
  `tick_length=0` / `tick_label_sides`. Pinned at the pack boundary by
  `test_empty_y2_tick_values_mean_automatic_ticks_like_the_primary_axis` and
  across hosts by the `empty_y2_ticks` / `empty_y_ticks` cross-host cases and the
  Node `an authored empty tick list is automatic ticks` test.
- **Annotations on y2 (known gap, review round 3).** Scene projects annotations
  through the primary y scale only. pyplot twin annotations (entries live on the
  host with `y_axis == "y2"`) and public `y_axis="y2"` annotations were silently
  projected through it (SVG `y="-18052.8"` for a twin `text(0.5, 200)` on a 0..4
  primary axis). The binding is now preserved end to end: pyplot tags twin
  annotations, `xyg.text`/`label`/`marker`/`arrow`/`callout`/`hline`/`y_band` take
  `y_axis`, the figure annotation dict carries `y_axis`, and both hosts marshal
  `y2` plus the authored `coordinate_space` into the `XYFS` annotation observation
  (`XygFigureSupportAnnotationObs`, ABI 391). Rust
  (`scene_figure_support_materialize.rs`, observation bit 11; reason in
  `scene_export.rs`) refuses a y2-bound annotation that reads y data with
  `XYG_SCENE_UNSUPPORTED_Y2_ANNOTATION`; axes-fraction and `xaxis_transform` rows
  never read the y scale and are admitted. Projecting annotations onto y2 is not
  implemented **in the static Scene path** (known gap, `compat.md`); the live
  client path is the mirror decision recorded below (round 4).
- **Live payload parity and live annotation projection (review round 4).** Both
  hosts now marshal the live wire identically for a chart that admits y2
  (decision recorded per dossier §28 — emit faithfully, fail closed only where
  the binding is unresolvable):
  - Node `buildPayload` computes one range per declared axis (like Python
    `_payload_spec`'s `axis_range` cache), passes each trace its own bound
    ranges, emits an axis spec for every axis in `axis_options`, and derives
    `view.ranges` from those specs. Previously it collapsed every trace onto the
    primary x/y ranges and omitted `axes.y2`/`ranges.y2`, so `toHtml()` drew y2
    data on the primary scale with no right axis while Python emitted x/y/y2.
    A range-sensitive proof rides the tier-2 density grid, which is binned
    against the trace's own y2 domain (a direct line column is data-relative
    offset-f32 and cannot distinguish the two).
  - Node `setAxis("y2")` preserves an omitted `side` (the stored option stays
    absent, as Python `set_axis` does; the primary x/y defaults are unchanged), so
    the omission reaches Rust unobserved on the static path and Rust resolves it
    to the right edge. It also syncs the authored x/y `label` into
    `x_label`/`y_label`, exactly like Python `set_axis`, so the same authored
    chart produces the same live spec in both hosts. The live path resolves an
    absent non-primary y side to the right edge with host mirror constants
    (`_Y2_LIVE_SIDE` / `Y2_LIVE_SIDE`); those predate this PR as host defaults and
    are tracked for replacement by a Rust-owned resolution in #1044.
  - A y2-bound annotation keeps `y_axis: "y2"` on the live wire (Python
    `_annotation_common`, Node `annotationCommon`); the key is emitted only when
    bound, so unbound payloads stay byte-identical. Both hosts refuse the
    binding when the chart never declared a y2 axis
    (`annotation y_axis 'y2' has no matching xyg.y_axis(id='y2')`), mirroring
    the mark `y_axis` admission rule — the client's `_axis` fallback must never
    silently re-project a bound annotation through the primary scale. Y
    coordinates (including category lookups) resolve against the bound ladder.
  - The client (`js/src/51_annotations.ts`) projects a bound annotation through
    its y2 axis in exactly the coordinate spaces that read the y data scale
    (default/`data` and `yaxis_transform`), matching Rust's
    `coordinate_space_uses_y_scale` admission rule; axes/figure/xaxis fraction
    spaces ignore the binding, as in static admission.
  - The wire grows `annotations[].y_axis` and Node's `axes.y2`/`ranges.y2`, so
    the renderer protocol moves 13 → 14 (`spec/design/wire-protocol.md` §7): a
    cached v13 client ignores the binding and silently misplaces the
    annotation, which is exactly what a bump exists to prevent.
  - Pinned by `tests/test_live_dual_axis_cross_host.py` (axes/ranges/annotations
    and packed-blob identity across hosts, density grid byte identity,
    identical fail-closed messages), `packages/xy-node/test/live-dual-axis.test.mjs`
    (Node-local), and `tests/test_dual_axis_live_client.py` (headless Chromium:
    the y2 ladder renders on the right and the bound annotation lands at the y2
    projection, far from the primary one). Each fails when its change is
    reverted.

  implemented (known gap, `compat.md`).
- **Omitted y2 side means right (review round 4).** The secondary y axis is
  right-hand by default and Rust owns that default: hosts pass an absent side
  through (`XYFS` side code 0, `AXIS_SIDE_UNOBSERVED`; the chrome observation's
  `side_authored` / `tick_sides_authored` / `label_sides_authored` flags in
  `XygChromeY2In`), `scene_export.rs` admits an unobserved y2 side as right, and
  `scene_chrome_pack.rs::pack_y2_sidecar` resolves an unauthored side to high and
  unauthored side masks to that side. The host chrome marshal no longer invents
  `"left"` for an unauthored y2 side (placeholder codes are ignored without the
  flags); x and y defaults are unchanged. Before this, a raw/Node y2 axis without a
  `side` was refused as `_Y2_SIDE` while the Python public axis config defaulted
  non-`y` axis ids to the right. Pinned by the cross-host cases `y2_side_omitted`
  and `y2_side_public_default` (byte-identical to the explicit `side="right"`
  output), Rust `an_unauthored_y2_side_is_the_right_side_and_masks_follow_it` and
  the unobserved-side case of
  `only_a_right_side_secondary_y_with_a_trace_is_admitted_with_stable_reasons`.
- **Invalid-input tests.** `tests/test_static_dual_axis_cross_host.py` sends a zero
  and a negative constant, an infinite domain and ±infinite
  `tick_label_angle`; Python and Node get the same rejection message,
  `invalid canonical scene batch`. That is the generic host malformed-scene
  message for any Scene the encoder refuses, not a stable
  `XYG_SCENE_UNSUPPORTED_*` reason; Python raises it as a `ValueError` and Node
  returns it from `sceneExportSupportReason`. A
  category y2 gets `XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS` in both.
