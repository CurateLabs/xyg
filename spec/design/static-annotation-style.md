# Native static annotation-style projection

M2 #873 moved the annotation normalization loop in `figure_document` into
`static_annotation_style::resolve_packed` (dossier §21/§28); #1006 made its
typography and box facts **per label** instead of panel-wide. This is a bounded
authoring query, not a second annotation renderer or Scene admission table.
The original annotation and unknown style entries remain host-owned authoring
objects. Hosts apply native remove/set patches, remove rows marked dropped,
and forward the resolved **label table** into XYST (see
[static-document.md](static-document.md) §1.1). Scene remains the authority for
geometry, arbitrary unknown keys, and kind-specific admission.

## XYAS v2 input

The 16-byte header is `<4s3I>`: `XYAS`, version 2, annotation count (0..128),
reserved zero (version 1 is rejected with `..._ANNOTATION_STYLE_VERSION`). Each
row starts with `<2I>` style-entry count (0..64) and **row flags**, then optional
text and optional kind strings. Row flags are host observations that decide
which Scene label the row yields: bit 0 = `wrap` authored (text/callout), bit 1 =
any of `dx`/`dy`/`anchor`/`rotation` authored; other bits fail with
`..._ANNOTATION_STYLE_FLAGS`. A string is u32 byte length followed by UTF-8;
`0xffffffff` means absent. Strings are NUL-free, at most 4096 bytes, and the
complete input is at most 2 MiB.

Each style entry contains a required key string, u32 type, and payload:

| Type | Value | Payload |
| ---: | --- | --- |
| 0 | null | none |
| 1 | string | required length-prefixed UTF-8 |
| 2 | number | little-endian raw f64 |
| 3 | boolean | u32 0 or 1 |
| 4 | opaque object/array | none; original value stays in host object |

Duplicate keys, unknown types, nonzero reserved words, malformed strings,
truncation, and trailing bytes fail. Unknown style keys are not normalized;
their original values still pass to the canonical Scene predicate. Numeric
nonfinite values are rejected when consumed by this query, not silently
discarded from unrelated original style entries.

## Preserved normalization and defaults

Rust classifies the literal kind. Text rows with absent/empty text are dropped
before semantic style validation (their framing is still validated).

- `math_italic_ranges` is admitted only when absent/null, empty string, false,
  or numeric zero. Other values reject with the existing mathtext reason.
- `font_family` wins over `fontFamily`, including explicit null. Both keys are
  removed. Admitted values remain exactly null, empty string,
  `system-ui,sans-serif`, `DejaVu Sans`, and `sans-serif`; there is no new custom
  font support or case normalization of this legacy annotation-family seam.
- The same snake-case precedence applies to font style, weight, and size.
  Absent/null/empty/false/zero style or weight selects `normal`. Style and
  weight names are case-insensitive but not whitespace-trimmed. Normal,
  italic, and oblique are admitted; weight aliases match the XYDA label query.
  Numeric weights 400/600/700/800/900 are also admitted. This preserves legacy
  Python integer weights and deliberately admits equivalent f64 values across
  hosts, removing the old incidental `str(700)` versus `str(700.0)` distinction.
  Other nonzero numeric weights reject, including fractional and nonfinite values.
  Family/style/weight are validated for all retained annotation kinds.
- Every row that yields a label (a retained text row, or a labelled
  callout/rule/band/marker) contributes its own **effective** font size
  (default 12), text flags (default upright/normal), and vertical alignment
  (default baseline). Size must be finite in [1,1000] before f32 narrowing. Rows
  with no label (arrows, unlabelled rules, unknown kinds) contribute nothing and
  their size key is removed without interpretation.
- Text `label_color` overrides `color`. Rust validates literal paint with the
  existing CSS parser and returns canonical `#rrggbbaa`; no CSS parser is copied.
- `vertical_align` is removed from every row. Labelled rows accept baseline=0,
  top=1, bottom=2, center/center_baseline=3.
- Non-null `rotation` is numerically coerced and normalized modulo 360 into
  [0,360), with canonical positive zero. Nonfinite rotation fails. Actual
  kind-specific rotation support remains Scene policy.
- Non-null `background` becomes `label_background`. Border syntax remains
  `<number>px solid <literal CSS color>` and becomes positive finite
  `label_border_width` plus `label_border_color`. Border width must survive
  f32 narrowing. The three CSS-like authoring keys are removed.
- **Box padding** is the CSS shorthand `<v>px` (all sides) or `<v>px <h>px`
  (vertical, horizontal), each finite in [0,1000]; three or more values fail
  with `..._ANNOTATION_BBOX`. The label records `(horizontal, vertical)`. A
  boxed label with omitted padding records the historical 3px default; this
  includes canonical `label_background`. Unboxed labels without authored padding
  record none. A label that requests padding but has no box is rejected
  downstream by the Scene consumer.
