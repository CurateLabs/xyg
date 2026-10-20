# StaticDocument product export boundary

Status: M2 contract for issue #873. This document is normative for native
static export. Interactive HTML and Chromium capture keep their existing
browser/CSS contract and do not pass through `StaticDocument`.

## 1. Boundary

`StaticDocument` is a versioned, bounded Rust-owned document made from one or
more already validated canonical Scene documents plus literal panel placement
facts. Rust validates the complete envelope and exclusively owns SVG structure,
panel id namespacing, raster composition, PDF lowering, and PNG/JPEG/WebP
encoding. Python and Node may coerce public arguments, compile the same Scene,
marshal the envelope, invoke the generated ABI, and translate stable errors.
They must not retry a host renderer after the Rust support predicate or
consumer has been selected.

The envelope is `XYST` (see §1.1 for the layout version): a fixed header, fixed-size panel table, optional
bounded UTF-8 document title, the per-label annotation table region, and concatenated canonical Scene bytes. Numeric
facts are little-endian integers; no JSON numeric array crosses the boundary.
The decoder rejects unknown versions/flags, empty or oversized panels,
out-of-canvas placement, overlapping byte ranges, invalid UTF-8, invalid Scene
documents, and resource totals above the published limits before rendering.
The companion Rust-owned marshal contracts are
[panel/title layout](static-document-layout.md),
[panel chrome](static-panel-chrome.md),
[best-legend placement](static-legend-fit.md), and
[document-label](static-document-labels.md) and
[document-legend](static-document-legend.md) authoring, plus
[annotation-style projection](static-annotation-style.md), and the
[chrome-style projection](static-chrome-style.md). Hosts may carry their
literal facts but do not repeat those contracts' defaults or policy.

### 1.0 Legend ownership

A document legend belongs to either the **document** or one **panel**. The
document legend (figure legends) is laid out against the whole canvas. A panel
legend (every axes legend, including pyplot's) is laid out against that
panel's Scene plot box, offset by the panel's placement, by the same Rust
`legend_box_layout`, so each axes of a multi-panel document keeps its own
legend and location. The XYDD header's first reserved word carries the byte
length of a trailing panel-legend section appended after the colorbar name:
repeated `<2I>` (panel index, block length) plus an XYDD legend block, strictly
ascending by panel index and each index below the panel count. The XYDD envelope is version 2 (44-byte legend item records); version 1 is
rejected. Documents without panel legends keep a zero word. The
`XYG_STATIC_UNSUPPORTED_MULTIPLE_PANEL_LEGENDS` rejection now applies only to a
second legend within one axes (`extra_legends`). Both hosts marshal the same
facts (`_static_document.encode(panel_legends=)`, Node
`staticDocumentEncode({ panelLegends })`). The anchor is `SceneDocument::plot_bounds`: the Scene plot box, except that a
polar Scene's box is the **visible** disc or sector (`polar::visible_box`, the
same sector bounds `partial_sector_layout` fits into the layout rectangle),
which always lies inside that rectangle. At decode, Rust resolves every legend
box and **rejects** the document with
`XYG_STATIC_UNSUPPORTED_FIGURE_LEGEND_BOUNDS` if a layout fails or any box
leaves the document canvas; nothing is clipped or silently dropped. (Legend
boxes are otherwise clamped into their anchor box by `legend_box_layout`, so the
guard only fires for authored anchors or boxes that cannot fit.)

### 1.1 XYST v3 framing

Version 3 (#1006) replaced the four uniform annotation facts (panel flags 3, 6,
7, 9) with a per-label table region (below); version `2` documents are rejected
with `XYG_STATIC_DOCUMENT_VERSION` like version `1`.

