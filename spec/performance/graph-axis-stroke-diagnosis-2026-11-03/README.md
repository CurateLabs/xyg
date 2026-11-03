# Remaining WASM pixel failure: axis stroke diagnosis, 2026-11-03

Diagnosis only, based on independently approved legend repair
`f006d413c25177e65f60cbcb21a8f0e9ead5138b` (parent reports reviewer
`m4_defaults_audit`, repair diff `3516b408...`, whole diff `1625381c...`).
No production file, existing test/helper, specification, old receipt or commit
is changed. This new diagnostic directory is intentionally uncommitted pending
the parent's shared-contract decision. Visual acceptance remains unfinished.

## Established cause

The canonical Scene and native raster have centered spine strokes. The browser's
axis DIV has the correct 1 CSS px thickness and paint, but its center is shifted
half a CSS pixel toward the plot interior. This is a geometric stroke-placement
contract mismatch, whose visible symptom at DPR 1 is different antialias coverage.
The observations do not support a DPR/backing-store mismatch or a native raster
kernel error as the cause of these dominant rows/columns. The complete residual
image difference has not been attributed to a single cause.

Actual Rust SVG and display-list records have bottom spine `(52,376)→(624,376)`
and left spine `(52,24)→(52,376)`, width 1. `raster.json` and the four
`*.raster.bin` files prove the actual emitted OP_STROKE coordinates, widths,
RGBA8 and round-cap value (1), at scales 1 and 2. These are inspected real native
outputs, not just expected values inferred from source.

Actual browser plot is `{x:52,y:24,w:572,h:352}`. In both themes and both DPRs:

- Left DIV: `{x:52,y:24,width:1,height:352}`, center x=52.5.
- Bottom DIV: `{x:52,y:375,width:572,height:1}`, center y=375.5.
- Padding and every border width are zero; transform/translate/scale are none,
  opacity and zoom are 1. Parent/root/labels styles are retained in `dom.json`.
- Window DPR and view DPR agree at 1 and 2. The marks/chrome/overlay canvas
  backing-to-CSS ratios are exactly 1/1 and 2/2. Visual viewport scale is 1.
- DOM geometry is identical in CSS pixels at both DPRs. At DPR 2 the same
  half-CSS-pixel offset becomes one physical pixel; it does not disappear.

The responsible browser rules are `js/src/50_chartview.ts` lines 7833–7868:
left uses `p.x`, bottom uses `p.y+p.h-xHeight`. A filled 1px box at those
coordinates is interior-aligned. Rust `scene.rs::append_raster_axes` emits
strokes at `layout.left` and `layout.bottom`; the SVG lowering uses those same
centerlines. `raster.rs::stroke_segment_u8_at` samples at pixel centers and
uses coverage `clamp(width/2 + 0.5 - distance_to_segment, 0, 1)` for these
interior straight-stroke pixels. For width 1 at integer y=376, rows 375 and 376
have coverage 0.5 each, composited over their respective plot/chart backgrounds.
The browser DIV instead paints row 375 fully and row 376 not at all.

Dark raw pixels, `(x,y)` at DPR 1:

- `(300,374)`: native, WASM and canonical-SVG browser all `[17,24,39]`.
- `(300,375)`: native `[123,128,137]`; WASM `[229,231,235]`;
  canonical-SVG browser `[123,128,137]`.
- `(300,376)`: native `[116,119,127]`; WASM `[3,7,18]`;
  canonical-SVG browser `[116,119,127]`.
- `(300,377)`: all `[3,7,18]`.
- At y=200, column 51 is native/SVG `[116,119,127]` vs WASM `[3,7,18]`;
  column 52 is native/SVG `[123,128,137]` vs WASM `[229,231,235]`.

The dark native values follow 128/255 coverage over actual plot `[17,24,39]`
and chart `[3,7,18]`, with axis paint `[229,231,235]`. The light axis is
`[31,41,55]`, plot `[248,250,252]`, chart `[255,255,255]`. Light native samples
are `[139,145,153]` on row 375 and `[143,148,155]` on row 376; canonical SVG
browser differs by at most 1 channel value there. This small rounding difference
is distinct from the >96 errors caused by the shifted opaque DIV.

At DPR 2, dark bottom native/SVG paints physical rows 751 and 752 fully; WASM
paints rows 750 and 751. At the left edge native/SVG paints columns 103 and 104;
WASM paints 104 and 105. Raw adjacent samples and full-image counts are in
`pixels.json`, with actual DOM boxes/styles/transforms/ratios in
`captures-physical-size/dom.json`.

## Unchanged full gate and independent control

The existing Python producer and completely unchanged browser acceptance helper
ran into fresh `baseline/`. The normal helper exits **1** with all four existing
failures, including the separately owned canonical-vs-native comparisons.
DPR-1 WASM/canonical captures are byte-identical to f006's committed after
captures, and the separate diagnostic WASM captures are byte-identical to that
fresh baseline. There are no masks, layout overrides, forced positions,
CSS/DOM interventions, pixel substitutions or tolerance changes.

WASM full-image results at the required 640×420 / DPR 1 remain:

- Light: mean 2.213389136904762, fraction >96 0.010751488095238095,
  **2,890 failing pixels; FAIL**.
- Dark: mean 2.2173549107142856, fraction >96 0.010758928571428572,
  **2,892 failing pixels; FAIL**.

Diagnostic concentration counts only: both themes have 570 failing pixels on
row 376 and 569 on row 375. Column 51 has 348 in each; column 52 has 345 light
and 344 dark. Counts overlap at intersections and must not be added as an
exclusive partition. They never remove any pixel from a comparison or waive a
full-image gate.

