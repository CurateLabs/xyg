# Retained geographic source contract

This is the first #50 foundation. `geo_source.rs` retains a bounded manifest and
reads canonical geographic chunks through a host-neutral Rust callback. It does
not implement geographic LOD, a spatial tile index, networking, a cache,
chart/temporal lifecycle, export, or massive-performance evidence. A source-wide
scan is bounded in resident memory but linear in candidate rows; it is not an
interactive pan/zoom claim. Dossier §27/§28 and
[geospatial.md](geospatial.md) remain the geometry and precision authority.

## Canonical source and identity

A source is homogeneous in geometry kind and explicit CRS. All six GeoColumn
kinds are supported: Point, LineString, Polygon, MultiPoint, MultiLineString,
MultiPolygon; canonical coordinate order, bitwise f64 geometry, nested offsets,
nulls, holes and multipart topology are unchanged. `GeoChunk` delegates geometry
validation to the existing `XYGD` parser, with stricter chunk admission before
that parser allocates. No Arrow, filesystem or browser dependency is introduced.

Chunks preserve source input order; data need not be spatially or temporally
sorted. Each `FeatureRef` carries chunk index, local source row, original global
source ordinal (including null rows), and exact source u64 feature ID. Duplicate
IDs do not collapse source rows. IDs including u64MAX and annotation-shaped IDs
are ordinary source IDs. Future spatial partitioning must carry an explicit
original-ordinal mapping; it cannot reinterpret partition position as identity.
The current format does not spatially reorder rows.

Optional intervals follow [temporal.md](temporal.md): signed i64 UTC microseconds,
[start,end), null start/end unbounded past/future, finite start >= end rejected.
Every source row, including null geometry, has an interval slot when attached.
Null endpoint payloads are canonically zero. Optional one-f64-per-source-row
scalar values preserve all bits (including signed zero, NaN, infinity); the shared
layer compiler owns scalar domains and missing-value interpretation. MultiPoint
vertices share their source-row scalar. Per-row style-patch/state/text planes are
not part of this slice; massive inherited custom styling needs a bounded
attachment follow-up rather than whole-source host arrays.

## Resource admission

| Resource | Hard ceiling / default |
|---|---|
| Planned and validated source rows | 1,000,000,000 |
| Manifest chunks | 65,536 |
| Source rows per chunk | 65,536, including nulls |
| Vertices per chunk | 524,288 |
| Packed chunk and retained geometric payload | 16 MiB each |
| Manifest metadata | 32 MiB ceiling; fixed wire entries make actual maximum about 8 MiB |
| Chunk parse phase | 96 MiB, lowered by surrounding reservations |
| Processor phase | 128 MiB for manifest, parse, result/consumer memory and fixed scratch together |
| Membership page | 1..4096 source rows |
| Default per operation read budget | 128 MiB cumulative, stored as u64 |
| Default source-row examination budget | 1,000,000, stored as u64 |
| Default considered-chunk budget | 65,536 |

`GeoSourcePlan::new(1B,65536)` returns 15,259 chunks, 1,953,216 wire manifest
bytes and the 128 MiB processor ceiling without allocating data. This is an
admission plan, not evidence that 1B rows were ingested, rendered or queried.
Row/byte read budgets may be explicitly increased for a streaming scan without
increasing resident memory. Cumulative bytes use u64 in native and wasm32; a
valid streaming operation can read more than 4 GiB without retaining it.

The processor subtracts actual manifest vector capacity, bounded membership
capacity or an explicit consumer reservation, and scratch before admitting the
chunk parser. Reader vectors account for capacity beyond logical length as well
as the normal descriptor/parser peak. Oversized capacity is rejected. All
geometry/interval/scalar length arithmetic is checked before typed allocations.
Persisted manifest validation reserves incoming and comparison wire bytes plus
conservative metadata vector-growth capacity and chunk parse scratch. The
reader must obey each exact bounded request *before* allocating or doing I/O;
Rust can reject a returned oversized vector but cannot undo a host allocation.

The enclosing source/query/cache coordinator must reserve the 128 MiB processor
phase within its 512 MiB total, leaving at most 384 MiB for cache. This source
module does not implement that cache or silently borrow its memory. The shared
[resumable session](geo-source-session.md) owns the global processor ledger for
product operations; synchronous helpers require their caller to reserve live
source/consumer/output memory. Streaming
callbacks must remain within their declared `consumer_bytes` reservation and
publish only after the operation succeeds.

## Chunk wire: XYGK v1

All integers and f64 bit patterns are little endian; numerical payloads are raw
planes, never JSON numbers. Header is 64 bytes:

| Offset | Type | Meaning |
|---:|---|---|
| 0 | bytes[4] | `XYGK` |
| 4 | u32 | version 1 |
| 8 | u32 | bit0 intervals, bit1 scalar values; other bits rejected |
| 12 | u32 | zero |
| 16 | u64 | embedded XYGD byte length |
| 24 | u64 | top-level source row count |
| 32..64 | bytes | zero |

The complete embedded XYGD starts at 64. It uses explicit source IDs (flag1)
and the existing canonical coordinate/validity/offset planes, each padded to
8 bytes with zero padding. The XYGK row count must match XYGD. Optional interval
planes follow XYGD: starts i64[n], ends i64[n], start validity u8[n] padded8,
end validity u8[n] padded8. Optional scalar f64[n] follows intervals (or XYGD
when intervals are absent). No trailing bytes are accepted. `encode` forwards
to `encode_with_values(...,None)`; writers derive canonical bytes from an
already validated GeoColumn. Chunk digest is BLAKE2s-8 over domain
`xyg-geo-chunk-v1` followed by the whole XYGK document. Digest keys are not a
cryptographic authentication or authorization mechanism.