Version 2 (#1004) widened the panel record from 108 to 128 bytes. The version
is the only layout discriminator: a version `1` document (108-byte panels) is
rejected with `XYG_STATIC_DOCUMENT_VERSION` and guidance to re-encode, never
decoded with the new table boundaries. Rejections carry a stable
`XYG_STATIC_DOCUMENT_*` code through the C ABI (`HEADER`, `VERSION`, `FLAGS`,
`LIMIT`, `PANEL`, `TITLE`, `SCENE`, `RASTER`, `ENCODE`), surfaced as
`StaticDocumentRejected.code` in Python and a `RangeError` with `.code` in Node.
Encoders accept panel title paints as a CSS color string (converted by the
native color conversion) or resolved RGBA8 bytes; anything else is rejected.

The header is 64 bytes. It begins with `XYST`, version `3`, width, height,
document flags, panel count, and title byte count as little-endian `u32`.
Header flags are `BACKGROUND=1`, `OPTIMIZE_PNG=2`, `TIGHT_CROP=4`, and
`TITLE_X_CENTER=8`; every other bit is rejected. The center flag requires
canonical zero title-x bytes and makes Rust resolve `width / 2`; without it,
title x is an explicit authored fact. Bytes 28–35 are background/title RGBA8,
bytes 36–47 are title size/x/y `f32`, bytes 48–49 are title anchor and
italic/bold flags, bytes 52–59 are decoration byte count and crop padding, bytes 60–63 are the
byte length of the per-label annotation table region (a multiple of 20; zero when
no panel has the flag below), and all reserved bytes must be zero. The region sits
between the decorations and the Scene bytes.

Each panel record is 128 bytes (`<2i6I12fII2f4B2II16B>`; the `u32` at offset
104 carries the grid dash nibbles and the final 20 bytes the chrome-text word
plus four RGBA8 paints). The first 24 bytes carry
signed x/y, width/height, Scene offset/length; byte offset 24 is the panel flag
mask. Optional floats and integers are canonical zero when their flag is
inactive. The admitted flags are:

| Bit | Fact |
| ---: | --- |
| 0–1 | x/y tick-label size, axis-label size, and tick padding |
| 2 | colorbar shrink and x/y anchor |
| 3 | per-label annotation table: the `u32` at offset 28 is the table's byte offset in the document's label-table region and the `u32` at offset 84 its byte length (see below) |
| 4 | uniform arrow head/start/end shaft metrics |
| 5 | low/high x/y spine masks |
| 6–7 | retired (v2 uniform annotation flags/padding); rejected |
| 8 | panel-title size and RGBA8 |
| 9 | retired (v2 uniform annotation vertical alignment); rejected |
| 10 | pyplot colorbar logarithmic projection |
| 11–12 | pyplot colorbar minimum/maximum endpoint extends |
| 13 | pyplot colorbar label/orientation compatibility |
| 14 | uniform grid dash codes for (x major, y major, x minor, y minor) |
| 15 | Rust-resolved chrome text: italic/bold flags for the title, axis titles, and tick labels plus separate tick-label and axis-title RGBA8 paints ([chrome-style projection](static-chrome-style.md)) |
| 24 | explicit pyplot `cax` fills the panel Scene plot rectangle |

Bit 3's table is the annotation-style projection's per-label output
([static-annotation-style.md](static-annotation-style.md)): 20-byte entries in
the order of the panel Scene's annotation labels (`<I3f2B2x>`: present bits, font size, horizontal
and vertical box padding, italic/bold bits, vertical alignment). Panels consume
the region sequentially, the entry count must equal the panel Scene's
annotation-label count (labels with the Scene-wire annotation provenance flag, XYLB v7, never an id pattern;
other labels such as a composed graph's own are untouched; an empty table with
the flag set over a Scene with annotation labels is rejected), absent facts and reserved bytes must be canonical zero, and the region
must be consumed exactly; Rust applies size, flags, alignment shift and the
per-axis box inset to each label (`SceneDocument::apply_static_annotation_labels`).
A label that requests padding but has no box, or a count mismatch, rejects the
document (`XYG_STATIC_DOCUMENT_PANEL`).

