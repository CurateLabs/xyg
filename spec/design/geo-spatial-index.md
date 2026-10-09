# Retained geographic spatial sidecar

Dossier §27/§28. This engine slice adds an authenticated, rebuildable external
index for retained Point/MultiPoint sources. Canonical XYGK chunks and their
validated XYGI source manifest remain authoritative. It preserves existing
screen-bin direct/cluster/density policy; it does not introduce a geographic
aggregate pyramid or an approximate temporal tier.

The current product protocol, host storage adapters, actual native/WASM indexed
parity and massive warm-query evidence are subsequent integration gates. This
engine implementation alone does not establish interactive 100M/1B performance
or close #50. Whole-world queries still visit all eligible vertices. Directory
selection scans bounded page metadata; the current cost is O(directory pages +
candidate vertices), not a demonstrated O(visible tiles) product path.

## Build and validation authority

`geo_spatial_build_session::GeoSpatialBuildSession` consumes a privately
validated `GeoSourceManifest`, `GeoSpatialOptions`, `QueryBudget` and cumulative
vertex ceiling. `step_with_cancel` requests one exact authenticated source read
or one exact sidecar write. `supply`, `release_read`, `write_bytes` and
`acknowledge_write` require the original session nonce and ticket. A successful
write ACK means the host has retained immutable exact page bytes and has dropped
transient borrowed/copy buffers. `finish(&mut self)` publishes the private
`ValidatedGeoSpatialIndex` only after all canonical chunks and final partial
pages have been processed and every loan acknowledged. Calling finish early
fails without consuming the session. Hosts must keep sessions alive while
`has_outstanding_io()` is true, including after cancellation.

The default Mercator grid is 16×16. One partial wire buffer per cell is carried
across source chunks. Records append in original source-row/vertex order. A full
818-record page is flushed through the write ticket before further folding;
remaining pages flush in cell order at end. Directory entries are grouped by
cell, then ascending page ID. Original chunks need no spatial ordering and no
whole-source sorting or owned array is created. MultiPoint vertices retain
original row provenance and original chunk-global vertex ordinal. Null/empty
geometry contributes no vertices. Full u64 feature IDs, duplicate IDs, signed
half-open intervals and optional scalar f64 bits are retained literally. Scalar
preservation does not yet add scalar-driven retained styling.

`build` is the synchronous ticket adapter. `validate_import` first checks the
bounded directory framing and exact source identity, then rebuilds every page
from every authenticated canonical chunk, compares each imported page byte for
byte, and compares the complete canonical directory. Hashes or authored
summaries alone confer no pruning authority. Missing pages, omitted records,
forged bounds/time summaries and altered payloads fail even when outside the
current camera. Cold imported validation is linear source work. After
validation, changed storage bytes fail exact length/digest checks before use.
The existing eight-byte BLAKE2s identity scheme is a deterministic corruption
and identity contract, not an adversarial cryptographic authentication service.

## Exact indexed queries

`GeoIndexedQuerySession::new` accepts an `Arc<ValidatedGeoSpatialIndex>`, camera,
time, current `GeoLodOptions`, layer/style/state identity and cumulative read
ceiling. It returns `None` for `FullScanFrontier` when more than 256 populated
candidate leaf streams are required; callers must use the existing canonical
full-scan path. Default cross-chunk compaction makes each grid cell one stream,
independent of source chunk count. No records are silently thinned.

`GeoViewport::point_index_bounds` conservatively bounds the front-ground camera
footprint in Mercator. Failed/horizon inverse bounds retain all cells. Bearing,
pitch, wrap and outward numerical padding are respected. Both antimeridian
columns admit the union of both seam footprints after latitude pruning, even
without wrap: shared cross-CRS conversion can alias -180 to +180. Distant
viewports admit neither column; seam-visible views overfetch both rather than
changing shared projection semantics. The overflow sentinel
is always a candidate; canonical finite coordinates may exceed the projection domain, so the
sentinel preserves shared projection/error semantics. Coarse grid cells and conservative bounds can still select much
more than the visible geometry.

The query holds one decoded page head per selected leaf and merges heads by
original source-row and vertex ordinal with a bounded heap. It refills an
exhausted stream before advancing other heads. Time summaries prune page reads;
per-record exact time filtering precedes projection and projected-work admission.
Records feed the extracted shared `GeoPointLod` vertex accumulator. Visibility,
LOD hysteresis, screen-bin membership, count and source-order f64 centroid sums
therefore use one engine policy. Aggregate queries perform the existing second
pass over selected pages. The canonical binding key, visible output and ordinary
XYGS Scene bytes match a canonical full scan; projected-work/read telemetry can
be lower and is deliberately not an output-equality assertion.

