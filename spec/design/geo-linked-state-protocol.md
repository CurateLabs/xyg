# Explicit retained geographic selected-state protocol

This bounded Rust-only integration follows dossier §17/§27/§29/§34 and
[linked-state policy](geo-linked-state.md). It extends XYGQ v1's existing
256-byte header and fixed XYGZ v1 mutation replies without ABI signatures.
No host numeric selection/LOD policy, inferred ID join, source-sized flag plane,
new chart surface or quota increase is introduced.

## Scope, intent and ownership

| Command | Authority/header sequence | Exact payload and result |
| --- | --- | --- |
|32 create scope|Immutable SceneData + exact nonzero publication sequence|16 bytes: namespace u64@0, layer u64@8 matching the frame; returns Scope handle|
|33 publish state|Scope, sequence0|24-byte prefix: state revision u64@0, selected RGBA@8, zero@12..16, raw ID count u64@16; exactly count u64 IDs@24; returns State handle and revision@24|
|34 explicit link|Target Scope, sequence0|16 bytes: input State handle@0, target state revision@8; returns target-bound State handle|
|35 canonical selected begin|SourceSession + new nonzero sequence; full existing query header|8-byte State handle; success captures immutable State/Scope and consumes State handle, returns unchanged Source handle|
|36 indexed selected begin|Index + new nonzero sequence; full existing query header|8-byte State handle; success replaces State entry with selected Query at the same handle; explicit frontier/leaf-work fallback code10 preserves State and transition|

All other framing words follow existing reserved-field rules. Commands32–34
admit valid explicit QueryBudget words; no unused camera words acquire meaning.
Commands35/36 validate full source, camera/time/revisions, state binding and
options before consuming authority. Failure preserves the issued State handle.
Canceling accepted work does not recreate its consumed State; the caller may
publish an identical new handle from the retained Scope.

A Scope owns a preleased validated manifest clone and immutable lineage
(namespace, source digest/generation/full shape, layer). At most8 live scopes
fit inside16 total handles. A duplicate live namespace/source/layer scope is
rejected. Same-revision authorization compares full canonical IDs and profile,
not a fingerprint. The10,000-ID cap applies before dedup. Explicit34 is the
only linking operation; equal IDs do not imply coordination.

Scope admission retains every successfully published state across cancellation
and before any frame commit. Stale State handles cannot begin newer work after
scope revision advances. A selected source/index lane stays bound to its Scope;
legacy5/18 cannot silently drop selection. Previously accepted Data and Rows
retain their original immutable State even after the scope admits newer intent.
Command10 on Scope refuses while State, source/index lane, selected query, SceneData or RowsData
holds private Scope authority. Membership and hit outputs retain their ordinary
full query key; they do not create another selection-state scope or apply a
selected-only geometry filter. Disposal/recreation cannot reset a live baseline.

### Indexed replacement publication

Only Queries created by36 opt into command19 replacing the completed Query
entry with immutable SceneData at the **same handle**. Scene compilation,
metadata/semantic leases, style checks and output admission complete before
replacement. Failure leaves the Query authority intact. Legacy19 continues to
allocate a separate Data handle. Data's packet owner remains its former Query
handle; its reply's owner@40 identifies that handle. Command26 duplicates
selected Data with independent output ownership and shared immutable semantics.

## Selected output: explicit XYGZ v2

None Scene/Rows output remains byte-identical v1. Selected Scene or Rows uses
version2 in its existing256-byte header. Footer byte length u64@248 is nonzero;
exact length is256 + existing Scene/metadata (or64*rowcount) + footer length.
Scene length@32 and base metadata length@40 preserve their original meaning.
Rows flag bit7 is sparse selected intent independently of null/time eligibility.
Original rows stay paged at4096 max with no full mask. Private continuation
cursors retain exact State authority and reject changed IDs/profile, including
same-revision changes or removal of selection.

The appended **XYSE v1** footer has128-byte header:

