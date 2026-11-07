# Immutable temporal graph acquisition and retained exports (XYFG v1/v2)

Native Python/Node export SVG, PNG and offline HTML through retained canonical
Scene geometry. Public browser sessions capture XYFG v2 through their actual
Worker and export Scene, XYPB, SVG, PNG and the same offline HTML. PNG uses the
same Rust raster/encoder in the single module under the unchanged packaging
caps. Full #45 and milestones 4–7 acceptance remain open. Composition remains the only
chart-building surface. No host owns graph filtering, layout or style policy.

The v1 acquisition and ABI403 checkpoint descriptions below retain their
historical scope. The ABI404/WASM36 continuation supersedes their future-seam
statements; historical receipts and original producer bytes are immutable.

## Public native acquisition

Python `TemporalGraph.freeze(revision=..., timezone=..., window=None,
budget_bytes=384*1024*1024)` and Node
`TemporalGraph.freeze({revision, timezone, window:null, budgetBytes:384n*1024n*1024n})`
return `FrozenTemporalGraph`. Python revisions are exact integer u64 values;
Node uses bigint u64/i64 inputs. The explicit revision must be the current
successfully accepted frame of that object. Mutable `frame()` dictionaries or
caller-supplied membership are never accepted as authority. No frame evaluation
or topology rebuild occurs. Rust calls the existing `TemporalGraph::freeze`
against the actual private native frame, including its graph-instance token.

`window=None` / null explicitly records no playback window. A supplied pair
is a half-open UTC-microsecond window containing the cursor. It is independent
of the selected frame range and is never inferred from it. `timezone` is required:
a nonempty UTF-8 display tag, at most 128 bytes, without NUL or control characters.
It preserves presentation intent only; it neither converts canonical UTC time
nor asserts an IANA database lookup. Ingest column timezones are not inferred
as controller/display bindings. A future controller adapter must supply its
actual window and display tag explicitly.

`to_bytes()` / `toBytes()` returns owned bytes. `metadata` provides inspection
of those Rust-validated bytes; editing returned Node byte copies cannot mutate
native storage. Python inspection uses a read-only mapping and immutable bytes
and tuples. The native snapshot handle owns encoded storage independently of
the graph, source column, projection or session lifetime. Later scrubs,
selection/focus/pin changes and source disposal leave snapshots unchanged.
Explicit `close()` releases the snapshot (Python also supports context managers).
`FrozenTemporalGraph.from_bytes` / `.fromBytes` validates offline bytes through
Rust before retaining them. Imported provenance never restores or authorizes
live graph/session handles. The checksum is an integrity check, not a signature.

## Optional accepted retained publication

Python may pass the existing private transport `session=` and guarded
`render_revision=`; native Node integrations may pass `sessionHandle` and
`renderRevision` (the shared native-handle helper is in
`temporal-graph-frozen.js`). This is integration with the existing GraphSession,
not a public session/chart constructor. Automatic notebook/browser publication
acquisition remains a later checkpoint.

Rust takes the session lock before the temporal operation/state lock, as normal
session commands do. The binding must name the **same native owner**, not merely
another temporal graph with identical UUIDs. The temporal frame and render
revision must still be accepted. The snapshot copies the exact original XYGF
document and current complete XYGR publication plus the accepted seven-f64
camera `[scale_x, scale_y, offset_x, offset_y, width, height, dpr]`. A session
without an explicit accepted camera fails closed. CPU resolved paint geometry,
source/render membership, visual flags, source positions and GPU publication
planes remain byte-identical to the producer. No host recomputes them.

The frame's persistent selection/focus/pins describe **frame publication time**.
The retained publication describes its own later interaction/style state, bound
to its render revision and full publication bytes; style-only republication can
share a revision in the existing session protocol. These records intentionally
remain distinct. A next adapter must paint the accepted publication's state and
retain both records, rather than silently substituting frame-time flags.

