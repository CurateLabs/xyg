# Immutable mixed geographic frame coordinator

`geo_mixed_frame.rs` adds a Rust-only atomic composition foundation over the
existing immutable retained SceneData and tile SceneData authorities. It does
not add a chart API, transport command, ABI signature, host projection/filtering
policy, or claim completion of #50/#39. See dossier §20/§27, source/session,
geo-tile-protocol and geo-scale-protocol.

`GeoMixedCoordinator::begin(GeoMixedRequest)` returns a private owner/monotonic
nonce ticket after framing and revision admission. The request names exact
source Data handle/sequence, full source `GeoOperationSnapshot`, tile Data
handle/epoch, expected tile cache handle/view ID, complete selected tile keys and configuration/payload digests,
and an explicit tile temporal guarantee. At most64 tile stamps/capacity are
retained. The source snapshot compares source digest/generation, camera bits,
signed predicate, layer identity and all camera/time/layer/style/state revisions.
Regressed revisions, changed camera/time/source under unchanged corresponding
revision, changed style bytes under a successfully prepared trusted style revision and changed
content for an identical tile key fail closed. Tile revisions absent from the
original authority are not invented.

`prepare(ticket,budget,cancel)` borrows trusted source registry first and tile
registry second, validates exact authorities and composes their actual Scenes.
These synchronous callbacks cannot reenter either registry or perform I/O.
Cancellation is checked before authority access, before Scene decoding and after
bounded synchronous composition; it is not an asynchronous mid-instruction
cancellation claim. The prepared candidate retains a private ticket. After the
consumer stages its painter, `commit(candidate)` replaces the published frame
only if its ticket/request is still current. New begin, exact cancel or foreign
coordinator tickets cannot publish stale work. Failed admission/preparation or
stale commit leaves the previous frame usable. Published frames are borrowed
through Arc; previously retained Arcs survive coordinator/source/cache disposal.
This core does not yet couple host staging failure or live controller revisions
to the existing transport.

## Temporal truth and layer scope

Tile XYGD/raster payloads have no per-feature signed-time interval plane.
`EngineFiltered` therefore rejects. `Timeless` requires every selected tile key
to have no time predicate and explicitly means a time-independent basemap while
the retained analysis source uses its actual Rust-filtered predicate.
`ProducerWindow` requires an exact signed source Window equal to every selected
tile window. It identifies producer-filtered immutable content; it does not
claim that Rust filtered its individual vector rows. Instant filtering cannot
be certified from the interval-only tile keys and is refused for this profile.
This distinction remains a concrete #50 mixed signed-time integration gate.

The existing tile frame can also contain an arbitrary ordinary foreground XYLK
catalog with no temporal/state attachment. This coordinator refuses those layers:
every catalog layer must be authorized by at least one **selected** `VectorXygd`
tile key for that layer. A configured but unselected vector source grants no
catalog authority; a zero-vector selection cannot admit vector catalog layers. No
basemap layer may overlap the retained analysis layer identity. Raster identity
remains the Scene Image identity plus raster tile/configuration/content stamps,
never a fabricated feature ID. The exact original tile receipt and configured
sources/attributions are retained alongside the source manifest, full LOD key,
direct/cell provenance and exact uniform source style. Typed retained-record and
style ranges keep ownership unambiguous when IDs repeat across basemap and analysis.

## Scene and resource ownership

`SceneDocument::compose_geographic` places the complete raster/vector basemap
records before the retained records. It preserves literal full-u64 IDs, original
CSS f64 coordinates, invisible separators, primitive topology tags, style
references and linecaps, Scene images, baseline labels and legend. The foreground
cannot own decorations; conflicting image IDs and unsupported polar/colorbar,
boxed labels, gradients/glyphs, dashes and static authored metadata reject rather
than being silently discarded. Canonical layout/scales must match bit-for-bit.
No source coordinates are mutated, no host geometry is generated, and no second
Scene wire format is introduced.

The coordinator uses the existing GeoTileCache derived pool (global384MiB),
including its admitted1MiB metadata charge. Before decoding/allocation it
reserves conservatively `32*(sourceSceneBytes+tileReceiptBytes+tileSceneBytes)
+128*sourceOutputCount+1MiB` under both caller and shared budgets. This covers
both decoded Scenes, style/record rebuild vectors, image/label copies, encoded
output, retained receipt/configuration/stamps and source provenance; old and
candidate storage coexist under the same ledger. The retained validated source
manifest is independently preleased in the shared128MiB processor pool before
cloning. Private frame storage drops before its leases. Extra transport/painter
copies require their existing separate admission; the core does not promise a
free independent output copy.

## Bounded proof and remaining integration

`cargo test -p xyg-engine --offline geo_mixed_frame --lib` exercises actual shared
Scene compilers with raster, vector, source full-u64 identity and attribution,
exact signed-window/camera/revision/content mismatch, unfiltered catalog refusal,
private nonce/cross-owner/cancel/stale commit, selected-vector refusal,
cache/view/epoch mismatch, equal-epoch Data swap and A→B→A/cancel history,
eight-scope exhaustion, low-budget rejection before Scene
decoding and immutable previous-frame ownership. Tests use the private borrowed
core seam; they do not constitute native/WASM protocol or browser mixed-frame
conformance. The public preparation path uses existing trusted registry getters.

Remaining work: typed mixed-frame transport/host staging and immutable export
binding; actual native/WASM/browser parity and pixel proofs; full source-row
linked selection/state; engine-filtered temporal attachments for non-timeless
vector content; and notebook/Reflex/VS Code live journeys. No performance or
massive interactive mixed-frame claim follows from these small core fixtures.

The coordinator retains its last admitted source/provenance authority through
cancellation, independently of the old published frame. Same-layer-revision
source publication sequences cannot regress. Equal source sequences must reuse
the identical immutable Data handle and snapshot; rebuilding the same frame
under a new handle requires a newer source publication. A layer revision change
authorizes a fresh source sequence scope. These guards prevent an older LOD
frame from replacing a newer admitted query even when camera/time counters match.
Tile epoch admission retains up to eight lifetime `(cache handle, view ID)`
scopes. Within one scope an epoch cannot regress; an equal epoch must reuse the
same immutable tile Data handle. A different cache or view has an independent
epoch baseline, without inferring order from opaque source generations. Returning
from scope A to B and back to A still enforces A's stored baseline. Cancellation
and failed preparation preserve admitted scope history. The ninth distinct scope
fails with ResourceLimit; dispose/recreate the coordinator when intentionally
starting another lifetime of cache/view ownership.

Preparation checks the trusted immutable XYGU receipt magic/version/frame kind
and compares cache handle at16, epoch at24 and view ID at32 against the expected
request. Request authoring is admission intent, not proof of receipt ownership;
only trusted registry preparation can publish a candidate.

The bounded pending and last-admitted requests retain a separate 16 KiB credit
plus `size_of<[Option<TilePublication>;8]>` for the fixed scope history and
`size_of<Mutex<Option<PreparedStyle>>>` for a fixed trusted paint baseline in the
shared derived ledger; frame charges cover owned frame authority.

The trusted paint baseline records the one analysis layer ID, style revision
and exact48 style bytes after **successful preparation**, before the first
commit. It survives cancellation and staging failure. Independent SourceData
owners with newer publication sequences cannot reuse that layer/style revision
with different bytes. Failed validation, resource failure and preparation cancel
do not advance the trusted style baseline. The short internal mutex is never
held across registry or user cancellation callbacks; complete preparation
rechecks and updates the baseline after its final cancellation probe.
