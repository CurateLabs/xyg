# Frozen geographic snapshot and export

`geo_snapshot.rs` is a bounded #50 foundation for freezing one complete
geographic Scene and its provenance. It contains no filesystem, network,
Arrow or third-party dependency. Encoding/decoding works without raster
features; native static export follows the existing `raster` feature gate.
This contract does not complete #50 or establish scale/performance evidence.

The canonical geometry, camera and identity authorities remain
[geospatial.md](geospatial.md), [geo-retained-source.md](geo-retained-source.md)
and [geo-lod.md](geo-lod.md). The process accounting contract is
[geo-tiles.md](geo-tiles.md), following dossier §27/§29. Geographic comparison
scope remains [geographic-capabilities.md](geographic-capabilities.md).

## Immutable identity and attribution

`GeoFrozenIdentity` records the canonical `GeoViewportRebuildKey`, shared
`TimePredicate` (all/instant/half-open window in signed i64 UTC microseconds)
and ordered layer records. Each layer records exact u64 layer/source IDs,
source generation, layer/style/state revisions, source digest, source row count,
geometry kind and CRS. Layer order is paint order, never sorted by ID. Source
generations are nonzero and identify immutable content/configuration; changed
source content, locator or attribution needs a new generation. Duplicate layer
IDs, invalid time windows and noncanonical camera keys are rejected.

Direct references contain `(layer_id, original_source_row, full_u64_feature_id, chunk_index, row, vertex)`.
Distinct source rows with the same literal ID remain distinct, including
u64MAX and annotation-shaped IDs. Reduced cells carry kind, grid dimensions,
cell index, source-row membership count and an optional exact `QueryCursor`;
they have no invented representative feature ID. Cursor generation/digest
must match the referenced frozen source, and row/chunk fields obey the shared
source limits. A deterministic BLAKE2s8 provenance token binds each reduced
reference to the complete camera/time/layer identity and cell/grid/count.
Tokens and artifact digests link content; they do not authenticate untrusted
data or authorize source access.

Paged references preserve the existing membership protocol, including its
query digest. They do not embed all members, promise an offline drill result,
or cause a read. A future membership resolver must reopen the exact source
and validate the complete frozen LOD identity/cursor. The compiler/coordinator
must supply truthful source/Scene relationships and every required attribution;
the snapshot does not rediscover which network provider produced pixels.

Attribution is a bounded literal UTF-8 string, never HTML. Every recorded
attribution must already have a matching canonical Scene label satisfying the
shared `SceneDocument::has_visible_attribution` policy: exact text, no controls,
zero rotation, font size at least 8 CSS pixels, alpha at least 128/255, and its
anchor-aware shared text-advance bounds wholly within the viewport. The vertical
extent is `y-font_size..y+0.3*font_size`. Missing, invisible, offscreen, rotated
or undersized labels fail freeze/decode. Hosts must let Rust composition place
these labels before freezing; the snapshot does not implement a second label
layout. Thus static artifacts retain painted attribution even when separated
from their companion metadata.

`freeze(cache,scene,identity,direct,membership,attributions,budget)` validates
the Scene and metadata, binds the Scene viewport dimensions to the exact camera
and produces immutable owned bytes. All fields owning data are private; callers
receive borrows. `decode(cache,bytes,budget)` admits the complete envelope before
typed allocations and reruns the same validation. No malformed input is repaired.

## XYGX v2 binary framing

All numeric fields are little endian raw integers/f64 bit patterns. There are
no JSON numeric payloads, platform pointers or implicit fetch instructions.
The exact concatenation is header192, layer records80 each, direct records48,
membership records96, compact LOD descriptors/count planes, attribution records, an optional tile authority blob and the canonical Scene32. There is
no padding, overlapping range or trailing data. Unknown versions/flags and
nonzero reserved bytes reject the envelope.

| Header offset | Type | Meaning |
| ---: | --- | --- |
| 0 | bytes4 | `XYGX` |
| 4,8 | u32,u32 | envelope version2, Scene version32 |
| 12 | u32 | artifact binding present0/1 |
| 16,24 | u64,u64 | total envelope bytes, Scene bytes |
| 32,36,40,44 | u32×4 | layer/direct/membership/attribution counts |
| 48 | u32 | attribution record bytes including their length prefixes |
| 52 | u32 | time kind0=all,1=instant,2=window |
| 56,64 | i64,i64 | instant/start and end; inactive words canonical zero |
| 72,76 | u32,u32 | camera CRS, world-wrap0/1 |
| 80..136 | f64 bits×7 | center x/y, zoom, width/height, bearing, pitch |
| 136 | u64 | camera revision |
| 144,148 | u32,i32 | artifact format and quality; zero without binding |
| 152 | f64 | artifact scale; zero without binding |
| 160 | u64 | artifact byte count; zero without binding |
| 168 | bytes8 | artifact content digest; zero without binding |
| 176 | u64 | time revision |
| 184 | u32 | compact LOD descriptor count |
| 188 | u32 | tile authority blob byte count; zero for retained source snapshots |