Bit 14 packs four nibble codes (`0=solid, 1=dashed, 2=dotted, 3=dashdot`)
into the panel's trailing fact `u32`; the pattern table is Rust-owned and
mirrored by `js/src/50_chartview.ts`. Bits 10–13 and 24 are non-serialized
`SceneColorbar` overrides applied only while
Rust consumes XYST. They do not mutate the canonical Scene wire. Extend uses
`0=neither`, bit 11=`min`, bit 12=`max`, and both bits=`both`; log colorbars
require a positive ordered domain and ticks. The pyplot label flag rotates a
vertical label by -90 degrees and centers horizontal labels. Unknown panel
flags or colorbar-only flags on a panel without a canonical colorbar reject the
document. Bit 24 replaces ordinary outer-gutter placement with the decoded
Scene plot bounds; placement still resolves in Rust and both SVG/raster consume
the same rectangle.

## 2. Frozen migration contract

The checked registry in `tests/fixtures/static_document_contract.json` is the
machine-readable inventory. `RETAIN` means the journey must use the Rust
`StaticDocument` kernel and keep golden/differential coverage. `BROWSER_RETAIN`
means it deliberately keeps the existing browser-only route. `FAIL_CLOSED`
means the former Python compatibility renderer is not a fallback: the public
call raises the listed stable `XYG_*` reason.

- Figure and Chart native SVG/PNG/PDF/JPEG/WebP retain every journey admitted
  by the Rust public Scene predicate. Export-only literal backgrounds are a
  document fact. Scene-rejected custom fonts, browser-only CSS/classes,
  unresolved gradients, and unmodeled mark/style/data combinations fail closed
  with the predicate's exact stable reason.
- Large data takes the browser's first-paint LOD tier, never a silent
  host-side reduction (#1006; [scene-ir.md](scene-ir.md#public-static-lod-tiers-1006),
  dossier §28): a Cartesian line above `DECIMATION_THRESHOLD` (10,000) exports
  the browser's M4 rows (`payload_m4_indices`, buckets = figure CSS width
  clamped to 16–4,096, window = resolved x domain) in SVG, PNG, PDF, JPEG, and
  WebP alike; a scatter the browser draws direct exports one marker per point
  up to `DIRECT_SOFT_CEILING` (2,000,000 summed over the figure's direct
  scatters); a density-tier scatter exports one density Image binned in Rust
  from the canonical columns; a non-joined triangle mesh above the 1,024
  PolyFill-group budget exports one smooth dense-fill Image Rust rasterizes
  from its faces (`<image data-xy-dense-fill="true">` in SVG, `/Interpolate
  true` in PDF, a bilinear blit in raster formats). A scatter with per-point
  color/size/stroke channels exports directly only while its paint plane fits
  one 4 MiB XYTA record (about 174,000 points), and the figure's packed rows
  share the 2,000,000-mark Scene ceiling. Polar lines, areas, and other kinds above their
  record budgets, forced-direct scatters beyond the ceiling, and lines whose
  x cannot be M4-binned fail closed as `XYG_SCENE_UNSUPPORTED_PUBLIC_LOD`;
  non-finite large lines keep the shared non-finite row reason.
- `to_html()` and Chromium image/PDF capture retain live CSS, custom fonts, and
  `custom_css`; they remain browser journeys and never silently substitute for
  an explicitly requested native engine.
- `write_image()` and `write_images()` retain format inference, atomic writes,
  argument validation, mixed formats, and the shared Chromium session. Each
  native member independently compiles and exports one `StaticDocument`; an
  unsupported member stops the batch without changing prior-write semantics.
- `FacetGrid` native static formats retain fixed grid placement, gaps, panel
  labels (as panel Scene titles), the optional grid title, and literal document
  backgrounds only when every panel is Scene-admitted. A rejected panel fails
  closed with its indexed Scene reason. Facet HTML/Chromium remains unchanged.