A separate page renders the actual, unmodified canonical SVG in the same
Chromium, at the same CSS size and DPR. It is a diagnostic consumer control,
never a substitute for WASM product paint. Its two bottom rows and two left
columns each retain only one >96 pixel at DPR 1 (three per band at DPR 2), and
its sampled interior-spine coverage matches native. Its full-image mean/fraction
are light 1.180126488095238 / 0.003712797619047619, dark
1.144750744047619 / 0.003470982142857143. This control independently supports
centered-stroke geometry as the cause of the long error bands. It does not
prove the product repair or attribute every remaining pixel.

DPR 2 WASM full-image diagnostic fractions are light 0.007358630952380952 and
dark 0.007189360119047619, despite the same incorrect half-CSS-pixel shift.
The denominator scales with area while the spine error scales mainly with
length; these results are not a DPR workaround, a changed acceptance setting,
or a product pass. The required DPR-1 full gate remains failed.

Native raster uses round caps; canonical SVG currently defaults to butt caps,
and axis DIVs have flat ends. That separate, small endpoint discrepancy remains
visible in the control's isolated corner pixels. It is not needed to explain
the hundreds of interior pixels on each spine and has not been repaired here.

## Proposed decision and smallest repair

Recommended next authorized slice: make the existing Rust-resolved Scene axis
consumer interpret the canonical axis coordinates as **stroke centerlines**.
For a vertical spine of resolved width w, the perpendicular box origin is
`spine_x-w/2`; for a horizontal spine it is `spine_y-w/2`. Preserve the actual
Rust-resolved plot boundaries, length, width, paint, sides, ordering and public
axis slot cascade. Do not add pixel snapping, integer rounding, DPR offsets,
new layout, or changes to native raster/Scene geometry to compensate for a DOM
box convention. Merely changing thickness or painting opacity cannot reproduce
coverage on both sides of the boundary over two different backgrounds.

Prefer a repair scoped to axes already marked `tick_resolution: rust_scene`
(the existing resolved-Scene discriminator), pending the parent's decision on
broader ordinary-axis unification. The same projection rule should cover all
four resolved spine sides and additional resolved y2/axis instances, rather than
special-casing this graph fixture or its bottom/left coordinates. Ordinary live
host axes currently share this renderer but carry other tick-resolution paths;
changing every chart now would broaden compatibility scope. No such global
behavior change is authorized by this diagnosis.

The existing `Math.max(1, axis_width)` also needs an explicit decision before
claiming arbitrary authored-width fidelity: Rust admits subpixel positive widths
and zero-width invisibility. A default-width centering repair alone does not
prove that broader authored-axis contract. Endpoint caps and spine intersections
likewise need a stated contract; do not silently change every axis, SVG exporter
or raster kernel while addressing this seam.

Prospective regression proof for an implementation decision:

1. Fresh canonical PNG/SVG vs actual resolved browser spines on all four sides,
   at DPR 1, fractional DPR and DPR 2, with authored widths 0.5/1/1.5/2/3,
   and actual centerline/box assertions. No supplied positions or pixel masks.
2. Width zero, transparent/partial-alpha paint, hidden axes, distinct plot/chart
   backgrounds, authored tick directions/lengths/widths and independent tick
   visibility. Check endpoint/corner behavior explicitly.
3. Resolved y2 and extra axes; log/symlog/reversed domains; authored frame-side
   choices; class_names/styles axis-line overrides. Preserve the public slot
   cascade and authored geometry semantics.
4. Keep ordinary HTML/live-host charts in the unchanged branch unless broader
   unification is explicitly chosen. Include the existing baseline-over-bars,
   zero-pinned bar/histogram and dual-axis cases if that scope is chosen.
5. Rerun the untouched full-image property helper normally. Only fresh actual
   images under the existing thresholds can establish visual acceptance.
   Preserve captions, UUIDs, routes, heads, legend and layout checks.

No production repair, commit, ABI/budget/dependency/workflow change, remote
operation or performance claim is made. Parent owns the next shared decision.

## Evidence and reproduction

`commands.json` records exact argv, explicit environment, exit codes and logs.
`probe.mjs` observes the real product and separate canonical SVG at DPR 1 and 2;
`analyze.py` reports full-image metrics plus clearly diagnostic counts/samples;
`raster.py` inspects real emitted display-list records. `manifest.json` records
source/artifact/output hashes and tracked-worktree immutability. The cached
Chromium and pinned Node 22 are unchanged from f006; the exact S5a WASM hash
remains `355a31bc7f949070251e73dbeebdd7f466d55e9a242a14f7c85bf29fdec59c50`.

Diagnostic harness development failures are retained, not product failures:
`diagnostic-browser.txt` records a Buffer-vs-Uint8Array input error before any
image capture; the probe now passes a plain Uint8Array to the decoder.
`captures/` retains the first diagnostic captures; its scale-2 native output
used an insufficient 640×420 physical framebuffer and was rejected by the
analysis shape assertion (`pixel-analysis.txt`). The valid scaled control uses
1280×840 physical dimensions with the same Scene and CSS layout; the corrected
run is separately retained in `captures-physical-size/`. The first raster
record inspection assumed cap enum 0; its assertion failed. Inspection of the
actual record and Rust constants showed round is enum 1; the successful retry
records this explicitly. No old capture or committed receipt was overwritten.

Use the environment in `commands.json`; regenerate the producer into a new
output directory, run the unchanged helper there (expected exit 1), then run
`probe.mjs` into another new directory with that producer directory as its
second argument. `analyze.py` takes the receipt root and capture-directory name;
`raster.py` takes the receipt root containing `baseline/`. Native export width
and height are physical framebuffer dimensions; browser viewport dimensions
remain CSS pixels. No browser monkeypatch or temporary intervention is used.
