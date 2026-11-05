# Issue 889 acceptance evidence

All eleven historical families now have a scenario-specific disposition: active
shared Rust rendering proof, or a documented existing fail-close with an active
exact-reason test. This is a locally verified **candidate for independent review**,
not a merge or issue-closure assertion. Future capability debt remains explicit.

Workspace: `/home/ubuntu/.t3/worktrees/xyg/t3-96471efa`, branch
`t3/pyplot-static-journeys`. Starting base `74195403ccd18c760e3d20a18f024daab95d711a`
has the accepted-main `40c0cc5af2fead54684197c0ef90affbbff53519` tree.
The initial repair commit `14fe6c57` and its original receipts are retained.
No other worktree, #1095 change, push, PR, GitHub object, or issue closure is part
of this implementation. Independent final review and the merge queue belong to
the parent.

## Acceptance matrix

Every successful native export below uses canonical Scene → Rust XYST consumers.
There is no compatibility renderer fallback. A deferred rendering test's xfail
is **not** its acceptance evidence: the corresponding active test invokes the
same original function body and asserts its complete diagnostic. Unexpected
successful export also fails that active test.

| # / family | Accepted shared-route proof | Accepted fail-closed scope / future capability debt |
|---|---|---|
| 1 gradients, contour/contourf, mesh face paints, listed cmaps | Existing solid-band/truecolor paths retain coverage; `test_matplotlib_style_extremes_are_shared_by_images_and_contours` now checks native canonical paints and passes | The three exact unresolved-gradient programs in `tests/pyplot/issue_889_rejections.json` assert `XYG_SCENE_UNSUPPORTED_GRADIENT`, including level colors, face-matched bar/mesh strokes and corner-mask triangles. Ordinary named cmap or truecolor support is not revoked |
| 2 contour colorbars | Decimal ticks, reversed/post-hoc imshow cmap and existing discrete contourf colorbars pass; the over-budget continuous-ramp test still requires >20 steps at the unchanged stop budget | The fixture's four direct line/overlay/listed-band colorbar programs assert `XYG_SCENE_UNSUPPORTED_PUBLIC_COLORBAR`; the second automatic colorbar program asserts `XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_STYLE`. Exact authored shapes, not all contour colorbars, are deferred |
| 3 scatter faces, edges and alpha | `test_colormapped_scatter_default_edges_use_each_points_face_color` verifies both LUT endpoints, matched face/edge paints and 0.4 alpha on each point. `test_scatter_alpha_applied_with_colormap_encoding` verifies all 50 points' face/edge alpha. Registry `document_scatter_colormap_alpha` checks Scene/XYST, raster commands and all five formats | None for these named journeys; old group-element SVG assertions were replaced by per-point paint assertions |
| 4 authored axes, autorange, labels/rotation/minor tickers, collections, dates | Ordinary Rust autorange remains admitted. The public pyplot adapter resolves its domains and chrome; `test_public_savefig_tick_padding_uses_the_resolved_frame` exercises that route | Nine direct composed-figure programs in the exact rejection fixture retain `XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS`: tick padding, errorbar-container legend, label rotations, minor/date tickers, visibility/alpha annotations, and collection colors. Their missing authored domains/domain-shaping options are not silently admitted |
| 5 callout, arrow, rule and coordinate spaces | Existing axes-fraction text is proven by `tests/test_static_annotation_space_cross_host.py` (XYAF and five-format parity) | Original callout/connector/rule programs and each of the ten named unadmitted style keys are active exact checks for `XYG_SCENE_UNSUPPORTED_ANNOTATION_STYLE`. Arrow head-style value rejection is `XYG_SCENE_UNSUPPORTED_ARROW_STYLE`. Four Rust-registry per-kind witnesses require matching Python/Node reasons. Figure-fraction text retains `XYG_SCENE_UNSUPPORTED_ANNOTATION_COORDINATE_SPACE` |
| 6 rc font weight and quoted font families | Native rc/chrome projection outside the deferred direct programs retains its existing tests | The two exact original direct programs assert `XYG_SCENE_UNSUPPORTED_PUBLIC_TEXT` and `XYG_STATIC_UNSUPPORTED_CUSTOM_FONT`. No custom font or rc-weight policy was invented or weakened |
| 7 figure/panel legend glyphs, relabel and frame | Explicit relabelled items are preserved instead of rebuilt from trace names. `test_legend_handles_labels_form_relabels_handles` and `test_legend_frameon_false_removes_frame_in_static_export` pass. Registry `document_legend_relabel` / `document_legend_frameless` checks exact content, transparent frame and five-format cross-host identity | The explicitly requested non-circle scatter legend program asserts `XYG_STATIC_UNSUPPORTED_FIGURE_LEGEND_STYLE`, the existing XYDL contract. Tests request a legend explicitly, matching pyplot's documented semantics |
| 8 shared layout / serialization | `tests/pyplot/test_frame_geometry.py` reads actual emitted clip rectangles and proves reported/rendered agreement for single/grid/dense/overlay/matshow/twinx/constrained frames without changing tolerances. `test_constrained_subplot_xlabels_stay_inside_static_canvas`, rc tick spacing, public tick-pad override, suptitle/facecolor, boxed text and imshow-hidden-grid checks pass. Registry `document_authored_frame` pins exact XYCF margins through both hosts/all formats | Direct raw Chart tick-padding export without qualifying domains remains the exact family-4 rejection. User/notebook `_padding` remains a minimum gutter, preserving the long-y-title clearance tests |
| 9 two raw errors | `test_null_locator_removes_ticks_from_the_export` passes through Rust using hidden labels and empty authored ticks. Rust registry `line_hidden_tick_labels` / `scatter_hidden_tick_labels` pins two shapes/axis modes with unchanged pairwise rules | `test_categorical_text_static_export_has_a_stable_reason` asserts `XYG_SCENE_UNSUPPORTED_ANNOTATION_COORDINATE`; the original future-rendering test stays xfailed |
| 10 dense and overlapping composition | Unchanged `test_dense_grid_composite_draws_every_panel` probes all 64 panels, original >0.5 coverage and opaque canvas. Registry `document_overlap_red_blue` / `document_overlap_blue_red` independently authors wide translucent panels, checks all five formats and exact opposite-order source-over pixels `(127,63,191,255)` / `(191,63,127,255)` | None for these named journeys |
| 11 rich polar | Ordinary categorical radar labels, authored theta ticks, line/scatter/bar projection, styled grid/labels, and hole/sector PDF export have active rendering tests. Raster rim labels now paint after the plot clip resets. Full annular PDF clips retain both circle boundaries under even-odd clipping. Registry `document_polar_annulus` checks both hosts/all formats | All 17 deferred original programs/parameter cases are active exact checks in `tests/test_issue_889_polar_rejections.py`: the documented advanced combinations assert `XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS`, and all-NaN radar asserts `XYG_SCENE_UNSUPPORTED_NONFINITE_COORDINATES`. Secondary angular/radial validation has exact `XYG_POLAR_UNSUPPORTED_SECONDARY_AXIS` checks. Full case details are in the polar JSON inventory |

