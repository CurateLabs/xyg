# Issue 889 acceptance audit

This is an incomplete acceptance audit, not closure evidence. Base
`74195403ccd18c760e3d20a18f024daab95d711a` has the accepted-main
`40c0cc5af2fead54684197c0ef90affbbff53519` tree. The historical issue body
predates several admissions. Do not infer that a passing xfail proves its whole
family, or that a green suite with remaining xfails closes this issue.

## Reproduction

Build the local release core and generated client/WASM assets before testing.
Put the installed Rust toolchain on PATH (`/home/ubuntu/.cargo/bin` here).
Use `XYG_CHROMIUM` to select the browser recorded in
[evidence/889/environment.json](evidence/889/environment.json).

```
cargo build --release
npm ci
node js/build.mjs
npm ci --prefix packages/xy-node
npm rebuild --prefix packages/xy-node koffi
npm run build:wasm
uv run pytest tests/pyplot --ignore=tests/pyplot/corpus -q
uv run pytest tests/test_polar_charts.py -q
uv run pytest tests/test_static_export_cross_host.py -q
make check-host-parity
```

For the historical gaps, disable xfail with `--runxfail`. The exact failing
node IDs are preserved in [pyplot-before.txt](evidence/889/pyplot-before.txt)
and [polar-before.txt](evidence/889/polar-before.txt). The selected pyplot
baseline had 39 failures and 4 passes; polar had 31 failures and 118 passes.
The regular initial pyplot run had one missing-WASM-asset failure during setup;
that is not a product regression. After packaging WASM and these changes the
explicit-browser run has **1135 passed, 163 skipped, 40 xfailed, no XPASS**.
The skips include optional reference dependencies; they are not reference
qualification. No competitor timing claim is made by this correctness repair.

## Acceptance matrix

All native successful exports below use canonical Scene → Rust XYST consumers,
with no compatibility renderer fallback. Rows marked remaining require further
implementation or exact rejection qualification before closure.

| Family | Current evidence / exact test suffix | Disposition |
|---|---|---|
| 1 gradient contour / mesh / listed paints | `test_contour_demo_cycles_listed_colors_per_level_through_renderers`, `test_contourf_corner_mask_uses_exact_band_clipped_triangles`: `XYG_SCENE_UNSUPPORTED_GRADIENT` | Remaining; existing rejection, original xfails retained |
| 2 contour colorbars | `test_contour_colorbar_inherits_extend_lines_and_colorbar_axes_state`: `XYG_SCENE_UNSUPPORTED_PUBLIC_COLORBAR`; `test_second_automatic_colorbar_uses_explicit_axes_without_overwriting_first`: `XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_STYLE` | Remaining; ordinary decimal colorbar ticks and reversed imshow cmap pass their original tests, two stale xfails removed |
| 3 scatter faces / edges / alpha | `test_colormapped_scatter_default_edges_use_each_points_face_color`, `test_scatter_alpha_applied_with_colormap_encoding` | Remaining; native SVG is produced, old group-opacity assertions fail; no unsupported claim justified |
| 4 authored axes / collections / dates | `test_numeric_axis_label_rotation_reaches_both_rendered_axes`, `test_text_date_string_coordinates_on_a_date_axis`: `XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS` | Remaining; ordinary autorange admission exists, richer journeys still rejected |
| 5 callout / arrow / rule styles | `test_callout_arrows_reach_static_exports`, `test_svg_and_raster_keep_connector_outside_axes_when_target_is_inside` | Remaining; style rejections still lack stable XYG prefixes |
| 6 rc weights / font families | `test_title_and_label_weight_rc_overrides_reach_every_renderer`: `XYG_SCENE_UNSUPPORTED_PUBLIC_TEXT`; `test_quoted_font_families_remain_well_formed_in_svg`: `XYG_STATIC_UNSUPPORTED_CUSTOM_FONT` | Remaining; original xfails retained |
| 7 figure legend surface | `test_legend_handles_labels_form_relabels_handles`, `test_legend_scatter_entry_renders_marker_glyph`, `test_legend_frameon_false_removes_frame_in_static_export` | Remaining; native output generated, expected legend content assertions fail |
| 8 shared layout | `test_rc_tick_padding_places_labels_by_the_matplotlib_rule`, `test_constrained_subplot_xlabels_stay_inside_static_canvas`, `test_cached_axes_aligns_with_same_position_overlay_in_static_exports` | Remaining; geometry and serialization assertions need separate evaluation; no thresholds changed |
| 9 raw errors | `test_null_locator_removes_ticks_from_the_export` now passes; `test_categorical_text_static_export_has_a_stable_reason` asserts `XYG_SCENE_UNSUPPORTED_ANNOTATION_COORDINATE` | Null formatter uses shared `tick_label_strategy=none`, locator keeps empty authored ticks. Categorical string native annotation ingress remains explicitly rejected; future rendering test stays xfailed |
| 10 dense composition | `tests/pyplot/test_frame_geometry.py::test_dense_grid_composite_draws_every_panel` | Passes unchanged (all 64 panels, coverage > 0.5 and opaque canvas); separate wide overlapping alpha-blend witness remains to be qualified |
| 11 rich polar | `tests/test_polar_charts.py` | 118 passed, 31 xfailed. Unmasked failures include `XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS`, old SVG dialect assertions, and missing `test_png_export` helper imports. Not complete |

`test_fill_betweenx_static_export_joins_dense_triangle_strip` and
`test_fill_betweenx_static_export_joins_each_disconnected_region` also pass
unchanged; their stale xfails are removed.

The Rust-owned #875 registry adds `line_hidden_tick_labels`: an authored-domain
line with x labels hidden and an empty authored y tick list, and
`scatter_hidden_tick_labels`: an autoranged scatter with the axes exchanged.
These retain the exact two-row, different-shape/axis pairwise requirement for
the new `hidden-tick-labels` and `empty-ticks` concerns. Python and Node
builders consume this row; `tests/test_static_export_cross_host.py` compares
canonical Scene, SVG, raster commands, PNG bytes, and decoded RGBA. All 34
registry tests pass. This row qualifies the shared representation used by the
NullFormatter repair; no Rust runtime policy or ABI changed.

## Additional validation

`make check-host-parity` passed: ownership/inventory/registry gates, ABI smoke
(673 checks), executable delegation corpus, adapter contracts, and 1089
cross-host tests. The focused annotation/chrome tests passed (16 tests).
`test_dense_grid_composite_draws_every_panel` passed in 1.08 seconds.
Raw failure inventories above were captured before edits. No timing claim,
render threshold relaxation, new xfail, runtime dependency, or fallback renderer
was introduced. Independent final review and merge-queue work belong to the
parent; no PR, push, issue comment, or closure was performed here.
