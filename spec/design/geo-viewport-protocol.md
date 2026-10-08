# Geographic camera transport (#48)

`geo_viewport_protocol::execute` is the single Rust processor behind native C ABI
380 and WASM ABI 30. Python, Node and browser adapters only frame and read typed
bytes. Source f64 geometry and camera values never become JSON numeric arrays.
The protocol exposes engine operations, not a second public chart-building API.

## XYVC v1 request

Every request has an exact 128-byte little-endian header. Only operation 10
appends a canonical XYGD descriptor; other operations reject trailing bytes.

| Offset | Field | Type |
| --- | --- | --- |
| 0 | `XYVC` magic | four bytes |
| 4 | version, always 1 | u32 |
| 8 | operation | u32 |
| 12 | CRS, 4326 or 3857 | u32 |
| 16 | world wrap, 0 or 1 | u32 |
| 20 | reserved, zero | u32 |
| 24..80 | center X/Y, zoom, width/height, bearing, pitch | seven f64 |
| 80..120 | operation arguments, unused values zero in host encoders | five f64 |
| 120..128 | reserved, zero | eight bytes |

| Operation | Arguments | Result |
| --- | --- | --- |
| 0 normalize | none | canonical camera and rebuild key |
| 1 project | source X/Y | f64 CSS pixel X/Y |
| 2 inverse | CSS pixel X/Y | f64 source X/Y |
| 3 pan | delta CSS pixel X/Y | transitioned camera |
| 4 zoom | zoom | transitioned camera |
| 5 resize | CSS width/height | transitioned camera |
| 6 bearing | degrees | transitioned camera |
| 7 pitch | degrees | transitioned camera |
| 8 center | source X/Y | transitioned camera |
| 9 fit | min X/Y, max X/Y, padding CSS pixels | transitioned camera |
| 10 column | appended XYGD | projected finite buffers and topology |

Authoring adapters require an explicitly supplied wrap flag to be boolean;
strings, numeric flags and null are rejected rather than inferred. Omission uses
false. Rust validates the complete starting camera and candidate state. An error
publishes no response and cannot mutate the caller's camera snapshot. Camera
policy, polar clamps, wrapping and equations remain in `geo_viewport`, not hosts.

## XYVR v1 response

Every response starts with 256 bytes. Each following plane begins on an eight-byte
boundary and its tail padding is zero. Adapters reject nonzero reserved/padding
bytes, count overflow, nonfinite floats, truncated planes and trailing bytes.

| Offset | Field | Type |
| --- | --- | --- |
| 0 | `XYVR` magic | four bytes |
| 4 | version, 1 | u32 |
| 8/12/16 | operation / CRS / wrap | three u32 |
| 20 | ordinary geometry kind: 0 none, 1 points, 2 outlines | u32 |
| 24..80 | normalized camera, request field order | seven f64 |
| 80..96 | operation result X/Y, or ordinary buffer decode origin | two f64 |
| 96..168 | nine retained plane element counts, table order below | nine u64 |
| 168 | bounds present, 0 or 1 | u32 |
| 172 | reserved zero | u32 |
| 176..184 | source XYGM metadata digest, zero for camera-only operations | eight bytes |
| 184..216 | min X/Y, max X/Y: source-CRS camera footprint for operations 0..9; visible CSS feature bounds for operation 10; zeros when absent | four f64 |
| 216..232 | polygon buffer decode origin X/Y | two f64 |
| 232..256 | reserved zero | 24 bytes |

Camera operations always return the normalized camera's ground footprint from
Rust `GeoViewport.bounds()`. EPSG:4326 longitude is an unwrapped interval, so a
dateline-spanning footprint can exceed ±180°; latitude obeys the certified
Mercator clamp. EPSG:3857 bounds use source metres. Operation 10 retains
CSS-screen bounds of visible feature geometry, absent for no visible geometry.
Hosts decode these values and never derive bounds themselves.

The canonical rebuild key is 64 exact bytes: response bytes 12..20 (CRS/wrap),
then 24..80 (seven canonical float bit patterns). It excludes operation and
derived output, so no-op transitions reproduce the same key. The key describes
the exact returned normalized snapshot; native/wasm math is compared at existing
projection tolerances, and independently computed transcendental transitions may
differ by one f64 ULP. Replaying the same snapshot produces the same bit key. Source identity
uses full u64 values throughout; hosts never convert identity to JS Number.