This checkpoint admits only sessions with the same ordered persisted node/edge
UUIDs and topology as the temporal source. Derived session edges fail closed;
they require an explicit identity/provenance extension before export. An
unpublished/stale session or a poll acknowledgement cannot stand in for a
publication. Passing another instance, even with identical topology, fails.

## Canonical codec

`temporal_graph_frozen.rs` owns private encoded storage. XYFG uses the existing
GraphForge named-section container framing v1 (32-byte header, ordered 40-byte
entries, 8-byte-aligned payloads). It appends eight digest bytes to the complete
container. Digest: BLAKE2s8 with the existing `xykeyv1` personalization over
`b"xyg-frozen-temporal-v1" + container`. Container total length excludes the digest.
All numbers are raw little endian; no JSON numerical wire is introduced.

Sections appear exactly in this order, always at index zero:

| Section | Type / meaning |
| --- | --- |
| version | u32[1] = 1 |
| identity | u64[2]: opaque graph instance, frame revision (both nonzero) |
| time | i64[3]: cursor, selected range start/end |
| window.kind | u32[1]: 0 absent, 1 half-open |
| window | i64[2]: start/end, canonical zero when absent |
| timezone | literal UTF-8 tag |
| node.uuid, edge.uuid | canonical source UUID order |
| edge.source, edge.target | u64 source node ordinals |
| node.visibility, edge.visibility | exact accepted u8 visibility (0/1) |
| visible.node.uuid, visible.edge.uuid | exact visible membership in source order |
| selected.node.uuid, selected.edge.uuid | persistent frame-time selection |
| pinned.node.uuid | persistent frame-time pins |
| focus.kind | u32[1]: 0 none, 1 node, 2 edge |
| focus.uuid | one UUID; all zero for none |
| render.identity | u64[2]: session instance, render revision; zeros without publication |
| render.camera | f64[7] above; empty without publication |
| render.document, render.publication | original XYGF / XYGR bytes; empty without publication |

Decode validates checksum, canonical framing/padding/order, exact section types,
nonzero unique source UUIDs, endpoint bounds/closure, exact visible memberships,
canonical ordered selection/pins, focus membership, temporal/window ingress,
selection count, and source/publication identity/topology. Attached publications
also pass the existing CPU paint and GPU validators and render-revision check.
Their CPU render planes must have matching counts and finite x/y positions;
edge endpoints must name render nodes. Node and edge CSR offsets start at zero,
end at the exact member count and delimit nonempty, ascending member lists.
Node lists and source-to-render maps are exact inverses. Source edges appear
at most once and their mapped source endpoints agree with their render edge;
all represented source entities must be temporally visible. Each CPU paint-node
center must bitwise equal the source render position projected with the captured
camera through the same Rust projector used by live paint. This also rejects
finite source/camera mutations that leave old paint centers behind; DPR controls
backing resolution and does not multiply CSS-space coordinates. Visual-state and
emphasis planes match the corresponding render counts. These checks validate
imported publications as well as acquisition; a recomputed checksum cannot
replace topology and membership validation. Unknown sections, versions, noncanonical
padding/trailing bytes, malformed or cross-source publications fail. Re-encoding
an accepted snapshot is byte-exact. Different live instances deliberately have
different provenance tokens even for equivalent source data.

## Admission and lifetime

Encoded snapshots are capped at 24 MiB. A conservative `16*encoded + 64 KiB`
peak envelope is capped at the unchanged 384 MiB per-operation limit. Retained
caller-owned snapshots accumulate across operations; the256-handle registry cap
is not a global process byte budget. Global CPU/source/WASM budget integration
remains part of #111. Acquisition
first bounds canonical source/state rows at 128 bytes per node/edge plus borrowed
publication/document bytes and 8 KiB framing, adds the bound session’s existing
retained-budget charge, and admits that envelope **before**
cloning state or allocating builder/typed buffers. Decode admits the input length
before parsing typed arrays. No crate dependency is added.

