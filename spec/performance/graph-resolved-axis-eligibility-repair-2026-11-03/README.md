# R4 resolved-axis eligibility repair

Base: `25d455f0e7bc3a510210c1959c51165e0423aaf9`.
Worktree: `/home/ubuntu/.t3/worktrees/xyg/t3-42669f21`.
Branch: `t3/resolved-svg-legend-style`.

The parent reported that `m4_defaults_audit` approved 25d's source/evidence,
while `s5a_final_review` required three narrow eligibility fixes. This receipt
records new actual reproductions and their repair. It does not claim fresh
independent approval; the parent owns review/integration. No parent writes,
remote operations, native/WASM rebuild, dependencies, ABI, budgets, profiles,
layout, geometry policy or performance claims. All prior receipts remain intact.

## Narrow production change

Only the resolved-spine SVG eligibility predicate changes:

1. Computed `pointer-events` other than `none` keeps the existing HTML paint and
   hit region. No event forwarding, synthetic product events, gesture-band
   changes or new pointer policy is introduced.
2. A supported, nonempty computed `offset-path` other than `none` on either the
   slot or an already-checked ancestor keeps HTML. An axis-aligned SVG line is
   not substituted for motion-path paint/auto-rotation.
3. A supported, nonempty computed `-webkit-box-reflect` other than `none` on the
   slot keeps HTML, preserving the browser's reflected paint.

The empty/undefined/`none` cases do not trigger the last two fallbacks. Existing
solid/default SVG eligibility, literal Rust coordinates/widths, canonical plot,
classes/inline cascade and ordinary HTML axes are unchanged. The exact contract
is updated in [browser-wasm.md](../../design/browser-wasm.md). Authored effects
remain browser/CSS appearance, without invented native-export parity.

## Actual failing-before / passing-after proof

`tests/browser/resolved_axis_eligibility.mjs` serves the independently built
188f baseline and either the frozen actual 25d module or the fresh repair
bundle. Styling uses normal public `dom.class_names` / `dom.styles` and ancestor
CSS. Actual Playwright mouse input, `elementFromPoint`, hit stacks and DOM
observations are used. No product DOM geometry/paint is manually patched and
no product method or reporter is monkeypatched. Every screenshot compares all
76,800 pixels; there are no masks or numeric tolerance changes.

Cached Chromium `156.0.8078.4` supports and actually applies both motion paths
and reflection. The support-aware probe reports unsupported features as SKIP,
not PASS. No other browser engine is claimed.

| Case | Actual 25d vs 188f failure | Repair vs 188f |
| --- | --- | --- |
| Inline pointer auto | Public hit false, clicks 0, hover false | true / 1 / true |
| Important-class pointer auto | Same failure, overriding inline `none` | true / 1 / true |
| Motion path on slot | 3,454 differing pixels; rotated HTML replaced by large aligned rectangle | 0 differing pixels |
| Motion path on labels ancestor | 4,533 differing pixels | 0 differing pixels |
| Reflection on slot | 640 reflected pixels lost | 0 differing pixels |

The pointer positive control uses public slot CSS `left:17`, `top:19`,
`width:80`, `height:8`, `background:red`, `z-index:99`; y is hidden by an authored
class. The actual input point is `(22,22)`. The z-index is essential to put the
slot above the unchanged axis gesture band. The baseline really hits the slot;
25d instead hits `axis_band`. Important-class coverage explicitly checks the
normal inline `pointer-events:none` loses to the class's important `auto`.
Hover's blue outline also supplies an actual visible before/after difference.

The diagonal motion-path cases compute `offset-rotate:auto`, with
`transform`, `translate`, `rotate` and `scale` all `none`. An 80×8 CSS box has an
actual rotated screen rectangle about 62.2254×62.2254. Raw ancestor matrices,
computed paths, box bounds and complete screenshots are retained.
Reflection computes `below 4px none`; exact red pixels fall from 1,332 to 692
under 25d and return to 1,332 after repair.

- `before-complete/`: 12 baseline/candidate case records and 12 pointer-switch
  records; normal probe exit **1**, with nine reproduced assertions failing.
- `after/`: the same records, normal probe exit **0**, no failures or skips.
  Both inline refresh and important-class automatic ancestor observation
  switch auto → none → auto. None retains SVG, no public hit and no click/hover;
  auto restores HTML, its hit region and events. SVG presence/count and HTML
  clipping prove there is no stale visible copy.
- `after-pixels.json`: all 12 complete screenshot pairs (static and switching)
  are exactly equal to 188f. `before-complete-pixels.json` preserves raw losses.
- Actual motion images: [baseline](before-complete/motion-box.baseline.png),
  [25d failure](before-complete/motion-box.candidate.png),
  [repair](after/motion-box.candidate.png). Reflection:
  [baseline](before-complete/reflection.baseline.png),
  [25d failure](before-complete/reflection.candidate.png),
  [repair](after/reflection.candidate.png).

The parent's v3 source/raw observations are copied read-only into
`parent-pointer-v3/` with origin paths and hashes. The parent's initial v1/v2
no-hit fixture attempts are not treated as product proof failures. The local
initial `before/` attempt failed because SVGMatrix lacks `toJSON`; its log and
partial captures remain, separately from the complete reproduction. The exact
complete-before harness is retained as `before-probe.mjs`.

## Existing acceptance and preservation

`canonical-proof.json` verifies **111 independent canonical SVG plot cases and
276 actual SVG spine coordinates/width/paint checks**, with unchanged .01 CSS
pixel geometry tolerance and 3,036 raw adjacent-pixel samples. All 222 DOM
matrix records, all 144 existing slot records and all literal `.3` precision
records are identical to 25d. Ordinary 111 records / 12 screenshots also remain
identical to 188f. All 144 slot screenshots and six literal/fractional CSS
precision screenshots are byte-identical to 25d.

