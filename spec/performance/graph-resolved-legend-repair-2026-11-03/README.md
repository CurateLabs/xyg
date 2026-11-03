# Resolved SVG legend presentation repair, 2026-11-03

This bounded #934/#935 repair separates the full-viewport resolved SVG legend
from the ordinary HTML legend's box defaults. Rust owns the resolved frame,
background, swatches and text coordinates. The SVG container must have zero
default padding, a transparent default background and zero default border radius;
the explicit Rust frame supplies its legend background and border. The public
`legend`, `legend_title`, `legend_item` and `legend_label` slots still apply.
Authored class names and inline slot styles retain their cascade precedence,
including deliberately authored padding/background/radius on the container.
Ordinary HTML legends retain their existing 4px 8px padding, translucent gray
background and 4px radius. This is a structural CSS variant in the existing base
layer, following the custom-tooltip attribute pattern; it introduces no legend
geometry, layout or theme policy in TypeScript.

The isolated implementation checkout starts at parent `5840b479`, branch
`t3/resolved-svg-legend-style`, worktree
`/home/ubuntu/.t3/worktrees/xyg/t3-42669f21`. Reviewed proof dependency
`bce5339b8d07edf2dae213aca2c6d1f4b9eec70c` (proof base `030c7906`) was merged
normally as `b705c96cbd21f023c0d744c7ae9699686e07998d`. The merge preserves every
committed proof and erratum byte; full-worktree hooks and Ruff checks ran before
the merge commit. The parent supplied whole-proof reviewer `m4_defaults_audit`
and review reference `98ea5d7f14bdf32491917d64f87d9ec1317797c87d7c39f4899a1bf75f0ff99b`.
That review concerns the dependency, not this repair. Parent owns independent
review of the final repair diff and integration.

The documented Playwright helper `tests/browser/graph_property_default_export.mjs`
adds actual computed styles, DOM rectangles, SVG bounding box/screen transform,
Rust-resolved bounds, frame paint/attributes, swatch attributes and text anchors.
It captures before and after in distinct directories, using fresh Python/Rust
canonical PNG/SVG and public native exports for each run. It never compares to
committed screenshots as an oracle. Full-image limits remain mean maximum RGB
channel difference <3.5 and fraction of pixels differing by >96 <0.01. There are
no masks, forced positions, layout overrides or tolerance changes. Temporary
constructor/slot-cascade probes are removed before the screenshot; they do not
change the chart under comparison.

No Rust, native/WASM ABI, GPU/session, controller, theme palette, package budget,
profile, dependency or workflow change is made. Native dark background, canonical
axes/captions and native/Scene home-view differences remain separately owned.
This cannot close #934, #935, M4 or #108 and makes no performance, scale,
competitor or release acceptance claim.

## Actual before and after

In both themes the before SVG computed `padding:4px 8px`,
`background-color:rgba(128,128,128,0.08)` and `border-radius:4px`. Its actual
screen matrix was `[1,0,0,1,8,4]`. Rust-resolved bounds, SVG local bounding box
and frame attributes were all `[467.25,32,148.75,98]`, but the actual DOM frame
rectangle was `[475.25,36,148.75,98]`. Both frame and text-anchor screen errors
were 8 CSS px. The outer SVG rectangle was `[0,0,576,348]`, showing that the
background belonged to the container over the plot, not to the Rust legend frame.
These are actual DOM observations, not image/source inference.

After the repair both themes compute `padding:0px`, transparent background and
`border-radius:0px`, with identity screen matrix `[1,0,0,1,0,0]`. The actual
frame rectangle is exactly `[467.25,32,148.75,98]`; frame and text-anchor errors
are zero. Rust's light frame fill remains white at alpha 238/255, with border
`[75,85,99,255]`; dark remains `[17,24,39,238]` with border
`[170,178,191,255]`. Raw frame attributes, all swatches, text coordinates and
DOM rectangles are in each capture's `observations.json` and `browser.json`.
Swatch numeric attribute error is at most 0.000001526 CSS px against canonical
SVG. No Rust-resolved bounds, coordinates or paints were changed.

The ordinary HTML constructor retains its exact default padding/background/
radius in both themes. An unlayered authored class overrides the resolved SVG
with `3px 6px` padding, `rgb(1,2,3)` background and `7px` radius. Authored
`dom.styles.legend` wins over that class with `9px 10px`, `rgb(4,5,6)` and
`11px`, on both SVG and HTML constructors. These assertions pass before and
after. They exercise `_legendBox` and `_applySlot`, preserving the actual public
slot cascade. Temporary probe legends are removed before full-image capture.

