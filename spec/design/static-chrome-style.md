# Native static chrome-style projection

#1004 restores the admitted `title`, `axis_title`, and `tick_label` slot
styling that native export used to discard. `static_chrome_style::resolve_packed`
(dossier §21/§28) is the single owner of admission, the precedence rule, and
the resolved text decisions. It is a bounded authoring query like the
[annotation-style projection](static-annotation-style.md), not a second text
renderer: Rust Scene/StaticDocument consume its result for SVG, raster
(PNG/JPEG/WebP), and PDF, and the Python and Node hosts only marshal facts and
apply what comes back. The duplicated host tables (admitted slots/keys/families,
`14px`/`12.0` defaults, root-theme `setdefault`) are deleted from
`python/xyg/_static_document.py`, `python/xyg/pyplot/_grid.py`, and
`packages/xy-node/src/scene.js`.

## XYCS v1 input

`<4s3I>`: `XYCS`, version 1, flags, reserved zero. Flag bit 0 = the panel has a
title; bit 1 = admit the pyplot-owned `legend` slot's closed key set (it is
validated here, never resolved). Then, all little-endian:

1. root theme entries, 2. slot count (0..8) then `(name, entries)` per slot,
3. for the x and then y axis, the authored `style` entries followed by the
`minor_style` entries.

Entries are a u32 count (0..64) then `(key, value)`; a string is a u32 length
(<= 4096, NUL-free UTF-8) and the whole frame is at most 256 KiB. Values use the
XYAS tags: 0 null, 1 string, 2 raw f64, 3 bool, 4 opaque. Duplicate keys or
slots, unknown tags, nonzero reserved words, truncation, and trailing bytes
fail.

## Admission and precedence

*Absent* means a missing key, null, or empty string — all one "not authored"
fact. Slot keys are `font-size`, `color`, `font-weight`, `font-style`,
`font-family`; anything else is `XYG_STATIC_UNSUPPORTED_CHROME_STYLE`.

| Fact | Admitted values | Reason on rejection |
| --- | --- | --- |
| `font-size` | `<number>px`, 1..=`MAX_SCENE_CHROME_LENGTH` | `..._CHROME_FONT_SIZE` |
| `color` | a fully parsed color (no `var()`, `currentColor`, `color-mix`) | `..._CHROME_COLOR` |
| `font-weight` | `normal`/`400`, `bold`/`700` (text or number) | `..._CHROME_FONT_WEIGHT` |
| `font-style` | `normal`, `italic` | `..._CHROME_FONT_STYLE` |
| `font-family` | DejaVu Sans / sans-serif only | `..._CUSTOM_FONT` |
| root keys | `background`, `--chart-bg`, `--chart-grid`, `--chart-axis`, `--chart-text`, `font-family`, `font-size` | `..._BROWSER_CSS` |
| axis `tick_label_size`/`tick_size`/`label_size` | number or numeric text, in range | `..._CHROME_AXIS_STYLE` |
| axis `tick_padding` | number or numeric text, ±`MAX_SCENE_CHROME_LENGTH` | `..._CHROME_AXIS_STYLE` |

All reasons are `XYG_STATIC_UNSUPPORTED_*`; frame errors are
`XYG_STATIC_CHROME_STYLE_{HEADER,VERSION,FLAGS,LIMIT,TEXT}`. Validation covers
the whole frame before any output exists, so a rejection is atomic and there is
no fallback renderer. Root `font-size` is validated but inert: the canonical
theme gives each chrome slot an explicit pixel size.

Precedence, highest first (one rule for both hosts):

| Decision | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- |
| axis-title size / paint | axis `label_size` / `label_color` | `axis_title` slot | root `--chart-text` (paint) | 12 / Scene paint |
| tick-label size / paint | axis `tick_label_size` (alias `tick_size`) / `tick_label_color` | `tick_label` slot | root `--chart-text` (paint) | 12 / Scene paint |
| title size / paint | `title` slot | root `--chart-text` (paint) | 14 / `#262626` | |
| weight, style | slot only | normal | | |
| tick padding | axis `tick_padding` | 4 | | |

Tick-label and axis-title paints are separate decisions even though the canonical
Scene wire has one `label_rgba` per axis; XYST carries the split.

## XYCO v1 output

`XYCO`, version 1, flags (bit 0 = title), the XYST `chrome_text` word, four RGBA8
paints (x tick, y tick, x title, y title; zero when absent), title size (f64) and
RGBA8, six f64s (x then y tick size, axis-title size, tick padding), then for each
axis the `style` and `minor_style` keys the host must drop because XYST carries
them. The `chrome_text` word packs two-bit flags (bit 0 italic, bit 1 bold) for
title, x title, y title, x ticks, y ticks (bits 0..10) and four paint-present bits
(10..14).

## XYST consumption

The panel record grows to 128 bytes (`<2i6I12fII2f4B2II16B>`): panel flag bit 15
announces the trailing `chrome_text` word and four RGBA8 paints, all canonical
zero when inactive. `SceneDocument::apply_static_chrome_text` validates them
(unknown bits, paints without their presence bit, title flags without a title
fail the document) and stores them on the axis chrome / document. SVG emits
`font-style="italic"` / `font-weight="700"` (PDF reads them from the SVG), and the
raster display list uses the styled-text command, so pixels and PDF agree with
the SVG. The sizes and title size/color continue to ride bits 0–1 and 8.

## Evidence

* Rust: `static_chrome_style_tests.rs` (framing, precedence, atomic failure).
* Python public composition: `tests/test_static_chrome_style.py` — SVG attributes,
  decoded PNG/JPEG/WebP pixels, PDF text/fonts, legacy defaults, malformed input,
  ownership (a tampered or discarded native result changes the output).
* Node Figure: `packages/xy-node/test/static-chrome-style.test.mjs`, including a
  panel-record equality test against the raw native result.
* Cross-host: `tests/test_static_chrome_style_cross_host.py` with
  `packages/xy-node/scripts/static_chrome_style_cross_host.mjs` — byte-identical
  SVG/PNG/PDF/JPEG/WebP, identical stable reasons, identical raw XYCS results,
  and a source guard that the hosts carry no policy tables.
* Registry: `panel.chrome-text` (bit 15) and case `document_chrome_text` in the
  Rust support registry; mask `0xffff`.
* Matplotlib reference: `scripts/chrome_style_reference.py` records
  `spec/benchmarks/chrome-style-reference-1004.json` (Matplotlib 3.11.2, resolved
  size/weight/style/paint decisions; fixed-font limitation noted, not pixel parity).
