# Retained geographic host coordinators

> Support update (#1063): Reflex-specific adapters, fixtures and journeys described
> below are retired historical evidence, not current support or acceptance gates.
> Shared native ownership, selection, binary transport and cleanup contracts remain
> required for notebook, Node/VS Code and browser hosts. Current application coverage:
> [application-consumers.md](application-consumers.md).

The internal Python `_geo_retained` and Node `geo-retained` modules coordinate
Rust `XYGQ` sessions without adding a second chart API. Public composition wiring
is owned by `components.py` and the Node composition entry point. This first
coordinator accepts one Point or MultiPoint source. It rejects other source
geometry after authenticated validation. No host performs projection, temporal
filtering, tier choice, cluster membership, picking, or feature selection.

## Explicit input and publication

`RetainedGeoSource` receives canonical manifest bytes, an exact owning-storage
read callback, and explicit query budgets. Command 4 and the sequence-zero
session drive authenticate every source chunk before exposing source identity.
Query updates receive the complete frozen camera, time predicate, all revision
counters, source identity, row/work bounds, and tier profile. Style is the exact
48-byte typed Rust framing. Commands 5/6/7/8 drive the bounded point processor;
11 prepares a durable Scene snapshot and 23 reads it. The coordinator replaces
its `current` reference only after the new snapshot is parsed successfully. Canonical,
spatial-index and hierarchy source overrides all honor the internal private-frame
publication flag on synchronous and asynchronous compilation. A private compile
returns an independent frame without replacing `current`; ordinary compilation
retains its default publication behavior. This flag grants no temporal-binding
admission to indexed or hierarchical sources.
A failed update preserves the previous frame. Every published frame also retains its immutable semantic LOD, validated source,
and exact style binding. Frame membership and picking address the frame Data
handle and its sequence, so an old visible frame remains queryable after a
failed replacement, a later publication, or source disposal. Source convenience
methods forward to the current frame; they do not address an invisible newer
query publication.

Source operations are serialized: a concurrent operation is rejected. An async
caller can cancel the active operation and wait for it to settle before another
update. There is no unbounded coordinator queue. Python synchronous construction,
update, membership and picking directly call the native ABI; they never invoke
`asyncio.run`, including when called from a notebook's running event loop.
`create_async`, `aupdate`, `membership_async`, and `pick_async` separately serve
async readers/transports. Node methods are asynchronous.

## Ownership and cancellation

Each frame, membership page, or pick reply owns an independent Rust Data handle.
Data parsing borrows the owned packet. Consumers must destroy painters and drop
all packet-derived views and copies before `close`/`aclose` (Python) or `dispose`
(Node). The coordinator clears its references before command 10 releases the
snapshot's shared derived-memory charge. It never automatically closes an old
frame when publishing a replacement. Source disposal does not invalidate these
independent snapshots. No destructor or garbage-collection callback is used as
an acknowledgment of consumer ownership.

Async source disposal cancels the active operation, waits for its read and
transport promises/tasks to settle, and acknowledges outstanding Rust tickets
before disposing the session. The read callback must return exactly the ticket's
encoded byte count with no larger backing allocation and retain no extra copy.
Callbacks are not assumed to terminate immediately on cancellation. Request and
read copies use the underlying adapter's pre-copy admission; processor/source
charges remain under the shared 128 MiB ceiling, immutable derived snapshots
under their shared 384 MiB ledger, and packets under 32 MiB. Handle and copy limits
remain those of `geo-scale-protocol.md`; these modules do not expand them.

## Exact membership and picks

Command 12 creates a bounded exact cell-membership session against an explicit
frame Data handle and its sequence. A cursor is opaque 208-byte Rust state, never a host numeric
object. Command 13 prepares its durable page. The page contains at most 4096
32-byte records with full u64 feature IDs and source rows; MultiPoint membership
is deduplicated by source row in Rust. Callers explicitly page using the returned
cursor and their next work allowance.

Command 14 uses the frame's exact successful command-11 style binding and
sequence. Its typed payload contains style, CSS coordinates, tolerance, mode,
and a maximum hit count. The response distinguishes direct provenance from a
cell hit; cells carry their ordinal and count, without invented feature IDs.
Direct u64 IDs/source rows and signed i64 times remain Python integers or Node
bigints throughout. The host does not synthesize a pick result or expand a
reduced cell into full source membership.

## Evidence and remaining integration

`uv run pytest tests/test_geo_retained.py -q` exercises real native source
validation and Scene publication inside a running notebook loop, independent
old-frame survival after source disposal, whole-packet Node/Python parity with
u64 MAX/i64 MIN, exact cursor paging, old-frame full-ID picking after source disposal, disposal during an unsettled
async read, and cancellation while membership-session disposal is unsettled
(which releases the unreturned page). These are bounded correctness proofs, not massive-source throughput
measurements. Multiple retained layers,
retained vector-layer processing and the complete #50 massive-data evidence
remain separate integration gates.

## Public composition

The existing `xyg.geo_chart(xyg.geo_layer(...), camera=...)` surface accepts
`xyg.RetainedGeoSource` as a data source. `RetainedGeoSource` is a lazy root
export; looking up ordinary geographic composition does not load `_geoscale`
or the retained coordinator. The composition module's existing dependencies
are unchanged. Source construction is explicit and authenticates the manifest
and reader before composition.

The first retained composition accepts exactly one **points** layer with
`query`, `sequence`, and `style` properties. `query` supplies every field of the
shared typed query, including exact source identity, temporal predicate,
revision counters, camera, preferred reduced profile, and work limits. The
query camera must match the chart camera's CRS, explicit boolean wrap flag,
and all seven f64 fields byte for byte; the layer ID must match the query ID.
The chart budget is an upper ceiling and must cover the source's explicitly
authored processor budget. The source's lower limit governs execution; the
chart does not expand it. A narrower chart budget requires recreating the
source with a suitable processor budget.

Uniform style is either exact 48-byte framing or a complete dictionary with
`fill`, `stroke`, `stroke_width`, `diameter`, `opacity`, and `symbol` (Node uses
`strokeWidth`). No style defaults are inserted on this path. Per-feature
patches, scalar channels, authored state, labels, legends, catalog events,
and mixed retained/static or multiple retained layers are rejected. A retained
`density` mark is also rejected: the query's preferred density reduction may
still produce the direct tier for small data, as Rust specifies, and is not
an always-density mark. The points layer may explicitly request either cluster
or density as its preferred reduction profile.

For Python, `GeoChart.compile()` retains its ordinary catalog-dictionary result
for static sources and returns an `OwnedGeoData` frame for a retained source.
`await chart.compile_async()` uses the same composition with an asynchronously
created source and returns the same frame owner. Synchronous notebook use:

```python
source = xyg.RetainedGeoSource(manifest_bytes, read_chunk, budget=query_budget)
chart = xyg.geo_chart(
    xyg.geo_layer("points", source=source, layer_id=query["layer_id"],
                  query=query, sequence=sequence, style=uniform_style),
    camera=query["camera"],
)
frame = chart.compile()
try:
    consume_scene(frame.data.scene)
finally:
    # First destroy consumers and drop borrowed scene views.
    frame.close()
    source.close()
```

Node exposes `RetainedGeoSource`, `GeoChart`, `geoLayer`, and `geoChart` from
its existing root entry. `geoChart(geoLayer("points", {source, layerId, query,
sequence, style}), {camera})` composes the equivalent request. The ordinary
`chart.compile()` returns the static catalog synchronously. Retained callers
explicitly use `await chart.compileRetained()` to obtain the owned frame and
`await frame.dispose()` after consumers release its views. This avoids making
the static compile result depend on asynchronous reader behavior.

Retained composition's `to_image`/`toImage` requires an explicit owned frame and
returns an owned accountable artifact through the
[frozen-frame export contract](geo-snapshot-protocol.md). These methods never
recompute a query. The existing zero-argument SVG convenience remains a static
source API; retained callers use `frame.export("svg")`. Python asynchronous frames
use `frame.export_async`. Static-source geographic export continues through the
existing Rust Scene exporter and returns ordinary bytes.

`uv run pytest tests/test_geo_retained_components.py tests/test_geo_components.py
-q` verifies public root access, notebook-loop synchronous publication,
asynchronous publication with fully authored style, early rejection of unsupported
properties/camera/layer/budget combinations, actual Node/Python packet parity,
and unchanged static geographic compilation/SVG output. These tests complement
the lower-level lease, exact-membership and full-ID pick evidence above.

`frame.export(format,...)` returns an owned artifact carrying exact image/HTML
bytes plus the bound XYGXv2 companion. Python adds `export_async` for asynchronous
matching snapshot transports. Native export supports SVG/PNG/PDF/JPEG/WebP/offline
HTML; no-raster WASM returns explicit Unsupported for rendering. Drop all borrowed
artifact and snapshot storage before close/aclose/dispose releases its charge.

Retained `GeoChart.to_image(...,frame=frame)` (Node `toImage(...,{frame})`) requires
an explicit owned frame from this source and exact authoring query/sequence/style.
It returns the owned artifact rather than ordinary bytes; an old advertised frame
remains legal after source publication/disposal. Omitting frame raises an actionable
compile-then-export error rather than repeating the same sequence. Ordinary static
geographic charts retain their existing bytes return type. Export never performs
source reads or chooses a newer invisible frame.

## Native retained geographic presentation

The immutable notebook, Reflex binary namespace and VS Code webview adapters
are specified in [geographic-hosts.md](geographic-hosts.md), including public
composition wiring, one-mount admission, release acknowledgment, actual host
journey evidence and the remaining native live-update/orphan-recovery gates.
This checkpoint is pending follow-up PR integration.

## Automatic browser temporal binding (#50 partial)

`await retainedChart.bindTemporal(temporalController, mode)` binds the public
`XygWasmTemporalController` to one ready retained Point/MultiPoint chart. The
explicit mode is `cursor` (default: existing Instant predicate) or `range`
(existing half-open Overlap predicate). The adapter copies exact signed i64
fields from complete Rust snapshots; it does no arithmetic on time, row filtering,
projection, LOD, membership or tile policy. Initial state, local scrubber/playback
changes and received coordination snapshots use the same path, including controllers
with no exchange group. Selection-only and playback-status changes that leave the
chosen predicate unchanged do not issue a geographic query.

The binding retains one running automatic update and one latest pending intent.
New time cancels the old read/preparation but waits for callback settlement and
Rust ticket ACK before reuse. Every changed predicate advances the geographic
query's existing time revision (with checked u64 exhaustion). All explicit
`update(query)` calls while bound inherit the latest bound time/revision; their
camera, source and budget fields still come from the explicit caller. This lets
viewport changes race playback without restoring a stale time. The existing
Rust source/optional index handle, authenticated chunk cache, admission and
immutable Data ownership remain authoritative. No additional host cache is added.
Failure preserves the last painted frame and reports through `onError`.

The returned binding exposes `whenIdle()` for work accepted so far and async
`dispose()` to detach and settle automatic work. Rebinding detaches the prior
subscription. Geographic disposal detaches before awaiting its operation chain;
temporal disposal detaches without disposing the geographic source. Independent
chart updates remain available afterward. Caller-owned temporal Workers and
controllers retain their own lifetime; a geographic binding never destroys them.
`subscribeState` on the temporal controller observes immutable Rust snapshots,
including received events and disposal, without consuming the existing event
callback or changing coordination policy. Observer exceptions are isolated.

This is a bounded browser retained-point integration slice. It does not establish
automatic mixed-layer/tile coordination, Python/Node/native-host automatic binding,
frozen attributed temporal export, complete linked selection, or #50/#39 closure.
The existing retained-source strict-CSP smoke now exercises real temporal Worker
commands, direct identity, aggregate membership, cursor/range updates, an unsettled
read racing viewport/time, failed-read recovery and independent disposal. See
[the implementation receipt](../performance/geo-temporal-binding-2026-11-06/README.md).

## Automatic native temporal binding

`chart.bind_temporal(controller, mode="cursor")` in Python (a running asyncio
loop is required) and `chart.bindTemporal(handle, mode="cursor")` in Node bind
one canonical retained points composition to native temporal snapshots. `range`
selects the existing half-open Rust predicate. No temporal values or feature
identities are converted to floating point. Each time change advances the
geographic time revision independently of controller revisions, including remote
applies. Selection/playback-only changes with the same effective predicate do
not query geography. Initial binding always schedules one query.

The binding admits one running query and one latest desired snapshot. `set_camera`
/ `setCamera` replaces the complete authored camera and advances its revision.
A newer camera or time invalidates running work at publication; admitted native
reads finish before the latest query runs. This is bounded stale suppression,
not immediate interruption of a storage callback. Failures leave the accepted
frame and its exact provenance intact and are available as `binding.error`.
A notification arriving between pump completion and its completion reaction still schedules the newest intent; idle waits include that successor. No automatic retry of the same failed intent runs. Revision exhaustion fails closed.

Python `await binding.snapshot()` returns `(chart, frame)`; Node returns
`{chart, frame}`. The chart is the exact public composition that produced this
frame, so existing export and native host adapters consume it without a second
renderer. Frames are independently retained Rust Data owners. Consumers must drop
borrowed views before closing them. The binding copies authored query, camera and style values at construction.
Each snapshot returns isolated nested composition values while retaining the
same opaque source owner; mutating one snapshot cannot change later snapshots
or future styles. The binding never exposes or transfers its
private accepted owner, never publishes into the source's batch `current`, and
releases only its own superseded frames. Failed cleanup retains its owner for
retry before admitting another query. One binding per source prevents competing
sequence ownership; independently constructed sources can run concurrently.

`when_idle` / `whenIdle` drains latest work. `aclose` / `dispose` unsubscribes,
suppresses pending publication, drains admitted reads, and releases private
owners. Controller disposal also initiates this cleanup; explicit binding cleanup
awaits it. Independent snapshots survive either controller or binding disposal. Python controller notifications arriving from another thread dispatch to the
binding's creating event loop before changing desired state or creating tasks.
Source-initiated cancellation settles as a binding operation error and preserves
the accepted snapshot; explicit binding cleanup still releases its private owner
and source registration. Cancelling a caller waiting for idle does not cancel the
admitted pump. Reader-raised cancellation is an operation failure that retains
the accepted frame. A terminally cancelled pump does not block private-owner
teardown, including cleanup from a caller cancellation handler. Native Node
unsubscribe closures are idempotent and cannot remove
a later observer set for the same controller handle.
The source remains caller-owned. Source disposal can make future queries fail
without invalidating accepted snapshots. Static/batch compilation stays synchronous.
Python sync readers run in a worker thread so the notebook event loop can accept
new snapshots while native work proceeds. Async readers retain their existing
loop and cancellation semantics.

This slice supports canonical retained points (including Rust cluster/density
reduction). Indexed/overview/hierarchy/mixed-tile automatic bindings and direct
low-level Python ABI mutations outside the controller wrapper are not covered.
Snapshot callers acquire an exact frame for existing host/view
or export routes. Automatic replacement of an already mounted canonical or
explicitly framed `GeoSpatialIndex` notebook or Node/VS Code view is specified in
[mounted temporal hosts](geo-mounted-temporal-hosts.md),
using the existing XYGH CAS and retirement ACK contract.
This does not establish all-host accessibility, complete attributed frozen
exports, massive/five-view/competitor acceptance or M6/#50/#39 closure.

### Bounded Python temporal notification ingress

Python snapshot and mounted temporal bindings share the protected latest-state
inbox described in [mounted temporal hosts](geo-mounted-temporal-hosts.md).
Foreign notifications retain one copied native snapshot and one owning-loop
wakeup rather than an unbounded callback list. Owner-loop updates cannot be
replaced by an older queued nonterminal snapshot; pending disposal wins over
late nonterminal delivery. The existing native read pump, frame leases, exact
predicates and source exclusion/cleanup semantics remain unchanged.