- **Explicit label box (#1006, Matplotlib table cells).** `box_width` and
  `box_height` replace the text-sized box with an exact rectangle. Rust strips
  both keys (static-only facts; the raw canonical Scene path has no box
  vocabulary and rejects them like any unknown key). They are admitted only
  together (a null pair is "no box"), only on a `text` row that has a box
  (`background` or `label_background`), is upright (rotation absent or
  normalizing to 0), and is vertically centered (`vertical_align`
  center/center_baseline). Each side is a px **number** in (0,16384], or — only
  on text whose `coordinate_space` is `"axes_fraction"`, whose containing block
  is the panel plot rectangle — a CSS-style **`"<n>%"`** string: a fraction
  (0,16] of the plot width (`box_width`) or plot height (`box_height`). A
  cell's padding may give its horizontal component as a percentage of the plot
  width in the two-value form `<v>px <n>%` (the vertical component stays px and
  is unused by a cell); a percentage anywhere else, a one-sided box, a string
  px side (`"40px"`), any other kind, or an ineligible row fails with
  `XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX`. Percentages are resolved by Rust
  against the **final** plot rectangle when the entry is applied, so a host
  never needs (or sees) the post-layout plot size.
- **Axes-fraction anchors.** A `text` row whose `coordinate_space` is exactly
  `"axes_fraction"` takes an XYAW label slot (the bulk XYAF pack routes it
  there, [scene-ir.md](scene-ir.md) "ABI 390 axes-fraction text anchors");
  `coordinate_space` itself is canonical Scene vocabulary and is not stripped.
- **Box style.** `border_radius` is the Matplotlib `boxstyle="round*"` fact.
  The Scene label box is a rectangle (the Scene label wire has no corner
  radius), so a non-zero radius fails with
  `XYG_STATIC_UNSUPPORTED_ANNOTATION_BOXSTYLE`; a zero/absent radius is the
  `square` boxstyle and is stripped. Rounded boxes are never drawn square
  silently.

There is no panel-wide uniformity rule: different labels in one panel carry
different sizes, weights, styles, alignments, colors, and boxes
(`XYG_STATIC_UNSUPPORTED_HETEROGENEOUS_ANNOTATION_STYLE` is retired). No
annotation sampling or per-row typography fallback is permitted.

## XYAO v3 output

Version 3 (#1006) appended the explicit label box to each label-table entry;
hosts reject any other version. The 16-byte header is `<4s3I>`: `XYAO`,
version 3, original input count, **label
count** (the number of *annotation* labels in the compiled Scene's label
section). Then, for each input
row, u32 drop (0/1), u32 patch count, then patches: required key string, u32
operation (remove=0, set-string=1, set-f64=2), followed by the corresponding
value payload. Numeric patches are raw f64. Dropped rows have no patches. Patch
ordering is deterministic.

The remainder is the **label table**: `label count` entries of
`LABEL_ENTRY_BYTES = 28` (`<I3f3Bx2f>`): present bits (1 = typography, 2 =
padding, 4 = explicit box), f32 font size, f32 horizontal padding, f32 vertical
padding, u8 italic(1)/bold(2) flags, u8 vertical alignment, u8 **unit bits**
(1 = box width is a plot-width fraction, 2 = box height is a plot-height
fraction, 4 = horizontal padding is a plot-width fraction), one reserved zero
byte, f32 box width, f32 box height. Absent facts (and the unit byte without a
box) are canonical zero; a box requires typography with center alignment and
padding, and positive sides bounded by 16384 px or a 16 (1600%) fraction.
Entries are in the order of the Scene's annotation labels, which
`scene_annotations::label_slots` owns (it reuses the XYAF dispatch plan, so a
host never repeats the routing): unwrapped text (XYAT), attached rule/band/marker
labels (XYAL), wrapped text and laid-out marker labels (XYAW), then callouts
(XYAC) and wrapped callouts (XYAW). Hosts copy the table verbatim into the
XYST panel record. Rust applies entry *i* to the *i*-th annotation label
(`SceneDocument::apply_static_annotation_labels`), identifying annotation labels
by an explicit **provenance flag** carried in the Scene wire (`SceneLabel::annotation`,
XYLB v7: the v6 record plus a `u32` flags word, bit 0 = annotation label, and a
zero reserved word; unknown bits fail), never by raw position or by an id
pattern alone — literal source ids are arbitrary, so an ordinary chart/graph/geo
label (or the id of literal-tagged `0x80` geometry) may carry exactly the ids
annotation labels get. Annotation decoration (XYAT/XYAL/XYAW/XYAC) sets the flag.
It is serialized (v7) only where it disagrees with the reserved-id pattern, so
Scenes without a collision keep their prior bytes; the browser painter's label
table carries only the id-implied flag and stays at its client-readable versions. Non-annotation labels — a composed graph's own labels,
chrome — keep their canonical typography, so a Scene that carries both (the
composed-graph annotation shape of #922: graph labels first, annotation labels
appended) takes a table of annotation entries only. Panel flag 3 requires exact
coverage: one entry per annotation label, and an explicitly empty table over a
Scene that has annotation labels is rejected like any other length mismatch.

**Applying an explicit box** (after the font size; the measured box is not
re-measured): Rust first resolves fractions against the finalized plot
rectangle (`width·(right − left)`, `height·(bottom − top)`, inset
`pad_x·(right − left)`), then places the box against the label anchor — the
text keeps the horizontal inset from the edge it is anchored to (start:
`x − inset`; end: `x − width + inset`; middle: centered) and the box is centered
on the measured text block, so the center alignment that follows centers both
on the anchor. The inset must lie in [0, width] and the label must be upright
(malformed facts fail with `XYG_STATIC_DOCUMENT_PANEL`). Two geometric rules
are stable unsupported-authoring rejections,
`XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX` (`StaticDocumentError::AnnotationCell`):
the text must fit its cell in Rust text metrics (`textblock::measure` width at
the label's final size ≤ `width − inset` for a start/end anchor, ≤ `width` for
a centered one — Matplotlib's `auto_set_font_size` would shrink such text
instead; xyg never draws past the cell edge), and the placed box must lie
inside the panel viewport (sub-pixel slack only) rather than being clipped or
moved.

Existing product failures retain the mathtext/custom-font/annotation-typography/
vertical-align/bbox reasons and add `XYG_STATIC_UNSUPPORTED_ANNOTATION_BOXSTYLE`.
Invalid consumed rotation or text paint uses
`XYG_STATIC_UNSUPPORTED_ANNOTATION_STYLE`. Framing failures use
`XYG_STATIC_ANNOTATION_STYLE_HEADER`, `VERSION`, `FLAGS`, `LIMIT`, or `TEXT`.
Output is atomic: no bytes are returned on any row's error.

## Evidence

`cargo test -p xyg-engine static_annotation_style` covers exact empty/default
headers and patches, aliases and explicit-null precedence, every supported
typography/alignment family, per-label heterogeneity (size, style, weight,
alignment, one- and two-value padding), the Scene label order across every
annotation kind, CSS paint/box projection, the round-boxstyle rejection,
negative/full-turn rotation, malformed framing, all truncated prefixes,
resource limits, nonfinite numbers, and pre-narrowing bounds; `explicit_label_box_*`,
`axes_fraction_cells_carry_plot_relative_units` and
`axes_fraction_text_takes_an_xyaw_slot` pin the #1006 box/unit facts and slot
routing. `cargo test -p xyg-engine static_` adds the XYST label-table decoder
(including box/unit rejection) and the Scene per-label application
(`static_annotation_labels_*`, `static_annotation_label_cells_*`).

`tests/test_static_annotation_style_cross_host.py` and its Node companion
`packages/xy-node/scripts/static_annotation_style_cross_host.mjs` send raw
query bytes through both bindings and compare exact XYAO bytes, independent
expected label-table facts, and exact errors.
`tests/test_static_annotation_labels_cross_host.py` with
`packages/xy-node/scripts/static_annotation_labels_cross_host.mjs` authors the
same mixed-style, box-padding and mixed-kind charts through the public Python
composition API and the public Node `Figure`, requiring byte-identical
SVG/PNG/PDF/JPEG/WebP and identical stable rejection reasons; its
`table_cells`/`axes_fraction_text` cases and the box/coordinate failures are the
#1006 table vocabulary (Rust lays out percentage cells against the final plot
rectangle on both hosts). `tests/pyplot/test_corpus_annotations_1006.py` covers
the Matplotlib 3.11 corpus cases 25 and 53 annotation surface through pyplot,
and `tests/pyplot/test_table_static_export.py` pins `ax.table` cell
rectangles against Matplotlib 3.11. `tests/test_annotation_cells_browser.py`
(headless Chromium) pins the browser half: the fixed px/percentage box, forced
vertical centering, the border-inclusive padding inset, drawing axes-fraction
text outside the plot while figure-fraction text there stays culled, and DOM
cell rectangles equal to the Rust static cells within 0.05 px.
