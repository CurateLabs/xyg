# Frozen retained geographic selected state

This extends [frozen export](geo-frozen-export.md) and the exact
[XYSE selected-state contract](geo-linked-state-protocol.md), following dossier
§17/§27/§28/§29/§34. It changes neither the C/WASM signatures nor the live
selection registry, host controller, query policy or limits. Integration and
M6/#50 closure remain pending until the reviewed changes land and the remaining
milestone gates pass.

## Authority and compatibility

Native trusted SceneData and mixed-frame freezing borrow the original private
`GeoPointSelection` Arc and validate its full result before any frozen allocation.
The snapshot captures the complete sparse intent, including absent, null,
offscreen and time-excluded IDs. Visible selected counts count vertices after
the canonical time/viewport fold; duplicate IDs and MultiPoint vertices retain
that existing meaning. No source-sized selection mask or query is reconstructed.

`None` selection retains **exact XYGX v2 bytes**, including the192-byte header and
all existing offsets. Explicit empty selection retains its namespace, profile
and revision in v3; it paints the exact ordinary Scene and has no count plane.
Selected import is inert metadata. It never constructs a live `GeoLinkedState`,
source, Scope, Rows, membership resolver or query capability.

Imported files validate structural consistency with their retained base grids,
full direct feature references and actual captured paint. Without the original
source they cannot authenticate which original rows contributed to a reduced
selected count, or whether an invisible intent ID existed. Fingerprints are
deterministic identity hints, never authentication. Trusted freezing obtains
those facts from the original private authority rather than imported metadata.

## Selected-only XYGX v3 framing

All v2 header fields at0..192 retain their meanings. V3's header is208 bytes:

| Offset | Field |
| --- | --- |
|4|version u32=3|
|192|selected record count u32,1..64|
|196|total selected record bytes u32|
|200..208|zero|

Exact order is208-byte header → layer80 records → direct48 records → membership96
records → grid232 records with base u64 count planes → selected records → bounded
attributions → optional tile blob → Scene32. No padding or trailing bytes are
permitted. Scene/tile lengths retain their original header locations.

Each selected record is **full grid key160 + exact XYSE v1 footer128 + IDs/counts**.
The key is byte-identical to the base grid key and binds source digest,
generation, original rows, source CRS/geometry, layer/style/state revisions,
camera bits, exact signed time predicate, reduction kind, direct flag and complete
grid dimensions. The XYSE footer is identical to the live selected SceneData
footer, with flags3 (intent plus visible-count presence). It preserves namespace,
source shape/binding, state revision, explicit straight RGBA8, both fingerprint
words, visible selected vertices and sorted unique exact-u64 IDs followed by
exact-u64 cell counts. All XYSE reserved fields stay zero.

Selected layer IDs must be unique and match an existing full base-grid/layer
binding. Each record admits at most10,000 IDs; duplicate/nonascending IDs are
rejected rather than silently canonicalized on import. Direct records have no
selected-cell plane; their visible selected total is recomputed by membership of
each full-ID direct reference, counting duplicate vertices separately. Nonempty
reduced intent carries the complete top-first grid plane; each selected count is
no larger than its base count and checked-u64 sum equals the visible selected
total. Empty intent has no count plane and visible total zero.

## Paint, mixed provenance and admission

Decode compares the explicit profile and base style with actual Scene paint.
Direct selected IDs use selected fill with ordinary opacity applied once;
stroke, width, diameter and symbol preserve ordinary policy. Cluster/Density
colors reuse Rust's existing viridis, opacity and exact integer
`selected_fraction_color`; clusters preserve the existing diameter channel and
density verifies every RGBA texel. A profile changed together with a recomputed
fingerprint still fails if it disagrees with captured visible paint.

Mixed mode2 retains the complete tile/source provenance and original foreground
Scene. Selection checks use that original foreground, while existing exact
recomposition validates the entire mixed Scene, record/style ranges and tile
attribution footer. Pure-tile mode1 and ordinary point snapshots remain unchanged.
Snapshot storage survives disposal of original source, query, Data and mixed
coordinator owners, with no retained live query capability.

Selection ID/count storage, encoded bytes, parsed tables and validation scratch
share the existing derived lease. The complete8×ordinary or32×mixed envelope
peak is admitted before copying; checked length scans and caps precede individual
selection-plane allocations. Existing32 MiB envelope,16 MiB Scene,128 MiB frozen
phase,64 layers and196,608 total grid cells remain in force. Selected cell planes
also total at most196,608. No third wire-copy quota, new pool or host allocation
allowance is granted. Admission/validation failure drops candidate storage and
leaves the old immutable frame/snapshot usable.

All six native formats preserve this same Scene and selected snapshot metadata.
SVG/PNG/HTML embed the unbound v3 envelope; PDF/JPEG/WebP keep the existing paired
bundle contract. HTML remains a static script-free, network-free replay with
literal attribution. PNG uses the existing opaque-white RGB Scene export;
selection opacity is composited onto that background, not changed by freezing.
WASM supports selected binary freeze/import; existing raster-disabled artifact
export remains explicitly Unsupported.

## Reproduction and remaining gates

`cargo test -p xyg-engine selected_snapshot` covers actual canonical direct and
MultiPoint Cluster/Density folds, full-u64/i64 intent, null/time/offscreen intent,
original authority disposal, deterministic encoding, ordinary v2 byte identity,
empty-state Scene identity, profile/fingerprint/binding/count tampering, budget
failure recovery and six native formats with exact PNG pixel composition.
Existing actual protocol regressions compare selected live and frozen XYSE bytes
and preserve selected mixed state after source/tile/coordinator disposal.

`node scripts/geo_selected_snapshot_conformance.mjs` uses the actual native C ABI
and packaged wasm32 to compare ordinary/mixed v3 bytes and live XYSE footers,
exercise six native formats and bounded failure recovery, and reject WASM raster
export. Build using the recorded O3/inline100/Binaryen packaging path; measure
against the existing1408 KiB raw /576 KiB gzip gates, without a profile change.
This small proof is not evidence of massive interactive performance, live linked
host events or imported-source query authority.
