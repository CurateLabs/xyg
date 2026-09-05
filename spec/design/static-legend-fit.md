# Static pyplot best-legend query

M2 #873 moves pyplot's measured `loc="best"` footprint and occupancy policy
to `xyg-engine::static_legend_fit::resolve_packed`. This preserves the pyplot
contract, not composition's approximate mean-occupancy heuristic. Text metrics
come from the shared `legend_layout` kernel and dossier §21; sampling is an
explicit §28 policy below. Hosts obtain plot geometry from Rust Scene layout,
pack literal authoring facts and source columns, and consume the returned
decision. They do not call the retired Python `_svg` layout/legend modules.

## XYLF v1 input

The header is 144 bytes (`<4s11I12d>`). Every numeric field is little-endian.
The request is bounded to 64 MiB, 4096 names, 4096 entries, and 4096 bytes per
NUL-free UTF-8 string. Oversized requests fail explicitly; no host-side
downsampling is permitted to fit the envelope.

| Offset | Type | Field |
| --- | --- | --- |
| 0 | bytes4 | `XYLF` |
| 4 | u32 | version 1 |
| 8 | u32 | flags: reverse x=1, reverse y=2, authored handle length=4, text pad=8, height=16 |
| 12, 16 | u32 | name count, entry count |
| 20 | u32 | authored column count, 0..4096 (zero resolves to one) |
| 24, 28, 32, 36 | u32 | title, font-size CSS, padding CSS, row-gap CSS byte lengths |
| 40, 44 | u32 | reserved zero |
| 48, 56, 64, 72 | f64 | Rust-resolved plot x, y, width, height |
| 80, 88, 96, 104 | f64 | displayed x low/high, y low/high domains |
| 112, 120, 128, 136 | f64 | handle length, handle-text pad, handle height, border-axes pad |

All header numbers are finite. Plot dimensions are positive; plot and handle
facts have magnitude at most 65535. Inactive handle fields have all-zero bytes.
Negative border padding clamps to zero. Domains may arrive reversed; Rust
sorts each pair, then applies the independent authored reverse flags. Equal
domains produce the historical first-candidate fallback after full validation.

The body contains the four header-length strings in order, then each name as
u32 byte length followed by its text. Font-size CSS ending in `px` resolves to
at least 1 pixel, otherwise the established default is 11; padding/row-gap
CSS ending in `em` resolve to at least zero, otherwise defaults are 0.4/0.5.
Numeric CSS values must be finite; malformed values retain those established
defaults. Resolved values above 65535 fail. Empty title means no title; an empty
name list measures one empty entry as the old pyplot legend-footprint path did.

Each entry has a 24-byte header (`<6I>`): kind, x count, y count, base count,
width count, reserved zero. It is followed by those four raw f64 columns in
order. NaN/infinity in source columns are allowed and handled as missing data
in Rust; they never reach a painter through this query.

| Kind | Authored columns | Rust expansion/scoring |
| --- | --- | --- |
| 0 path | x/y | vertex and connected-segment scores |
| 1 scatter | x/y | vertex scores only |
| 2 vertical bar | x categories, y values, optional base/width | rectangle overlap |
| 3 horizontal bar | x categories, y values, optional base/width | swapped rectangle overlap |
| 4 stairs | x edges (one more than y), y values | repeated edge/value path |
| 5 ECDF | x observations, other columns empty | finite sort, initial zero plus cumulative path |
| 6 area | x/y top edge, optional base, width empty | top edge, reversed baseline, closing vertex |

Path/scatter/area/bar x/y support equal lengths or scalar broadcasting.
Base/width may be empty (defaults zero/0.8), scalar, or the broadcast row count.
Unused columns must be empty. Unknown kinds and incompatible column shapes
fail with `XYG_STATIC_UNSUPPORTED_LEGEND_FOOTPRINT`; they are never silently
ignored. Hosts may perform unit/category coercion, but normalization, bar/path
expansion, sampling, finite handling, and scoring remain native policy.

## Geometry and score policy

The shared legend box kernel measures labels/title/columns with the supplied
style, dropping unresolved location/anchor for footprint measurement. Nine
candidates follow pyplot order: upper right, upper left, lower left, lower
right, right, center left, lower center, upper center, center. `right` has the
same anchor as `center right`; only its first Matplotlib code position is used.

Border-axes padding insets each candidate's normalized container. Remaining
travel is `max(0, 1 - 2 * inset - box_fraction)` on each axis. Source coordinates
normalize linearly against displayed domains, as on the former pyplot path;
off-plot points remain outside rather than being clamped to the border.

Paths sample at most 512 vertices and scatter at most 4096 offsets, using
NumPy's nonnegative integer-linspace floor rule with the final index exact.
A stride sample with no finite source pair falls back to all points so sparse
finite data cannot disappear. Counts use strict box containment and weight
each sample by expanded source length / sample length. Each non-scatter path
adds one additional point for touching/crossing the candidate, including
edge-only crossings. NaN gaps retained in the sampled path are not bridged.
As in the former pyplot policy, a source gap omitted by downsampling can be
bridged by the sampled path; the sample is an occupancy approximation, not a
gap-preserving rendering polyline. In particular, a 1023-vertex path whose odd
vertices are NaN samples its 512 finite even vertices and may score a crossing
that the unsampled path does not have. This historical approximation is pinned
explicitly, not silently changed by the migration. Bars count strict rectangle
overlaps without vertex sampling. ECDF and area/stairs expansion precedes the
sample rule. The first score within `best * (1 + 1e-9)` wins; no scorable
entries return the first candidate. This deliberately does not use the
composition heuristic's 0.02 tie band or estimated label-length footprint.

## XYLR v1 output and evidence

The result is 184 bytes (`<4s3I21d>`): `XYLR`, version 1, chosen candidate
index 0..8, number of scorable entries; then 21 f64 values:

1. Input Rust plot x/y/width/height.
2. Measured legend width/height and normalized border pad x/y.
3. Nine candidate scores in order.
4. Chosen scoring rectangle x/y/width/height in top-left viewport coordinates.

The last rectangle is the scored candidate witness, not an independent second
layout implementation. All returned values are finite. Malformed requests use
`XYG_STATIC_LEGEND_HEADER`, `VERSION`, `FLAGS`, `LIMIT`, `TEXT`, or `FACTS` under
that prefix; unsupported footprint errors retain their stable reason through
both host wrappers. No trailing bytes are accepted.

Run `cargo test -p xyg-engine static_legend_fit` for parser, measured footprint,
path crossing/gap, bar overlap, expanded path, reverse, and fallback tests.
Run `uv run pytest tests/test_static_legend_fit_cross_host.py` after rebuilding
the release core for Python/Node byte parity, a separate NumPy/Liang–Barsky
score oracle, all seven footprint kinds, sparse-sample fallback, and malformed
input rejection at both host boundaries.
The public runtime ownership corpus additionally exercises fixed and automatic
pyplot legends for SVG and PNG while rejecting legacy Python renderer calls.
