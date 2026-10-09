# Typed mixed geographic frame transport

This implementation checkpoint connects the Rust atomic coordinator in
[geo-mixed-frame.md](geo-mixed-frame.md) to the existing native/WASM Tile execute,
read and trusted painter exports. It adds no ABI signature, provider, host
geometry policy or public chart-building API. Integration and #50 closure remain
pending. The bounded fixtures establish composition correctness, not massive
interactive performance or linked selected-ID conformance.

## Authority and publication

`XYMX` v1 requests, `XYMY` v1 replies and `XYMF` v1 immutable data have separate
magic values. Mixed handles use the high u64 bit to route trusted Tile painter
preparation to the private mixed registry. The tag alone grants no authority:
lookup and exact publication nonce are mandatory. Handles increase monotonically
and are not reused after registry disposal. Lock order is snapshot → mixed →
source → tile; borrowed callbacks cannot perform I/O or reenter those registries.

Preparing retains one independently charged SourceData owner through source
command26. Its immutable semantic authority supplies picking, rows and membership
without re-querying or forging a SceneData packet. Source-row/membership reads
still require the caller's explicitly retained exact-source reader and Rust-issued
tickets; the registry introduces no file/network reader. Mixed history continues to
name the **original** source Data handle/publication sequence. Each mixed Data
owns its private anchor, full composed Scene, source snapshot/style, original
tile receipt/configuration/content stamps, and exact retained record/style
ranges. It survives original source/session, tile frame/cache and coordinator
disposal. Command6 can transfer another independently owned SourceData anchor;
the existing eight-SourceData cap still applies. Disposal of that returned owner
uses source command10 after its borrowed packets/painters have dropped.

Command2 begins and prepares a candidate. After staging its painter successfully,
command3 commits only that exact current candidate. New begin, exact cancel4,
stale nonce, mismatched content or resource failure cannot publish old work.
Preparation failure preserves the last published frame and its existing painter.
Cancellation preserves admitted revision/content history. Changing stamp content
under the same admitted source revision is refused, including after failed
preparation; restarting a coordinator deliberately starts a new history scope.
An immutable Data can still be read, painted or frozen after cancellation, but
cannot subsequently commit that cancelled candidate. Hosts must drop all views,
GPU/CPU painter copies and prepared candidates before disposal5 ACK.

## Framing

Every integer below is little endian. Full IDs and signed time remain u64/i64;
there are no JSON numeric payloads. All unspecified words and padding are zero.
Requests are at most32 MiB and have an exact256-byte header plus declared payload.

| XYMX offset | Meaning |
| ---: | --- |
| 0,4,8 | magic, version1u32, commandu32 |
| 16,24 | owner handleu64, candidate nonceu64 |
| 32,40 | processor budgetu64, payload byte countu64 |
| 64..112 | command2 source handle/sequence, tile handle/epoch/cache/view, six u64 |
| 112,116 | command2 tile-time policyu32, stamp countu32 |
| 256 | command2 snapshot160, then at most64 exact96-byte tile stamps |

Commands1=create coordinator; 2=begin/prepare; 3=commit; 4=cancel;
5=dispose owner; 6=retain source authority; 20=read mixed Data.
Commands1/3/4/5 require zero budget; 2/6/20 require65536..128 MiB. Commands1/2/5
require zero nonce. Only command2 carries the authority words or payload. Pure
read size probes consume no lifetime copy slots; insufficient native output
capacity does not consume a slot. Data admits at most two actual ownership reads.

Snapshot160: CRS0u32, wrap4u32; seven canonical f64 bits8..64 for center x/y,
zoom, width/height, bearing/pitch; source digest64..72; generation72u64;
layer80u64; camera/time/layer/style/state revisions88..128, five u64;
time kind128u32, zero132u32, signed instant/start136i64 and end144i64,
zero152..160. Inactive time words are zero and windows are strictly half-open.
Tile stamps are the existing exact key80 followed by Rust-owned configuration
and accepted-payload digests, eight bytes each. Hosts read these through Tile
read23's `XYUP` descriptor; they never recompute hashing policy.

XYMY is256 bytes: magic0/version4/kind8u32; handle16, nonce24, owner32,
byte length40, all u64. Kind0 is an ordinary mutation reply; kind1 identifies a
candidate mixed Data; kind2 transfers independently retained SourceData.

XYMF is256 bytes followed by exact mixed Scene32, original XYGU tile receipt,
snapshot160 and style48. Header: coordinator16/nonce24; Scene length32 and
receipt length40; retained record start48/end56 and style start64/end72;
original source handle80/sequence88, tile handle96/epoch104/cache112/view120;
tile-time128u32, zero132u32; total length136, visible vertices144 and projected
vertices152. Offsets160..256 are zero. Ranges are half-open and refer to the
actual mixed Scene, preserving paint order even when literal full IDs repeat
across basemap and retained analysis. Private SourceData anchor handles are not
exposed inside this packet.