The complete deferred programs/messages are committed in
[`issue_889_rejections.json`](../../tests/pyplot/issue_889_rejections.json) and
[`issue_889_polar_rejections.json`](../../tests/fixtures/issue_889_polar_rejections.json).
The [marker-coverage receipt](evidence/889/completion/marker-coverage.json) proves
that every remaining pyplot #889 xfail has its active exact-reason counterpart.
The other two pyplot xfails predate this work and are not #889 acceptance claims.
The compatibility contract is [compat.md](compat.md#qualified-deferred-native-journeys-889).

## Verification and reproduction

Use the local source build and the dependency setup in AGENTS.md. The actual
environment and unchanged WASM gates are recorded in
[completion/results.json](evidence/889/completion/results.json).
On this machine the Rust tools need `/home/ubuntu/.cargo/bin` on PATH; the Node
host/gate run uses Node 22.23.4. Set `XYG_CHROMIUM` to
`/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`
(Google Chrome for Testing 156.0.8078.4).

```
cargo build --release
node js/build.mjs
npm run build:wasm
cargo test --workspace
uv run pytest tests/pyplot --ignore=tests/pyplot/corpus -q
make check-host-parity
uv run pytest tests/test_polar_charts.py tests/test_issue_889_polar_rejections.py tests/test_static_lod_polar_cross_host.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/static-lod-polar.test.mjs
python3 scripts/verify_wasm_assets.py
uv run ty check
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

- Required pyplot gate: **1184 passed, 163 skipped, 26 xfailed, no XPASS**.
  Twenty-four are the qualified #889 future programs; two are existing unrelated
  expected failures. Optional reference-dependency skips are not qualification.
- Required host gate: **green**, including **1096 cross-host tests**, registry,
  ABI smoke (673 checks), inventory/ownership and delegation corpus.
- Polar bundle: **157 passed, 17 xfailed**, including 19 active rejection cases
  and the shared large-source/LOD golden checks. Node polar suite: **7 passed**.
- Full Rust workspace: **1967 unit tests passed**, plus **5 doctests passed**;
  no failures. Type checking and packaged WASM verification pass.
- Post-type-check metadata-storage adjustment: focused frame/gutter/padding
  tests **45 passed, 3 pre-existing/qualified xfailed**. Assignment uses the
  established internal `Figure.__dict__` metadata seam; behavior is unchanged.

The original unmasked baseline was **39 failed / 4 passed** in the selected
pyplot set and **31 failed / 118 passed** in polar. The qualified unmasked
receipts show only the explicitly documented deferred programs; they are
intentional failures when xfail is disabled. Original raw logs, new receipts,
hashes, and source base are preserved under
[evidence/889/completion](evidence/889/completion), alongside the original
partial-repair receipts. No initial receipt was rewritten.

## Output contracts and limits

The polar SVG golden stays byte-identical. Its PNG golden changes because rim
labels now paint outside the plot clip; the active raster-color test proves the
previously missing angular label ink. The continuous colorbar fallback SVG
snapshot changes because the resolved colorbar frame is carried into Scene,
while the stop budget and >20-step contract are unchanged. These exact hash
changes have receipts, not relaxed thresholds.

The #875 registry now has 14 pairwise edge rows, 23 fail-close rows and 51 XYST
runtime cases. Its exact two-row/different-shape/axis concern checks remain
unchanged. Existing 1M-line, 100k-direct-scatter and 150k-categorical-scatter
outputs retain their golden hashes; this is correctness proof, not a new
competitor timing or massive-data performance claim. No runtime crate, C ABI,
profile, optimizer, export/guard, size budget, tolerance or arena limit changed.

Review images are native exports, reproduced with
`uv run python spec/matplotlib/evidence/889/completion/render_examples.py`:
[shared frames/legend/scatter](evidence/889/completion/examples/shared-route.svg),
[polar chrome](evidence/889/completion/examples/polar-chrome.png), and
[wide overlap](evidence/889/completion/examples/overlap-red-blue.png).

## Independent Rust review repair

The initial complete candidate 9487d791 received two blocking Rust/PDF review
findings. The [review repair record](evidence/889/review-r1/README.md) supersedes
its annular-clip claim and records the independently reproduced original diff
checksum. Scene now emits a genuine compound SVG annulus, native raster marks
use the existing annular clip opcode, and PDF rejects invalid clip input.
A diameter-crossing registry witness checks the clear center, painted ring and
even-odd PDF path, with independently authored Python/Node byte parity. Fresh
required pyplot, host-parity, polar/registry, Rust/Clippy and unchanged packaging
gates passed as recorded there. Other independent reviews and re-review of this
repair are still required; no PR or closure approval follows from these results.