| Plane | Element type | Meaning |
| --- | --- | --- |
| xy | f32 | ordinary center-relative interleaved screen geometry |
| feature IDs | u64 | one per point or independent line segment |
| offsets | u32 | outline segment boundaries |
| visible feature IDs | u64 | first-source-order visible identity set |
| polygon xy | f32 | closed projected fragments, center-relative |
| ring offsets | u32 | vertex ranges for polygon rings |
| polygon offsets | u32 | ring ranges for fragments |
| polygon feature IDs | u64 | source identity per fragment |
| ring-is-hole | u8 | explicit shell 0 / hole 1 topology |

Polygon topology is a rebuildable input for later layer/fill programs; this
protocol does not add fill rendering or basemap behavior. A polygon covering the
viewport remains visible even when none of its original outline edges appear.
The detailed projection semantics and supported frustum belong to
[geospatial.md](geospatial.md).

## Admission and lifecycle

Native `xyg_geo_viewport_execute(request, length, budget, out, cap, out_length)`
returns stable GeoError codes. A null output and zero capacity is a size query.
An undersized output returns `XYG_GEO_OUTPUT_CAPACITY` (-13) with output and
out_length untouched. All other failures also preserve both destinations.
Length/budget admission happens before constructing any caller input slice;
the caller owns and guarantees the readable memory stated by accepted lengths.
The maximum configured budget is 384 MiB; the browser transfer encoder limits
requests to 256 MiB. Native host adapters check length against the configured
budget before staging/copying or invoking Rust. Browser and Node `encodeGeoViewportColumnRequest` write XYVC + XYGD directly
into one allocated buffer from the existing GeoArrow typed descriptor. Python
`_geoviewport.encode_column_request` uses that same descriptor shape and explicit
little-endian dtypes. All three reject narrowing, preserve the source planes,
and preflight the complete packet length before allocating it. `encodeGeoViewportRequest` accepts an already packed XYGD
and copies it once behind the header; callers retain that separate input. Python
framing builds one mutable packet then freezes it to bytes (one transient copy),
with a temporary per-plane byte copy while writing noncontiguous inputs;
execution adds the ctypes staging copy. Caller source planes remain caller-owned
and separate from Rust's configured operation admission.

Before geometry allocation, Rust admits at most three request bytes per input
byte, sixteen bytes per source feature, 128 bytes per worst-case projected
record (six per source vertex for outlines), plus 32768 fixed bytes. Polygon
requests additionally admit 4096 bytes per source vertex and 512 bytes per feature
for clipping/topology capacity before decoding.
The XYGD decoder additionally checks its own peak/geometry ceilings. Staging
capacity beyond the request is subtracted by WASM. Output size is checked before
publication. Size queries recompute the bounded result; those allocations end
before the copy call starts. No persistent native camera registry is required.

WASM `xyg_wasm_geo_viewport_execute(handle, sequence, offset, length)` uses the
existing geographic single-use lane. Zero/stale/cancelled calls protect newer
active jobs; accepted calls supersede them and release input staging on every
success or failure. Worker `geoViewportExecute` transfers its request, supports
cancel/dispose, and returns the packed response. Calls cannot be interrupted
inside synchronous Rust work; shared resource and topology ceilings bound it.

## Evidence and reproduction

`packages/xy-node/test/geo-viewport-wasm-parity.test.mjs` compares every operation
through the native conformance executable, C ABI and actual wasm32 artifact. It
also checks inverse/project at polar/dateline/extreme Mercator coordinates,
canonical six-kind geometry planes and full-u64 IDs, and malformed/resources.
`tests/test_geo_viewport_protocol.py` proves Python round-trip/key behavior and
C ABI failure writes. Rust processor tests cover framing and transitions.

```
cargo build --release -p xyg-core
cargo build -p xyg-wasm --bin geo_viewport_conformance
cargo build --release --target wasm32-unknown-unknown -p xyg-wasm
node js/build.mjs && node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node --test packages/xy-node/test/geo-viewport-wasm-parity.test.mjs
uv run pytest tests/test_geo_viewport_protocol.py
```

Use the platform's library suffix when reproducing outside macOS.

Worker sequence admission includes aggregate-stream begin in the shared operation
watermark. Deferred geographic/scene/graph operations recheck that watermark
before cancelling active lanes or staging bytes. Stale or zero camera messages
preserve a newer active stream; a current valid camera still supersedes it.

Main-thread geographic/camera adapters retire their pending promise entry if
transfer submission fails (including non-detachable WASM memory buffers), throw
`XYG_WASM_INVALID_ARGUMENT`, and retain subsequent valid-call recovery.
