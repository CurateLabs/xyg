# Native document-label authoring

M2 #873 removes figure-label style/placement defaults and admission policy
from Python/Node `_decorations` adapters. `static_document_labels::resolve_packed`
consumes raw optional XYDA facts and returns concatenated XYDD label records.
Hosts may frame the surrounding XYDD counts and append this returned byte
block; they do not normalize font families, select style flags, map alignments,
or apply numeric/color defaults.

## XYDA v1

Header: 16 bytes `<4s3I>`, magic `XYDA`, version 1, label count (0..64), and
reserved zero. Each label starts with 48 bytes `<2I5d>`: flags, reserved zero,
x, y, size, rotation, opacity. Presence bits are x=1/y=2/size=4/rotation=8/
opacity=16. Inactive numeric facts require exactly zero bytes. Unknown flags
and nonzero reserved bytes fail. All numeric input is raw little-endian f64.

Seven optional UTF-8 strings follow each numeric record: text, family, anchor,
vertical_align, font_style, weight, and color. Each has a u32 byte length;
`0xffffffff` is absent, distinct from an empty string. Each string is NUL-free
and at most 4,096 bytes. Total input is at most 2 MiB; trailing bytes fail.

## Policy

Defaults retain the migrated label behavior: x=y=0.5, size=12, rotation=0,
opacity=1, empty text, system-ui/sans-serif family, middle anchor, center
vertical alignment, normal style/weight, and `#262626` paint. Coordinates and
rotation may be outside ordinary canvas/unit intervals but must remain finite
when narrowed to output f32. Raw f64 size must be in [1,4096], opacity in [0,1]; neither
silently clamps. Nonfinite inputs and f32 overflow fail.
Range admission runs before narrowing: a slightly out-of-range f64 value must
not become valid merely because f32 rounding collapses it to an endpoint.

Native family normalization lowercases and removes ASCII spaces; only
system-ui,sans-serif, dejavusans, and sans-serif pass. Anchors start/middle/end
map to 0/1/2; vertical top/baseline/bottom/center map to 0/1/2/3, with
center_baseline an alias of center. Alignment names remain case-sensitive.
Style/weight names are case-insensitive: normal is upright; italic/oblique set
bit 1. Normal/regular/book/400 have normal weight; bold/semibold/demibold/heavy/
black/600/700/800/900 set bit 2. Other values fail. Colors use the same Rust
literal CSS parser as the Scene; browser-only paints do not silently fall back.

Each output label has the existing 40-byte `<5f4B4B3I>` XYDD record followed by
its UTF-8 text: x/y/size/rotation/opacity, RGBA8, anchor/vertical/style-flags/
reserved, text byte length, and two reserved words. Empty label arrays return
empty output. Stable framing errors use `XYG_STATIC_DOCUMENT_LABELS_*`; style,
font, color, and numeric admission errors use
`XYG_STATIC_UNSUPPORTED_FIGURE_LABEL_STYLE`.

## Verification

`cargo test -p xyg-engine static_document_labels` pins exact defaults/empty
output, every alignment and weight alias, literal RGBA and UTF-8, out-of-canvas
placement/rotation preservation, nonfinite/narrowing rejection, invalid styles,
all truncated prefixes, unknown flags, reserved/inactive bytes, size/count/text/
total limits, malformed UTF-8/NUL and trailing bytes. The host delegation
cutover must additionally run the shared XYST registry label cases in every
format and query-level cross-host/error tests; unit coverage is not that proof.
