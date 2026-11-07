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

The selection, focus, and pin state is one `GraphInteractionState`
(`crates/xyg-engine/src/graph_interaction_state.rs`) owned by the temporal graph
and shared, not copied, with any interaction session bound to it
([graph-interaction.md](graph-interaction.md) §1). Selection is bounded at
10,000 identities (nodes + edges + derived edges, the coordination snapshot
bound): a `set_selection` whose result would exceed it fails with
`TemporalError::SelectionTooLarge` (−16) and changes nothing. Previously
unbounded. A derived-edge selection or focus made through a bound session is
part of that state but has no temporal counterpart: it is absent from frame
projections, and a `set_selection` replacement drops it.

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

The Rust engine's `frame_with_output` prepares a downstream output against an
immutable candidate before publishing its revision and visibility. Output
admission failure leaves the previous world and its frozen provenance usable;
the caller may retry the same revision. Cancellation after output construction
still rejects publication through the existing lock-held gate. The ordinary
native `frame` delegates to this same path with no transport output.

The WASM XYTF encoder uses this gate: exact reply-size admission and complete
packed topology/membership construction precede publication. A one-byte-under
reply budget returns ResourceLimit without advancing temporal state observed by
bound interaction sessions. This does not change ABI versions, packet bytes,
work budgets, arena limits or spatial policy. It closes a failure-atomicity gap
in #45's temporal-before-downstream contract; automatic temporal/geographic
controller wiring remains unimplemented.

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

The browser `XygWasmTemporalGraph` coordinator validates packed frame inputs
before reserving a revision or cancelling active layout work. It captures the
submitted revision once; later caller option mutations cannot change the encoded
request or its reply check. It tracks the highest submitted revision separately
from the successfully returned frame
revision. A rejected frame command releases only its own attempt reservation,
allowing that same highest revision to be retried. Lower superseded revisions,
duplicate in-flight requests, and successfully returned revisions remain stale.
A late failure cannot lower the highest requested revision or release a newer
attempt. Each submission has a distinct attempt identity, which gates frame
responses and progressive layout callbacks even across same-revision retries.
Disposal cancels owned layout work and rejects late replies.

Rust output-admission rejection leaves its applied revision unchanged, so a
same-revision retry with smaller visible membership can succeed under the same
arena cap. A transport failure permits another submission but cannot establish
whether Rust already committed before delivery failed. Rust remains the applied
revision authority in that case. Once a valid frame returns, later layout
encoding, scheduling, or execution failure leaves that frame revision consumed.
`frameAndLayout` captures its revision once, checks that same scalar against
the narrower nonzero u32 width, and submits it unchanged to `frame`. It does not
re-read a caller revision getter between admission and encoding. These transport guards do not filter topology or change Rust layout,
identity, or work-budget policy.

The [public retry receipt](../performance/temporal-browser-retry-2026-11-06/README.md)
records failing-before and passing-after public coordinator journeys through the
unchanged packaged WASM and real browser Worker, plus deterministic late-error,
supersession, duplicate, input-validation, and disposal regressions. Existing
browser frame/layout goldens remain part of the full foundation run.

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

## Focused output-publication proof (2026-11-06)

[Receipt and raw logs](../performance/temporal-frame-publication-2026-11-06/README.md)
cover output-budget rejection, same-revision retry, cancellation after output
preparation, unchanged persistent UUID state and frozen prior provenance, and
exact native-engine/WASM-adapter output equivalence. Existing real wasm32/native
replays qualify the artifact separately. These bounded checks make no massive
latency, competitor advantage, rendered export or whole-issue acceptance claim.
The supported application matrix is defined by
[application-consumers.md](application-consumers.md); obsolete Reflex wording in
#46/#50 does not restore the retired adapter or waive the remaining supported
host, accessibility, export and scale requirements.

## Automatic browser controller coordinator (bounded #45 slice)

`XygWasmTemporalGraph.attachController(controller, {budget, layout, onFrame,
onError})` subscribes to complete Rust controller snapshots and schedules the
initial time automatically. Scrub, range/window recentering, step, playback and
received coordination snapshots share one active frame/layout and one pending
latest time intent. A received event can change time without changing the local
controller revision; the coordinator issues its own strictly increasing graph
revision. Identical canonical time snapshots do not restart layout. A newer
intent cancels active CoSE and suppresses old frame/checkpoint publication.
`whenIdle()` observes completion; it is not a user frame pump. `snapshot()` and
observer values are defensive copies of the last completed membership/layout.
Failure keeps that result; the next controller notification can retry a failed
time. Observer errors do not corrupt the accepted result. Binding disposal
unsubscribes immediately, suppresses late publication and drains active work;
controller and Worker ownership stay with the caller. Graph/controller disposal
also detaches the binding. Do not mix manual frame submissions with a binding.

