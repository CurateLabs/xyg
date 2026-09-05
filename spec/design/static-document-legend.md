# StaticDocument legend authoring query

M2 #873 moves document-legend defaults, mark-kind classification, CSS metrics,
paint resolution, alpha, and byte framing into Rust. This is distinct from
Scene's `XYLG` and the `XYLF` best-placement query. Hosts marshal authored facts
to `static_document_legend::resolve_packed` and copy its output into XYDD; they
must not select glyph kinds, apply style defaults, or retry a host renderer.

## XYDL v1 input

The 64-byte header is `<4s3IiI5d>`: magic `XYDL`, version 1, flags, item count,
signed ncols, reserved zero, then f64 handle length, handle text padding, border
padding, anchor x, and anchor y. Flags mark authored ncols=1, handle length=2,
handle text padding=4, border padding=8, and anchor=16. Inactive numeric fields
must contain all-zero bytes; unknown flags and nonzero reserved words fail.

Eleven optional UTF-8 strings follow in this order: title, loc, figure_loc,
fontSize, padding, rowGap, text color, background, borderColor, frame alpha,
and fontFamily. Each is prefixed by a u32 byte length; `0xffffffff` means
absent, distinct from an explicitly empty string. Text is NUL-free and bounded
to 4,096 bytes per field.

Each item has a 40-byte `<2I4d>` header: flags, reserved zero, width,
stroke_width, size, opacity. Presence bits are width=1, stroke_width=2, size=4,
opacity=8; bit 16 carries authored dash truth. Four optional strings follow:
kind, name, color, symbol. Inactive numeric bytes must be zero. There are at
most 256 items and 2 MiB of input. No JSON numeric arrays cross this boundary.

## Native policy and output

Absent defaults match the migrated adapter: one column, 11px font, handle
length 2, handle text padding 0.8, padding 0.4em, row gap 0.5em, zero border
padding, no anchor, `upper right` location, empty title/name, line kind,
`#4c78a8` item color, width 1.5, size 8, and opacity 1. Explicit width wins over
stroke_width. Nonpositive ncols becomes one; above 256 fails. Border padding
floors at zero. `figure_loc="outside right upper"` selects `upper right`.

CSS metric strings with the expected px/em suffix are parsed as numbers;
unparseable or wrong-unit strings retain the established defaults. Nonfinite
values reject. Font must remain positive and other metrics nonnegative after
the declared default/floor policy; narrowing to f32 must stay finite.
Nonnegative metric admission happens on raw
f64 before narrowing, so a tiny negative width cannot round to an admitted -0.
Anchors may be outside [0,1] but must be finite before and after f32 conversion.

Line, segments, step, stairs, errorbar, and stem use the line glyph; scatter
uses a circle; other admitted kinds use a fill swatch, matching the previous
adapter classification. A non-circle scatter symbol fails explicitly. The
query does not replace the public Scene mark admission predicate.

Colors resolve through the existing Rust literal CSS parser. Browser-only
colors and custom fonts fail with `XYG_STATIC_UNSUPPORTED_FIGURE_LEGEND_STYLE`.
Text defaults to `#262626`, background to `#808080`, and border to `#cccccc`.
Default frame alpha is 0.08 without an authored background and 1 otherwise.
Finite frame/item opacity clamps to [0,1]; nonfinite values fail. Frame alpha
uses f64 round-to-even on the RGBA8 alpha, resolving the former Python/Node
half-integer rounding divergence. Item opacity is retained as an f32 for the
shared renderer. No other dimensions silently clamp.

Output is the existing XYDD legend block: 64-byte `<4I6f12B2fB3x>` header,
title/location bytes, then 28-byte `<8B3f2I>` item records and name bytes.
It has no independent magic. Zero items produce empty output after validation.
Malformed inputs use stable `XYG_STATIC_DOCUMENT_LEGEND_*` reasons;
unrepresentable anchors use `XYG_STATIC_UNSUPPORTED_PANEL_LEGEND_ANCHOR`.

## Evidence

`cargo test -p xyg-engine static_document_legend` covers exact default bytes,
all glyph classes, CSS/alpha/location policy, numeric presence and precedence,
out-of-box anchors, clamping, every truncated prefix, inactive bytes, browser
paint/font rejection, and unsupported symbols. Host cutover must additionally
exercise this query through both generated ABI bindings and pin identical
decorations and native outputs; unit tests alone do not prove that cutover.