| Offset | Field |
| --- | --- |
|0/4|magic XYSE / version u32=1|
|8|flags u32: intent1, visible-count presence2; Scene3, Rows1|
|16|namespace u64|
|24|canonical ID count u64 ≤10,000|
|32|selected-cell count u64; zero for direct output, Rows and empty state|
|40|visible selected **vertices** u64 when flag2, otherwise zero|
|48|selected fill RGBA4;52..56 zero|
|56/64|source digest8 / generation u64|
|72/80/88|layer ID / state revision / original source rows, all u64|
|96/100|geometry / CRS, u32|
|104/112|two-u64 fingerprint identity hint; never content authorization|
|120..128|zero|
|128|canonical exact-u64 IDs followed by exact-u64 selected counts|

Cell counts index the complete top-first reduced grid and count selected
vertices, not original rows. They bind the complete camera/time/style/state key
already in the Scene header. Direct output's exact full IDs/FeatureRefs remain
in base metadata. Sparse intent may include null/offscreen/time-excluded rows;
Rows does not fabricate visible selected counts. Before encoding, the shared
selection validates the full result key and exact per-cell/total invariants.

## Admission and five-view lifecycle

State owns shared128 MiB processor credit; temporary raw IDs are separately
preleased while canonical state is built. Manifest, active/old output, wrapper,
result and original-row metadata remain charged. Selected footer copies are
added to shared384 MiB durable Data admission before encoding. Existing two-read
copy quota and drop-before-command10 rule apply; command23 ordinary Data reads
retain sequence0, publication sequence remains encoded privately in Data.

Canonical five Source + five Scope + five displayed Data =15 handles. A
State temporarily uses16;35 consumes it, returning15. Candidate SceneData
uses16/six Data; closing the old displayed Data after paint returns15. Indexed
five Index + five Scope + five Data =15; State16 is replaced with Query16 by36
and Data16 by selected19. No hidden old-frame disposal is performed.

Original-row publication requires two temporary owners. Five live engines at15
fail closed under pressure. Explicitly disposing an inactive engine preserves
all five immutable frames and allows a single rows-session/Data pair. To retain
an old page while preparing its replacement, explicitly park two engine owners:
13 baseline + old page14 + next rows session15 + next page16/seven Data. This
is a caller-visible ownership tradeoff, not simultaneous five-engine paging or
an increased quota.

## Proof and remaining integration

Focused byte tests cover state consumption, cancel/ACK, stale/same-revision
IDs/profile, full-u64 duplicate dedup, explicit namespace link, reduced canonical/
indexed Scene and18,000/36,000 selected/visible vertex parity, immutable original
rows, five-view handle ceilings, explicit engine parking, failed next-page read
with old-page preservation and scope draining. Original-row core tests cover
selected null/time-excluded/offscreen rows and full-content cursor binding.

Native/WASM wrappers, typed host parsers, public linked events and selected
frozen-export provenance remain later integration gates. Trusted
`with_scene_data` exposes `result.selection` with full immutable intent/count
ownership for that integration; selected freeze must fail closed until complete
XYSE authority is carried. This slice makes no selected export, host-journey,
massive latency or M6/#50 completion claim.

Command 34 admits the complete new canonical ID plane and state owner against the caller processor budget before linking or changing target admission. A failed low-budget link preserves the source State and target revision for an explicit retry.

Selected SceneData freeze returns Unsupported before frozen allocation while XYGX lacks full XYSE intent, profile and count authority. Ordinary unselected snapshots retain their existing contract. This rejection is a release gate until selected export carries and validates the full authority.

Picking uses the effective painted alpha. Direct selected points replace the
ordinary fill with selected RGBA, with ordinary opacity applied once; stroke
visibility remains independent. Aggregate Cluster/Density cells use the same
exact integer selected-fraction alpha blend as Scene compilation. Fully selected
transparent cells cannot be picked, and opaque selected points remain pickable
when the ordinary fill is transparent. Rust validates complete selection binding
before allocating hit output. Actual protocol regressions cover both direct
alpha directions, zero opacity, fully selected clusters and density cells.
