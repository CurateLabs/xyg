# Temporal graph bindings and identity-safe filtering

**Status:** Rust engine foundation, Part of #45. Native/WASM transport,
timebar-to-layout scheduling, graph LOD aggregate membership, and host export
attachment remain required before #45 closes.

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

This slice deliberately has no C ABI entry point while ABI 81 graph work is in
flight. The later native/WASM seam must transport typed i64/u8/u64 buffers and
opaque UUID bytes, never graph or temporal numbers through JSON.

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

## Evidence and remaining closure work

Rust tests cover half-open boundaries, event-range conjunction, endpoint-safe
edge membership, canonical ordering, hidden/reappearing interaction state,
unknown identities, cancellation, work budgets, stale revisions, and frozen
state. #45 remains open until:

- the GraphForge assertion-validity and event-history fixtures bind through
  native and direct-browser/WASM hosts;
- revisioned timebar commands cancel/coalesce layout and reject stale replies;
- direct and aggregate graph LOD report exact deterministic membership;
- HTML/PNG/SVG adapters attach and render frozen temporal provenance; and
- large/massive playback, accessibility, and native-versus-WASM parity evidence
  passes the documented budgets.
