# Graph interaction, coordinated selection, and accessibility (#36)

Status: **S1–S3 typed engine approved on the parent base; S4 shared native/WASM session wire implemented locally, merged with the parent-approved S3 aggregate-style repair; S4 package gate fails and final independent parent review remains required** (see [Implementation status](#implementation-status)).
Scope: interaction, selection, focus, and accessibility over composed GraphForge
graphs, plus the position hooks (pin, drag, relayout step, persistence).
Non-goals: editing; layout *scheduling* (#35). Related:
[graph-mark.md](graph-mark.md) §7, [graphforge-compositions.md](graphforge-compositions.md),
[temporal-graph.md](temporal-graph.md), [temporal-controller.md](temporal-controller.md).

Rust owns every policy below; hosts (Python, Node, VS Code, browser) forward
bytes and paint. The design passed three independent review rounds; where a
later resolution replaced earlier text, the resolution is folded in here.

## Decisions
1. Default brush/lasso policy is NodesAndInducedEdges.
2. `xy:graphforge-select` stays one release as a deprecated alias; its detail
   shape is kept exactly (`49_wasm_graphforge.ts`).
3. The latency ladder is recorded evidence, not a gate.
4. Compound disclosure stays bounded at 1,024 source nodes.
5. Keyboard move mode and a Relayout key/button.
6. Selection is capped atomically at 10,000 refs.
7. Outbound coordination uses its own monotonically increasing sequence,
   independent of camera/render revision, so repeated identical selections
   remain deliverable.


## 1. Ownership
### 1.1 One state instance
`GraphInteractionState` (`crates/xyg-engine/src/graph_interaction_state.rs`) is
the selection, focus, pin, and highlight state: selection and the three highlight
planes (Path, Community, External) are each an `ElementSet` of node UUIDs, edge
UUIDs, and `DerivedKey`s; focus is an entity or a derived key; pins are node
UUIDs. `TemporalGraph` owns one (`temporal_graph.rs`); its mutators are thin
calls on it and its frame publication reads it. Behavior is unchanged except the
selection bound (§2.2).

`GraphSession.state: StateSlot` where `enum StateSlot { Owned(GraphInteractionState),
Bound { host, handle } }`. **Bound sessions own no state**: every read and
mutation runs on the temporal graph's own value through `TemporalHost::with_graph`
(the registry that owns the graph implements it; `xyg-core` and `xyg-wasm` adapters execute the shared S4 wire transaction), under
that registry's lock. Divergence is impossible by construction: there is one
`GraphInteractionState` value, reachable from either owner. Binding
(`GraphSession::bind_temporal`) validates that the session's node UUID plane and
persisted-edge UUID plane equal the temporal graph's, else
`GF_INTERACTION_INVALID` with no change; on success the session's `Owned` state is
discarded (the temporal graph pre-existed and may already be linked). Dropping a
session never touches temporal state; a temporal graph disposed while bound makes
every session op return `GF_INTERACTION_UNBOUND` until `unbind`, which installs a
fresh empty `Owned`. A derived-edge selection/focus has no temporal counterpart:
frame projections omit it and a `TemporalGraph::set_selection` replacement drops it.


### 1.2 Session ingress
`GraphSession::create(document, load, instance_id)` takes the composed `XYGF`
document and session-local inputs only:
```
load.x.f64 / load.y.f64        optional, both or neither; absent -> CoSE from the deterministic seed (300 steps, document parents)
load.collapsed.u8              optional, per source node
load.pinned.u8                 optional, per source node; seeds the UUID-keyed pin set
load.budgets.u64 [node_budget, edge_budget]   default 200_000 / 500_000 (_graph.py layout_render)
load.seed.u64
```
**The hierarchy is not a load input.** It is composed from the base node table's
`parent_uuid` column ([graphforge-compositions.md](graphforge-compositions.md) §4.1)
and carried in the document as `node.parent` / `node.parent.valid`; the session
reads it only from the document, so native, direct-browser, Python, and Node
hosts see identical forests. Documents of any other `composition.version`, error
documents, and malformed planes (unequal lengths, parent out of range, a
self-parent or cycle) are `GF_INTERACTION_INVALID`; `load` planes whose length is
not the node count, non-finite positions, flag values above 1, or zero budgets
likewise. The Scene path (`with_scene`; at most 1,024 nodes) is static export
only; sessions never call it.

### 1.3 Other owners
Rust `graphforge/interaction.rs` owns the session: identity resolution, state ops,
render publication, pick, disclosure, positions/relayout, stamps, companion text.
`xyg-core` holds sessions in a handle table beside the document store;
`xyg-wasm` holds one session per instance beside `instance.output`. The browser
`js/src/63_graph_controller.ts` (new): pointer/keyboard capture, DOM focus, ARIA,
companion DOM, `xy:graph-*` dispatch; it forwards the two Rust planes to paint;
the hover policy in `58_graph.ts` is deleted. Python `_graphforge.py`/`channel.py`
and Node `graphforge.js` wrap the same bytes; no policy outside Rust.


## 2. Contracts
### 2.1 Identity
`ElementRef` (`graphforge/identity.rs`) is kind-qualified:

| Kind | Identity |
|---|---|
| Node | `uuid` |
| Edge (persisted) | `uuid` (a node and an edge may share a UUID; the kind disambiguates) |
| Derived edge (NIL UUID in the document) | `(result id, layer, path, order)` = `DerivedKey` |
| RenderAggregate | `(render_revision, render node index)`; valid only while the revision is current, else `GF_INTERACTION_STALE`; resolves to member source nodes; never stored |

**Derived keys.** For ordered overlays (paths, walks, cycles, Euler trails)
`path` is the overlay index and `order` the step (`edge.path`, `edge.order`;
`compose.rs` assigns them per derived step, and overlay indices are global across
layers). Derived *pair* edges (similarity, reachability, flow) have no overlay
(`edge.path = u64::MAX`, `edge.order = -1`), so `order` is the layer's result row
for that edge (`layer.edge_rows`, unique per pair edge) and `path` stays
`u64::MAX`. `(layer, path, order)` is therefore unique per composition; a document
where it is not is `GF_INTERACTION_INVALID`.

**Exact result identity.** The session holds an exact string table of the
layers' result ids; an absent id is a distinct "none" entry, not the empty
string. Local refs carry a table index; refs that cross sessions or hosts carry
the exact UTF-8 result id (`ResultRef::Exact`). A 64-bit FNV-1a hash is used only
to find candidates; **identity is the string comparison**. A ref whose result id
is absent from the receiver's table, or is present but belongs to a different
layer, resolves to nothing (counted as unresolved) and is never matched to a
hash-equal neighbor. State keys store the exact id, so an update that replaces a
layer's result id invalidates derived state keyed to the old string.

Resolution: `kind + uuid` through the document's node/edge indices; derived refs
through `(layer, path, order)` then the exact result id; aggregates resolve
against the current publication (`GF_INTERACTION_STALE` before one exists or
after the revision moved on). An unresolved
ref is fatal for local `SelectRefs` (`GF_INTERACTION_INVALID`, nothing changes)
and counted for transported refs and `SelectUuids`.

**Generation/update identity.** The session records `base.generation`.
`session_update` with a different generation drops derived state (provenance is
generation-bound) and reports it in `result.dropped`; UUID-keyed state is
re-resolved and unresolvable UUIDs dropped likewise. Coordination events carry
the sender's generation; derived refs from another generation count as unmatched,
UUID refs still apply. `SelectUuids{uuids}`: a UUID naming both a node and an
edge selects **both**; `SelectRefs` disambiguates by kind.


### 2.2 Operations (`GraphInteractionEvent`)
```
0 Hover{x,y} 1 SelectAt{x,y,mode} 2 Brush{bounds,mode,policy} 3 Lasso{pts,mode,policy} 4 Clear
5 FocusStep{±1} 6 FocusRef{ref} 7 SelectFocused{mode} 8 FocusRing{±1} 9 ToggleDisclosure{ref,action}
10 SelectUuids{uuids,mode} 11 SelectRefs{refs,mode} 12 SetHighlight{plane,refs,mode}
13 Pin{ref,on} 14 MoveNode{ref,dx,dy,space,commit} 15 RelayoutStep{steps} 16 ApplyRemote{event}
17 Companion{page,size} 18 Bind{temporal_handle|0}
```
mode Replace/Add/Toggle; policy Nodes/Edges/NodesAndInducedEdges. Hover sets HOVERED + NEIGHBOR over CSR; focus independent of selection; Clear empties selection and highlight planes, keeps focus.
**Selection cap.** `MAX_GRAPH_SELECTION_REFS = MAX_COORDINATED_SELECTION_IDS = 10_000`, enforced inside `GraphInteractionState` mutators: the would-be size `|nodes|+|edges|+|derived|` is computed first; if > 10,000 the whole operation returns `GF_INTERACTION_SELECTION_TOO_LARGE` with no change. Covers Brush/Lasso/SelectAt/SelectRefs/SelectUuids/SelectFocused in every mode, each highlight plane separately, and `ApplyRemote` (rejected at validation, before any write). `TemporalGraph::set_selection` surfaces it as new `TemporalError::SelectionTooLarge` (recorded in temporal-graph.md; today unbounded).
**SetHighlight**: planes Path/Community/External → state bits `FLAG_PATH=1<<8`, `FLAG_COMMUNITY=1<<9`, `FLAG_EXTERNAL=1<<10`, `FLAG_FOCUSED=1<<7`; `KNOWN_STATE_FLAGS` stays `(1<<7)-1` (the authored style vocabulary every host validates, `state_flag_mask` 127); only `compound_collapse` widens to `KNOWN_SESSION_FLAGS=(1<<11)-1`, so the emphasis flags are session state and never authored style. Path refs are ordered nodes; each consecutive pair must share a composed edge in either direction, and the lowest composed source-edge index is highlighted; otherwise `GF_INTERACTION_INVALID`. Community flags nodes + induced edges.
**Pin{ref,on}** writes the node's current f64 into the session pin mask bit-for-bit (`graph-mark.md:275-277`). **MoveNode**: `space` 0 data / 1 screen-delta (converted through the stamped camera in Rust); `commit` 0 preview (positions plane updated, `move_origin` recorded once), 1 commit (implicitly pins, emits `graph.positions`, clears `move_origin`), 2 cancel (restores `move_origin` f64 bit-exact). Out-of-bounds → `GF_INTERACTION_INVALID` (`graph-mark.md:277`). Any committed position change invalidates the relayout state (§2.6) and republishes.
**Idempotency.** Every mutating request carries `op_seq: u64`. The session keeps `last_op_seq` and the last result bytes; `op_seq == last` returns the cached result with no state change; `op_seq < last` → `GF_INTERACTION_INVALID`. `GF_INTERACTION_CAPACITY` means the state was applied but the result did not fit; the retry with the same `op_seq` and a larger `out_cap` returns the retained result.

### 2.3 One render/publication path
`session_render(camera)` with `camera = f64[scale_x, scale_y, offset_x, offset_y, vp_w, vp_h, dpr]` produces one `RenderOutput`:
```
tier u32, edges_kept u64, node_x/y f64, member_of u64, edge_src/tgt u64, edge_members CSR u64,
visual_states u8, emphasis u8 (nodes), edge_visual_states u8, edge_emphasis u8 (edges)
(no separate `visible` plane: `member_of == NOT_RENDERED` says a source node is hidden, culled, or temporally
invisible; a node hidden by a collapsed group rides its representative's render node)
```
Pipeline order (source index space until the last step): (1) the bound temporal frame's source visibility (nodes and edges) masks the source graph *and its hierarchy* (§2.9: an invisible node leaves the forest, its children re-attach to the nearest surviving ancestor, its collapsed flag is dropped); (2) `compound_collapse` (`graph_style.rs`) over that surviving hierarchy, `load.collapsed`, and the propagated state flags yields visibility, `representative[]`, and rerouted endpoints with edge provenance; (3) `graph::build_render` (budgets, viewport culling, LOD) runs over the collapsed source graph; (4) membership composes source -> representative -> render node and source edge -> render edge CSR; then `resolve_visual_state` per render element. A collapsed group whose representative is outside the viewport is culled with its hidden descendants; an on-viewport hidden child does not cause either element to render. Aggregate centroids exclude hidden descendants. **The same `RenderOutput` value is (a) copied into the `render.*` result sections the host packs into its existing §29 paint payload (`_graph_wire.py` keys `visual_states` etc. unchanged, plus `emphasis`) and (b) the only input to the pick index.** Hosts never run `layout_render` beside a session. Proof: pick index node count equals `render.n_nodes`, every hit index `< n_nodes`; the Python wire payload built from result bytes is byte-equal to `_graph.layout_render` on the same inputs at direct tier.
Pick index: render nodes, and render-edge pieces from `edge_route_segments_with_ends` clipped by `clip_edge_piece` / `node_shape_span`, with filled heads from `GRAPH_EDGE_HEAD_LENGTH_PX` (as painters do, `edge_route.rs:481-494`); self-loop = 3 pieces; parallel lanes separate (ties: draw order, then `order`); compound frame band hits the compound, interior passes through; collapsed representative selects members. Admission (`interaction.rs`, geo's shape `geo_interaction.rs:8-14`): `MAX_GRAPH_PICK_PRIMITIVES=131_072`, `_GRID_ENTRIES=1_048_576`, `_CANDIDATES=65_536`, `MAX_GRAPH_INTERACTION_WORK=4_000_000`, 64×64 grid. Admission clarification (S3): the default 200,000-node publication can exceed
131,072 index primitives. Primitive and grid duplication limits are checked
before appending or allocating cell entries. Overflow records
`RenderOutput.pick.degraded`; the index remains bounded. When nodes (or compound
bands) cannot all fit, `node_scan` scans the **same publication** exactly under
the work limit, with no second source-sized index. Degraded point edge picks
include only admitted, canonically single-piece routes, in deterministic draw
order; omitted loops/routed edges are unavailable, never replaced by chords.
Degraded Brush/Lasso edge policy uses induced published edges. Query candidate
storage is capped at 65,536; grid visits/dedup, nodes, polygon edges, membership
expansion, dash spans and induced-edge scans consume the 4,000,000-unit work
limit. A limit failure precedes selection/hover writes and never returns a
truncated selection. Region node inclusion uses published centers (boundary
inclusive), with an even-odd test for concave lassos; exact edge policy intersects
clipped, butt-ended, dash-aware painted stroke bands and filled heads.
Point overlap order is nodes, then the head pass, then shafts, then compound
bands; within each pass the later canonical draw index wins. A compound's
unpadded interior passes through. The publication carries the resolved node and
edge styles/layers, screen geometry, heads and frame bands used by the index;
source semantic planes and directedness are retained at create/update. Authored
selected flags seed the initial Owned selection and are then state-owned, so
Clear can remove them; bound sessions use the temporal owner selection. Node
`size` is the outer marker diameter with inset stroke, and edge clipping uses
its half diameter, matching the composed point painter. Metric domains resolve
over source rows before membership projection; Aggregate omits source semantics
and uses the resolver's neutral aggregate style for every render node and edge,
including singleton memberships. The tier controls style and semantic-layer
omission, not membership counts or the aggregate state flag. Projected state and
emphasis still apply. The global directed-graph fallback remains unchanged when
semantic edge status is absent. Direct and EdgeSample
retain source semantics, including collapsed representatives and authored state
flags. Geometry and index are rebuilt
on **every** publication, including style-only republication at the same revision. Work exceeded mid-query → `GF_INTERACTION_BUDGET`, no change. `render_revision` advances on *structural* change only (pin, move, relayout, an effective disclosure, a changed temporal frame, bind/unbind, or a render requested with a different camera than the previous publication); a render with nothing structural changed republishes the same revision with fresh style planes. This supersedes "each render bumps": selection, focus, hover and highlight change style planes only, and aggregate refs must stay valid across them. The revision never wraps: at `u32::MAX` a structural change fails `GF_INTERACTION_REVISION_EXHAUSTED` before any mutation.

**Finite geometry refusal (S3 review repair).** A publication rejects
`GF_INTERACTION_INVALID` when a retained edge's data-space routing delta or
length is non-finite, or its mapped piece endpoints, delta, or computed length
are non-finite. Local S3 admission also validates the canonical circle outline
quadratic (including its discriminant and returned span) and square/diamond
half-plane arithmetic before `clip_edge_piece` can interpret non-finite
comparisons as a miss or suppress a required head. A finite canonical `None`
remains a valid miss; the polygon kernel's unbounded parallel-plane sentinels
remain valid for tiny occluded chords. This does not replace the canonical
algorithm or alter legacy shared renderer/ABI behavior.
Routing validation precedes the shared kernel, which may omit
invalid intermediates; checking only its emitted pieces is insufficient.
Coincident finite endpoints and valid fully occluded pieces may still emit no
paint; the existing finite zero-length omission remains unchanged, including
tiny occluded chords whose squared length underflows. Geometry construction
must succeed before replacing the publication, camera, or render revision,
so a rejected camera retains the complete old paint/index/membership,
pick identity, stamp, interaction state, pending outbound snapshot/sequence,
and operation retry state. This adds no coordinate cutoff, clamp, alternate
outline algorithm, or fallback chord.

### 2.4 Stamps and coordination
Destination stamp `(instance_id, render_revision)` on every local event; mismatch → `GF_INTERACTION_STALE`, no change (host repaints, resubmits). Origin stamp on `ApplyRemote`: `GraphCoordinationEvent { group_id, source_instance, revision, generation uuid, refs[0..10_000] sorted unique }`. The gate (`group_id!=0`, wrong group no-op, self → SelfEcho, `revision<=last_seen` → StaleRevision, atomic apply, no local bump, no echo; `temporal_controller.rs:346-389`) is extracted to `coordination.rs::CoordinationGate` and used by both controllers. Outbound: each distinct successful local selection request (including Clear
and a successful request that leaves membership identical) in a nonzero group
queues a complete identity snapshot; its sequence is independent of render
revision and op_seq. Retrying the same successful op_seq returns its retained
outcome without another snapshot. The pending slot coalesces to the newest
snapshot. This graph request-level delivery contract intentionally differs from
temporal's normalized no-op suppression, which remains unchanged. Transport refs
are strictly ordered by kind (Node, Edge, Derived), UUID bytes within persisted
kinds, and `(exact result id: None before Some, layer, path, order)` for Derived;
aggregates and local result-table indices are rejected. Exact result-id strings preserve the successful XYGF reader contract: arbitrary
valid UTF-8, including present-empty, spaces, Unicode and more than 128 bytes.
This is distinct from XYGQ authoring, whose 1–128-byte identifier grammar in
`request.rs` is unchanged. Reader success never implied that XYGQ accepted
empty authoring IDs. Transport length is bounded by checked u32 pool offsets,
request/selection caps and charged session resources; a valid long ID can
return Budget, never Invalid merely for the authoring grammar. Validate the whole event
before zero/wrong group, self or stale filtering. Unknown refs and derived refs
from another generation are unmatched; UUID refs still resolve. Resolve all refs
before selection replacement, then commit the source watermark only on success.
Remote apply mutates the shared bound state, with no local revision/sequence
bump and no new outbound event; existing pending delivery stays intact.
`create_linked` adds the typed Rust group configuration; `create` stays compatible
and unlinked. `pending_outbound`/`take_outbound` expose the retained snapshot;
The S4 `poll_event` forwards this snapshot → host link channel kind `graph_select` (`interaction.md:294-297`) or same-process `coordinate_deliver`. Receiver fires `graph.select` with `source:"linked"`, never rebroadcast.

### 2.5 Disclosure
`ToggleDisclosure{ref,action}` on a compound runs `compound_collapse_transition` then `compound_collapse` and `session_render` in one call. **Tier decision (recorded in graph-mark.md §7.1.5 and the §28 ledger):** explicit compound disclosure is a direct-tier feature bounded at `MAX_COMPOUND_TRANSITION_NODES = 1_024` source nodes (`graph_style.rs:30, 1664-1675`). Above it the op returns `GF_INTERACTION_COMPOUND_TOO_LARGE`, no state or revision change, and the companion shows "grouping is camera-driven for this graph"; large graphs get render-tier aggregates (camera-driven LOD), which are selectable (members), focusable, hover "group of k", and reject `action` with `GF_INTERACTION_INVALID`. Hidden members keep UUID-keyed state; `CompoundCollapse.flags` propagates to the representative. Proof: 1,024-node fixture toggles; 1,025 → status, revision unchanged.

### 2.6 Positions and relayout
The session owns `positions: (Vec<f64>, Vec<f64>)`, `pinned: Vec<u8>`, `parents`, and `relayout: Option<ForceState>`. `RelayoutStep{steps ≤ 64}` lazily builds `ForceState::new_configured(LAYOUT_COSE, …, init = current positions, pinned, parents)` (`graph.rs:670-703`, the only engine honoring pins + parents) and steps it; `force_steps × (visible_nodes + visible_edges) > MAX_GRAPH_INTERACTION_WORK` → `GF_INTERACTION_BUDGET` before layout allocation or position mutation. `force_steps` includes the 300 initial seed steps whenever positions are absent, plus the requested steps. **Relayout always uses CoSE seeded from current positions regardless of the composition's original layout**, because `xyg_graph_layout` has neither pins nor parents (`lib.rs:15480-15492`) and the issue requires pins honored; simplest and keeps Pin/MoveNode valid for every layout. Pinned nodes stay bit-exact (`graph-mark.md:275-277`). Any MoveNode commit, Pin change, or `load` update drops `relayout` (rebuilt on next step). Result `relayout.alpha.f64`, `relayout.done.u8`. Scheduling/animation remains #35 (`python/xyg/graph_layout.py`). Persistence: result `positions.changed` (ref, x, y, pinned); `session_update(load.x/y/pinned)` restores without relayout.

### 2.7 Visual semantics
`resolve_visual_state` precedence (`graph_style.rs:1497-1514`) is untouched; the new bits never compete there. Rust emits an **independent `emphasis` u8 plane** per render node and render edge: bit0 FOCUSED, bit1 PATH, bit2 COMMUNITY, bit3 EXTERNAL, bits 4–7 zero. Projection: `collapsed_node_flags`' `PROPAGATED` (`graph_style.rs:1882-1890`) gains the four bits so hidden members project to their representative; across LOD aggregates the plane is the OR over `member_of` members (edges: OR over CSR members). `emphasis = (flags >> 7) & 0xF`. Painter contract: one extra u8 attribute on the existing node/edge instances, drawn in an emphasis pass after base elements: community halo (tinted, under), path stroke (accent, nodes and edges), external dashed outline, focus ring (theme focus color, 2 px × dpr, top). All set bits draw; no precedence. Reduced motion: static ring.

### 2.8 Status codes
Stable codes (`InteractionStatus::code`): `GF_INTERACTION_STALE`, `_UNLINKED`,
`_INVALID`, `_BUDGET`, `_CAPACITY`, `_SELF_ECHO`, `_STALE_REMOTE`,
`_SELECTION_TOO_LARGE`, `_COMPOUND_TOO_LARGE`, `_UNBOUND`, `_REVISION_EXHAUSTED`. A failed operation
never changes state and never consumes its `op_seq`. Composition failures that
belong to the hierarchy keep their composition codes: `GF_BASE_PARENT_UNKNOWN`,
`GF_BASE_PARENT_SELF`, `GF_BASE_PARENT_CYCLE`, `GF_BASE_PARENT_CONFLICT`.
`TemporalGraph::set_selection` over the bound fails with
`TemporalError::SelectionTooLarge` (-16).

### 2.9 Temporal visibility
A `Bound` session obtains the current frame's source visibility (nodes and edges)
from the temporal graph it is bound to, inside Rust, under the same lock as the
shared state; frame changes bump the session render revision. An `Owned` session
has no temporal visibility (all visible). Visibility is applied at step (1) of
§2.3, before collapse, LOD, layout updates, picking, and styling. An expired node
and its incident edges are neither painted nor pickable in the bound session;
re-entry restores selection without remapping.


### 2.10 Atomic structural update (typed S3)
`GraphSession::update(header, document, load)` validates a complete temporary
replacement before touching the live session. This is a replacement, not a
load patch: absent x/y means lazy deterministic seed layout; absent collapse
means all open; absent budgets means the create defaults. Old positions do not
implicitly persist. UUID selection, highlights, focus **and pins** survive when
the replacement resolves them. Explicit `load.pinned` replaces the retained pin
set; omitted pins retain surviving tags, which anchor at the new document's
seeded positions when layout is created. Explicit x/y plus pins restores exact
persistence without relayout. A different generation drops every derived state
key; within one generation only exact result/layer/path/order keys survive.
`dropped` counts removed identities per state plane, including focus and pins.

A bound update checks node and persisted-edge UUID planes against the temporal
owner **in order**, plus persisted endpoints, then reconciles that owner's
current state under that same single registry lock. It never copies/unbinds the
owner. A mismatched replacement is Invalid, a disposed owner Unbound, and a
frame that changed before the transaction is Stale without session writes.
Success reserves and increments the structural revision exactly once, clears
publication/index/hover/ring/move preview/force state, and retains instance,
group, coordination watermark/history/sequence and pending delivery. Failure
preserves document/load/positions/state/binding/revision/outbound and the last
successful op_seq. The same successful op_seq retry retains its outcome.

## 3. ABI / WASM
Container codec unchanged; add `DT.u32` to the **browser encoder** (`49_wasm_graphforge.ts:91-99`; the decoder `:164` and Python `DTYPE.U32` `_graphforge_container.py:49` already have it).
S4 native surface (`xyg-core`; assign the next ABI version and regenerate
the manifest when signatures change; native ABI 397 has 537 functions; WASM ABI 35 has 65 functions): `xyg_graphforge_session_create(doc, load, instance_id, group_id, out_handle)`, `_update`, `_render`, `_interact`, `_bind_temporal`, `_poll_event`, `xyg_graphforge_coordinate_deliver`, `_destroy`; `GRAPHFORGE_MAX_SESSIONS=256`; `out_cap` short → `GF_INTERACTION_CAPACITY` + required length. WASM: `_session_open/_update/_render/_interact/_close`, one per instance, output in `instance.output` under `max_arena_bytes`.
Request `XYGI`: `header.u64`[instance_id, group_id, op_seq]; `header.u32`[render_revision, operation, mode, policy, plane, action, commit, steps, space]; `camera.f64`; `coordinates.f64`; `refs.bytes` (kind-tagged refs; transported derived refs carry the exact result id, §2.1; byte layout fixed with the ABI); `uuids.uuid`; `remote.bytes`; `companion.u32`[page, size≤200]; `load.*` (§1.2).
Result `XYGR`: `status.u32`; `header.u32`[render_revision, pick.degraded, unmatched, dropped]; `render.*` (§2.3, whenever geometry or style/emphasis planes changed); `node.flags.u32`/`edge.flags.u32` (source-indexed state); `focus.bytes`, `focus.ring.u32`; `changed.refs.bytes`; `candidates.bytes`; `positions.changed.bytes`; `relayout.alpha.f64`, `relayout.done.u8`; `companion.text.utf8` + `companion.total.u32`; `summary.text.utf8`; `outbound.bytes`. Companion text: rows `\n`-separated, cells `\t`-separated, cell escaping `\\`→`\\\\`, `\t`→`\\t`, `\n`→`\\n`; DOM sets `textContent` only.
Statuses: `GF_INTERACTION_STALE, _UNLINKED, _INVALID, _BUDGET, _CAPACITY, _SELF_ECHO, _STALE_REMOTE, _SELECTION_TOO_LARGE, _COMPOUND_TOO_LARGE, _UNBOUND, _REVISION_EXHAUSTED`. Static export path (`request.selected`, `compose.rs:640`) unchanged.

## 4. Events (all hosts)
`graph.select` (stamp, source user|api|linked, mode, selected refs, changed refs); `graph.focus` (ref, summary); `graph.hover`; `graph.disclosure` (ref, collapsed, members, revision); `graph.positions` (changed, revision); `graph.relayout` (alpha, done, revision); `graph.render` (revision, tier, degraded); `graph.stale`. Browser `CustomEvent("xy:graph-*")`; `xy:graphforge-select` alias one release. Python `ChannelCallbacks.on_graph_*` via `handle_message` kind `graph_interact` → `graph_result`; Node `session.interact(bytes)`/`on("select")`; VS Code `xyg.pick` / `xyg.select {uuids|refs}`.

## 5. Accessibility
Surface `role="application"`, `tabindex=0`; companion `<table>` follows in DOM order (`62_geographic_controller.ts` pattern). **Tab/Shift+Tab are never handled.**
| Key | Operation |
|---|---|
| Arrows | FocusStep ±1 (normal) / MoveNode preview (move mode) |
| `]` `[`, PageDown/Up | FocusRing ±1 (Nodes → OutEdges → InEdges → Neighbors) |
| Enter | SelectFocused Replace (normal) / MoveNode commit=1 (move mode); Ctrl/Meta+Enter Toggle |
| Space | ToggleDisclosure on compound, else SelectFocused Toggle |
| Escape | move mode: cancel (commit=2) and exit; else Clear, `preventDefault` only when something was cleared |
| Home/End | FocusRef first/last visible node |
| `p` | Pin toggle on focused node |
| `m` | Toggle **move mode** on a focused direct node (not aggregates); exits on blur or focus change with cancel |
| `r` / Shift+`r` | RelayoutStep steps=8 / 32; companion **Relayout** button = `r` |
Move mode: arrows move by 8 CSS px, Shift 32 px (`space=1`, Rust converts via camera); each preview bumps the render revision; bounds rejection leaves the node at its last valid position. Live region (`aria-live="polite"`) = Rust `summary.text`: `"{Node|Edge|Group} {label}, {relationship}, {selected|not selected}, {n of m}"`; move mode appends `", moving, x y"`; relayout announces `"relayout, alpha a"` / `"relayout settled"`. Companion rows paged in Rust (≤200/page, default 50) with Prev/Next, a Select button per row (`SelectRefs`), Relayout button, and a visible "Move mode" indicator. Reduced motion: instant transitions, static ring.

## 6. Proofs
| Criterion | Proof |
|---|---|
| Identity | ref→index→ref for nodes, persisted edges, derived edges (two path rows sharing endpoints → distinct `(layer,path,order)`), aggregates→members; stale aggregate → STALE; shared-UUID node/edge; `result_hash` mismatch → unmatched; generation change drops derived only |
| Ownership | bound session mutation visible in `TemporalGraphFrame` and vice versa; temporal dispose → UNBOUND; bind with mismatched UUID planes rejected |
| Ingress/publication | session from `load.*` equals `_graph.layout_render` byte-equal at direct tier; pick index built from the same `RenderOutput`; Scene never invoked |
| Picks | trimmed gap, arrowhead, self-loop, 3-lane bundle, compound band/interior, representative; degraded fallback |
| Disclosure | 1,024 toggles; 1,025 → COMPOUND_TOO_LARGE, no change; hidden selection survives |
| Relayout | pins bit-exact after 64 steps with parents; non-CoSE composition relayouts via CoSE from current positions; budget exceeded → BUDGET; cancel restores bit-exact; persistence round-trip |
| Emphasis | plane bits per flag; propagation through collapsed and aggregate; `visual_states` unchanged for the same flags |
| Keyboard | Playwright: sentinel Tab in/out both directions; every op reachable including move/relayout; Escape propagation when empty; axe on companion |
| Cap | brush over 10,001 nodes → SELECTION_TOO_LARGE, selection unchanged; 10,000 ok; remote event 10,001 → rejected; temporal `set_selection` 10,001 → SelectionTooLarge |
| Idempotency | same `op_seq` replay returns cached result, no change; CAPACITY retry returns retained result |
| Isolation | two sessions: group 0 → UNLINKED; linked applies `source:"linked"`, no echo; SelfEcho/StaleRemote rejected |
| Latency | `scripts/bench_graph_interaction.py` 1e3–1e6 nodes: render/hover/select/brush/disclosure p50/p95 under `spec/performance/` |
| Parity | fixture bytes `tests/fixtures/graph_interaction/` replayed byte-equal in Python, Node, browser; VS Code reload + two panels |

## 7. Slices and implementation status
<a id="implementation-status"></a>

| Slice | Content | Status |
|---|---|---|
| S1 | Hierarchy in composition (`parent_uuid` -> `node.parent`, composition v2); identity (`ElementRef`, exact result-id table); `GraphInteractionState` extraction and 10,000-ref cap; `GraphSession` create / select / clear / focus / bind / unbind with stamps and `op_seq` idempotency | **implemented** |
| S2 | Render publication (§2.3 minus the pick index, §2.9): `RenderOutput`, emphasis plane, aggregate refs, hover, highlight, disclosure, pin/move/relayout, FocusStep/FocusRing, F4 bound visibility, revisions | implemented (see S2 notes) |
| S3 | Pick index, admission and degraded mode (§2.3); `CoordinationGate` + `ApplyRemote` (§2.4); `session_update` (§1.2) | typed Rust implemented locally; finite-geometry, real package/assets/parity and full strict-CSP proofs pass under authorized 1,513/626-KiB limits; final independent review and CI pending |
| S4 | Native + WASM session ABI, browser `DT.u32`, manifest. **Depends on** S3's `CoordinationGate` / `ApplyRemote` / `session_update` (deferred out of S2) and **must deliver the render style/emphasis planes whenever they changed, not only when `render_revision` changed** (style-only operations republish at the same revision) | implemented locally; validation/package status in the S4 receipt; independent parent review pending |
| S5 | Browser controller, accessibility, emphasis pass and painter attributes; delete the `58_graph.ts` hover policy | planned |
| S6 | Python/Node `GraphSession`, channel kind, VS Code protocol | planned |
| S7 | Evidence: bench, parity fixtures, Playwright, cross-session result-id proof | planned |

### S1 notes
- **Typed seam, no placeholder.** The session publishes no render in S1:
  `render_revision` stays 0, the only stamp that can match; an aggregate ref
  (which names a published render) answers `GF_INTERACTION_STALE`. Temporal
  visibility (§2.9) entered at S2 through the same bound `TemporalHost`.
- **Derived-pair keys.** The earlier claim that `(layer, path, order)` alone is
  unique was false for derived pair edges (`order = -1`, `path = NONE`); §2.1
  keys those by result row.
- **Wire shape.** Statuses and refs are Rust types in S1. The 56-byte
  `ElementRef` wire layout and numeric status values are defined with the ABI in
  S4; transported derived refs carry the exact result id, not a hash.
- **Coordination.** The `CoordinationGate` extraction and `ApplyRemote` are S3.

- **Recovery evidence.** The local history-preserving recovery on the combined
  milestone integration base, prior review findings, unchanged ABI contract,
  functional checks and failed unchanged WASM size gates are recorded in
  [S1 recovery](../performance/graph-s1-recovery-2026-10-31/README.md).

### S2 notes
- **Revisions.** `render_revision` is the stamp. It advances on structural
  changes only (pin, move preview/commit/cancel, relayout step, an effective
  disclosure, a changed bound temporal frame, bind/unbind) and when a render is
  requested with a different camera than the previous publication. Selection,
  focus, hover and highlight republish at the same revision. A bound session
  folds the temporal frame revision in before every stamp check (F4), so a host
  holding a pre-frame render is rejected `Stale` and repaints. `render(None)`
  is the unculled render the host `layout_render` produces; `Some(camera)` culls
  to the camera's data-space viewport (`screen = data * scale + offset`).
- **Visibility is not a published plane, and membership is not source
  visibility.** `member_of == NOT_RENDERED` says a source node is hidden,
  culled, or temporally invisible; the design's separate `visible` u8 would
  restate it, so S2 omits it (S3's pick index and the S4 wire read `member_of`).
  A collapsed group is visible and rendered, and its collapse-hidden members
  map to its render node: a member can be hidden from the source graph yet
  have a render node. Consumers must not read "has a render node" as "was
  drawn as itself".
- **One locked world per operation (F4).** A bound session validates the
  temporal revision, applies the stamp check, mutates the shared state, and
  captures the render inputs (revision, visibility, state) under a single
  registry lock (`TemporalGraph::world_parts`); a render builds and publishes
  inside it. A frame therefore cannot advance between the check and the apply,
  and no render pairs new visibility with an old revision. An Owned session has
  no lock to hold.
- **Temporal masking precedes the hierarchy.** An invisible node leaves the
  parent forest (its children re-attach to the nearest surviving ancestor, its
  collapsed flag is dropped) *before* `compound_collapse`, so an expired
  collapsed group neither hides nor reroutes its live members.
- **Layout follows the snapshot.** The initial layout and every relayout run on
  the visible subgraph with the surviving hierarchy (invisible nodes do not
  repel, invisible edges do not pull) and write back to source indices;
  invisible nodes keep their positions (an unplaced one is parked at the
  visible centroid). The retained force state is dropped on a frame change,
  bind/unbind, and whenever the visible nodes or the authoritative pin set
  differ from those it was built with, including pins changed through
  `TemporalGraph::set_pinned_nodes`.
- **Admission before expansion.** A request carries at most 10,000 refs; each
  distinct aggregate expands once, and the total is admitted against the
  selection cap before anything is allocated.
- **Keyboard selection is whole.** `select_focused` selects what the focused
  drawn stop stands for (an aggregate's or collapsed group's member nodes, an
  aggregate edge's member edges), as a pointer selection does; with no current
  publication it is the focused element.
- **Revision exhaustion.** `GF_INTERACTION_REVISION_EXHAUSTED` replaces wrapping.
- **Focus on a group.** Focus is UUID-keyed state, so an aggregate render node
  (or collapsed group) is focused through its lowest-index visible member
  (`RenderOutput::focus_node`), a rendered aggregate edge through its
  lowest-index member edge. `FocusRing` orders the ring node, out-edges,
  in-edges, then neighbors (each ascending in render index) around an anchor
  that persists until focus changes by another operation or the render changes.
- **Hover** is a transient session set (HOVERED on the target and every member
  of an aggregate, NEIGHBOR across temporally visible, collapse-rerouted edges);
  it is not part of
  `GraphInteractionState`, so it neither binds to a temporal graph nor bumps the
  revision.
- **Path highlight** accepts consecutive nodes joined by a composed edge in
  either direction (the lowest edge index joins the highlight); a pair with no
  edge is `Invalid` and nothing changes. Community highlight adds the induced
  edges.
- **Deferred to S3.** The pick index and admission, `CoordinationGate` /
  `ApplyRemote`, and `session_update` are not in S2. Relayout persistence is by
  re-creating a session from `positions()` + `pinned()` (`load.x/y/pinned`),
  which restores without relayout and renders byte-identically.
- **Bounded work.** Every pass of render, hover, walks, highlight and
  disclosure is linear in nodes + edges (+ the bounded selection); a
  deterministic `work()` counter in the session backs the size-ladder test, and
  a 100,000-node parent chain renders in the same test run.

### Bounded S2 recovery

The #1038 slice table above retains the PR's explicit deferrals: pick,
coordination and update are S3; the native/WASM session ABI is S4. The original
S1 table bundled these into S2; this narrower recovery does not establish that
broader acceptance or #36/milestone 4 completion. Browser controller,
accessibility and host delivery remain later work. Rust focus walks here are
state operations, not a keyboard/browser implementation.

Recovery fixes three remaining review findings: initial force work participates
in relayout admission; rejected moves validate before seeding and keep any
fresh positions local until successful; hover resolves current representatives
and follows rerouted edges, including after disclosure changes. Aggregate
admission counts the union with explicit member refs, preserving the exact
10,000-ref limit without expanding oversized groups. These changes leave
composition v2, the shared temporal interaction state, authored flags, ABI
surfaces and worker ACK/cancel behavior unchanged. The deterministic nearest
visible ancestor implementation remains shared with composition and bounded
by `<=2n` parent-link visits.

Source-bound validation and package status are recorded in
[S2 recovery evidence](../performance/graph-s2-recovery-2026-10-31/README.md).
The subsequent
[bounded size repair](../performance/graph-s2-size-repair-2026-10-31/README.md)
retains scratch-free forest validation with unchanged exact first-error order.
It saves 136 raw / 88 gzip bytes; at that checkpoint packaging failed the
unchanged S1 gates by 515 raw / 527 gzip bytes. A subsequent explicit S2
functionality decision sets the smallest next-KiB limits to 1,512 raw / 626
gzip KiB without changing session behavior, validation or compiler profile;
see the separate [packaging decision and validation receipt](../performance/graph-s2-package-budget-2026-10-31/README.md).
Final independent review of the complete integrated diff remains required.

### S3 local candidate
Typed publication picking, shared coordination admission, and atomic replacement
are implemented locally; validation receipts and remaining package/review gates
are recorded in [S3 local evidence](../performance/graph-s3-local-2026-10-31/README.md).
The separate [S3 review repair](../performance/graph-s3-review-repair-2026-10-31/README.md)
records the first finite edge-arithmetic blocker repair and two historically
rejected codegen boundary experiments. At that checkpoint the raw package gate
failed by 221 bytes; the original S3 receipts remain unchanged.
The separate [S3 package decision receipt](../performance/graph-s3-package-budget-2026-10-31/README.md)
records the later independent circle-outline clip finding and local finite
admission repair, the parent's retention of only `#[inline]` on the shared gate,
and the authorized 1,513-KiB raw limit with gzip unchanged at 626 KiB. Fresh final
source packages at 1,548,390 raw / 640,709 gzip bytes (922 / 315 bytes headroom).
Real paired assets, Node native/WASM parity, native temporal seams and the
original full strict-CSP foundation pass. Final independent review of the whole
integrated S3 diff and CI remain pending.
This does not establish S4 wire capacity behavior, browser/host delivery, #36,
milestone 4, or release completion. No ABI/export/manifest version changes.

### S4 wire decisions (implementation contract)

`XYGI` and `XYGR` use the existing version-1 named-section container, little
endian and 8-byte aligned. All request sections have index zero; unknown or
operation-inapplicable sections, wrong types/counts, nonzero unused header
fields, invalid enums and overflow are Invalid. `header.u64` is exactly
`[instance, group, op_seq]`; `header.u32` is exactly the nine fields above.
Operations 0–18 retain §2.2 numbering; 19 Open, 20 Update, 21 Render and 22 Poll
complete the transport vocabulary. Open/Update carry `document.bytes` (XYGF).
Open/Render/Bind also require a nonzero sequence; all successful commands share
one last-sequence cache of complete serialized bytes. An equal sequence with
different request bytes is Invalid; a byte-identical retry returns that exact
reply, including across a temporal frame change (a disposed binding still
returns Unbound). Native create additionally retries identical open bytes by
instance id until destroy; a conflicting open for that id is Invalid.

Status values are 0 success, and -1 Stale, -2 Unlinked, -3 Invalid, -4 Budget,
-5 Capacity, -6 SelfEcho, -7 StaleRemote, -8 SelectionTooLarge,
-9 CompoundTooLarge, -10 Unbound, -11 RevisionExhausted. `status.u32` contains
the two's-complement value. Export return codes use this same vocabulary;
instance/staging errors on the new WASM exports also use it. Existing exports
retain their own vocabulary. Failed commands leave the last success cache and
all state unchanged. Capacity is a native copy refusal after successful
execution: required length is written, no bytes are copied, and the reply is
retained. Poll is the exception: it serializes and tests capacity before taking
the pending event; short polls never consume. Poll retries use their sequence
and return the same bytes without consuming a newer event.

Each refs byte plane starts with `[count:u32, string_bytes:u32]`, followed by
`count * 56` fixed records and one UTF-8 string pool. Record offsets are:
`kind:u32@0` (0 node, 1 edge, 2 derived, 3 aggregate), `reserved:u32@4=0`,
`uuid[16]@8`, `layer:u32@24`, `render_revision:u32@28`, `path:u64@32`,
`order:u64@40`, `string_offset:u32@48`, `string_length:u32@52`.
Unused fields are zero. Derived refs have NIL UUID and zero render revision;
`string_offset=0xffffffff,length=0` means absent id. Present ids contain exact UTF-8 bytes of any length admitted by the request
and resource caps. A present-empty id has the actual current pool cursor and
length zero; it never uses the absence sentinel. Aggregate index is in `layer`; other identity fields are zero.
Pools must be contiguous in record order with no unused bytes. All outgoing
derived refs use exact strings, never local table slots or hashes.
`remote.bytes` is itself an XYGI container with `remote.u64` = group, source,
sequence, optional one `remote.generation.uuid`, and `refs.bytes`.
`temporal.u64[handle]` is present only on Bind (zero unbinds); WASM accepts 1
for its own current owner and 0 to unbind, never another instance handle.

`companion.u32[page,size]` defaults to [0,50], size is 1–200; this also pages
`candidates.bytes` in canonical source node then edge order, with
`candidates.total.u32`. Rows contain kind, identity, label, relationship and
selected state, escaped as §3. Focus ring is `[kind,index]` pairs (node=0,
edge=1) in the existing ring order, paged by the same bounds. Results always
include current render geometry/style/emphasis, source flags, focus, summary
and the bounded companion/candidates page; style changes are delivered even
at the same render revision. Position records are 80 bytes: one fixed 56-byte
node ref, x/y f64, pinned u32 and zero reserved u32. The resolved CPU paint snapshot below uses the existing container and
`RenderOutput.paint`; there is no second host style/layout/router or Scene path.
No S5 painter/controller change.

Commands execute on an admitted speculative session and interaction state
under one authoritative temporal world lock. Typed mutation, render, semantic
reply construction and serialization all succeed before installing either
session or owner state; a failure discards the candidate and consumes no
sequence, watermark, publication or delivery. This is a bounded transaction,
not a second canonical graph: only the interaction state is speculative; the
owner's graph/visibility is borrowed from that single locked world. The
candidate's visibility snapshot is temporary and discarded at commit.
Admission conservatively reserves retained session/document/publication/index,
old/new reply, input/staging, speculative copies, and render/layout/codec work
BEFORE candidate allocation. Checked arithmetic overflow refuses Budget.
The accounting constants and source-size formula live beside the executor;
they intentionally refuse some graphs whose actual allocation could fit.
Native sessions default to the existing 384-MiB WASM arena ceiling. WASM
includes other retained instance work in this admission. No budget change is
implied by exposing the session exports.

Native handles are monotonic, never reused; at most 256 entries. The registry
is held only to clone/remove an entry. Lock order is session -> temporal
operation -> temporal state; disposal invalidates an owner even if an Arc
survives. WASM keeps one session per instance and a directly locked temporal
owner, never a host adapter that re-enters the instance registry. Replacing or
dropping the temporal binding, destroying the instance, or acquiring geographic
transport disposes the old owner. A new owner cannot revive an old binding.

A WASM instance with a live session rejects unrelated ordinary compiler/job
operations; close it first. Temporal-graph commands remain compatible and are
pre-admitted with the retained session. Geographic transport acquisition drops
the session and disposes its temporal owner. WASM `interact` also accepts Poll
operation 22; the instance output is the complete retained reply. Render is a
repaint request: its revision is advisory, allowing recovery after a temporal
frame advance; every interaction still requires the exact current stamp.
Disclosure action values are 0 Toggle, 1 Collapse, 2 Expand; step/ring direction
is action 1 or 0xffffffff. Mode is 0 Replace, 1 Add, 2 Toggle; policy is
0 Nodes, 1 Edges, 2 NodesAndInducedEdges; plane is 0 Path, 1 Community, 2 External.
`changed.refs.bytes` can contain up to 20,000 refs (the symmetric difference
of two admitted selections); request ref lists remain capped at 10,000.

Native create returns Capacity with a zero handle when the 256-entry table or
monotonic handle range is exhausted; this allocation refusal applies no state.
The applied-output meaning of Capacity applies to command replies, not create.
Native `out_len` is a `size_t*`; all request and output lengths are `size_t`.
Native create's `load` argument is the full OPEN request, including its document;
the separate document/scalar identity/group arguments must match it exactly.
The immutable OPEN request/ack is retained until close, independently of the
last command cache; WASM identical OPEN retries return that original ack even
after later commands. Close/destroy revoke lifetime and are not retryable.

OPEN acknowledges ingress with status/header only; Poll returns status and an
optional outbound snapshot only. Successful render/update/bind/interaction and
companion replies carry the semantic/publication planes described above. A
failed native request returns its negative export status and zero out_len,
without replacing the last successful XYGR cache; failed WASM requests likewise
return the status directly. The last successful cache is never an error reply.
Aggregate focus summaries derive Group/member counts from that same publication.

S4 final local proof after normal parent merge: full Rust/Clippy, native and real
WASM byte replay, capacity/disposal/transaction tests, exact-ID string-table
reordering and the original full strict-CSP diagnostic foundation pass. The
real shipping producer fails unchanged gates: 1,852,594 raw / 755,339 gzip6
bytes versus 1,549,312 / 641,024 allowed. No shipping assets are published;
diagnostic staged assets do not waive that failure. Detailed append-only proof:
[S4 local receipt](../performance/graph-s4-local-2026-10-31/README.md#final-merged-source-handoff).
`coordinate_deliver` targets one explicit receiver handle with ApplyRemote (16);
transport peer enumeration/routing is not public host integration in S4.


### S4 review repair: resolved CPU publication sections

Every successful post-Open command (including style-only operations at the same
revision) carries all sections below, index zero, including zero-length sections.
Open remains an ingress acknowledgment; Poll carries only its event/status.
Let N/M/P/F denote published nodes/edges/clipped pieces/frame bands. Container
scalar counts equal the counts below. Little-endian fields are packed explicitly,
without Rust struct padding; reserved bytes must be zero.

| Section | Container dtype / scalar count | Fixed record, in field order |
|---|---|---|
| `paint.node.center.f64` | F64 / 2N | mapped screen center x,y |
| `paint.node.style.bytes` | Bytes / 60N | style + semantic layers below |
| `paint.edge.style.bytes` | Bytes / 60M | style + semantic layers below |
| `paint.piece.index.u64` | U64 / 2P | published edge index; flags bit0 single_piece, bit1 head present, all others zero |
| `paint.piece.geometry.f64` | F64 / 14P | start x,y; end x,y; half_width; dash on,off; dash_offset; head triangle x,y ×3 (six zeros when absent) |
| `paint.frame.node.u64` | U64 / F | published node index |
| `paint.frame.geometry.f64` | F64 / 5F | xmin,ymin,xmax,ymax,half_width |

A 60-byte style/layers record is: fill RGBA u8@0, stroke RGBA@4,
halo RGBA@8; size/width/opacity f32@12/16/20; shape/dash/arrow/state
u8@24/25/26/27; semantic halo/body/stroke RGBA@28/32/36;
halo_extent/body_width/dash_on/dash_off f32@40/44/48/52; head u8@56
(0/1); reserved u8@57..59=0. These are the resolver's exact values;
style size is the outer node diameter. All geometry and style floats are finite.
The Rust `wire::decode_paint` validator reconstructs `PaintGeometry` with no
semantic, route or layout evaluation, checking types, strides, cross-plane
counts, indices, flags, absent-head zeros and reserved bytes. Scalar type/count
mismatches and malformed pools remain Invalid. Node and edge flags remain the
source-indexed `node.flags.u32` / `edge.flags.u32`; visual/emphasis planes and
membership CSR retain their existing publication indexing.

Vector order is canonical draw order within each pass: frame bands, shafts,
heads, nodes (later vector index wins within a pass). Pick precedence is nodes,
heads, shafts, frame bands. The piece record refers to its edge style/layers;
frames refer to their node style. Routed clipped endpoints, dash origins and
head vertices are already resolved by Rust. Aggregate snapshots include neutral
aggregate styles even for singleton memberships and omit compound frames.

These f64 geometry sections are a **resolved CPU publication snapshot**, not
vertex buffers or a new GPU wire. They allow host-independent inspection and
replay of the same geometry used by the pick index. Subsequent generic GPU
encoding remains Rust-owned and must use the existing §29 offset-f32/u8
lowering. Hosts must not upload these f64 arrays directly, narrow them in
TypeScript, or recompute semantic/router policy. S5 controller/shader/DOM/ARIA
and emphasis rendering remain outstanding.

### S4 review repair: admission and owner transitions

The unchanged browser default is 16 MiB, native default / arena maximum 384 MiB.
A real two-node/one-edge XYGF open/render/select/focus is admitted at 16 MiB.
This is a bounded tiny-session proof, not arbitrary-cardinality admission or
S7 scale/responsiveness acceptance. Every command still speculatively clones,
renders and serializes: O(source + publication) work per command. No interaction
latency improvement is claimed.

Before candidate allocation, checked admission reserves the following peak
envelope. With D encoded document bytes, n/m source counts, R=n+m,
S=min(R,10,000), Q=min((2n+11m)*4096,1,048,576), W coordination watermarks:

| Component | Reserved bytes | Scope |
|---|---:|---|
| bounded tables/codec metadata | 98,304 | fixed baseline overhead; bounded section metadata is covered by document/request factors |
| document/decoded copies | 48D | retained document, identity/style tables, old/new decoding and codec temporary copies |
| source/publication/layout/route work | 8,192R | old/new publication/index primitives, membership, route scratch (up to 11 pieces/edge), layout and query arrays |
| grid duplication | 16Q | old/new bounded grid entries; includes up to n compound bands as well as n nodes |
| possible local state | 1,024(4S+n+1) | four capped identity planes, all possible node pins, focus; tree overhead and bounded delta/outcome/candidate copies |
| watermarks | 128W | retained/cloned coordination gate |
| expanded document text | 128T | T = per-row label bytes + layer ID bytes + m × longest layer ID byte length |
| retained request/reply caches | 3 × each actual byte length | opening, Open reply, last request and last reply |
| next request/staging | 128 × actual request bytes + external | decoded request identity copies, codec work; WASM arena/output/other owner retention is external |
| replacement | full new document envelope | Update retains old while admitting new |

Current Owned state is charged additionally. Inside the authoritative owner
lock, before cloning bound state, actual state items and exact UTF-8 bytes are
also charged at 1,024/item and 128/text byte. This includes all four planes,
pins and focus, even identities retained by another session but absent from
this document. Pending outbound exact-ID bytes are separately charged at 128×.
All products/sums are checked; overflow or exceeding the arena returns Budget
before candidate/state/sequence/cache mutation. Borrowed request/event/ref
validation checks UTF-8, offsets, sentinel, reserved fields, ordering and count
caps without cloning result-ID text before admission.

T counts dictionary-expanded labels at every row occurrence: XYGF uses a
monotonic-offset TextList, not Arrow dictionary indices, so its entire per-row
UTF-8 pool is charged before allocating Strings. The m×longest-ID bound covers
repeated derived identities, even when a short document stores one layer ID.
The 128× text allowance covers retained/speculative/state/delta/outcome copies,
20,000 changed refs, 10,000 pending refs, 200 candidates and focus, old/new
reference pools/builders/final replies, and companion formatting. Arbitrary UTF-8
Debug escaping can expand a byte up to tenfold; subsequent cell escaping up to
twice that, with rows, joined rows and builder/final buffers overlapping. The
128× envelope includes these expansions and intermediate copies. Fixed item
reserves account for string headers separately. This intentionally refuses
some inputs that would fit actual allocation; it is not an RSS report.

Bind/Unbind validate the old LIVE owner's frame revision and destination stamp
in the same authoritative snapshot immediately before installation. Same-owner
rebind validates, constructs and installs under that owner's one lock; native
adapters identify the underlying owner, not their temporary wrapper allocation.
Cross-owner bind constructs the destination snapshot first and releases its
lock, then validates the old owner and installs under the old owner's lock.
No owner locks are nested. A destination frame advancing after its snapshot is
handled by the usual next-operation stale check / Render recovery. A change to
the old frame during construction refuses Stale without installation. Unbind
validates a live old owner under its lock; a disposed owner explicitly permits
Unbound-to-unbind recovery with the last session stamp. Failure preserves owner,
session, publication, retry cache, sequence and outbound event. Render refreshes
the stamp, allowing the same unconsumed operation sequence to recover.

Repair evidence is append-only in
[the review-repair receipt](../performance/graph-s4-review-repair-2026-10-31/README.md).
Historical S1–S4 receipts, including failed package/diagnostic proofs, are unchanged.


The native S4 create parameter is named `document_bytes` in generated C/Koffi
metadata so the existing Node browser-global guard does not confuse its FFI
signature string with a runtime global. All 537 native binary function types,
argument order and calling convention remain unchanged (ABI 397); official ABI
generation updates the named-signature digest. No guard exemption or runtime
host behavior change is involved. The final repaired module remains over the
unchanged package gates; diagnostics and final independent review do not imply
shipping or M4/#36 acceptance.
