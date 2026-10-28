# Tile-keyed density painter (#10)

This is the native spilled-pyramid client path (dossier §5/§28/§29,
Phase-4 WP3). Existing eligible spatial point drills and exact-grid refinements run before
the keyed painter; inventory observations cannot change tier selection.
Initial payloads and masked/nonlinear-axis requests retain the
existing truthful window compose/re-bin path. Rust owns level selection,
aggregation, encoding and texture inventory; Python/Node pack observations
and forward bytes; TypeScript validates, uploads and paints them.

## Identity, quality and resource rules

A texture is identified by `(store generation, level, tx, ty)`; colored
textures also depend on style opacity. Level **0 is finest**. Appends change
the store generation; a rebuilt store has a new generation. A matching key
ships no pixel body. New edge tiles alone cross the wire during a pan;
Rust can keep nearby tiles for return pans. Host tile reads needed to compute
window exposure remain CPU work, even when no paint bytes are transferred.
The transport `fetches` count is missing logical paint tiles, distinct from
TileStore disk-cache `hit`/`miss` counters.

Rust first chooses the coarsest existing source level with enough cells for
the requested viewport dimensions, using the existing pyramid chooser. It
paints that source grid directly; it does not create a shifted window grid.
One source-cell gutter on every side and a clipped interior allow bilinear
sampling across tile boundaries without overlapping compositing. Domain
edge gutters repeat the edge cell. Cached/uncached identity means the same
Rust-served source level, framing, source log scale and window exposure,
with the oracle fetching every active tile. It does not claim identity to
the older area-resampled window compose.

The previous eight-texture ceiling becomes `8 * width * height * bytesPerCell`
per trace (`R8`: 1, premultiplied `RGBA8`: 4), including gutters and retained
adjacent levels. Rust pins current tiles within half that budget, reserves
the remainder for previous/nearby tiles, and retains at most 256 keys. Reply
allocation is capped at 64 MiB; each viewport dimension is 16–4096. If the
requested level cannot fit, Rust coarsens and records it. This is an explicit
**GPU painter** resource exception; it does not change Phase-4 D3 CPU tile
working-set pinning, compose quality, or its `over_budget` reporting.

Ordinary level changes advance at most one level per reply and use the
existing 140 ms `_densitySwitchPrev` transition. A further adjacent refine
is requested when necessary. A large viewport/budget change can make the
adjacent level itself exceed the ceiling: Rust records resource coarsening,
serves a fitting level, and the client directly replaces a nonadjacent
surface rather than blending unrelated resolutions. Same-level pans update
membership without blending a surface over itself. Reduced-motion rendering
sets both transition and exposure to their completed values.

A resize, generation replacement, or same-level reply during an active fade
can remove some outgoing textures from Rust's retained inventory. The client
checks every live outgoing frame, including `_densitySwitchPrev`, by texture
object identity. If any source is incomplete it immediately completes the
presentation transition, clears outgoing aliases, and removes incomplete
cached frames before they can draw. This applies even to adjacent levels or
an unchanged served level. The client does not exceed Rust's budget to keep
a fade alive. Retiring an incomplete frame preserves the current color/LUT
metadata for subsequent tiles.

Count tiles encode `round(255 * log1p(count) / log1p(source-level maximum))`
in Rust. The per-window maximum stays separate and uses the existing eased
exposure: the shader scales these stable texels by
`log1p(source maximum) / log1p(eased window maximum)`. Thus reuse does not
silently switch the display to global normalization. Mean-color tiles use
the existing linear-u16 mean → sRGB conversion and physical alpha
`1 - (1 - sourceAlpha * styleOpacity)^count`; they carry premultiplied RGBA8
and do not use count exposure. Existing approximate categorical legend dim
operates on the same allocation and restores the immutable Rust bytes.

An admitted mean-color XYDT frame retains header bit 0 as `tileSetRGBA`,
including when no legacy window `rgba` plane exists. Exact point drills use
that fact for the same native-opacity handoff as legacy mean-color grids:
`density_val` and the count-only `lod_blend` ramp are ignored. Entry/exit
layer fades, outgoing tile ownership, point-window caching and disposal keep
their existing T7/T10/T12/T13 rules. The bounded
`tests/test_keyed_colored_drill_browser.py` regression feeds actual
`density_view` replies from a forced-spill 262,144-row canonical source through
the real browser: native XYDT → canonical points → cached points → XYDT.
It covers continuous,
custom-colormap, categorical and direct-RGBA alpha channels, with per-row size,
stroke and width, cache promotion, painted mark ink, density return and GPU
cleanup. It does not establish a 100M localization or latency result.