The unchanged full-image gates **still fail**, so this is a partial presentation
repair and a remaining-failure handoff. No broader presentation change was made.
Both normal helper invocations return **exit 1**.

| Canonical PNG vs fresh WASM browser | Before mean / fraction >96 | After mean / fraction >96 | Final result |
|---|---:|---:|---|
| Light | 10.463013392857142 / 0.016878720238095238 | 2.213389136904762 / 0.010751488095238095 | FAIL: fraction >=0.01 |
| Dark | 9.653229166666666 / 0.015773809523809523 | 2.2173549107142856 / 0.010758928571428572 | FAIL: fraction >=0.01 |

Both means pass the <3.5 limit. The remaining full-image pixel mismatch has not
been attributed to a new cause in this bounded repair. The separately owned
canonical-vs-initial-native comparisons remain failures, unchanged: light
11.272161458333333 / 0.028463541666666668; dark
236.71340773809524 / 0.9927752976190476. Native PNG vs its own browser remains
passing at light 2.557715773809524 / 0.009308035714285715 and dark
2.390472470238095 / 0.008311011904761904. No false-green helper mode exists.

Caption text and identities still match canonical SVG within 0.004 CSS px;
node and route/arrowhead coordinates remain within 0.005 CSS px. All ten
node/relationship UUIDs and exact edge types/endpoints remain intact. All 17
shaft/loop/arrow pieces retain stable-ID counts 3,3,5,3,3. The parallel routes,
closed self-loop and nondegenerate arrow wings are checked by the unchanged
Python producer. Canonical request/document and SVG/PNG exports are identical
before/after and across Python, Node and packaged WASM composition. Native chart
exports are also byte-identical before/after. Browser errors remain empty and
native tick readiness passes.

## Validation and reproduction

`commands.json` records exact argv, environment, exit codes and raw logs. Node
v22.23.4 is the existing pinned binary under the parent's `target/task-tmp`,
linked into this worktree's `target/task-tmp`. Browser is the existing cached
Playwright Chromium at
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
No system Chrome, T3 browser tab or downloaded browser was used. Native and WASM
were freshly compiled in this checkout. `node js/build.mjs` ran before and after;
shipping bundles remain generated and uncommitted. The real WASM producer and
unchanged package gates passed; paired assets passed before/after. The final
WASM SHA-256 is exactly the required S5a value
`355a31bc7f949070251e73dbeebdd7f466d55e9a242a14f7c85bf29fdec59c50`.

Focused checks: Python producer 2/2 before and after; nearby graph/composition,
security and legend placement 101 passed / 1 existing expected failure;
post-repair security, legend resize and graph scales/legend 65 passed;
Node graph/composition/native-WASM suites 95 passed, no skips. Full existing
strict-CSP WASM foundation and GraphForge browser smoke both passed. The
foundation exercises Rust-resolved Scene legends, symbols and authored chrome;
its retained report is scoped by the existing report contract. The full long
Python suite was not run. Mandatory full-worktree pre-commit and Ruff checks
are recorded separately before each commit.

Reproduce into a **new** output directory, never over an existing receipt:

```bash
export PATH="$PWD/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
export XYG_NATIVE_LIB="$PWD/packages/xyg-node-linux-x64/libxyg_core.so"
cargo build --release
node js/build.mjs
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/package-wasm.mjs
python3 scripts/stage_node_platform_natives.py --lib target/release/libxyg_core.so
python3 scripts/verify_wasm_assets.py
XYG_GRAPH_PROPERTY_EVIDENCE=/tmp/graph-legend-fresh uv run pytest tests/test_graphforge.py -k property_default_exports -q
node tests/browser/graph_property_default_export.mjs /tmp/graph-legend-fresh
```

The last command must return 1 while the recorded remaining pixel gaps persist.
`source.json` identifies the source-only binary/full-index diff and source
hashes; `artifacts.json` inventories actual binaries, generated bundles, raw
inputs/exports, screenshots and observations. Generated native HTML is retained
losslessly as gzip with its uncompressed hash, rather than committed as a bundle.
`integrity.json` checks historical receipt bytes, unchanged canonical/native
exports, module identity and preserved non-legend browser facts.