Layer80: u64 layer ID/source ID/generation/layer revision/style revision/state
revision at0/8/16/24/32/40; source digest8 at48; u64 source row count at56;
u32 geometry/CRS at64/68; zero bytes72..80. Direct48: u64 layer ID, original
source ordinal, literal feature ID at0/8/16; u32 chunk/row/vertex at24/28/32;
zero36..48. Retained-frame source IDs are locator-neutral zero; source digest
and generation carry immutable content authority.

Membership96: u64 layer ID at0, derived provenance token8 at8; u32 cell/columns/
rows/kind at16/20/24/28 (kind0 cluster,1 density); u64 member count at32; u32
cursor-present at40; zero44..48; cursor u64 generation at48, source/query
digests8 at56/64, u32 chunk index/row at72/76; zero80..96. All cursor bytes
are zero when absent. Grids obey the shared cluster/density cell ceilings and
the cell is in range; nonempty source-row member count cannot exceed its
source's row count. Decoding recomputes and compares the provenance token.

Each compact descriptor is232 bytes followed immediately by its u64 count plane:
full LOD key160 (the same exact key layout as membership), u64 cell/visible-vertex/
projected-vertex counts at160/168/176, exact uniform style48 at184. The full grid
is CSS top-row-first including empty cells. Counts describe **visible vertices**,
not distinct source rows; MultiPoint counts may exceed source rows. Their sum
must equal visible vertices. There is no per-cell invented feature ID or embedded
full-source CSR. Membership remains an exact separately paged source-row query.
Direct tiers retain the same full key and style with an empty count plane and
zero grid dimensions; their visible count equals their direct provenance records.
All camera/time/source/layer/style/state key fields must match the envelope.

`freeze_lod` borrows an immutable published SceneData authority, records source
and camera/time revisions, preserves exactly its generated Scene bytes and
never recompiles or reads sources. It preleases direct-provenance scratch under
the128MiB freeze limit before allocation. Native frozen export supports all six
formats; no-raster builds return explicit Unsupported for export while retaining
snapshot encoding/decoding.

Each attribution record is u32 UTF-8 byte length followed by those exact bytes.
Strings preserve input order and Unicode; whitespace-only/control-containing/XML-forbidden
strings are rejected. The trailing Scene is decoded by `SceneDocument`,
including explicit Triangle6/Segment7 primitive boundaries and Image sidecars.
The snapshot adds no geometry or renderer policy to those records.

## Static artifacts and stale rejection

`require_identity(expected)` checks exact camera/time/ordered layer/source/
style/state identity. Native `export(cache,expected,format,scale,quality,budget)`
does this check before rendering or allocating output. A changed identity fails
with `Stale`; there is no export of the latest frame under an old snapshot's
provenance. Export never performs I/O or re-queries canonical sources.

The existing `scene_static_export` consumes the frozen Scene for SVG, PNG,
PDF, JPEG and WebP. Quality is1..100, scale is finite/positive, and raster
dimensions use `ceil(camera_dimension*scale)`. SVG/PDF retain the existing
consumer's vector dimensions; scale is still recorded and preflighted. The
JPEG flatten-over-white, PNG encoder selection and WebP policy are unchanged.

`GeoFrozenArtifact` privately owns artifact bytes and a binary companion
snapshot with format/scale/quality/byte-count/BLAKE2s8 binding. Borrow-only
accessors prevent moving buffers away from their memory lease.
`verify_artifact(bytes)` requires the exact count/digest, rejecting a swapped
or modified artifact. The companion is the complete provenance contract.

SVG additionally embeds base64 XYGX in `metadata#xyg-frozen-snapshot` and
XML-escaped literal attribution in `metadata#xyg-attribution`. PNG embeds base64
XYGX in a valid uncompressed `iTXt` chunk with keyword `XYG frozen snapshot`,
using the existing Rust PNG chunk/CRC writer. Embedded snapshots have no
artifact binding, avoiding a circular digest; they contain the same frozen
Scene and identity. The binary companion binds the final artifact including
its embedded metadata.

PDF/JPEG/WebP retain painted attribution but do not embed arbitrary geographic
metadata in this slice. Their output contract is the artifact paired with its
XYGX companion; writing just the image/PDF discards machine-readable provenance.
HTML format5 wraps the same metadata-bearing SVG in a data image and includes
the unbound XYGX in a template plus literal escaped attribution in a caption.
Its CSP permits only data images and blocks scripts, providers, external fonts,
forms and base changes. This is a static frozen replay; reopening does not
re-query sources or change camera/time. No external script URL, MapLibre import or network
permission is introduced by this module.