`step_with_cancel`, `supply`, `release_read`, `cancel` and `finish` mirror the
build lifecycle. Cancellation is checked inside final folds and after pass and
output transitions before publication. Stale tickets cannot advance a newer
session. Failed/cancelled pending reads retain their reservation until exact
release ACK; accepted old output remains independently leased and unchanged.
`process_indexed` is the synchronous adapter and passes cancellation into the
same step/fold body.

## Resource contract

All resident engine storage uses the existing shared global 128 MiB
`GeoProcessorLease` ledger; there is no additional pool or per-session 128 MiB
allowance. Old validated indexes/results and new candidates coexist within this
same ceiling. Host immutable external storage is canonical application storage;
host loan copies must obey the ticket capacity promise and be dropped before
ACK. The contract is bounded live processor storage, not OS RSS or persisted
sidecar size.

Build admission reserves source metadata clone, all cell partial capacities
(default approximately 16 MiB), control overhead, actual geometric directory
capacity (including old/new growth) and conservative source read/parse work
before allocation or I/O. A chunk promises eight times its encoded bytes plus
16 KiB; each pending write promises three 64 KiB buffers. Legal maximum-size
source chunks may be rejected with `ResourceLimit` when these concurrent
reservations do not fit; the index does not relax canonical parser bounds.
Directory wire bytes are capped at 32 MiB. Grid dimensions must be powers of two
from 1 through 256, but larger partial-buffer promises can reject before I/O.

Query preflight reserves shared LOD worst-case storage, up to 256 decoded page
heads, heap/control capacities and input scratch before reading. Cumulative
read/work counters are u64; page/chunk resident lengths remain usize. Source,
read, vertex, page and directory ceilings fail explicitly. Encoders return an owned `GeoSpatialDirectory` with borrowed `as_slice()` access
and no unleased extraction; repeated encodings retain separate three-copy
reservations until each directory is dropped. Imported validation reserves its
concurrent wire copies through the same global ledger.
The index is dropped before its lease; published results keep their lease until
their output storage is dropped.

## Canonical little-endian framing

All reserved bytes are zero; lengths are exact, checked before decode. Page IDs
are flush-order identities and need not equal directory positions. A cell is
`y * grid + x`; `u32::MAX` is a conservative overflow cell, never a feature ID.
Mixed-chunk page marker is `u32::MAX`.

XYIX v1 directory: 128-byte header, followed by 96-byte entries.

| Header offset | Field |
|---|---|
| 0, 4 | magic XYIX, u32 version 1 |
| 8, 12, 16 | u32 grid, CRS, geometry |
| 24, 32, 40, 48 | u64 generation, source rows, 8-byte source digest, u64 page count |
| 20..24, 56..128 | reserved |

| Entry offset | Field |
|---|---|
| 0, 8, 12 | u64 page ID, u32 mixed-chunk marker, u32 cell |
| 16, 20, 24 | u32 encoded length, u32 record count, 8-byte page digest |
| 32, 40 | first/last original source-row u64 |
| 48, 56, 64 | u32 time flags, i64 minimum start, i64 maximum end |
| 52..56, 72..96 | reserved |

Time flags bit 0/1 indicate bounded start/end; unbounded values encode zero.
Any unbounded member endpoint makes that page endpoint unbounded.

XYIP v1 page: 64-byte header plus 80-byte vertex records, at most 65,536 bytes.
The header contains magic at 0, u32 version at 4, u64 page ID at 8, u32
mixed-chunk marker at 16, u32 cell at 20, u32 record count at 24, then reserved
zero bytes 28..64. The digest uses `xyg-spatial-page-v1` domain.

| Record offset | Field |
|---|---|
| 0, 8 | u64 original source row, literal feature ID |
| 16, 20, 24 | u32 original chunk, row, chunk-global vertex |
| 28 | u32 presence flags: start bit 0, end bit 1, scalar bit 2 |
| 32, 40 | original x/y f64 bits |
| 48, 56, 64 | i64 start, i64 end, scalar f64 bits |
| 72..80 | reserved |

Absent endpoints/scalars encode zero. Scalar NaN payloads, signed zero and
infinity survive canonical source and sidecar readback; they do not reach paint
vertices. No fill/line/polygon index or temporal aggregate pyramid is claimed.

## Evidence and remaining gates

Focused Rust fixtures compare direct/cluster/density keys, full IDs, visible
records, counts, centroid bits and Scene32 bytes against canonical full scans.
They cover unordered sources, MultiPoint/null rows, signed half-open time,
source/camera CRS combinations, both wrap modes, pitch ±60/bearing, cross-chunk
full-page flushes/scalars, corruption/omission, stale tickets, cancel/ACK,
retained old output, global contention and explicit frontier fallback.

Remaining product gates include protocol/ABI and all-host exact ticket storage,
actual wasm32 parity, indexed immutable frame/membership/export authority,
warm 100M/1B performance and memory measurements, general geometry LOD,
retained scalar/style/state semantics and the full linked-view matrix.