- `xyg.pyplot` HTML remains browser-owned. Native `savefig` retains PNG and SVG,
  single and multi-axes placement, DPI, facecolor/transparent, suptitle, and the
  already supported figure-label/legend surface through `StaticDocument`.
  PNG metadata remains a byte-container post-process, not rendering policy.
  `bbox_inches="tight"` is retained only after Rust owns the crop. Existing
  unsupported formats/options keep their established `NotImplementedError`.
  Pyplot colorbars retain named palettes, explicit/default ticks, linear/log
  projection, shrink/anchor, endpoint extends, minor ticks, and vertical or
  horizontal labels through canonical XYCB plus XYST-only compatibility flags.
  Named palettes are a bounded table of literal samples; Rust resolves the
  pyplot override to 64 interpolated bands shared by SVG and raster. The
  retired Python SVG renderer's particular gradient element/id is not part
  of XYST. Unoutlined painted affine Cartesian and polar heatmaps lower in Rust
  to one RGBA Image record and share Scene's 2,000,000-pixel image ceiling;
  nonlinear Cartesian axes and authored visible per-cell outlines retain
  transformed cell records and the 10,000-record cell ceiling. The Scene
  consumer's existing 1,024 PolyFill-group ceiling remains
  authoritative. A pyplot hexbin above that bound (including the original
  100,000-source-row, `gridsize=50` gallery witness that yields 1,226 cells)
  fails closed as `XYG_SCENE_UNSUPPORTED_PUBLIC_LOD`, with no host-renderer
  retry. [Issue #887](https://github.com/CurateLabs/xyg/issues/887) tracks the
  separately versioned Rust admission and resource proof needed for a future
  static-only larger group budget.

  Rust owns these validated Scene behaviors for every host (#1006): an empty
  line/scatter trace is a no-op that emits no marks; per-segment colormapped
  strokes (`contour`, `tricontour`, `segments` with a numeric color array)
  intern one literal stroke per distinct mapped color from the per-item paint
  plane; and `side="top"`/`"right"` axes are admitted for heatmap-only
  geometry (`matshow`, `spy`) while contour and other literal geometry keep
  the default-side contract. The pyplot static adapter only translates author
  arguments: a scalar `alpha=` becomes the literal CSS alpha of constant
  fill/stroke paint (never filling `"none"`) or a constant `artist_alpha`
  channel for per-item paint.
  Hidden traces always fail closed (`XYFS_TRACE_HIDDEN`, scene-ir.md); a
  per-item scatter paint plane is final paint with trace opacity folded in.

## 3. Stable failure rules

Host validation errors keep their public `ValueError`/`TypeError` wording.
Authoring rejected by the Scene product predicate relays its exact
`XYG_SCENE_UNSUPPORTED_*` reason. A document-level rejection uses
`XYG_STATIC_UNSUPPORTED_*`; v1 reserves `PANEL`, `TITLE_STYLE`,
`FIGURE_LABEL`, `FIGURE_LEGEND`, and `TIGHT_BBOX`. Native consumer corruption
is a hard error and never requests a compatibility retry.

## 4. Ownership and evidence

Acceptance state (2026-09-05): the Python compatibility renderer is deleted
(`_export_*`, `_svg_render.py`, `_raster_render.py`, `_raster.py`,
`_svg_figure.py`, `_raster_figure.py`). `python/xyg/_svg.py` is a bounded
facade over the `_layout` measurement surface and slot metadata;
`_static_document.py` is the marshal-only XYST adapter. The runtime gate
`tests/test_static_document_ownership.py` arms before public chart
construction and covers ordinary, styled, facet, pyplot, legend, and
custom-font failure journeys; no legacy `_export_*`/renderer module remains
importable. Node authored-plan parity is complete: `figureStaticDocument`
mirrors the projection, and the registry corpus pins byte-identical XYST,
SVG, PNG, PDF, JPEG, and WebP output per admitted shape. Remaining pyplot
static-route admissions are explicit fail-closes tracked in #889.