## Binary controls and reply

All multibyte fields below are little-endian. Numeric inventories and pixel
planes are raw binary attachments. The small request metadata contains only
`tile_cache: true`; existing viewport controls keep their existing contract.
The transport-neutral channel and anywidget preserve the attachment unchanged. Unknown versions,
truncation, trailing bytes, invalid fields and excessive keys fail closed.
The host has no server-side texture residency state.

Reply dimensions are checked against the existing finite request dimensions
bounded to 16–4096, rather than against the raw canvas size. Thus a 4924-pixel
canvas can accept a valid 4096-pixel paint frame. Oversized headers, mismatch
with the bounded request, and non-finite requested dimensions fail before
allocation/cache mutation. Python normalizes through `ViewportRequest`; Node's
`densityViewFromPyramid` uses the same Rust-backed `screenShape` helper.
The low-level `tileStorePaint` helper still requires bounded dimensions and
refuses an unbounded direct call. Raw binary XYDC and structured Node inventory
options remain distinct; a typed array's built-in `keys()` is not inventory.

`XYDC` version 1 is a 32-byte header followed by `count * 12` bytes of u32
`(level, tx, ty)` triples (maximum 256, total maximum 3104 bytes):

| Offset | Field |
| --- | --- |
| 0 / 4 | `XYDC` / u32 version 1 |
| 8 / 16 | u64 generation / f64 previous colored opacity (`-1` initially) |
| 24 / 28 | i32 previous served level (`-1` initially) / u32 count |
| 32 | Key triples in the last Rust-provided inventory order |

`XYDT` version 1 has a 128-byte header, `count` 96-byte descriptors, then
contiguous bodies for missing current tiles only. Native ABI 395 adds
`xyg_tile_store_paint_capacity` and `xyg_tile_store_paint`; the latter returns
0 for a refused/stale store and `usize::MAX` for malformed/capacity failure.
This native-only helper does not alter the browser compute ABI.

| Header offset | Field |
| --- | --- |
| 0 / 4 | `XYDT` / u32 version 1 |
| 8 / 12 | u32 served level / flags (bit 0 mean color, bit 1 needs adjacent refine, bit 2 resource coarsening) |
| 16 / 20 / 24 / 28 | u32 retained count / current count / missing count / descriptor bytes (96) |
| 32 / 40 / 48 / 56 | u64 generation / f64 window maximum / f64 source log maximum / f64 opacity |
| 64 / 68 / 72 / 76 | u32 GPU byte budget / retained GPU bytes / viewport width / viewport height |
| 80 / 84 | u32 logical paint fetch count / resource-bounded target level |
| 96–127 | f64 viewport x0, x1, y0, y1 |

Each descriptor has u32 `level, tx, ty, width, height, bodyOffset, bodyBytes,
active` at offsets 0–31; f64 gutter texture x0,x1,y0,y1 and clipped interior
x0,x1,y0,y1 at offsets 32–95. Active entries precede retained entries.
Width/height include gutters (3–258). A retained texture has zero offset and
length; every nonempty body is contiguous and has exactly width*height*format
bytes. The browser validates the entire frame before allocating or changing
its texture inventory. Sequence and filter admission precede parsing;
disposal frees all owned tiles and rejects later replies.

## Reproduction

- `cargo test -p xyg-engine tile_store:: --offline`
- `cargo build --release --offline && node js/build.mjs`
- `uv run pytest tests/test_density_tile_frames.py tests/test_phase4_tile_spill_hosts.py -q`
- `XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/pyramid.test.mjs`
- `python3 scripts/density_tile_smoke.py /path/to/chromium`

The browser probe uses actual raw-control HTTP requests, native Rust frames,
WebGL upload counts, cached/fetch-all pixel comparison for counts and means,
nonblank alpha/ink and pixel hashes, a mandatory adjacent crossfade, legend
dim/restore, malformed/stale admission and disposal checks. Python and Node
also pin the same source-body SHA256 for a deterministic shared fixture. It is a
bounded structural proof; the dedicated 100M latency gate remains #11 work.
The existing CI Headless render smoke step runs this tile probe after the
general render probe, within the existing Test job and Release surfaces
aggregate; it adds no required status or large allocation.

The [review follow-up proof](../performance/density-tile-cache-2026-10-23/review-followup/README.md)
adds wide-viewport admission/refusal and actual mid-fade resize pixel oracles.
Earlier root proof files and installed-wheel reports remain historical records
for their original hashes; this source update does not requalify those artifacts.