`Timeless` policy0 requires untimed tile keys and explicitly permits a timeless
basemap alongside the source's Rust-filtered time predicate. `ProducerWindow`1
requires the source's exact signed Window on every selected tile key. It certifies
producer-filtered immutable content, not Rust filtering of XYGD rows.
`EngineFiltered` is unsupported because tile XYGD/raster has no per-row interval
plane. State revision is copied exactly; selected-ID sidecars and linked host
controllers remain a separate integration gate.

## Resource and host ownership

The registry caps four coordinators, eight mixed Data and twelve handles total.
Registry initialization preleases64 KiB in the shared128 MiB source/processor
pool and the existing1 MiB cache metadata in the384 MiB derived pool. No new
pool is introduced. Command2 preleases16 KiB framing storage before copying its
bounded snapshot/stamps. Existing core frame and SourceData-anchor leases cover
immutable semantic storage. A distinct derived lease of `7*XYMF_length+65536`
is acquired before encoding, covering stored packet, two transferred copies,
transport scratch and persistent painter/ChartView CPU buffers. Old and candidate
storage coexist only under that same shared ledger. Read budget must admit two
packet lengths. Source retained semantic owners and mixed copies are deliberately
charged independently. The scope is live product-owned CPU storage in one native
process/WASM module, not app input, OS RSS, committed linear memory, GPU or DOM.
WASM's separately admitted160 MiB transport credit and128 MiB phase still apply.

Thin helpers are `js/src/66_geo_mixed.ts`, Python `_geo_mixed.py`, and Node
`geo-mixed.js`. The Node wire body is mechanically stripped from the TypeScript
source; `node scripts/gen_geo_mixed_wire.mjs --check` verifies identity. The
helpers frame raw authority, parse bounded receipts, drop failed parsed views
before disposal ACK, and expose explicit commit/cancel/dispose. Concurrent
dispose calls coalesce only while pending; a rejected cleanup clears that
promise so an explicit retry can release the same private owner. Views remain
dropped on failure. Native negative controls fill the SourceData8 quota and
prove that only the successful retry recovers the source-anchor slot. They do not mount
an additional chart, select tiles, project source rows, or infer live revisions.
The calling host owns bounded transport admission and must await cleanup. Public
notebook/Reflex/VS Code/controller mixed mounting is not supplied by these helpers.

## Frozen whole-frame binding and proof

Snapshot command5 freezes the trusted complete mixed authority. XYGX v2 tile
blob mode2 retains the original Tile receipt, original retained foreground Scene,
complete source identity/time/style/state revision, tile temporal policy, exact
record/style ranges and required literal attribution. Decode re-runs exact Scene
composition; substituting the point-only Scene, changing ranges/camera/time/source
configuration, nonzero padding or unknown modes rejects. Legacy mode1 tile and
point-only snapshot contracts remain unchanged. Static native SVG/PNG/PDF/JPEG/
WebP/HTML exports all paint the complete mixed Scene; WASM binary freeze works,
while raster/static artifact export remains the existing unsupported profile.

Reproduce:

```sh
cargo test -p xyg-engine geo_mixed_protocol --lib
cargo test -p xyg-engine geo_tile_protocol --lib
cargo build -p xyg-core --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node scripts/gen_geo_mixed_wire.mjs --check
node scripts/geo_mixed_transport_conformance.mjs
```

The actual raw fixture is shared by native and WASM: retained Point IDu64MAX,
source generationu64MAX, a window at i64MIN, opaque raster, same-ID vector basemap,
explicit network attribution, stale/cancel/resource failures and disposal of the
original source/tile/coordinator authorities. It checks exact complete Scene and
frozen bytes, lifetime copy quotas and the native six-format export profile.
Rust tests additionally assert exact red analysis/blue background pixels,
visible literal footer/escaping, local byte identity, malformed framing and
mode2 recomposition negatives. The actual packaged Worker/borrowed WebGL2 fixture stages before commit, checks
exact pixels/full-u64 picking, injects a real scheduling callback failure, and
proves old-painter/resource/framebuffer preservation. Native frozen HTML is
actually reopened with its visible literal attribution and exact pixels under
offline CSP. Raw receipts and environment are in
[the mixed transport evidence](../performance/geo-mixed-transport-2026-10-09/README.md). No comparative latency,100M interactive,
implicit tile time filtering or full linked-selection claim follows from this
small fixture. Milestone/issue integration gates remain pending until review,
CI and normal merge-queue integration finish.

Candidate packaging uses the separately approved recorded size decision
`3b11dfd4b`:1408 KiB raw/576 KiB gzip, without an optimization-profile change.
Its two package-gate constants are copied mechanically here; root integration
must include the authoritative browser-wasm decision/ancestry before landing.
