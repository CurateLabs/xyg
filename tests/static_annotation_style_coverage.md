# Annotation-style cutover evidence

`uv run pytest tests/test_static_annotation_style_cross_host.py -q` sends
explicitly framed XYAS v2 bytes through the Python and Node bindings, compares
exact XYAO v2 bytes, and asserts independent expected patches, drop decisions,
per-label table entries (size, flags, vertical alignment, one- and two-value
padding), the Scene label order across annotation kinds, and errors. Empty byte
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
reasons for round box styles, three-value padding and custom fonts.

This focused corpus does not prove every pyplot journey or the retired renderer's
deletion. The Matplotlib 3.11 reference cases 25 and 53 clear the annotation-style
gate but still stop at separate Scene gaps (arrow head vocabulary, `axes_fraction`
table cells, zero-point `bxp` fliers); see `spec/matplotlib/compat-changelog.md`.
