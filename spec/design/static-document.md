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

The v1 envelope is `XYST`: a fixed header, fixed-size panel table, optional
bounded UTF-8 document title, and concatenated canonical Scene bytes. Numeric
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
[annotation-style projection](static-annotation-style.md). Hosts may carry their
literal facts but do not repeat those contracts' defaults or policy.

### 1.1 XYST v1 framing

The header is 64 bytes. It begins with `XYST`, version `1`, width, height,
document flags, panel count, and title byte count as little-endian `u32`.
Header flags are `BACKGROUND=1`, `OPTIMIZE_PNG=2`, `TIGHT_CROP=4`, and
`TITLE_X_CENTER=8`; every other bit is rejected. The center flag requires
canonical zero title-x bytes and makes Rust resolve `width / 2`; without it,
title x is an explicit authored fact. Bytes 28–35 are background/title RGBA8,
bytes 36–47 are title size/x/y `f32`, bytes 48–49 are title anchor and
italic/bold flags, bytes 52–59 are decoration byte count and crop padding, and
all reserved bytes must be zero.

Each panel record is 104 bytes (`<2i6I12fII2f4BI>`). The first 24 bytes carry
signed x/y, width/height, Scene offset/length; byte offset 24 is the panel flag
mask. Optional floats and integers are canonical zero when their flag is
inactive. The admitted flags are:

| Bit | Fact |
| ---: | --- |
| 0–1 | x/y tick-label size, axis-label size, and tick padding |
| 2 | colorbar shrink and x/y anchor |
| 3 | uniform annotation font size |
| 4 | uniform arrow head/start/end shaft metrics |
| 5 | low/high x/y spine masks |
| 6 | uniform annotation italic/bold flags |
| 7 | uniform annotation label-box padding |
| 8 | panel-title size and RGBA8 |
| 9 | uniform annotation vertical alignment |
| 10 | pyplot colorbar logarithmic projection |
| 11–12 | pyplot colorbar minimum/maximum endpoint extends |
| 13 | pyplot colorbar label/orientation compatibility |
| 24 | explicit pyplot `cax` fills the panel Scene plot rectangle |

Bits 10–13 and 24 are non-serialized `SceneColorbar` overrides applied only while
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

## 3. Stable failure rules

Host validation errors keep their public `ValueError`/`TypeError` wording.
Authoring rejected by the Scene product predicate relays its exact
`XYG_SCENE_UNSUPPORTED_*` reason. A document-level rejection uses
`XYG_STATIC_UNSUPPORTED_*`; v1 reserves `PANEL`, `TITLE_STYLE`,
`FIGURE_LABEL`, `FIGURE_LEGEND`, and `TIGHT_BBOX`. Native consumer corruption
is a hard error and never requests a compatibility retry.

## 4. Ownership and evidence

Acceptance requires Python `_export_*`, `_svg_render.py`, and
`_raster_render.py` policy to be deleted or reduced to bounded marshal-only
wrappers. Merely excluding those modules from the final native call graph is
not retirement. The migration remains incomplete while legacy layout/tick or
renderer policy is transitively reachable from a supported static journey.
The ownership gate must arm before public chart construction and cover ordinary,
styled, polar, extra-axis, automatic-tick, notebook-sizing, and custom-font
failure journeys. Independently authored Python and Node tests pin identical
Scene and `XYST` bytes and outputs for the shared low-level document vocabulary;
missing high-level Node authored-plan parity is an open acceptance item, not an
exception. Format goldens cover SVG, PNG, PDF, JPEG, and WebP.
