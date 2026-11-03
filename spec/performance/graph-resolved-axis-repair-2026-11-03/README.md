# Rust-resolved spine projection repair, 2026-11-03

This is the parent-authorized consumer-only follow-up to independently approved
legend repair `f006d413c25177e65f60cbcb21a8f0e9ead5138b`, in branch
`t3/resolved-svg-legend-style`, isolated worktree
`/home/ubuntu/.t3/worktrees/xyg/t3-42669f21`. The bounded DOM projection repair
passes its regressions. **Full-image WASM acceptance remains unfinished.** The
normal, completely untouched default-property helper still exits **1** with
all four visual failures; they are not waived or relabeled as passes.

## Implemented boundary

Only axes with existing `tick_resolution === "rust_scene"` change:

- Vertical origin is canonical boundary x minus half the resolved width.
- Horizontal origin is canonical boundary y minus half the resolved width.
- Segment length stays canonical; resolved finite nonnegative widths include
  zero and subpixel values. No minimum 1px clamp applies to these axes.
- The same rule handles top/bottom/left/right and secondary/extra X/Y axes.
- Public `axis_line` class and inline-style application stays in the existing
  rule constructor. CSS width/height overrides retain their current semantics;
  computed CSS dimensions never feed back into canonical origin calculation.

Ordinary/nonresolved axes retain their existing interior boxes and minimum
1px thickness exactly. Paint/visibility/alpha, ticks, Rust plot/layout, data,
identities, GPU/session behavior and native export are unchanged. No pixel
rounding, snapping or DPR offset is added. Native round caps and canonical
SVG/DIV flat ends remain a separate known limitation; endpoint equality is not
claimed. No SVG/raster/Rust, ABI, package budget, dependency, profile or workflow
change is made. No performance or release claim is made.

The accepted diagnosis directory is retained **byte-for-byte**, including its
uncommitted historical contents. `diagnosis-snapshot.json` was taken before this
repair; `verify.py` checks every file and the directory's complete file set.
The directory becomes tracked with this handoff without rewriting its receipt.
All earlier committed receipts remain unchanged.

## Actual browser regression proof

`tests/browser/resolved_axis_spines.py` uses public composition authoring to
produce 37 real Rust Scenes, canonical SVGs and ordinary live host payloads:
widths 0/.5/1/1.5/2/3; bottom/left plus real right-side y2; top/right primary
axes; opaque, 128/255-alpha and transparent paint; and a separate authored
hidden-axis case. Chart `[3,7,18]` and plot `[17,24,39]` backgrounds are distinct.
No layout, plot or graph positions are supplied to the browser.

`tests/browser/resolved_axis_spines.mjs` exercises those actual inputs at DPR
1, 1.25 and 2, through the real WASM Scene worker/hydrator and ordinary host
renderer with its normal tick attachment: **222 cases**. Browser boxes, resolved
axis metadata, paint, actual DPR, slot classes and inline styles are retained.
The existing 0.01 CSS-pixel geometric tolerance is used; no image tolerance is
changed. The public y2 proof reaches the actual canonical Scene secondary-axis
path. A separately identified consumer-registration seam clones existing
resolved descriptors into x2/y3 registrations, without inventing tick values or
plot positions. It covers the additional renderer loops, not new canonical
Scene admission for arbitrary extra axes.

Before repair, all **111 ordinary cases pass**, and all **111 resolved cases
fail** the centerline/width assertions. After the fresh bundle rebuild, **all
222 cases pass**. Additional class and inline override assertions pass in both
lanes at all three DPRs: class width/height/background override base defaults;
inline width/height/left/top/background override both class and structural
styles; the original origin remains derived from Rust width when only CSS
width changes. Temporary test overrides are restored before screenshots.

The preservation audit compares every ordinary case record before/after
exactly: **111 identical records**. All **12 ordinary screenshots** are also
byte-identical. Every case retains identical Rust plot bounds, axis descriptors
and computed paint/alpha. Against independently emitted native SVG, authored widths and RGBA8 match
in all 111 resolved cases and all 150 visible authored spine records, including
top/right and y2. The independent plot-bound comparison, however, FAILS in
108 cases with the same discrepancy already present in f006; it is recorded
separately in `canonical-contract.json`, and the audit returns exit 1. Native
SVG omits zero-width, transparent and hidden strokes as expected; the browser
retains zero-area or transparent structural boxes without altering their paint.
These assertions prove geometry and style consumption, not arbitrary native
pixel coverage from a CSS background rectangle.

Existing nearby proof: 82 Python tests pass (client security, live dual-axis,
cross-host dual-axis, static secondary axes and chrome ABI). The existing
non-NumPy render smoke passes all probes, including ordinary bar/histogram
baselines, axis-over-mark layering, DPR changes and context recovery. Full
strict-CSP WASM foundation and GraphForge browser smoke pass. Paired WASM assets
verify successfully. No full multi-hour Python suite was run.

## Pre-existing canonical plot gap exposed by the independent oracle

The local projection regression deliberately tests centering on the browser's
existing plot, while the independent audit compares that plot to actual native
SVG. It does not turn local centering into a claim of end-to-end canonical
position equality. Of 111 resolved matrix cases, 108 retain a pre-existing
native/browser plot discrepancy, identical before and after this repair. For
`w1-bottom-left-opaque`, Rust SVG plot `[46,6,239.75,198]` becomes browser plot
`[46,6,197.75,198]`, reserving another 42px on the right. Top/right cases also
move the plot top from 6 to 32 and reduce height from 198 to 172. The three
hidden-axis cases match. No layout or supplied position is changed to hide
this failure. `canonical-contract.json` retains all 108 failed comparisons and
both f006/repaired plots; the audit's normal exit is 1. Centering on the canonical
Rust boundary for these cases remains blocked by this existing plot-layout gap.
The narrow consumer arithmetic is implemented, but complete all-side canonical
layout acceptance is explicitly unfinished. Parent decision is required for a
separate layout repair; this patch does not add one.

