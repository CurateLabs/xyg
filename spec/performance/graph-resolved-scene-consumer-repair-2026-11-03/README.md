# Resolved Scene plot / spine consumer repair

Bounded follow-up to approved `188f7450bff332e0be6a80bf97b15b86e74b48ae` in
`/home/ubuntu/.t3/worktrees/xyg/t3-42669f21`, branch
`t3/resolved-svg-legend-style`. No parent worktree writes, remote operations,
Rust/Python product changes, performance claim, or issue/milestone closure.
Parent owns independent review and integration.

## Result and contract

The decoded XYPB plot rectangle is now privately carried into ChartView and
used directly at the resolved-Scene layout boundary. Ordinary responsive,
title/tick and top/right/secondary-axis gutters are not added to already-final
Rust geometry. Ordinary host layout/padding is unchanged.

Resolved spines with solid, undecorated CSS boxes now paint genuine SVG strokes
in the existing labels layer. Rust boundary centerlines, finite nonnegative
widths (including zero/subpixel), paint and visibility remain the inputs. No
rounding, snapping, DPR correction, layout/tick/color policy or producer
geometry compensation is introduced. The public HTML `axis_line` slot still
owns class/inline CSS cascade and box dimensions. Comparing against an
undecorated used box of the already-resolved geometry distinguishes browser
subpixel quantization from authored geometry changes. Unmodified geometry
keeps the decoded coordinates/width literally; changed CSS paint boxes map
mechanically to a flat SVG stroke; the HTML paint is clipped while that
SVG is present, preserving public computed background and box measurements.

The explicitly authorized compatibility boundary retains HTML for authored
box effects: gradients/images, borders/border images, padding, radii, shadows,
painted outlines, filters, transforms/zoom, masks/clips, blend/background-clip,
overflow, generated pseudo content, animations/transitions, and unsupported
box/ancestor geometry. Important clip rules that prevent suppression also
retain HTML. See the exact eligibility list and refresh behavior in
[`browser-wasm.md`](../../design/browser-wasm.md). There is no general CSS-to-SVG
renderer and no narrowing of dossier §36's plain-CSS chrome contract. Fallback
uses one HTML paint, with no SVG duplicate. Solid SVG uses one SVG paint, with
the HTML box suppressed. Each chrome redraw rebuilds that choice; both
`refreshTheme()` and automatic ancestor class observation are exercised.

## Authoritative unchanged full-image helper

`tests/browser/graph_property_default_export.mjs` is byte-identical to 188f:
SHA-256 `a9cc95b2bc1958abfa5e7f8b4b20a67706d0742f088b6c219eb8d33f801ffef8`.
Fresh native producers and real packaged Worker composition were run normally.
No masks, excluded pixels, supplied plot/layout/positions, blessed images or
threshold changes. Exclusive limits remain mean `<3.5`, fraction over 96
`<0.01`, across the whole 640×420 image.

| Comparison | 188f mean / fraction | Repair mean / fraction | Result |
| --- | --- | --- | --- |
| Light WASM vs canonical | 2.216078869 / 0.010747768 | 1.471573661 / 0.003950893 | PASS |
| Dark WASM vs canonical | 2.217901786 / 0.010755208 | 1.473861607 / 0.003962054 | PASS |
| Light initial native vs canonical | 11.272161458 / 0.028463542 | unchanged | FAIL |
| Dark initial native vs canonical | 236.713407738 / 0.992775298 | unchanged | FAIL |

**Whole helper still exits 1**, with exactly the two initial-native failures.
Those separately owned home-view/theme/caption failures remain; this cannot
close #934, #935, M4 or #108. `property-literal/browser.json`,
`property-literal-browser.txt` and `integrity-literal.json` preserve the complete result.
Native own-browser comparisons are also unchanged. XYGQ/XYGF, canonical and
public native SVG/PNG outputs are byte-identical to 188f. All painted
identities, node/route/head geometry checks, captions, legend frame/swatch/text
coordinates and authored legend cascade checks remain green and unchanged.

## Independent browser and CSS evidence

