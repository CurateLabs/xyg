# Immutable temporal graph acquisition (XYFG v1)

This is the first ordered checkpoint toward #45 frozen HTML/PNG/SVG exports.
It ships native programmatic acquisition and an offline binary codec. It does
not claim rendered artifact acceptance, a browser/WASM freeze API, or full
#45 / milestones 4–7 acceptance. Composition remains the only chart-building
surface. No graph filtering, layout, style policy or renderer is added to hosts.

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
all represented source entities must be temporally visible. Visual-state and
emphasis planes match the corresponding render counts. These checks validate
imported publications as well as acquisition; a recomputed checksum cannot
replace topology and membership validation. Unknown sections, versions, noncanonical
padding/trailing bytes, malformed or cross-source publications fail. Re-encoding
an accepted snapshot is byte-exact. Different live instances deliberately have
different provenance tokens even for equivalent source data.

## Admission and lifetime

Encoded snapshots are capped at 24 MiB. A conservative `16*encoded + 64 KiB`
peak envelope is capped at the unchanged 384 MiB process ceiling. Acquisition
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