Fresh full-property producers and the **untouched**
`tests/browser/graph_property_default_export.mjs` were run normally. Its SHA is
`a9cc95b2bc1958abfa5e7f8b4b20a67706d0742f088b6c219eb8d33f801ffef8`.
All canonical/public native exports, browser PNGs, identities, routes/heads,
captions, legend/frame/swatch/text observations and slot cascade checks remain
unchanged from 25d. Mean `<3.5` and fraction over 96 `<.01` still apply to every
pixel; no supplied plot/positions or blessed images are used.

| Full helper comparison | Mean / fraction over 96 | Result |
| --- | --- | --- |
| Light WASM vs canonical | 1.4715736607142857 / .003950892857142857 | PASS |
| Dark WASM vs canonical | 1.4738616071428572 / .003962053571428571 | PASS |
| Light initial native vs canonical | 11.272161458333333 / .028463541666666668 | unchanged FAIL |
| Dark initial native vs canonical | 236.71340773809524 / .9927752976190476 | unchanged FAIL |

**Whole helper still normally exits 1**, with exactly the two known initial
native failures. No #934 / #935 / M4 / #108 closure is claimed. Existing native
round vs SVG/HTML flat endpoint caps and grid/serialization limits remain.

The additional stricter `verify.py` audit still fails normally: it asks for
byte-exact equality of every re-captured matrix image. Sixteen re-captures
(including independent native-SVG images) differ by channel values 1–4 while
all 222 DOM records are identical. Raw differences/bounds are retained in
`matrix-image-diagnostics.json`. A selected control using the **same frozen
25d module**, same producer SVGs and unchanged Worker/WASM also differs from
25d's own old captures by channel values 1–2, including independent SVG images
(`frozen-25d-pixels.json`). Exact raster/compositor history is not fully
isolated, and arbitrary matrix bitmap equality is not claimed. No product
geometry, positioning, kernel or tolerance is changed to hide this diagnostic.
The existing canonical-geometry, ordinary-preservation, focused CSS and
untouched full-image acceptance checks above remain the required contracts;
`required-contract.json` reports that bounded scope explicitly.

Nearest validation: 82 existing resolved-scene/dual-axis/security/slot tests and
paired WASM asset verification pass. Required full-worktree pre-commit, Ruff
check and Ruff format check pass before commit. Unrelated suites were not
repeated. `history-snapshot.json` verifies **2,338 historical files unchanged**;
Git scope also excludes edits to any other committed receipt.

## Reuse, hashes and reproduction

No native/WASM rebuild. Exact f006/25d reuse:

- Native ABI 398: `708d2b3195e41e785e83de113cca8a5dec5ac9a45d5cb2061131e382d4fbfb15`.
- WASM ABI 35: `355a31bc7f949070251e73dbeebdd7f466d55e9a242a14f7c85bf29fdec59c50`.
- Worker: `3f11b1e05775d17ad917e829a43dd7f337844a4b9451ffc45007ffe631d5d2c1`.
- Independently built 188f index: `351fa5038800204a13a99ae9cb91612472e3368f6d7ecd4829d589e39b16acd7`.
- Frozen actual 25d index: `6cef37f9b430526cc0a4626cba7f56b67d4b67cf6161fbe0bd1f454fae45ec4f`.
- Fresh repair index: `b2c2066b1d6ed2687a1a248c3f7e8eb1541d4bf6a39ae56a75a99968b5a13f6b`.

`commands.json` has actual argv/environment/exits/logs. `source.json` records
source hashes, staged canonical source-diff argv/hash and actual artifact
hashes; `source.diff.gz` is lossless. `artifacts.json` hashes the new evidence.
`compression.json` records losslessly compressed generated HTML/build logs.
Generated shipping bundles remain ignored and uncommitted. The parent's future
combined P1/module-717 integration is not part of this isolated proof.

Use pinned Node 22.23.4 at `target/task-tmp/node-v22.23.4-linux-x64/bin` and
`XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
Reproduce into **fresh receipt/output directories**, preserving this evidence.
Copy the unchanged `slot.scene` / `precision.scene` from this receipt. Rebuild
188f separately with the existing historical `prepare-baseline.py` recipe if
needed; the local baseline above was reused exactly. The frozen 25d module is
kept at `target/task-tmp/axis-eligibility-25d-assets/index.js`; it can also be
independently built from 25d's JS sources using the same historical build
recipe with its base ref changed to 25d.

```sh
node js/build.mjs
node tests/browser/resolved_axis_eligibility.mjs <fresh-receipt> before \
  target/task-tmp/axis-eligibility-25d-assets/index.js  # expected exit 1
node tests/browser/resolved_axis_eligibility.mjs <fresh-receipt> after \
  packages/xy-client/dist/index.js                    # expected exit 0
node tests/browser/resolved_axis_slots.mjs <fresh-receipt> \
  target/task-tmp/resolved-spine-188f-baseline/packages/xy-client/dist slots
node tests/browser/resolved_axis_spines.mjs \
  spec/performance/graph-resolved-axis-repair-2026-11-03/inputs <fresh-matrix>
node tests/browser/resolved_axis_precision.mjs <fresh-receipt>
XYG_GRAPH_PROPERTY_EVIDENCE=<fresh-property> uv run pytest \
  tests/test_graphforge.py -k property_default_exports -q
XYG_NATIVE_LIB="$PWD/packages/xyg-node-linux-x64/libxyg_core.so" \
  node tests/browser/graph_property_default_export.mjs <fresh-property>
# Whole property helper expected exit 1: only the two initial-native failures.
```