## Limits and ownership

| Resource | Hard ceiling |
| --- | --- |
| Envelope bytes | 32 MiB |
| Scene bytes | 16 MiB |
| Snapshot validation/retained reserve | 128 MiB |
| Layer records | 64 |
| Direct references | 65,536 |
| Paged membership references | 4096 |
| Full compact grid | 196,608 cells; cluster at most32,768 |
| Attributions | 64, each at most4096 UTF-8 bytes |
| Static artifact | 64 MiB |
| Export pixels | 2,000,000 |
| Scaled dimension | 1..65,535 |

All limits apply together; the peak can reject an envelope below its individual
byte ceiling. Encode/decode preflight reserves `8*envelope_bytes+65536` before
copying/decoding. Native export preflights `32*envelope_bytes+64*pixels+1MiB`
against the supplied budget and the shared 384 MiB tile/derived ledger. The
bound includes decoded Scene, raster/codec scratch, metadata/base64, old/new
output copies and fixed font/validation work. Surrounding retained sources,
other sessions and borrowed input buffers remain the coordinator's reservation
responsibility under the separate shared 128 MiB processor phase.

Snapshot and artifact buffers drop before their `GeoDerivedLease`. Reservations
survive cache destruction and release only when their owned snapshot/artifact
drops. Rejected decode/export releases candidate reservations; old live output
retains its charge. Independently copying borrowed output requires an additional
coordinator reservation. The lease reports a conservative reserved peak, not
OS RSS or a measured codec-memory result.

## Reproduction and remaining gates

```bash
cargo test -p xyg-engine --offline geo_snapshot::tests -- --nocapture
cargo check -p xyg-engine --offline --no-default-features
cargo clippy -p xyg-engine --offline --all-targets -- -D warnings
```

Tests use actual Scene32 Scatter/Triangle/Segment output, full-u64 duplicate
source IDs, extreme i64 windows, exact roundtrip bytes, every stale identity
dimension, malformed framing/UTF-8/Scene/provenance, visible-attribution
negative controls, an exact byte-budget boundary and memory lifetime after
cache drop. Native tests export all six formats, decode PNG pixels and its
ancillary CRC/text, prove SVG escaping and verify companion/content linkage.
Public Python/Node/browser snapshot transport, source-backed
paged membership integration, export orchestration, provenance accessibility
and measured scale/size/memory evidence remain #50 integration gates.

The public retained-frame bridge is [geo-snapshot-protocol.md](geo-snapshot-protocol.md).
`frame.export(format)` and retained `GeoChart.to_image(...,frame=frame)` return an
owned artifact with image/HTML bytes and paired XYGX metadata. The caller drops
all borrowed bytes/views before close/aclose/dispose. Explicit old frames remain
exportable after source updates or disposal; the chart convenience path requires
that frame's exact source, authoring query and uniform style. Omitting frame never
recompiles the current sequence. Ordinary geographic export continues returning bytes.

## Immutable mixed tile snapshots

`freeze_tile` borrows the Rust-owned TileFrameData, preserving its exact catalog
Scene and XYGU receipt. It adds no host metadata or generated source revisions.
Tile snapshots contain no ordinary layer/direct/membership/grid records. Their
header time is All and camera/time revisions are zero: the receipt explicitly
records external time and unspecified global camera/time revisions. These values
are not evidence of a shared signed-time filter. Each XYZ key retains its actual
optional signed i64 source time window. Wiring a shared temporal predicate into
mixed tile composition remains a #50 integration gate.

The optional blob begins with64 bytes: u32 version1@0, kind1TileCatalog@4,
flags3@8 (external time plus unspecified camera/time revisions), source/key
counts@12/16, zero20..24, receipt bytes u64@24, zero32..64. Each source uses the
canonical112-byte tile source config plus config digest8@112, zero120..128,
then its exact locator/attribution UTF-8 bytes. Each96-byte provenance record is
the canonical80-byte tile key, config digest8 and payload digest8. The exact
XYGU receipt follows without padding. Source config and payload digests use the
shared tile protocol domain-separated BLAKE2s8 grammar. Decoding verifies config,
key, attribution and receipt digests and exact trailing Scene identity.

Raster source kind0 is an image identity; vector kind1 retains geometry feature
IDs through the catalog. Raster provenance never fabricates a feature ID.
Catalog layer/style/source metadata stays in the exact typed XYLM receipt;
authoring supplies no generation for those foreground columns, so freezing
cannot invent one. Immutable FrameData survives cache disposal.

Repeated exports of one Frame produce identical artifacts and companions. The
receipt preserves private cache handle/epoch as transport context; independently
created Python/Node frames compare canonical Scene, config/key/payload stamps and
pixels while excluding only that ephemeral receipt handle context. The frozen
bytes themselves are never normalized.
