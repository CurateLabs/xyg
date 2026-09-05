# Native PDF text-style completion

The #875 exhaustive XYST corpus found that #873 title/label italic flags were
accepted by SVG and raster consumers but rejected by PDF: the closed SVG
converter did not admit `font-style`. The native converter now accepts
text-level `normal`, `italic`, and `oblique` only. Unknown styles, angled
oblique requests, and custom font-family resolution remain fail-closed.

Normal/default text keeps the existing Helvetica or Helvetica-Bold selection
and deterministic output. Italic/oblique text uses Helvetica-Oblique, or
Helvetica-BoldOblique for bold weight. Each selected face has its own cached
PDF font resource; text remains searchable vector text, not a raster or a
silently upright substitute. Existing CP1252 mapping, anchor calculation,
rotation, opacity, and regular/bold advance tables are unchanged. Oblique faces
use the advance widths of their corresponding upright face.

These names are part of the existing standard-font PDF mechanism described in
[Adobe PDF Reference 1.4 §5.5.1](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.4.pdf).
This change does not add general CSS or font embedding.

The same expanded corpus exposed a second converter bug: XML entity decoding
consumed one character too few and inserted a literal semicolon after escaped
text. The decoder now consumes the complete named/decimal/hex entity, including
its terminator, exactly once. Adjacent entities, non-ASCII neighbors, an actual
literal trailing semicolon, and escaped entity-looking text retain exact text.
Malformed and out-of-range entities remain rejected.

Evidence: `cargo test -p xyg-engine pdf::tests` checks all four font resources,
reuse, mixed-face anchor/rotation matrices, absence of image substitution,
exact XML entity decoding, and unsupported style rejection.
`tests/test_static_document_registry_cross_host.py` covers the originally
failing italic/bold document-title and document-label cases through both
generated host bindings and all five retained formats. The full PDF structural
suite remains `uv run pytest tests/test_pdf_export.py`.
