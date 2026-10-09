# Geographic tile selection and cache contract

`geo_tile_cache.rs` is the platform-neutral #50 tile-policy foundation. It
selects a bounded camera window, authorizes owned read buffers before I/O,
validates raster/vector payloads and atomically publishes complete frames.
Native and WASM adapters must call this same policy. The module introduces no
filesystem, network, browser or third-party dependency. Public transport,
composition, temporal filtering, LOD production and massive-scale measurements
remain integration work; this foundation alone does not complete #50.

The source/precision authority is [geospatial.md](geospatial.md) and the
retained-source processor is [geo-retained-source.md](geo-retained-source.md).
Dossier §22/§27/§28 require bounded source reads, canonical CPU geometry and
explicit tier decisions. Geographic capabilities and comparison gaps remain
in [geographic-capabilities.md](geographic-capabilities.md).

## Explicit source configuration and identity

`GeoTileSource` names a full u64 source ID/generation and layer ID, layer/style
revision, optional half-open signed i64 time predicate, payload kind, available
zoom range and `GeoLimits` payload bounds. Generation identifies immutable
source content and configuration: changing a locator, URL template, attribution,
payload bounds or underlying bytes requires a new generation. Layer/style/time
changes likewise create distinct keys. Hosts must not reuse a generation for
new source content.

`GeoTileLocation::Local` carries an application-owned opaque nonempty locator.
`Network` carries an explicit HTTP(S) template containing `{z}`, `{x}`, `{y}`
and mandatory nonempty attribution. Each text value is at most 4096 UTF-8 bytes.
There is no default provider, implicit URL, fetch or remote asset. The host
executes the configured request after Rust authorizes it; the renderer displays
the complete frame's attribution strings. Duplicate `(source_id,layer_id)`
configurations within one selection are rejected.

`GeoTileKey` includes source ID, generation, layer ID, layer/style revisions,
time predicate, kind and XYZ zoom/x/y. Thus style/temporal changes cannot reuse
an old payload accidentally. The cache does not invent missing temporal values
or filter features inside an XYGD tile; the source producer must construct the
requested predicate's payload and the enclosing coordinator must validate that
relationship before composition. XYGD retains the shared GeoColumn's original
f64 coordinates, topology, nulls and exact u64 IDs.

## Camera selection

`select_tiles(&GeoViewport, sources, limits)` reuses the Rust camera's
perspective ground footprint and rebuild key. It converts the same camera to
Mercator bounds and selects tiles intersecting that footprint's axis-aligned
bounds. Bearing/pitch can conservatively overfetch; the policy does not omit
visible ground to meet a budget. Dateline columns wrap to canonical X, polar Y
clamps to the certified Mercator extent and disabled world-wrap clips X to the
world. The returned camera key records the full camera identity.

Tiles use the existing `tiles::TILE_DIM=256`. GeoViewport's world is 512 CSS
pixels at camera zoom0, so XYZ zoom is `floor(camera.zoom+1)`, clamped to the
source's explicitly declared `min_zoom..max_zoom` within `0..=25`. Source-level
clamping is recorded by each returned XYZ key. There is no silent arbitrary
coarsening when the requested window cannot fit. Rust checks the number of
keys before allocating the selection or authorizing reads. An impossible
window returns `GeoError::ResourceLimit`, retaining the previous frame.

Selection allocates only bounded visible keys, not a pyramid directory or a
whole-source array. It is independent of source row count. This is camera/tile
selection rather than a proof of an out-of-core feature index or responsive
billion-row pan/zoom.

## Hard resource ledger

| Resource | Hard ceiling / default |
| --- | --- |
| Geographic CPU policy | 512 MiB total |
| Shared tile/derived process pool | 384 MiB across all caches and derived leases |
| Source/query/consumer phase reserve | 128 MiB, shared with retained-source processing |
| Metadata reserve per cache | 1 MiB, included in the 384 MiB pool |
| Resident tile entries | 128 |
| Current requests plus retired live read leases | 64 |
| Visible tile keys across all selected sources | 64 |
| Selected sources | 16 |
| Published views per shared cache | 8; five views can reuse one source/cache |
| Active candidate frame | 1 |
| Input tile payload | 8 MiB |
| Raster dimensions | exactly 256×256×4 straight RGBA8, image-top-first |

Limits can be lowered but not raised past these ceilings. Cache construction
and `begin_frame` require an `other_live_bytes` reservation no greater than
128 MiB. The enclosing process coordinator must include every surrounding
source/query/consumer allocation in that phase and serialize active processing;
this module does not discover or account arbitrary application allocations.
The fixed 128 MiB reserve is never lent to tile or derived payloads. Retained-source
metadata and chunk decode use their existing 32/96 MiB limits within this
reserve. The tile pool's global atomic admission prevents independent cache
objects from each receiving 384 MiB. Engine-internal `reserve_derived(bytes)`
returns a noncloneable `GeoDerivedLease` before Scene, painter, raster or
transfer storage is allocated. Both old and candidate derived storage count
against the cache's local ceiling and the same global 384 MiB pool. Its charge
and ledger are private; adapters have no arbitrary release/update operation.
Derived leases can outlive the cache. The consuming owner must keep its exact
capacity/peak within the reserved amount and drop all storage before dropping
the lease. This is an allocation preflight seam, not an automatic measurement
of an arbitrary buffer's size.

