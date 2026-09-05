# Annotation-style cutover evidence

`uv run pytest tests/test_static_annotation_style_cross_host.py -q` passes
65 tests against rebuilt ABI 363. The query cases send explicitly framed XYAS
bytes through Python and Node bindings, compare exact XYAO bytes, and assert
independent expected batch defaults, typography flags, padding, patch values,
drop decisions, and errors. This is shared-query parity, not independent public
Node authoring. Empty byte buffers are rejected by the generic transport in
both hosts; nonempty malformed frames exercise native XYAS errors.

Two public Python composition exports observe the actual native query call and
require italic/bold SVG text for integer 700 and floating 700.0. Their axes
have explicit numeric domains to isolate annotation projection. A third public
journey rejects mixed default and authored font sizes. A host patch-application
witness preserves opaque unknown style data for downstream Scene validation,
preserves the original authoring object, and checks native alias removal,
paint canonicalization and rotation patches. Unknown-field preservation is not
an assertion that Scene admits those fields.

This focused corpus does not prove every pyplot journey, automatic Node
Figure-to-document normalization, legacy renderer deletion, or M2 completion.