## Manifest wire and trust: XYGI v1

Header64: magic `XYGI`, u32 version1 at4, geometry/CRS u32 at8/12, nonzero
source generation u64 at16, total original rows u64 at24, chunk count u64 at32,
zero bytes40..64. Each source-order entry is 128 bytes:

| Offset within entry | Type | Meaning |
|---:|---|---|
| 0 | u64 | first original row ordinal |
| 8 | u32 | source rows |
| 12 | u32 | encoded chunk byte length |
| 16 | bytes[8] | chunk digest |
| 24 | u32 | bit0 bounds present, bit1 intervals attached, bit2 start finite, bit3 end finite |
| 28 | u32 | zero |
| 32 | f64[4] | min x, min y, max x, max y; zero when absent |
| 64,72 | i64 | minimum start and maximum end; zero when corresponding bit absent |
| 80..128 | bytes | zero |

`GeoManifestBuilder.push(&GeoChunk)` derives every entry in Rust from validated
canonical content; summaries have no public authoring constructor for a trusted
source. `finish(generation)` freezes the source. Transactional registry finalization
may clone the bounded builder only after reserving the duplicate summaries and
canonical encoding scratch; cloning does not establish a trusted persisted
manifest or waive full chunk validation. Source digest is BLAKE2s-8 over
`xyg-geo-manifest-v1` followed by the exact manifest, including generation.

Persisted user-supplied summaries cannot justify skipping canonical reads.
`validate_with_budget` checks framing and total work admission, reads **every**
chunk on success, validates canonical bytes/digest, recomputes summaries in source
order and compares the entire canonical manifest before returning a trusted
source. `UntrustedGeoManifest` exposes the same allocation-free framing preflight,
read request, incremental per-chunk summary comparison and final comparison to
the resumable session; forged summaries may fail early without granting any
pruning capability. Requests include the authenticated original row count for
pre-I/O work admission.
`validate` uses the default operation budget; larger sources require explicit
streaming validation budgets. Failure/cancellation returns no trusted manifest.
Each later read checks generation in the request and rechecks the entire chunk
digest; stale content cannot inherit an old zone-map proof. The host reader must
bind the request generation to the immutable source backing its chunk index.
An in-process canonical writer can build the trusted manifest directly while
streaming ingestion, avoiding a second initial full read.

Bounds are conservative canonical-CRS zone maps. For any feature/chunk whose x
range spans more than half a world, bounds span the entire x world domain:
[-180,180] for EPSG4326 or +/-20,037,508.342789244 for EPSG3857. This avoids
false-negative pruning at the dateline, including multipart/unsorted data. It
can read extra chunks; it does not claim precise dateline localization. Bounds
of polygon vertices conservatively include its interior and holes; hole/frustum
visibility remains the existing GeoViewport's exact geometry policy.

Temporal summaries use the minimum finite start and maximum finite end among
non-null geometry rows; any unbounded endpoint makes its corresponding summary
unbounded. All-null/empty chunks remain conservative rather than inventing an
invisible temporal range. Candidate tests apply temporal summary *before*
spatial summary, then exact row interval *before* feature bbox or any consumer.

## Streaming, pagination and cancellation

`GeoChunk::rows()` yields borrowed `FeatureView`s for non-null geometry rows,
with exact local row, complete canonical column, vertex range, interval
endpoints and optional scalar value. Nested offsets retain polygon/hole/part
association. This is not an expanded GeoJSON or a sampled feature.

`scan_chunks(q,budget,consumer_bytes,reader,cancel,visitor)` reads each admitted
chunk once and folds time-filtered conservative spatial candidates in source
order. A count pass followed by an aggregate pass can use two reads; no global
O(N) selection/state/CSR mask is allocated. The source module does not decide
pixel bins, LOD tiers, simplification or tessellation.

`query_page` emits all matching source rows across pages without sampling.
`query_page_where` is its shared implementation with an additional Rust
predicate after time/bbox; only accepted rows occupy the page. This supports
exact bin membership, including one MultiPoint row qualifying through multiple
vertices without duplicating that row. Predicates may reject conservative bbox
candidates using shared Rust projection. The source cursor binds generation,
source digest and QuerySpec digest plus chunk/local row; the caller's outer LOD
cursor must also bind predicate identity (camera/bin/tier/style).

Every read/decode charges the *entire* chunk row count, including nulls and a
resumed prefix, to work admission. Membership pages can reread a chunk; full
folds must use `scan_chunks` to avoid page-size-driven rereads. Queries report
considered/read chunks, u64 bytes and examined rows. Read/processor limit
failures are explicit; a bounded considered-chunk/work page can return a resume
cursor. A per-operation budget too small to examine any selected chunk fails
rather than returning a permanently stalled cursor.

Cancellation is checked between chunks, before and after each read, and
periodically while visiting valid rows. No callback occurs after a cancelled
read. Consumer callbacks are tentative: consumer-owned aggregation/state must
publish only after success. Immutable source bytes/manifest survive malformed
queries, cancellation, resource failures and stale cursors.

## Evidence and remaining gates

Focused Rust fixtures cover six geometry kinds, exact IDs/nulls, holes and
multipart topology, conservative dateline bounds, unordered row/scalar input,
signed half-open/unbounded time, time-before-spatial callbacks, all-chunk trust
validation, tampered summaries/content, cancellation, resource/capacity limits,
paged full membership and query/source revision rejection. The module builds
for wasm32 without raster/host I/O features. Actual native-versus-WASM protocol
execution, configured transports, style/state attachments, spatial index/tile
pyramids, LOD/cache coordination, exports and scale benchmarks remain #50 gates;
a target compilation alone is not cross-host execution evidence.
