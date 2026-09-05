# StaticDocument layout query

M2 #873 moves native pyplot panel placement and suptitle reservation into
`xyg-engine::static_document_layout::resolve_packed`. The host packs authored
facts and reads the result; it does not calculate grid maxima, fractional
placement, title metrics, rounding, or baseline clamps. Text measurement uses
the embedded face and newline rules from design dossier §21 and `textblock`.

All numbers below are little-endian. Canonical authoring coordinates remain
f64. This query is native document layout, not a browser paint payload.

## XYSL v1 input

The 64-byte header is followed by exactly `panel_count` 40-byte records and
then `title_bytes` NUL-free UTF-8 bytes, with no padding or trailing data.

| Offset | Type | Field |
| --- | --- | --- |
| 0 | 4 bytes | `XYSL` |
| 4 | u32 | version = 1 |
| 8 | u32 | mode: 0 row-major grid, 1 normalized placement, 2 facets |
| 12, 16 | u32 | grid rows, columns; both zero in mode 1; rows zero in mode 2 |
| 20 | u32 | panel count, 1..256 |
| 24, 28 | u32 | canvas width, height; both zero in mode 0; grid width and panel height in mode 2 |
| 32 | u32 | bit 0: reserve shared colorbar band in grid mode; other bits zero |
| 36 | u32 | title byte length, at most 4096 |
| 40 | f64 | title size, finite and in (0, 65535] |
| 48, 56 | f64 | title x/y fractions, finite; defaults 0.5 and 0.98 |

Each panel record contains width/height u32 at offsets 0/4, then authored
left/bottom/width/height fractions as four f64 at offsets 8/16/24/32.
Grid mode requires all fraction bytes to be zero. Normalized mode requires
finite fractions and positive fraction width/height. Panel sizes are the
compiled Scene viewport sizes, which can include chrome outside the authored
axes rectangle. The fraction width is validated as part of that rectangle;
pixel width comes from the compiled Scene rather than being recomputed.

Grid rows equal `ceil(panel_count / columns)` and columns cannot exceed panel
count. Rust takes each column's largest panel width and each row's largest
panel height. It reserves round-to-even(measured title height + 12) pixels
above the grid for a nonempty title and 52 pixels below for a shared colorbar.
This deliberately unifies all output formats on the former SVG title band.
The retired PNG stitcher reserved measured title height + 16 instead, so
titled regular-grid PNG documents are four pixels shorter than that legacy
path; panel sizes and inter-panel placement relative to the title band are
unchanged. This is a recorded compatibility change, not legacy PNG geometry
identity. Normalized placement and untitled grids are unaffected.
Normalized placement uses round-to-even(left × canvas width) and
round-to-even((1 − bottom − fraction height) × canvas height). Signed
coordinates preserve chrome overhang; every panel must intersect the canvas.

Dimensions are in 1..65535; signed resolved coordinates have magnitude at
most 65535. Title x is the authored fraction times resolved document width.
The first baseline is `(1 − title_y) × document_height + ascent`, clamped so
the complete title block fits its reserved band (or the canvas for normalized
placement). The lower clamp is the ascent. The upper clamp is the larger of
the ascent and `band − trailing_line_steps − descent − 2`.

Facet mode carries the authored column count, total grid width, uniform panel
height, and gap before Scene compilation. Every panel record has zero width
and height; its first f64 is the same nonnegative integral gap (at most 65535)
and its other three f64 fields have all-zero bytes. Flags and rows are zero;
columns are 1..256. Rust computes the row count and panel width as
`max(120, floor((grid_width − (columns − 1) × gap) / columns))`, preserving
unused right-edge remainder pixels and the established minimum width.
The document height is `rows × panel_height + (rows − 1) × gap`, plus a
24-pixel title strip for a nonempty title. Panel offsets are
`column × (panel_width + gap)` and `title_strip + row × (panel_height + gap)`.
Each panel must intersect the document, including when the width floor makes
the final panel extend beyond the right edge. A wholly invisible panel is
rejected. Facet titles retain their fixed 16-pixel first baseline and centered
x position. Mode 2 requires title size/x/y facts to be their established
defaults 16/0.5/0.98 so alternate authoring cannot be silently ignored.

## XYLO v1 output

The 48-byte header is followed by one signed i32 x/y pair per input panel
in modes 0/1. Mode 2 appends the computed u32 width/height to each pair,
giving 16-byte records. Hosts use these dimensions to compile the panel Scenes
and marshal the same returned offsets into XYST.

| Offset | Type | Field |
| --- | --- | --- |
| 0 | 4 bytes | `XYLO` |
| 4 | u32 | version = 1 |
| 8, 12 | u32 | document width, height |
| 16 | u32 | panel count |
| 20 | u32 | reserved title height (zero in normalized mode) |
| 24, 32 | f64 | title x and first baseline |
| 40 | f64 | title band height |

Errors use `XYG_STATIC_LAYOUT_HEADER`, `VERSION`, `FLAGS`, `LIMIT`, `PANEL`,
or `TITLE` suffixes under the same prefix. Inactive mode facts, nonfinite
coordinates, invalid strings, size overflow, truncated inputs, and trailing
bytes fail closed. Reproduce the deterministic grid, normalized placement,
facet remainder/minimum-width layout, multiline title, bounds, and malformed-input tests with
`cargo test -p xyg-engine static_document_layout`.