The native registry permits 256 snapshots, charges transient peak allocations
against a shared atomic 384 MiB snapshot ceiling, then retains only encoded-byte charges.
Every rejected path releases reservations; capacity failure leaves the source
frame and existing snapshots usable. Copy reports exact required output length
and writes nothing when capacity is short. Destroyed/unknown handles reject.
Acquisition uses the existing independently callable temporal cancellation lane
and its lock-held publication gate. Deterministic engine tests cover cancellation;
this checkpoint makes no native concurrent-cancellation latency claim.

## Evidence and next seam

The [checkpoint receipt](../performance/temporal-graph-freeze-2026-11-07/README.md)
records exact Python/Node snapshot bytes, boundary/history oracles, actual native
bindings, original retained publication bytes/camera, capacity and malformed
cases, immutable lifetime, source/artifact hashes and reproduction commands.
Normal pytest discovers the Python regression, and the explicit Node test list
includes its native counterpart. Existing graph export controls remain separate.

Next: lower the captured accepted paint geometry into the normal Rust Scene
path without rerouting/layout/recoloring; bind Scene, dimensions and provenance;
admit Scene scratch/output; attach recoverable snapshot provenance inside actual
HTML/PNG/SVG artifacts; exercise independent recovery and pixel/vector oracles;
then expose equivalent acquisition and attachment through real WASM/browser
execution under the unchanged 1882/768 KiB package limits. No new renderer is
permitted. The original complete frozen-export task remains open until these
checks pass. Aggregate/scale/accessibility and other full #45 requirements remain.

This native provenance checkpoint establishes no rendering, customization or
performance advantage over Matplotlib, Seaborn, Plotly, Bokeh, Altair, Datashader,
HoloViews/hvPlot or emerging alternatives. Their export/customization capability
comparisons and rendered examples belong to the subsequent artifact checkpoint.

## Historical native retained-paint export checkpoint (ABI 403)

`FrozenTemporalGraph.export(format, focus_rgba=..., scale=1)` in Python and
`export(format, {focusRgba, scale:1})` in Node admit `svg`, `png`, `html`,
`scene` and `painter`. The latter two expose canonical XYGS and XYPB. Rust
validates XYFG, decodes the retained PaintGeometry, and lowers CSS coordinates
through identity x/y Scene scales with zero margins and suppressed chrome.
It never invokes layout, routing, outline trimming, head construction, or
semantic style resolution. Independent Segment pairs and Triangle triples
preserve primitive identity even when a render edge owns multiple pieces.
Node IDs are `1+render ordinal`, edge IDs `2*2^48+render ordinal`, and frame
IDs `3*2^48+node ordinal`. Exact source UUIDs and CSR maps remain in XYFG.

The required four-byte focus color is an explicit export override, bound into
the artifact; it is not a claim that XYFG v1 captured browser CSS. Existing v1
bytes and their acquisition contract remain unchanged. A future browser capture
version must capture its resolved CSS focus token explicitly. Frame-time UUID
state remains separate from the retained publication's emphasis/visual state.

Dash splitting uses `(dash_offset + CSS distance) mod (on+off)` and butt-cap
segments for every halo/body/status layer. The prepass bounds expansion before
column allocation against Scene's unchanged two-million-record limit and a
1024-byte-per-record export envelope, in addition to snapshot decode admission.
The existing 1024-style painter group ceiling fails closed. Raster export
reserves 32 bytes per backing pixel before Scene allocation; dimensions are
`round(CSS extent * captured DPR * scale)`, bounded to 32768 per axis. Scale
must be finite, positive and at most eight. These are operation reservations,
not the outstanding #111 global process budget.

`from_artifact` / `fromArtifact` recovers exact full XYFG from SVG metadata,
PNG uncompressed iTXt before IEND, or offline HTML. A versioned XYFE carrier
binds format, scale and focus override to full XYFG. Recovery validates XYFG,
regenerates the complete artifact with the same shared renderer, and demands
byte equality. Duplicate/truncated/mutated carriers or visible bodies fail.
This provides consistency, not authenticity. Artifact imports never restore
live handles. Recovery has a bounded four-times-input admission ceiling.