## Full-image result and newly isolated remaining gap

Fresh default-property Python/Rust outputs, actual browser captures and the
untouched helper are retained in `property/`. The helper checks all pixels at
its unchanged mean <3.5 / fraction-over-96 <0.01 limits. No mask, forced
position/layout, image substitution, browser monkeypatch or diagnostic pass mode
is used. Caption text/anchors, UUIDs/endpoints, legend, nodes and all 17
shaft/loop/arrowhead pieces continue to pass the existing checks. The exports,
identities, routes, captions and native-browser observations are identical to
f006; the audit verifies this explicitly.

Canonical PNG vs actual WASM browser:

| Theme | f006 mean / fraction >96 | Repaired mean / fraction >96 | Result |
|---|---:|---:|---|
| Light | 2.213389136904762 / 0.010751488095238095 | 2.216078869047619 / 0.010747767857142857 | FAIL: fraction >=0.01 |
| Dark | 2.2173549107142856 / 0.010758928571428572 | 2.2179017857142855 / 0.010755208333333334 | FAIL: fraction >=0.01 |

The separate canonical-vs-initial-native comparisons remain exactly unchanged:
light 11.272161458333333 / 0.028463541666666668 and dark
236.71340773809524 / 0.9927752976190476, both FAIL. Native export vs its own
browser still passes unchanged at light 2.557715773809524 / 0.009308035714285715
and dark 2.390472470238095 / 0.008311011904761904.

Actual post-repair property DOM boxes are now left `[51.5,24,1,352]` and bottom
`[52,375.5,572,1]`, with no transforms or borders. Rust plot stays
`[52,24,572,352]`. Nevertheless, Chromium's DIV background paint has pixel
coverage different from the centered native/SVG stroke. At DPR 1, dark samples:

- `(300,375)`: native `[123,128,137]`, repaired WASM `[17,24,39]`.
- `(300,376)`: native `[116,119,127]`, repaired WASM `[229,231,235]`.
- `(51,200)`: native `[116,119,127]`, repaired WASM `[3,7,18]`.
- `(52,200)`: native `[123,128,137]`, repaired WASM `[229,231,235]`.

Thus centering fixes the DOM contract but the fractional-edge background paints
as a solid row/column, rather than the native stroke's split coverage. The
horizontal solid row moves from y=375 to y=376; the left solid column stays at
x=52. At DPR 2, measured boxes remain correctly centered, with backing ratios
2/2, but bottom solid rows are 752/753 instead of native 751/752. This is
observed background-rectangle rasterization, not evidence that layout or Rust
coordinates should be shifted again. Its browser-internal snapping mechanism
has not been modified or fully reverse engineered in this bounded repair.
The separate unmodified canonical-SVG browser control still matches sampled
native spine coverage. `post-projection-captures/dom.json` and
`remaining-coverage.json` retain actual boxes, computed borders/transforms,
DPR, full-image metrics and adjacent raw pixels. Counts/samples are diagnostic;
no pixels are excluded from a gate.

This coverage gap requires a separate parent decision about resolved-spine
painting. No SVG replacement, CSS transform/rounding workaround, per-DPR
nudging, opacity-band emulation, raster change, new geometry policy or global
ordinary-axis change was added. The cap mismatch also remains separate. The
parent separately owns native graph theme/home/caption unification. This
handoff cannot close #934/#935/M4/#108.

## Sources, reuse and reproduction

`commands.json` gives exact argv, environment, exit codes and raw log paths.
`source.json` records the source-only binary/full-index diff SHA-256, source
hashes and base. `source.diff.gz` is that raw diff, losslessly compressed.
`artifacts.json` inventories fixtures, captures and export hashes; `integrity.json`
records preservation and independent SVG width/paint comparisons;
`canonical-contract.json` retains the independent plot-bound failures. Native HTML and build
output are retained losslessly as gzip. Mandatory full-worktree pre-commit,
Ruff check and Ruff format checks are run before committing.

Node is the existing pinned v22.23.4 binary and browser the cached Playwright
Chromium used by f006. `node js/build.mjs` produced fresh ESM/IIFE and worker
bundles and Python copies; generated shipping bundles are not committed. Native
and WASM producers were **not rebuilt**: `reuse.json` compares actual bytes to
f006's committed artifact inventory, including native/platform libraries,
WASM and worker. The module remains exactly
`355a31bc7f949070251e73dbeebdd7f466d55e9a242a14f7c85bf29fdec59c50`.
No dependency or browser download was needed for this repair.

Run producer/probes from the repository root into new output directories:

```bash
export PATH="$PWD/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
export XYG_NATIVE_LIB="$PWD/packages/xyg-node-linux-x64/libxyg_core.so"
node js/build.mjs
python3 scripts/verify_wasm_assets.py
uv run python tests/browser/resolved_axis_spines.py /tmp/axis-inputs-fresh
node tests/browser/resolved_axis_spines.mjs /tmp/axis-inputs-fresh /tmp/axis-browser-fresh
XYG_GRAPH_PROPERTY_EVIDENCE=/tmp/property-axis-fresh uv run pytest tests/test_graphforge.py -k property_default_exports -q
node tests/browser/graph_property_default_export.mjs /tmp/property-axis-fresh
```

The local projection regression matrix should exit 0; the independent
`verify.py` audit exits 1 for the retained canonical plot mismatches. The last,
unchanged full-image helper
currently exits 1; its failures must remain visible. Parent owns independent
review and integration. No push, PR or remote mutation was performed.
