# Graph interaction, coordinated selection, and accessibility (#36)

Status: **design final; S1 and S2 implemented** (see [Implementation status](#implementation-status)).
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
(the registry that owns the graph implements it; `xyg-core` does in S3), under
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
**SetHighlight**: planes Path/Community/External → state bits `FLAG_PATH=1<<8`, `FLAG_COMMUNITY=1<<9`, `FLAG_EXTERNAL=1<<10`, `FLAG_FOCUSED=1<<7`; `KNOWN_STATE_FLAGS=(1<<11)-1` (both validators `graph_style.rs:175,1738`). Path refs are ordered nodes; each consecutive pair must be a composed edge (lowest `order` lane flagged) else `GF_INTERACTION_INVALID`. Community flags nodes + induced edges.
**Pin{ref,on}** writes the node's current f64 into the session pin mask bit-for-bit (`graph-mark.md:275-277`). **MoveNode**: `space` 0 data / 1 screen-delta (converted through the stamped camera in Rust); `commit` 0 preview (positions plane updated, `move_origin` recorded once), 1 commit (implicitly pins, emits `graph.positions`, clears `move_origin`), 2 cancel (restores `move_origin` f64 bit-exact). Out-of-bounds → `GF_INTERACTION_INVALID` (`graph-mark.md:277`). Any committed position change invalidates the relayout state (§2.6) and republishes.
**Idempotency.** Every mutating request carries `op_seq: u64`. The session keeps `last_op_seq` and the last result bytes; `op_seq == last` returns the cached result with no state change; `op_seq < last` → `GF_INTERACTION_INVALID`. `GF_INTERACTION_CAPACITY` means the state was applied but the result did not fit; the retry with the same `op_seq` and a larger `out_cap` returns the retained result.

### 2.3 One render/publication path
`session_render(camera)` with `camera = f64[scale_x, scale_y, offset_x, offset_y, vp_w, vp_h, dpr]` produces one `RenderOutput`:
```
tier u32, edges_kept u64, node_x/y f64, member_of u64, edge_src/tgt u64, edge_members CSR u64,
visible u8, visual_states u8, emphasis u8 (nodes), edge_visual_states u8, edge_emphasis u8 (edges)
```
Pipeline order (source index space until the last step): (1) the bound temporal frame's source visibility (nodes and edges) masks the source graph (§2.9); (2) `compound_collapse` (`graph_style.rs`) over the document hierarchy, `load.collapsed`, and the propagated state flags yields visibility, `representative[]`, and rerouted endpoints with edge provenance; (3) `graph::build_render` (budgets, viewport culling, LOD) runs over the collapsed source graph; (4) membership composes source -> representative -> render node and source edge -> render edge CSR; then `resolve_visual_state` per render element. A collapsed parent that is off-viewport with an on-viewport child renders and picks the representative, not the child; aggregate centroids exclude hidden descendants. **The same `RenderOutput` value is (a) copied into the `render.*` result sections the host packs into its existing §29 paint payload (`_graph_wire.py` keys `visual_states` etc. unchanged, plus `emphasis`) and (b) the only input to the pick index.** Hosts never run `layout_render` beside a session. Proof: pick index node count equals `render.n_nodes`, every hit index `< n_nodes`; the Python wire payload built from result bytes is byte-equal to `_graph.layout_render` on the same inputs at direct tier.
Pick index: render nodes, and render-edge pieces from `edge_route_segments_with_ends` trimmed by `node_border_distance` and extended by `GRAPH_EDGE_HEAD_LENGTH_PX` (as painters do, `edge_route.rs:481-494`); self-loop = 3 pieces; parallel lanes separate (ties: draw order, then `order`); compound frame band hits the compound, interior passes through; collapsed representative selects members. Admission (`interaction.rs`, geo's shape `geo_interaction.rs:8-14`): `MAX_GRAPH_PICK_PRIMITIVES=131_072`, `_GRID_ENTRIES=1_048_576`, `_CANDIDATES=65_536`, `MAX_GRAPH_INTERACTION_WORK=4_000_000`, 64×64 grid. Over the primitive budget the index keeps nodes and single-piece edges, `pick.degraded=1` (recorded, §28); brush/lasso stay exact for nodes, edges fall back to induced. Work exceeded mid-query → `GF_INTERACTION_BUDGET`, no change. Each render `render_revision += 1`.

### 2.4 Stamps and coordination
Destination stamp `(instance_id, render_revision)` on every local event; mismatch → `GF_INTERACTION_STALE`, no change (host repaints, resubmits). Origin stamp on `ApplyRemote`: `GraphCoordinationEvent { group_id, source_instance, revision, generation uuid, refs[0..10_000] sorted unique }`. The gate (`group_id!=0`, wrong group no-op, self → SelfEcho, `revision<=last_seen` → StaleRevision, atomic apply, no local bump, no echo; `temporal_controller.rs:346-389`) is extracted to `coordination.rs::CoordinationGate` and used by both controllers. Outbound: after a local selection change in a nonzero group Rust queues one snapshot; `poll_event` → host link channel kind `graph_select` (`interaction.md:294-297`) or same-process `coordinate_deliver`. Receiver fires `graph.select` with `source:"linked"`, never rebroadcast.

### 2.5 Disclosure
`ToggleDisclosure{ref,action}` on a compound runs `compound_collapse_transition` then `compound_collapse` and `session_render` in one call. **Tier decision (recorded in graph-mark.md §7.1.5 and the §28 ledger):** explicit compound disclosure is a direct-tier feature bounded at `MAX_COMPOUND_TRANSITION_NODES = 1_024` source nodes (`graph_style.rs:30, 1664-1675`). Above it the op returns `GF_INTERACTION_COMPOUND_TOO_LARGE`, no state or revision change, and the companion shows "grouping is camera-driven for this graph"; large graphs get render-tier aggregates (camera-driven LOD), which are selectable (members), focusable, hover "group of k", and reject `action` with `GF_INTERACTION_INVALID`. Hidden members keep UUID-keyed state; `CompoundCollapse.flags` propagates to the representative. Proof: 1,024-node fixture toggles; 1,025 → status, revision unchanged.

### 2.6 Positions and relayout
The session owns `positions: (Vec<f64>, Vec<f64>)`, `pinned: Vec<u8>`, `parents`, and `relayout: Option<ForceState>`. `RelayoutStep{steps ≤ 64}` lazily builds `ForceState::new_configured(LAYOUT_COSE, …, init = current positions, pinned, parents)` (`graph.rs:670-703`, the only engine honoring pins + parents) and steps it; `steps × (n+e) > MAX_GRAPH_INTERACTION_WORK` → `GF_INTERACTION_BUDGET`. **Relayout always uses CoSE seeded from current positions regardless of the composition's original layout**, because `xyg_graph_layout` has neither pins nor parents (`lib.rs:15480-15492`) and the issue requires pins honored; simplest and keeps Pin/MoveNode valid for every layout. Pinned nodes stay bit-exact (`graph-mark.md:275-277`). Any MoveNode commit, Pin change, or `load` update drops `relayout` (rebuilt on next step). Result `relayout.alpha.f64`, `relayout.done.u8`. Scheduling/animation remains #35 (`python/xyg/graph_layout.py`). Persistence: result `positions.changed` (ref, x, y, pinned); `session_update(load.x/y/pinned)` restores without relayout.

### 2.7 Visual semantics
`resolve_visual_state` precedence (`graph_style.rs:1497-1514`) is untouched; the new bits never compete there. Rust emits an **independent `emphasis` u8 plane** per render node and render edge: bit0 FOCUSED, bit1 PATH, bit2 COMMUNITY, bit3 EXTERNAL, bits 4–7 zero. Projection: `collapsed_node_flags`' `PROPAGATED` (`graph_style.rs:1882-1890`) gains the four bits so hidden members project to their representative; across LOD aggregates the plane is the OR over `member_of` members (edges: OR over CSR members). `emphasis = (flags >> 7) & 0xF`. Painter contract: one extra u8 attribute on the existing node/edge instances, drawn in an emphasis pass after base elements: community halo (tinted, under), path stroke (accent, nodes and edges), external dashed outline, focus ring (theme focus color, 2 px × dpr, top). All set bits draw; no precedence. Reduced motion: static ring.

### 2.8 Status codes
Stable codes (`InteractionStatus::code`): `GF_INTERACTION_STALE`, `_UNLINKED`,
`_INVALID`, `_BUDGET`, `_CAPACITY`, `_SELF_ECHO`, `_STALE_REMOTE`,
`_SELECTION_TOO_LARGE`, `_COMPOUND_TOO_LARGE`, `_UNBOUND`. A failed operation
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


## 3. ABI / WASM
Container codec unchanged; add `DT.u32` to the **browser encoder** (`49_wasm_graphforge.ts:91-99`; the decoder `:164` and Python `DTYPE.U32` `_graphforge_container.py:49` already have it).
Native (`xyg-core`, ABI 383→384, regenerate manifest): `xyg_graphforge_session_create(doc, load, instance_id, group_id, out_handle)`, `_update`, `_render`, `_interact`, `_bind_temporal`, `_poll_event`, `xyg_graphforge_coordinate_deliver`, `_destroy`; `GRAPHFORGE_MAX_SESSIONS=256`; `out_cap` short → `GF_INTERACTION_CAPACITY` + required length. WASM: `_session_open/_update/_render/_interact/_close`, one per instance, output in `instance.output` under `max_arena_bytes`.
Request `XYGI`: `header.u64`[instance_id, group_id, op_seq]; `header.u32`[render_revision, operation, mode, policy, plane, action, commit, steps, space]; `camera.f64`; `coordinates.f64`; `refs.bytes` (kind-tagged refs; transported derived refs carry the exact result id, §2.1; byte layout fixed with the ABI); `uuids.uuid`; `remote.bytes`; `companion.u32`[page, size≤200]; `load.*` (§1.2).
Result `XYGR`: `status.u32`; `header.u32`[render_revision, pick.degraded, unmatched, dropped]; `render.*` (§2.3, when revision changed); `node.flags.u32`/`edge.flags.u32` (source-indexed state); `focus.bytes`, `focus.ring.u32`; `changed.refs.bytes`; `candidates.bytes`; `positions.changed.bytes`; `relayout.alpha.f64`, `relayout.done.u8`; `companion.text.utf8` + `companion.total.u32`; `summary.text.utf8`; `outbound.bytes`. Companion text: rows `\n`-separated, cells `\t`-separated, cell escaping `\\`→`\\\\`, `\t`→`\\t`, `\n`→`\\n`; DOM sets `textContent` only.
Statuses: `GF_INTERACTION_STALE, _UNLINKED, _INVALID, _BUDGET, _CAPACITY, _SELF_ECHO, _STALE_REMOTE, _SELECTION_TOO_LARGE, _COMPOUND_TOO_LARGE, _UNBOUND`. Static export path (`request.selected`, `compose.rs:640`) unchanged.

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
| S3 | Pick index, admission and degraded mode (§2.3); `CoordinationGate` + `ApplyRemote` (§2.4); `session_update` (§1.2) | planned |
| S4 | Native + WASM session ABI, browser `DT.u32`, manifest | planned |
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
- **Visibility is not a published plane.** `member_of == NOT_RENDERED` already
  says a source node is hidden, culled, or temporally invisible; the design's
  separate `visible` u8 would restate it, so S2 omits it (S3's pick index and
  the S4 wire read `member_of`). A collapsed group is visible and rendered; its
  hidden members map to its render node.
- **Focus on a group.** Focus is UUID-keyed state, so an aggregate render node
  (or collapsed group) is focused through its lowest-index visible member
  (`RenderOutput::focus_node`), a rendered aggregate edge through its
  lowest-index member edge. `FocusRing` orders the ring node, out-edges,
  in-edges, then neighbors (each ascending in render index) around an anchor
  that persists until focus changes by another operation or the render changes.
- **Hover** is a transient session set (HOVERED on the target and every member
  of an aggregate, NEIGHBOR across visible edges); it is not part of
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