HTML currently embeds the existing Rust Scene SVG renderer inline and needs
no network, Worker, or WASM sidecar. **This is not yet the requested XYPB
ChartView HTML framing.** Public browser/WASM freeze attachment, live CSS
capture, focus SDF parity for symbols other than circle/square (currently rejected), native/WASM rendered parity and full scale evidence
remain explicit #45 acceptance work. The native export continuation does not
close #45 or milestones 4–7. Existing ordinary chart export remains unchanged.

## Worker capture and shared rendered exports (ABI404 / WASM36)

`await session.freeze({timezone, window?, budgetBytes?})` is available only after
an accepted temporal publication and while the session is idle. The serialized
attachment lane keeps ownership and existing deadlines. Rust borrows the actual
retained session publication and private successful temporal frame. It never
accepts host membership or rebuilds paint. The painter retains the exact four f32 values resolved from computed
`--chart-focus` by its existing color parser (default `#aa99ec`) on the last
successfully presented paint. Freeze copies that accepted value, not a fresh
idle CSS lookup that could disagree with the displayed publication. A later
CSS change without repaint and later controller changes cannot rewrite it. No JSON numeric paint wire is introduced.
The Worker refuses foreign compile/stream/aggregate owners. Snapshot import and
export use a fresh/drained `XygWasmWorker`; an attached live graph remains its
exclusive owner. Disposing source/session/controller Workers does not invalidate
owned snapshot bytes. Snapshot imports confer no authority over live handles.

The controller frame ingress additionally supports XYTG frame v2, header72:
existing frame fields through byte55, accepted window duration i64 at56 and
controller revision u64 at64. Existing v1 frame56 ingress remains valid. Only a
successfully accepted frame updates this context. It is independent of later
interaction publication and the caller's optional display-window pair.

### XYFG v2 presentation capture

Acquisition without presentation capture continues producing v1 unchanged.
V2 uses the same canonical named-section framing and BLAKE2s8 personalization,
with domain `xyg-frozen-temporal-v2`. It preserves all v1 fields and appends,
in this exact order:

| Section | Type / meaning |
|---|---|
| render.focus.rgba | u8[4], Rust-rounded RGBA8 Scene color |
| render.focus.f32 | bytes[16], exact raw little-endian computed/explicit f32 RGBA |
| render.focus.origin | u32[1], 0 explicit override, 1 computed CSS capture |
| controller.kind | u32[1], 0 absent, 1 captured accepted context |
| controller.window | i64[1], nonnegative raw duration, zero when absent |
| controller.revision | u64[1], raw accepted revision, zero when absent |

Each f32 is finite in [0,1]; RGBA8 must equal Rust's rounding of f32*255.
The original f32 remains recoverable; existing Scene style storage is RGBA8.
`capture_focus` / `captureFocus` promotes validated native snapshots with an
explicit RGBA8 override (origin0); it preserves any existing controller context.
V1 exports still require an explicit focus override. Public browser
`captureFocus(rgba, worker)` returns v2 explicit provenance; browser exports
also accept an explicit `focusRgba`. Neither labels an override as CSS capture. V2 exports default to their
captured color. All six retained graph symbols are admitted, with bounded Rust
flattening of the existing shared marker SDF for inset strokes and focus
band levels1..3, plus noncircle/nonsquare interiors. Circle/square interiors
and all halos use fill-only Scatter records. Disjoint stroke bands avoid
the generic Scene stroke-path radius convention in the existing raster
primitive, preserving retained outer size and inner fill across renderers. Graph diamond keeps its live L1
half-diameter normalization. Curved/positive-offset bands use512 portable-trig
rays plus glyph corner rays; polygon interiors use their corner directions.
Each band is capped at8192 records and expansion is charged before columns.
This is explicit Scene tessellation, not a new host renderer or style resolver.
Frame outlines lower into disjoint filled Rect
strips, preserving their square SDF corners and alpha. Scene record/style and
operation reservations still apply before expanded columns allocate.