Before I/O, raster reads reserve `2*max_payload_bytes+8192`; vector XYGD reads
reserve `4*max_payload_bytes+17*max_features+8192`. This covers the owned input
buffer, shared descriptor decoder peak, generated identities even for all-null
rows, canonical planes and bounded validation/metadata scratch. Input capacity
and retained capacity are counted, not just logical lengths. Raster residency
retains the entire authorized read allocation; vector residency keeps a
conservative `2*encoded_length+17*features+8192` charge after decode. The initial
peak is released only after temporary allocations have been dropped.

Resident entries and all published frames' pinned working sets count against
both byte and entry ceilings. The old frame remains pinned while replacement
requests are admitted, so replacement requires room for both the old payload
and the candidate's full decode peak. If that room does not exist, admission
fails before I/O. Eviction chooses the oldest unpinned entry outside the new
selection; no pinned working-set overshoot is permitted. Existing native
`TileStore` allows compose-time pinned overshoot under its separate budget and
is therefore not the implementation of this hard geographic ledger. If it is
used by a future source backend, its buffers must fit the enclosing reserved
phase as well.

## Requests, cancellation and atomic publication

1. `GeoTileCache::new(limits,other_live_bytes)` reserves cache metadata.
2. `begin_frame(view_id,camera,sources,other_live_bytes)` validates selection,
   plans deterministic LRU eviction, reserves every missing tile's peak and
   returns a monotonically increasing epoch. Admission failure leaves current
   frames and still-authorized requests intact, except reaping abandoned
   reads whose buffers have already been dropped.
3. `requests()` exposes bounded descriptors with a cache/epoch/ordinal/key
   identity, input ceiling and reserved bytes.
   `request_source(ticket)` returns the corresponding explicit source config.
4. `start_read(ticket)` authorizes exactly one owned read lease and allocates
   its bounded input buffer. The host fills `GeoTileRead::bytes_mut()`; it
   cannot extract or clone this buffer apart from its reservation.
5. `publish(read,GeoTileData)` consumes that lease, validates exact raster
   dimensions/length or shared canonical XYGD geometry and declared
   feature/vertex bounds, then caches the valid payload. It returns whether
   the current candidate has all its tiles. A payload failure cancels that
   candidate, preserving every published frame.
6. `prepared_frame(epoch)` borrows the complete current candidate's view ID,
   epoch, camera rebuild key, tile keys and source configurations while the old
   frame remains pinned. The enclosing composer reads candidate payloads via
   `payload(key)`, reserves all derived storage and stages Scene/paint output.
   Composition/render staging failure drops candidate output and calls
   `cancel(epoch)`, preserving the old frame.
7. After successful composition/render staging, `commit_frame(epoch)` atomically
   replaces that view's camera/key/attribution table. It succeeds only for the
   current complete candidate. Composition and paint consumers themselves are
   integration work outside this cache module.

`cancel(epoch)` cannot cancel a newer candidate. Stale publication drops its
input and releases its reservation without changing the new frame. Cancelled
or superseded requests with outstanding reads continue to reserve their full
peak and count toward the 64-read window until the buffers are actually dropped
or consumed. Abandoning a live read causes its incomplete candidate to be
cancelled on the next admission/read operation; requests cannot remain stranded
without their read lease. Cache destruction transfers outstanding reservations
to the read leases, whose drop order frees the input buffer before releasing
the process charge.

`frame(view_id)` and `payload(key)` borrow published/cache state; copying those
values into independently retained application memory needs a surrounding
reservation. `drop_view` releases that view's pins and cancels its active
candidate; ordinary eviction can then reclaim the payload. `stats()` reports
charged/resident/pending/derived bytes, global tile/derived-pool charge,
surrounding phase reservation, entries, requests, read leases and views. The
global number is a reserved tile/derived ledger, not an OS RSS measurement.

## Validation and remaining integration

```bash
cargo test -p xyg-engine --offline geo_tile_cache::tests -- --nocapture
cargo clippy -p xyg-engine --offline --all-targets -- -D warnings
```

The tests cover dateline/poles/bearing/pitch with independent visible-ground
samples, explicit provider attribution and every revision key dimension,
one-byte-too-small replacement admission, exact-boundary admission, pinned
entry rejection, real LRU eviction, five-view reuse, shared process contention,
malformed vector/invalid raster rejection, full u64 identity, abandoned/foreign
reads, the retired-read window limit, duplicate reads, cache destruction and
stale completion after a newer published frame, precommit composition failure,
derived local/process contention and derived leases surviving cache destruction.
These prove bounded Rust
selection/cache policy. Native/WASM request transport, source-to-tile indexing,
temporal/scalar aggregation, raster/vector Scene composition, shell attribution
DOM and failure staging, cancellation scheduling, public APIs and measured
multi-scale/multi-view performance remain required before #50 can close.