The standalone coordinator remains available for explicit frame/layout consumers.
Retained composition now uses the optional `temporal` property of
`attachWasmGraphSession`, described below. No timezone setter exists on this
UTC-microsecond controller; timezone/export presentation remains outside this
slice. Aggregate/export/scale and comparative performance gates remain open.
No competitor performance lead is claimed.

The existing full strict-CSP foundation command executes the automatic Worker
journey and exact seven-frame assertion-validity/event-history fixture shared
with `tests/test_temporal_graph_native.py`. This adds no separate CI gate.

## Retained automatic presentation (bounded #45 slice)

```js
const graph = attachWasmGraphSession({
  el, worker: graphWorker, instanceId: 950n, document, load, camera,
  temporal: { controller, binding, budget: 14n },
});
await graph.ready;
await controller.setCursor(20n); // normal controller controls drive the graph
```

The existing attachment owns one exclusive Worker lifetime. Its internal lane
has named temporal-create and temporal-frame messages; both use the same queue,
request/sequence/lifetime checks, bounded retained bytes and lost-reply watchdog
as graph commands. Foreign public temporal commands still fail admission. There
is no public arbitrary execute endpoint, alternate renderer, topology rebuild,
JavaScript filter/identity resolution, or independent layout. The controller
uses a separate Worker; its complete canonical snapshots, including received
coordination events, automatically drive initial and subsequent presentation.

Initialization performs OPEN, XYTG create, XYTG frame, Rust Bind (operation 18),
and Rust render before first paint. Bind itself renders in Rust, so initial
membership is published before binding as well as before presentation. Bind adopts the temporal owner's initially
empty interaction state, per the existing Rust contract. Nonzero authored
`load.pinned` with this option is refused synchronously; use the bounded
`pinFocused(boolean)` action after ready. That action forwards the single Rust
focus-action ref and remains subject to busy/stale/applicability guards.
Selection, focus and pins then live in the same Rust temporal owner and persist
when UUIDs leave/re-enter visibility. Companion rows remain canonical, including
hidden entities; they are not the visible render membership oracle.

Each time intent occupies one latest pending snapshot beside one active lane
operation. Supersession suppresses older frame/render/layout replies before
paint and pauses the old continuation. Rust frame publication is failure-atomic;
render synchronizes that published visibility before graph LOD, picking or
retained layout. The session's actual acknowledged revision is tracked even if
its reply is superseded. Interactions are withheld while the presentation and
Rust temporal world differ. `load.progressive` reuses the existing retained
continuation, with unchanged chunk/wall/work limits, after matching render.

A refused frame retains the last accepted picture, camera, snapshot and UUID
state. A successful frame followed by refused render also retains that picture;
interactions stay blocked until a successful matching render. `refreshRender`
can recover with the last Rust-accepted membership, while the next controller
notification retries failed time. Snapshot temporal membership is installed
with the picture, never in advance. `whenIdle()` asynchronously drains admitted
UI/time work without a microtask spin or application frame pumping; it does not
wait for every future animation opportunity. Terminal Worker failures clear pending time intent, unsubscribe from controller notifications, and reject existing or later idle waits with the terminal error; explicit disposal is not required to settle them. Late replies cannot publish after terminal invalidation. Snapshot buffers are defensive
copies. Disposal immediately unsubscribes, stops scheduling, suppresses late
publication, and drains the lane before CLOSE/releasing its claim. Disposing
the controller disposes its attached view. Rust temporal storage remains owned
by the borrowed Worker until replacement/Worker disposal, as on the existing
standalone path; dispose an owned Worker after the attachment.

The existing full source-dist foundation command now includes the retained
journey in `graph_session_controller_wasm_smoke.mjs`. Its seven-frame shared
assertion-history fixture verifies actual pixels, exact Rust render/UUID
membership, native picks and hidden/reappearing selection/focus/pins. It also
covers real Rust frame and render refusals, remote snapshots, step/play/pause,
held-reply latest-wins/disposal and in-flight progressive checkpoint replacement.
The existing Node native/WASM wire test compares complete retained replies,
including GPU, membership and interaction state, for the same fixture. Evidence:
[retained presentation receipt](../performance/temporal-retained-presentation-2026-11-07/README.md).

This bounded direct-tier proof does not close aggregate membership, exports,
large/massive playback, full accessibility, timezone presentation, supported
host parity or competitor comparison acceptance.