### Binary operation and HTML carrier

The official native `xyg_temporal_graph_frozen_execute` and WASM
`xyg_wasm_frozen_graph_execute` accept XYFX v1 header64. Fields: operation u32@8,
format u32@12 (SVG0/PNG1/HTML2/Scene3/XYPB4), explicit focus bytes@16, focus-kind
u32@20 (captured0/explicit1), scale f64@24, source length u64@32, shipped-client
length u64@40, budget u64@48, reserved-zero@56; source and client follow64.
Operations1/2/3/4 export/recover/attach explicit focus/validate-copy respectively.
WASM operation0 is the internal actual-owner capture ingress: render revision
u32@12, reserved-zero@16, window-kind@20, private frame revision u64@24, explicit
display-window start/end i64@32/40, budget u64@48, timezone byte length u64@56,
then UTF-8 timezone followed by four raw f32 focus values. Standalone operation0
is rejected: it requires the retained GraphSession attachment.

HTML embeds full XYFG, canonical Scene, XYPB and the exact shipped standalone
client. It calls the shipped `hydrateWasmPainter` / ChartView; no SVG fallback,
second renderer, network request, or WASM sidecar is required for offline paint.
Four raw f64 controls (CSS width/height, captured DPR*scale, scale) are base64
binary. ChartView uses the explicit backing ratio and rounds backing dimensions
exactly as Rust; coordinates stay CSS y-down. Scale changes output extent and
backing resolution without rerouting or reprojecting retained geometry.

The HTML XYFE v2 carrier contains magic/version/format, scale f64@12,
focus bytes@20, XYFG/client lengths u64@24/32, then complete XYFG and client.
Recovery requires the expected shipped client bytes and regenerates the full
artifact before byte comparison, binding visible Scene/painter/body/controls
and client to the recovered provenance. Native hosts obtain the trusted client
from their package; public browser `fromArtifact(bytes, worker, client)` takes
the shipped bytes explicitly. Missing/wrong client, duplicate/truncated carriers,
body/Scene/painter mutations and contradictory metadata reject. SVG/PNG retain
XYFE v1 framing and the same whole-artifact comparison. This proves consistency,
not authenticity; there is no signature or hostile-producer trust claim.

Client input is capped at8 MiB; HTML preflight reserves client*12 + snapshot*8
+ backingpixels*32 before Scene expansion and checks Scene/painter/output bounds.
Recovery's four-times-input admission remains. Per-operation limits do not solve
the outstanding #111 global process budget.

### Shared retained PNG capability

The browser keeps `default-features=false` and enables `frozen-raster` only.
`SceneDocument::to_raster_commands_retained` validates the complete decoded
Scene before allocating commands: no text, glyph sidecars, gradients, images,
legend/colorbar, axes/ticks or unsupported record kinds can be silently skipped.
All supported retained graph input remains representable: circle/square marks
use existing point SDF paint; the other four graph symbols and focus bands were
already lowered by the shared retained contour policy into independent triangles.
Frames are solid rectangles; phase-split shafts are solid butt segments.
Unexpected full-Scene commands reject before output/framebuffer allocation.

The existing Scene mark writer and raster dispatcher are const-specialized;
primitive coverage, SDF, clipping, alpha and draw order have one implementation.
A solid two-point butt segment calls the same existing box-coverage compositor
without materializing generic dash/polyline run vectors. The full native Scene
route retains text, image, gradients, general strokes and other commands.
The checked PNG adapter reserves the encoded buffer after command admission;
the existing export reservation of snapshot*8 + backingpixels*32 covers command,
RGB framebuffer, encoder/filter/compression/output and provenance temporaries.
Checked arithmetic, 384MiB ceiling, default16MiB Worker refusals, cancellation by
Worker disposal and owned-instance lifetimes remain. Caller-retained/global
process budgets remain #111; this change does not resolve them.

