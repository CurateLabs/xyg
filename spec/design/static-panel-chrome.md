# Static panel chrome query

M2 #873 moves pyplot's panel gutter and outside-padding policy into
`xyg-engine::static_panel_chrome::resolve_packed`. Text uses the embedded
metrics and newline contract from design dossier §21. Existing Rust
`compat_layout`, `layout_rooms`, and `textblock` functions remain the shared
primitives. Hosts pack authored facts, invoke the query, and copy results.

## XYPC v1 input

The fixed header is 200 bytes. All integers and f64 values are little-endian;
authoring facts never pass as JSON number arrays. The entire input is at most
1 MiB. Each text is NUL-free UTF-8 and at most 4096 bytes; each tick-label
plane has at most 4096 labels, and there are at most three title slots.

| Offset | Type | Field |
| --- | --- | --- |
| 0 | 4 bytes | `XYPC` |
| 4 | u32 | version = 1 |
| 8 | u32 | flags described below |
| 12 | u32 | figure rows, 0..256; zero for unattached axes |
| 16, 20 | u32 | x/y tick-label counts |
| 24 | u32 | title-slot count |
| 28, 32 | u32 | x/y axis-title byte lengths |
| 36 | u32 | unsupported facts: 0 none, 1 browser CSS, 2 custom font |
| 40 | u32 | y tick direction: 0 out, 1 in, 2 inout |
| 44 | u32 | colorbar: 0 none, 1 axes-horizontal, 2 axes-vertical, 3 figure-horizontal, 4 figure-vertical |
| 48 | u32 | colorbar flags: bit 0 has label, bit 1 authored zero pad |
| 52 | u32 | compact hint: 0 derive from plot width, 1 compact, 2 regular |
| 56 | 8 bytes | reserved, all zero |
| 64, 72 | f64 | plot width, figure canvas height |
| 80, 88 | f64 | DPI, table bottom reservation in points |
| 96, 104, 112 | f64 | x tick size, x tick angle, x title size |
| 120, 128, 136 | f64 | y tick size, y tick angle, y title size |
| 144, 152, 160 | f64 | y tick length, y tick padding, authored y title offset |
| 168, 176, 184, 192 | f64 | optional Rust-measured left/top/right/bottom gutters |

Flags: bit 0 y tick labels visible; bit 1 primary x axis at top; bit 2 a twin
or right-side secondary y axis exists; bit 3 y title offset is authored; bit 4
measured gutters are present. All other bits are rejected. The y title offset
and measured-gutter bytes must be all zero when their flags are absent.
Colorbar flags must be zero when no colorbar exists. A compact hint can carry
an already resolved compact/regular choice from a native layout consumer;
zero delegates the pyplot threshold `plot_width + 54 < 520` to Rust.

Every numeric fact must be finite with magnitude at most 65535. Plot width
and DPI are positive, canvas height and table reservation are nonnegative,
and measured gutters are nonnegative. Rows and canvas height are either both
zero (unattached) or both positive. Negative tick length/padding clamp to
zero, and negative text size measures at zero, matching the existing shared
measurement contract.

After the header, pack x axis-title bytes, y axis-title bytes, then the x
tick-label plane and y tick-label plane. Each tick label is a u32 byte length
followed by its text. Each title slot follows as a 32-byte record: f64 size,
f64 pad, f64 y fraction, u32 automatic-y flag (0 or 1), and u32 text byte
length; then its text. No trailing bytes are accepted.

## Policy and XYPO output

Rust chooses compact/regular base gutters, measures the widest rotated y
tick label, accounts for inward/outward/inout tick length and label offset,
and measures y axis-title height. It takes the maximum reservation across
the three independent title slots, including manual y placement. Multiline
x tick/title ink adds to the bottom or top side. Colorbar and right-secondary
reservations use the existing Rust constants. The table reservation scales
from points by DPI/72. Optional Rust Scene gutters combine by sidewise maxima.

The result is exactly 88 bytes: `XYPO`, u32 version 1, u32 compact flag
(0 or 1), u32 zero, then nine f64 values in this order:

1. Final left, top, right, bottom gutters.
2. Outside top, right, bottom reservations.
3. Probe width and height for the Scene measurement pass.

Probe width is round-to-even(plot width + default left + default right),
floored at 120. Probe height is round-to-even(canvas height / rows), floored
at 120. Both are zero for unattached axes. The host can run a first query to
obtain probe dimensions, call Rust's Scene layout query, and pack those
returned measurements in a second query. Probe dimensions depend only on the
defaults, so adding measured gutters does not create a feedback loop.
All returned geometry must remain finite, nonnegative, and at most 65535.

Malformed inputs produce `XYG_STATIC_CHROME_HEADER`, `VERSION`, `FLAGS`,
`LIMIT`, `TEXT`, or `FACTS` suffixes under the same prefix. Explicit browser
CSS and custom-font facts return `XYG_STATIC_UNSUPPORTED_BROWSER_CHROME` and
`XYG_STATIC_UNSUPPORTED_CUSTOM_FONT`. Static callers relay a hard failure;
HTML callers can retain their existing browser presentation route.

Reproduce defaults, text-direction deltas, multiline/title/colorbar/table
combination, measured-gutter reconciliation, bounds, and malformed-input
coverage with `cargo test -p xyg-engine static_panel_chrome`.