- `literal-matrix/`: 222 actual-browser cases, 111 resolved and 111 ordinary,
  at DPR 1 / 1.25 / 2. All four sides, real Rust-resolved y2, width
  0 / .5 / 1 / 1.5 / 2 / 3, opaque/alpha/transparent/hidden, distinct chart/plot
  backgrounds. Existing extra x2/y3 consumer registrations and class/inline
  width/height/position overrides now also assert actual SVG line attributes.
  These extra registrations reuse resolved descriptors; they do not claim an
  additional Rust authoring API. No plot is supplied by the harness.
- `canonical-literal-proof.json`: all **111 independent native-SVG plot checks PASS**
  (previously 108 failed), with 276 actual SVG spine width/paint/coordinate
  checks. Existing geometry tolerance stays .01 CSS px. **111 ordinary records
  and 12 ordinary screenshots are byte-identical to 188f**.
- `precision/`: a separately authored real Rust Scene uses width .3. At all
  three DPRs, actual SVG attributes equal the decoded width literally
  (`0.3`), while the public CSS box is `.296875`. Native
  centerlines remain exact. Fractional authored width/height/position overrides
  still project their actual CSS footprint. This catches the pre-commit
  candidate's DOM-quantization issue without adding a snapping/tolerance rule.
- `slots-literal/`: 144 real-chart before/after screenshots at three DPRs,
  using an independently rebuilt 188f bundle as the baseline. All **57 HTML
  fallback screenshots are byte-identical**, including border, gradient,
  inline border/gradient, radius, shadow, outline, padding, filter, transform,
  individual translate, ancestor transform, clip/mask/overflow, pseudo content,
  important clipping, transition and animation eligibility. All 15 solid,
  alpha, inline, important-class and visibility screenshots are also identical.
  Alpha equality proves there is no duplicate background paint. Six live
  switching runs check HTML clipping plus exact SVG presence/count while
  ancestor classes switch automatically and inline styles switch through
  `refreshTheme()`. No stale visible copy remains.
- Inspect actual border screenshots:
  [before](slots-literal/border.dpr1.before.png),
  [after](slots-literal/border.dpr1.after.png); gradient:
  [before](slots-literal/gradient.dpr1.before.png),
  [after](slots-literal/gradient.dpr1.after.png).
- `default-literal-captures/`: fresh actual DOM/computed CSS/line attributes
  and complete native raster, native SVG browser, and WASM screenshots at all
  three DPRs. Plot is exactly `[52,24,572,352]`. Actual lines are
  `(52,24)→(52,376)` and `(52,376)→(624,376)`, width 1, flat caps.
  `capture-literal-metrics.json` retains adjacent raw RGB samples and additional full
  image diagnostics. All six extra full-image measurements are also below
  the existing limits; the untouched helper at DPR 1 remains authoritative.

## Precision and remaining limits

Default/solid styling gets the native-stroke coverage claim; authored box
fallback preserves browser/CSS appearance and has no invented native export
parity. Native raster endpoint caps remain round, versus flat canonical SVG
and browser spines. Arbitrary endpoint equality is not asserted or repaired.

`canonical-literal-pixel-samples.json` retains all 3,036 adjacent raw samples, with
2,369 exactly equal to the independent SVG browser image. These are diagnostics,
not masks or a replacement acceptance gate. Residual grid-edge differences
exist even at width zero: the unchanged browser grid clamps/snaps its Canvas
edges (`xEdge`/`yEdge`), while native SVG draws centered grid strokes.
Additionally, native SVG's existing two-decimal serializer emits `306.62`
where the decoded Rust boundary is `306.625`. A separate, explicitly diagnostic
component control (`fractional-svg-swift-kernel/`) reproduces the resulting
coverage step at DPR 1.25 using either inline SVG or an SVG image: at
pixel `(384,99)`, `306.62` gives `[45,49,59]`, while `306.625` gives `[60,63,72]`.
The native export, product chart and gate are never modified by this control.
The earlier default-ANGLE control is retained separately. No coordinate nudge,
SVG serializer, grid or antialias kernel change is made to compensate.

