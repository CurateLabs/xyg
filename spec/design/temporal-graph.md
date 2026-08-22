# Temporal graph bindings and identity-safe filtering

**Status:** Rust engine plus native Python/Node and direct-browser/WASM frame
transport. Graph LOD aggregate membership, rendered host export attachment,
and massive playback evidence remain required before issue 45 closes.

**Authority:** [temporal.md](temporal.md) defines canonical i64 UTC micros and
half-open intervals; [temporal-controller.md](temporal-controller.md) defines
revisioned playback and coordination; this document defines how that state is
applied to canonical graph identity before downstream graph work.

## Ownership and ordering

`xyg_engine::temporal_graph::TemporalGraph` binds node and edge temporal planes
to the exact UUID order of a Rust-owned `GraphProjection`. For every frame,
Rust applies this order:

1. validate the nonzero, newer revision and canonical `[range_start, range_end)`;
2. evaluate node and edge half-open validity at `cursor`;
3. when `event_at` is bound, intersect validity with event membership in the
   selected range;
4. hide any edge whose source or target node is hidden; and
5. emit deterministic node/edge visibility bytes and UUID membership in
   canonical source order.

The resulting visibility must be consumed **before** graph LOD, layout updates,
picking, styling, or geographic LOD. A host must not independently filter raw
topology or infer temporal fields. Missing validity planes mean unbounded
validity; a bound null event is not visible.

## Identity and interaction state

Selection, focus, and pin state are stored as canonical UUIDs, not dense frame
positions. Replacement updates validate every UUID before committing, so an
unknown identity cannot partially change state. When an entity leaves a frame,
its persistent state remains present but it is absent from the frame's
`selected_visible_*`, `focused_visible`, or `pinned_visible_*` projections. If
the entity re-enters, the same state becomes visible without remapping.

This is intentionally distinct from the controller's linked-view `u64`
selection payload: an integrating host resolves application-stable linked IDs
to canonical graph UUIDs once, then Rust owns graph membership. Positional row
coincidence is never an identity seam.

## Cancellation, budgets, and stale replies

A frame declares a work budget covering node validity/event evaluation, edge
validity/event evaluation, endpoint closure, and canonical membership output.
Insufficient budget fails before scanning. Cancellation is checked before work,
cooperatively during every row scan, and through a lock-held publication gate
that linearizes revision commit against cancellation. A cancelled, invalid,
over-budget, or stale request cannot advance
the applied revision or mutate selection/focus/pin state. Revision zero and any
revision not newer than the applied revision fail as stale.

ABI 82 exposes the native graph seam through opaque graph handles. Creation
binds one projection handle and up to six temporal-column handles, copying the
canonical identity/time planes before returning so those source handles may be
released immediately. Python `xyg.TemporalGraph` and Node `TemporalGraph` only
coerce ergonomic host inputs and marshal typed buffers; they do not filter
topology or calculate work budgets. Rust reports the exact minimum budget,
validates exact nonzero `u64` revisions and signed `i64` time, publishes a
complete frame, and supplies packed UUID membership.

Frame metadata and frame buffers use a two-call contract. The copy call echoes
the metadata revision; if another frame wins between calls, Rust returns
`StaleRevision` instead of mixing memberships. Python and Node frame calls
also require the copied snapshot revision to equal the requested
revision, so a newer same-handle winner is rejected rather than returned.
Both hosts preserve opaque UUIDs as `(n, 16)`/packed `Uint8Array` values and
preserve Node `u64`/`i64`
scalars as `bigint`. The native cancellation endpoint remains callable from
another thread while frame work is active. Destroy removes the handle first
and cancels owned work. WASM ABI 9 retains these guarantees through packed
`XYTG` create/frame commands and `XYTF` frame output. It transports typed
i64/u8/u64 buffers and opaque UUID bytes, never graph or temporal numbers
through JSON. Rust emits visibility, visible UUID membership, and remapped
visible topology; TypeScript does not filter graph rows.

The browser `XygWasmTemporalGraph` coordinator cancels an active layout before
submitting a newer frame, rejects any response that is no longer the latest
requested revision, and only forwards progressive layout checkpoints for the
current frame. Disposal cancels owned layout work and rejects late replies.

## Frozen export provenance

`freeze(frame)` records the exact cursor, selected range, revision, visible
node/edge UUID membership, and persistent selection/focus/pin identities. This
is the Rust-owned provenance payload that later HTML/PNG/SVG adapters attach to
an export. Frame fields are read-only outside this module and carry an opaque
graph-instance token, preventing a host from forging, mutating, or cross-wiring
visibility before it is frozen. Frame publication atomically snapshots the
complete persistent selection, focus, and pin state; later interaction changes
cannot alter the provenance frozen from that frame. All emitted identity lists, including
persistent state, retain canonical projection order. Static output shows the
selected state but does not imply playback or other unavailable interaction.

The native frame result exposes that frozen state together with current
visibility: canonical node/edge visibility bytes, visible UUIDs, visible-only
selection/focus/pins, and persistent selection/focus/pins. This is export
provenance, not yet proof that HTML/PNG/SVG adapters render or attach it; that
adapter work remains a close gate.

## Evidence and remaining closure work

Rust tests cover half-open boundaries, event-range conjunction, endpoint-safe
edge membership, canonical ordering, hidden/reappearing interaction state,
unknown identities, cancellation, work budgets, stale revisions, and frozen
state. #45 remains open until:

- full GraphForge assertion-validity and event-history fixtures extend the
  direct-browser boundary golden now covered by packed validity intervals;
- temporal controller events attach to chart composition without application
  glue (the direct frame/layout latest-wins coordinator is now covered);
- direct and aggregate graph LOD report exact deterministic membership;
- HTML/PNG/SVG adapters attach and render frozen temporal provenance; and
- large/massive playback, accessibility, and native-versus-WASM parity evidence
  passes the documented budgets.
