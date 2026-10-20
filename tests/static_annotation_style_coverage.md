# Annotation-style cutover evidence

`uv run pytest tests/test_static_annotation_style_cross_host.py -q` sends
explicitly framed XYAS v2 bytes through the Python and Node bindings, compares
exact XYAO v3 bytes, and asserts independent expected patches, drop decisions,
per-label table entries (size, flags, vertical alignment, one- and two-value
padding, #1006 explicit cell boxes in px and plot-rectangle percentages with
their unit bits), the Scene label order across annotation kinds, and errors
(one-sided, uncentered, and data-space percentage boxes). Empty byte
buffers are rejected by the generic transport in both hosts; nonempty malformed
frames exercise native XYAS errors.

Two public Python composition exports observe the actual native query call and
require italic/bold SVG text for integer 700 and floating 700.0. A third public
journey renders three annotations with different size, weight, style and color
in one panel (#1006). A host patch-application witness preserves opaque unknown
style data for downstream Scene validation, preserves the original authoring
object, and checks native alias removal, paint canonicalization and rotation
patches. Unknown-field preservation is not an assertion that Scene admits those
fields.

`tests/test_static_annotation_labels_cross_host.py` authors mixed-style,
box-padding and mixed-kind (text, rule, callout) charts through the public
Python composition API and the public Node `Figure` with independent literals and
requires byte-identical SVG/PNG/PDF/JPEG/WebP plus identical stable rejection
reasons for round box styles, three-value padding and custom fonts. Its
`table_cells` and `axes_fraction_text` cases are the #1006 table vocabulary
(Rust-projected axes-fraction anchors and Rust-laid-out cells), with
`one_sided_box`, `uncentered_box`, `percent_box_in_data_space`,
`figure_fraction_text` and `cell_off_canvas` failing identically in both hosts.

This focused corpus does not prove every pyplot journey or the retired renderer's
deletion. The Matplotlib 3.11 reference case 53 exports natively
(`tests/pyplot/test_table_static_export.py` pins its `ax.table` geometry); case
25 still stops at the arrow-head vocabulary gap; see
`spec/matplotlib/compat-changelog.md`.