The extra strict `default-pixel-proof.py` diagnostic still normally exits 1:
its exact-RGB assertion finds ±1 channel antialias differences at four light
axis pixels. Dark `(300,375)` is exactly native `[123,128,137]` after repair,
versus the previous near-background value; adjacent `(300,376)` is exactly
`[116,119,127]`. Complete samples and both failed logs remain. This additional
strict diagnostic does not change or replace the successful WASM full-image
limits, and does not assert arbitrary exact native/SVG pixel equality.

## Preservation, artifacts and reproduction

`history-snapshot.json` proves 350 earlier diagnosis/repair files unchanged;
no previously committed receipt is edited. All new intermediate evidence is
also retained, including the rejected literal-SVG border/gradient prototype
(368 missing border pixels and 640 missing gradient pixels), the early
outline-eligibility failure, the hidden-transform eligibility probe failure,
and initial audit-script matcher errors. `layout-*`, `svg-matrix/`,
`active-stroke-*`, `property/`, `property-active/`, `slots/`, `slots-final/` and
`slots-observer/`, `slots-complete/`, `final-extra-matrix/`,
`property-final/` and `default-resolved-captures/` are chronological evidence, not substituted final results.

Native/WASM were **not rebuilt**. Exact f006/188f reuse:

- Native ABI 398, 6,075,160 bytes:
  `708d2b3195e41e785e83de113cca8a5dec5ac9a45d5cb2061131e382d4fbfb15`.
- WASM ABI 35, 1,872,541 bytes:
  `355a31bc7f949070251e73dbeebdd7f466d55e9a242a14f7c85bf29fdec59c50`.
- Worker, freshly built but byte-identical, 53,710 bytes:
  `3f11b1e05775d17ad917e829a43dd7f337844a4b9451ffc45007ffe631d5d2c1`.
- Actual fresh index.js:
  `6cef37f9b430526cc0a4626cba7f56b67d4b67cf6161fbe0bd1f454fae45ec4f`.
- Independently built 188f index.js:
  `351fa5038800204a13a99ae9cb91612472e3368f6d7ecd4829d589e39b16acd7`.

`commands.json` contains actual argv, environment, exit status and log paths;
`source.json` records source hashes and the exact canonical source-diff argv;
`source.diff.gz` is lossless review input; `artifacts.json` hashes the new
receipt files. Generated bundles remain ignored. Generated HTML and build
logs are stored as lossless `.gz` where noted in `compression.json`.

Use pinned Node 22.23.4 at
`target/task-tmp/node-v22.23.4-linux-x64/bin`, and cached Chromium
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome` via
`XYG_CHROMIUM`. Reproduce into **new directories**, preserving this receipt:

```sh
node js/build.mjs
node tests/browser/resolved_axis_spines.mjs \
  spec/performance/graph-resolved-axis-repair-2026-11-03/inputs <fresh-matrix>
uv run python spec/performance/graph-resolved-scene-consumer-repair-2026-11-03/prepare-baseline.py
node target/task-tmp/resolved-spine-188f-baseline/js/build.mjs
# First produce slot.scene with produce-slot-scene.py in a copied fresh receipt.
node tests/browser/resolved_axis_slots.mjs <fresh-receipt> \
  target/task-tmp/resolved-spine-188f-baseline/packages/xy-client/dist
node tests/browser/resolved_axis_precision.mjs <fresh-receipt>
XYG_GRAPH_PROPERTY_EVIDENCE=<fresh-property> uv run pytest \
  tests/test_graphforge.py -k property_default_exports -q
XYG_NATIVE_LIB="$PWD/packages/xyg-node-linux-x64/libxyg_core.so" \
  node tests/browser/graph_property_default_export.mjs <fresh-property>
# Expected whole-helper exit: 1, only the two known initial-native failures.
```

Validation also passes 82 nearby resolved-scene/dual-axis/security/slot tests,
strict-CSP WASM foundation, GraphForge WASM browser smoke, non-numpy browser
render smoke (including ordinary bar/histogram baselines), paired asset checks,
and the required full-worktree hooks and Ruff checks. Full raw logs are kept;
no broad test-suite/performance claim is made.
