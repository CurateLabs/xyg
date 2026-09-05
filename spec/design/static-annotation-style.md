# Native static annotation-style projection

M2 #873 moves the annotation normalization loop in `figure_document` into
`static_annotation_style::resolve_packed` (dossier §21/§28). This is a bounded
authoring query, not a second annotation renderer or Scene admission table.
The original annotation and unknown style entries remain host-owned authoring
objects. Hosts apply native remove/set patches, remove rows marked dropped,
and forward the four resolved panel-wide facts into XYST. Scene remains the
authority for geometry, arbitrary unknown keys, and kind-specific admission.

## XYAS v1 input

The 16-byte header is `<4s3I>`: `XYAS`, version 1, annotation count (0..128),
reserved zero. Each row starts with `<2I>` style-entry count (0..64), reserved
zero, then optional text and optional kind strings. A string is u32 byte
length followed by UTF-8; `0xffffffff` means absent. Strings are NUL-free,
at most 4096 bytes, and the complete input is at most 2 MiB.

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
- Every text row contributes its **effective** font size (default 12), text
  flags (default upright/normal), and vertical alignment (default baseline).
  Size must be finite in [1,1000] before f32 narrowing. Other kinds do not
  contribute typography facts; their size key is removed without interpretation.
- Text `label_color` overrides `color`. Rust validates literal paint with the
  existing CSS parser and returns canonical `#rrggbbaa`; no CSS parser is copied.
- `vertical_align` is removed from every row. Text accepts baseline=0, top=1,
  bottom=2, center/center_baseline=3; other kinds ignore that authoring key.
- Non-null `rotation` is numerically coerced and normalized modulo 360 into
  [0,360), with canonical positive zero. Nonfinite rotation fails. Actual
  kind-specific rotation support remains Scene policy.
- Non-null `background` becomes `label_background`. Border syntax remains
  `<number>px solid <literal CSS color>` and becomes positive finite
  `label_border_width` plus `label_border_color`. Border width must survive
  f32 narrowing. Padding syntax remains `<number>px`, finite in [0,1000].
  The three CSS-like authoring keys are removed.
- Explicit padding contributes a panel padding fact. A boxed annotation with
  omitted padding contributes the historical 3px default. This includes
  canonical `label_background`, preventing an omitted default on one box from
  being silently overwritten by another box's authored padding. Unboxed rows
  without authored padding contribute no padding. Whether a background exists
  for applying a requested padding remains the downstream Scene check.

The four batches are compared in f64/integer space before output narrowing.
Different effective sizes, text flags, vertical alignments, or participating
padding values fail with
`XYG_STATIC_UNSUPPORTED_HETEROGENEOUS_ANNOTATION_STYLE`. No annotation sampling
or per-row typography fallback is permitted.

## XYAO v1 output

The 32-byte header is `<4s3I2f2I>`: `XYAO`, version 1, original input count,
batch presence mask (font size=1, text flags=2, padding=4, vertical align=8),
f32 font size, f32 padding, u32 text flags, u32 vertical alignment. Inactive
facts are canonical zero. Each input row has u32 drop (0/1), u32 patch count,
then patches: required key string, u32 operation (remove=0, set-string=1,
set-f64=2), followed by the corresponding value payload. Numeric patches are
raw f64. Dropped rows have no patches. Patch ordering is deterministic.

Existing product failures retain the mathtext/custom-font/annotation-typography/
vertical-align/bbox/heterogeneity reasons. Invalid consumed rotation or text
paint uses `XYG_STATIC_UNSUPPORTED_ANNOTATION_STYLE`. Framing failures use
`XYG_STATIC_ANNOTATION_STYLE_HEADER`, `VERSION`, `FLAGS`, `LIMIT`, or `TEXT`.
Output is atomic: no bytes are returned on any row's error.

## Evidence

`cargo test -p xyg-engine static_annotation_style` covers exact empty/default
headers and patches, aliases and explicit-null precedence, every supported
typography/alignment family, effective-default heterogeneity, CSS paint/box
projection, negative/full-turn rotation, malformed framing, all truncated
prefixes, resource limits, nonfinite numbers, and pre-narrowing bounds.
Host integration must additionally observe actual query calls and compare
public document output; module tests alone do not establish host cutover.

`tests/test_static_annotation_style_cross_host.py` and its Node companion
`packages/xy-node/scripts/static_annotation_style_cross_host.mjs` prepare raw
query byte-equality checks, independent expected header/patch facts, and exact
error comparisons. Execution awaits consistent host bindings; this raw query
corpus does not by itself establish public authoring parity. Public delegation
requires a separate observed host-query witness.