The vendored existing png0.18.1 encoder has one const-generic implementation.
Its restricted RGB8 writer fixes exactly the prior nonanimated, noninterlaced,
metadata-free `Fast`/`Up` configuration. The ordinary writer keeps every option.
Fdeflate, its larger-than-stored fallback, CRC and chunk framing are unchanged.
The existing crc32fast1.5.0 dependency uses its existing byte-at-a-time update on
wasm32 with only the first IEEE table retained; native keeps SIMD/slicing-by-16.
This trades browser CRC speed for module space, without changing PNG bytes or
compression. Original licenses, source hashes and patch notes live in `vendor/`.

To reduce code duplication, wasm32 shares standard-library stable-sort bodies
per record type and callback-independent instance/graph transaction dispatch.
Native retains comparator/callback specialization; ordering, allocations,
validation/locking sequence and the standard-library sort algorithm remain.
No exported ABI signature, capability, guard, resource cap or encoder is removed.
The target-only O2/inline50 profile and Binaryen132 packaging pass stay fixed.
Module and offline classic Workers share the same bounded XYFX byte staging
helper. Both call the same Rust export/recovery entry; the classic entry refuses
active/queued aggregate work before touching the arena. A single strict-CSP file
embeds the checked module plus shipped classic Worker and exercises the public
frozen API without network access. Disposal rejects pending PNG work before the
Worker acknowledgement and an immutable snapshot exports identically through a
fresh Worker.

### Remaining acceptance

The append-only [shared PNG receipt](../performance/temporal-shared-png-2026-11-07/README.md)
separates fresh single-module/actual Worker/native PNG proofs from inherited
history and over-cap probes. Prior unavailable-PNG receipts remain authentic
historical checkpoints. Standalone module fit does not certify a future union
with other features or ABI additions. Full #45 scale/aggregate/accessibility
and whole-milestone acceptance remain OPEN. No comparative performance victory
or global process budget completion is claimed.

## Actual temporal aggregate/direct regression (2026-11-07)

The [aggregate receipt](../performance/temporal-aggregate-frozen-2026-11-07/README.md)
adds a separate fixture to the existing full foundation/Release surfaces gate.
The real `attachWasmGraphSession` controller binding and exclusive Worker lane
capture six publications: Direct setup at20, Aggregate at5 and10, Direct at20
and30, and Aggregate after a coalesced return to5. Keyboard focus/selection and
`pinFocused` establish UUID4 in Direct before it becomes grouped, hidden and
visible again. No host filters topology or constructs publications.

At5 all six source edges are temporally visible, while Aggregate represents
only edges0–3: forward parallel edges0/1 and edge2 share one render edge, and
reverse edge3 remains distinct. Loops4/5 intentionally disappear from Aggregate
membership under graph-mark §6. At20 Direct preserves exactly loops4/5.
At10 exact node CSR is `[0],[2,3]`; source node1 is absent at its exclusive
valid-to boundary. At30 UUID4 is hidden, its canonical selection/focus/pin
remain retained, and Direct represents node0 and loop4. Returning to5 restores
the original aggregate membership and state without identity remapping.

Frame-time interaction provenance and retained-publication flags are asserted
separately: the setup frame predates keyboard state; subsequent temporal frames
include UUID4. Complete native replay of observed browser request/reply bytes,
native frame acquisition, Worker/native Scene/XYPB/SVG/PNG/HTML byte parity,
exact recovery after source disposal, offline shipped ChartView renders, and
independent authored-center/live/raster/offline pixel checks run together.
Re-signed malformed CSR controls reject duplicated, stale and missing members;
independent visual controls reject translated and stale pictures. The existing
seven shape captures, resource/disposal controls and graph pointer/keyboard,
10k, GPU and filter regressions remain in the full gate.

This finite fixture establishes neither massive aggregate playback nor broad
accessibility, installed-host or competitor acceptance. Full #45 and milestones
4–7 remain open. No ABI, renderer, package cap, default, tolerance or deadline
changes accompany this proof.
