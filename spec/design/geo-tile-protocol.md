# Geographic tile transport v1

`geo_tile_protocol` exposes the existing shared Rust tile cache and mixed Scene
compiler to native and WASM hosts. Hosts supply configured I/O bytes and commit
only after staging the Rust painter. They do not choose tiles, generate geometry
or invent providers. Native ABI383 exports `xyg_geo_tile_execute/read`; WASM33
exports `xyg_wasm_geo_tile_execute/read` plus trusted
`xyg_wasm_geo_tile_frame_prepare(instance,transportSequence,dataHandle,epoch)`.
Retained WASM ownership first acquires the credit in [geo-transport.md](geo-transport.md).

All integers are little endian and full u64 identities stay typed. XYGT v1 has a
128-byte header: magic0, version4u32, command8u32, reserved12u32, handle16u64,
epoch24u64, view32u64, processor budget40u64, payload length48u64, zero56..128.
Only begin/drop-view admit view; only begin/prepare/read admit budget. Request
length is exactly128+payload length and at most32MiB. Commands without payload
reject trailing bytes. Processor admission is shared128MiB, subtracting live
source leases before allocating parser/compiler storage. No registry mutation
supports a length probe: C output must be non-null and have256 bytes first.

| Command | Operation | Payload |
| --- | --- | --- |
| 1 | Create default bounded cache | Empty |
| 2 | Begin candidate for explicit view | Camera and source configuration |
| 3 | Start next authorized read | Empty |
| 4 | Supply exact read handle/epoch | Raw authorized raster or XYGD bytes |
| 5 | Acknowledge read after host buffers drop | Empty |
| 6 | Prepare immutable mixed SceneData | Image identity, vector styles, XYLK catalog |
| 7 | Commit staged SceneData | Empty |
| 8 | Drop exact current view | Empty |
| 9 | Cancel exact candidate epoch | Empty |
| 10 | Dispose opaque owner | Empty |
| 21 | Read immutable routing receipt | Empty |
| 22 | Read immutable SceneData receipt | Empty |

Every mutation returns XYGU v1,256 bytes: magic0/version4, kind8u32, zero12u32,
handle16u64/epoch24u64; remaining fields below are command-specific. Create
returns cache handle. Begin returns selected missing count32u64/view40u64.
Next-read returns zero handle when no unstarted reads remain; otherwise kind1,
read handle16, authorized maximum payload32u64, engine reservation40u64, and
exact ticket64..168. Supply returns completion flag8u32. Cancel returns its
actual cancellation flag8u32; an old cancellation cannot cancel newer work.
Prepare returns immutable SceneData handle16, length32, cache owner40, view48.
Commit returns view32. All unspecified reply fields are zero.

Begin payload camera80: crs0u32, wrap4u32 (0/1), seven f64 at8..64 in
centerX,centerY,zoom,width,height,bearing,pitch order; source count64u32 and
zero68..80. At most16 sources follow. Each source has112 bytes followed by
its locator and attribution UTF8 (no padding): sourceID0u64,generation8u64,
layerID16u64,layerRevision24u64,styleRevision32u64; optional half-open signed
interval start40i64/end48i64,present56u32; kind60u32 (0straightRGBA,1XYGD),
minZoom64u8/maxZoom65u8,zero66..72; maximum bytes72u64/features80u64/vertices88u64;
locator length96u32, attribution length100u32, location104u32 (0local,1network),
zero108u32. Text is nonempty where required, at most4096 bytes and contains no
control characters. Local attribution is empty. Network configuration explicitly
provides HTTP(S) template with `{z}`,`{x}`,`{y}` and nonempty attribution.
Generation binds immutable configuration; changing it under the same identity
rejects before replacing the candidate. Bounded history has128 entries, with an
explicit resource failure rather than silently forgetting identity validation.

The104-byte ticket contains cacheID0u64,epoch8u64,ordinal16u32,zero20u32 and
an80-byte key at24. Key: sourceID0/generation8/layerID16/layerRevision24/
styleRevision32 u64; time start40/end48 i64,present56u32,kind60u32,
zoom64u32,x68u32,y72u32,zero76u32. Raster supply is exactly256*256*4 top-first
straight RGBA; vector supply is validated XYGD under declared GeoLimits.
Canonical tile time identifies producer-filtered tile content; XYGD has no
per-feature interval plane. This protocol does not claim to filter arbitrary
unfiltered vector rows by ticket time.

Read routing receipt uses XYGU256 kind2, read handle16/epoch24, local/network
code48u32, locator length52u32, attribution length56u32, ticket64..168, then
locator and attribution bytes. It authorizes a particular finite read; it never
fetches automatically. Credit includes three declared payload copies plus64KiB
before host ownership. Supply, cancellation and cache disposal do not release
that credit before ACK. An abandoned ACK cancels only its own candidate. Retired
read handles remain acknowledgeable after cache disposal.

Prepare payload starts32 bytes: image stableID0u64, vector-style count8u32,
zero12u32, XYLK byte length16u64, zero24u64. At most64 styles follow, each64:
layerID0u64, layer-kind8u32 (ordinary catalog1..7),zero12u32; uniform style48
at16: fillRGBA0,strokeRGBA4,strokeWidth8f64,diameter16f64,opacity24f64,symbol32u8,
zero33..48. One style per vector layer is required. Successful preparation binds
its bytes to layer/styleRevision; changed bytes under an existing revision
reject. Failed preparation creates no binding. The existing XYLK catalog follows
exactly and shares its one parser/compiler body; interactive-event flags are
unsupported here. Its camera must match the tile candidate. Visible network
attribution must be present as an ordinary legible Scene label inside the
viewport; missing attribution cancels preparation while preserving prior frames.

The SceneData receipt is XYGU256 kind1: cache owner16/epoch24/view32;
XYLM length40u64, selected-key count48u64, attribution count56u64,
attribution plane bytes64u64; crs72u32/wrap76u32 and camera f64 bits80..136;
BLAKE2s8 digest136..144,zero144..256. The body contains ordinary XYLM aligned8,
all selected80-byte keys, then attribution records (length0u32,zero4u32,
UTF8 at8 padded8). Digest domain `xyg-tile-scene-receipt-v1` binds header0..136
and complete body. Independent cached payload/configuration digests remain
available through the trusted borrowed `GeoTileFrameView` for snapshot export.
Payload digest domain `xyg-tile-payload-v1` binds exact accepted supply bytes;
configuration domain `xyg-tile-source-config-v1` binds kind/zooms/limits/text
lengths/location and configured text. These are content linkage, not cryptographic
provider authentication. Full foreground feature IDs remain ordinary XYGS IDs.

SceneData owns its semantic configuration, provenance and complete bytes under
private384MiB derived credit, admitted before encoding. It survives cache disposal.
It permits two ownership reads; pure length probes consume none and insufficient
C output capacity consumes none. Old and candidate receipts coexist only while
the shared ledger admits both. Cache commit requires the exact still-current
epoch and occurs after host painter staging. Cancellation between reads and
commit is explicit; synchronous compilation does not claim asynchronous
mid-instruction host interruption. Registry caps are4 caches,64 read owners,
8 SceneData owners and80 total handles, with explicit disposal.

`cargo test -p xyg-engine geo_tile_protocol --lib` proves actual mixed raster and
full-u64 vector Scene lowering, receipt digest, stale commit, immutable receipt
survival/two-read admission, retired ACK and missing attribution failure.
