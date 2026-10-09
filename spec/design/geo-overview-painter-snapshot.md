# Trusted temporal overview paint and frozen export

This bounded slice paints the existing Rust overview Scene and freezes its inert
domain-count facts. It adds no chart constructor, domain membership, source pick,
refinement, network provider or massive latency claim. Dossier §17/§27/§28/§29
applies. Temporal-exact/data-space/nonfinal flags remain exactly3. Scene literal
IDs0..255 are domain cells, never feature IDs. Selected input remains rejected by
command27 even for an empty selected ID plane.

## Authority and paint

The existing retained frame prepare export dispatches on private Data kind and
exact publication sequence. Generic authored Scene bytes do not gain retained
authority. All allocation follows private owner/snapshot validation. The same
Scene decoder and XYPB15 compiler are reused; Rust cell projection/palette remain
authoritative.

The fixed16MiB overview Data lease persists with its immutable owner and reserves
four complete XYOV packet copies, painter copies and bounded ChartView CPU
metadata. The maximum12288 Triangle vertex records (4096 primitives),256 styles
and constant label bound this profile. The exact notice is one upright black
8px viewport-local SceneLabel, start anchor0 at(4,height−4), with empty chrome
title. Rust text-advance must fit width−8 and the baseline/font bounds must fit
height; insufficient viewport space fails ResourceLimit without truncation.
It uses the existing Scene/DOM decoration seam and never reserves a title gutter.
The 800×600 cell projection therefore remains 800×600 in browser and static output.
The encoded Scene cap is160+256×16+12288×56+65536=757920B.
Persistent preflight uses painterBound=2×SceneBytes+65536 and reserves
4×(SceneBytes+2304)+4×painterBound+4096×1024+256×2048+1MiB;
the maximum is15133568B, below16777216B. The per-triangle term covers owned CPU
coordinate/style/ID/pick arrays and the per-style term covers trace metadata;
these are conservative allowances, distinct from GPU/DOM/application storage. The32×Scene+1MiB phase is temporary and
does not account for persistent views. A failed preflight preserves old output.
The existing128MiB source/384MiB derived ledgers and16/8/8 caps are unchanged.

## XYGXv4 overview-only envelope

Ordinary XYGXv2 and selected XYGXv3 remain byte-identical. Version4 is admitted
only for one overview layer, no direct/grid/membership/selection/tile/attribution
tables. It uses the existing192B identity header followed by16B:
count:u32=1, sidecarBytes:u32=2144, zero8. The existing80B layer record follows.
It binds the complete source digest/generation/rows/geometry/CRS and layer/style/
state revisions; the base header binds exact camera/time/camera/time revisions.

One2144B XYOF record then precedes the unchanged Scene32:

| Offset | Type | Meaning |
|---|---|---|
|0|bytes4|XYOF|
|4|u32|version1|
|8|u32|flags3: temporal_exact, data_space, nonfinal|
|12|u32|resolution16|
|16|u64|layer ID|
|24|u32|fixed logarithmic palette profile1|
|28|zero4|reserved|
|32|bytes8|validated overview digest|
|40|bytes8|source digest, matching layer|
|48|u64|source generation, matching layer|
|56|u64|source rows, matching layer|
|64|u32|source CRS, matching layer|
|68|u32|Point1 or MultiPoint4, matching layer|
|72|u64|countBytes2048|
|80|zero16|reserved|
|96|256 u64|bottom-first16×16 domain counts|

The v4 Scene cap and fixed XYOF profile/count framing are checked before the
owned input copy. Zero source rows require zero counts for both Point and
MultiPoint. Remaining lengths, reserved bytes and full identity binding are
checked within preleased input/decode scratch before typed metadata and geometry
allocation. Import deterministically recompiles the projected
Scene from inert counts/camera through the shared pure Rust lowering and demands
exact byte equality. This proves internal metadata/paint consistency, not source
authentication: an imported envelope is inert and grants no Rows/query/membership
capability. Trusted freezing uses the private GeoOverviewResult/source Arc.
Neither the process-local handle nor a fabricated GeoLodKey is serialized.

Snapshot command6 freezes an overview Data owner with its exact sequence using
existing snapshot execute/read ABI entry points. Existing commands1/4/5 remain
point/tile/mixed-specific. The ordinary six-format export path is reused: SVG/PNG
carry embedded frozen metadata; PDF/JPEG/WebP return paired accountable snapshot
bytes; HTML is an offline static SVG replay with strict no-network CSP. WASM
provides binary snapshot parity, while native raster formats retain their existing
feature/Unsupported contract. Public composition and membership remain pending.

## Reproducible scope

The small actual native/WASM fixture uses full-u64 source IDs and half-open time
intervals; instant0 contributes exactly one vertex to domain cells128 and143.
The shared ordinary and borrowed WebGL2 painters produce opaque composited
pixels(55,155,255,255) at(160,284)/(640,284) and white at the excluded cell.
Offline SVG replay produces(56,156,255,255) at the same points: its alpha
compositing rounds the two channels one unit higher. Both explicit output
contracts are tested; cross-renderer byte-identical pixels are not claimed.

The dense256-cell Rust control includes bearing120°,pitch60°,worldWrap=false.
It depends on the independently reviewed snapped-topology signed-zero fix54a29314a;
canonical source coordinates are unchanged. Raw proof, artifact hashes and
commands live in [the evidence folder](../performance/geo-overview-painter-snapshot-2026-10-09/README.md).
Public overview composition, final spatial refinement, cell-domain membership,
selected overview input and the massive interactive gate remain open.

The direct browser Rust/WASM CI lane runs the packaged overview conformance
script after fresh native/WASM builds and Chromium installation, including
ordinary and borrowed-layer WebGL pixels, six native export formats, frozen
v4 parity, and offline CSP replay. Its JSON report is retained with the direct
browser foundation artifact. The existing merge-group Release surfaces gate
continues to require this lane.
