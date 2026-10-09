# Native geographic spatial-index owners

Python and Node retained frames expose one explicit index ownership seam. This is
an acceleration path for the existing geographic composition API, not a second
chart builder. Rust owns canonical source authentication, index/page admission,
projection, temporal matching, query transitions and direct/reduced tier policy.
See `geo-spatial-index.md`, `geo-scale-protocol.md` commands 17–19/24–25, and
`geo-retained-hosts.md` for the source/frame contracts.

## Authoring and storage

Python `frame.spatial_index(grid=..., max_vertices=..., read_page=...,
write_page=...)` builds synchronously, including inside a running notebook event
loop. `spatial_index_async` supports asynchronous callbacks/transport; no
`asyncio.run` is used internally. Node `await frame.spatialIndex({grid,
maxVertices, readPage, writePage, signal?})` uses the same typed Rust protocol.
Both require an explicit grid, maximum projected vertices, and external durable
page storage. There is no implicit whole-index in-memory cache. Small test maps
are fixtures, not a massive-source storage policy.

Read callbacks receive the exact Rust-issued canonical chunk or leaf ticket and
must return exact-size owning storage, including an exact backing-buffer length.
Write callbacks receive the exact generated page and must persist it and drop
borrowed views before returning. A failed write does not publish the index.
Callbacks may copy bytes into their explicitly managed durable store; they must
not retain transient views covered by the transport ticket. Hosts save the
private issued ticket and authorized byte count before invoking callbacks.
Mutating a callback receipt cannot expand allocation authority.

Python callbacks may be synchronous or awaitable on the asynchronous index path;
the synchronous path rejects awaitables. Node storage callbacks return promises.
Cancellation settles outstanding reads, writes and transport calls before their
ACK releases credit. Command 25 copies remain limited by Rust's two-copy quota;
command 24 follows durable write completion and transient-view release. Query
leaf reads reuse command 7/8. All error/cancel paths ACK issued tickets and dispose
unreturned index/query/data handles.

## Queries and independent frames

`index.update(query, sequence=..., style=exact_48_bytes)` (Python) and
`index.update(query, {sequence, style, signal?})` (Node) execute command 18,
service the indexed query, and prepare command 19 as an ordinary immutable
SceneData frame. Python also has `await index.aupdate(...)`. Camera/time/source/
layer/style/state revision rules and all limits are validated by Rust. Hosts
snapshot typed query/style framing before awaiting callbacks.

`index.current` changes only after successful Scene publication and temporary
query disposal. Failed/cancelled reads, invalid revisions and failed preparation
keep the previous frame usable. New frames keep the existing `rows`, `pick`,
`membership`, and frozen `export` APIs, full u64 feature identities and signed i64
time provenance. `index_stats`/`indexStats` reports actual pages/bytes/candidate
vertices/pass count, rather than a planner estimate. Frames retain their exact source digest/generation and index owner identity.
The existing `geo_chart(geo_layer("points", source=index, ...))` / Node
`geoChart(geoLayer("points", {source:index, ...}), ...)` paths route compile to
this indexed owner; explicit `chart.to_image(..., frame=frame)` /
`chart.toImage(..., {frame})` verifies the same owner/query/style before export.
Canonical source charts still use canonical compilation.

A `GeoSpatialFullScanRequired` exception exposes Rust's command-18 fallback;
Python `reason_code` / Node `reasonCode` is 1 for the frontier ceiling and 2 for
selected leaf reads exceeding `max_chunks`. No indexed query handle or host
baseline is created. Cumulative `max_read_bytes` and candidate
`max_rows_examined` limits remain step-time resource failures before further I/O;
they are not a reason to run a canonical scan under the same insufficient budget. It never silently runs a
canonical scan or changes the tier. Callers explicitly choose the existing
canonical source update path when still available. Closing the source or index
does not invalidate independently owned frames; frame rows/membership/picking
still authenticate original chunks using the retained callback. Closing frames
requires dropping every borrowed Scene/metadata view and consumer first.

## Scope and evidence

`tests/test_geo_spatial.py` and `packages/xy-node/test/geo-spatial.test.mjs` exercise
actual native storage/build/query, full u64 identities, old-source/index disposal,
failed durable writes and authenticated reads, mutable receipt rejection, and
cancellation release ordering. Python additionally covers synchronous notebook
loops, explicit FullScanFrontier and unreturned SceneData cleanup during delayed
read/disposal. These host tests are bounded fixtures; they do not claim measured
massive-source performance or completion of #50/#39 linked application journeys.
Browser Worker and same-source performance evidence are separate gates.
