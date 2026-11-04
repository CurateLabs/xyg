# Live GraphForge scheduling in Node and VS Code (#35 slice)

This document is normative for the Node live payload API. It supplements
`graph-mark.md` §§4–5, `graphforge-compositions.md` §6.2, the host contract,
and dossier §§27–29. It does not qualify browser WASM exports, notebook
attachment, retained graph interaction/controllers, accessibility, a large-data
render ladder, or M4 completion. Historical checkpoint receipts are unchanged.
The shared composition/host contracts and release API inventory record this
owner-required API. Inventory preparation retains explicit classification and
acceptance gaps; this slice establishes no release freeze.

## API migration and ownership

Before this pre-v1 change, `graphforgeWebviewPayload(composition, options)`
synchronously returned a ready `Figure`, payload and render positions. Its
ordinary force graph path ran 300 Rust ticks on the calling thread.
`composeGraphForge(input)` without `render` only recognizes and composes
metadata/planes; it is not itself force iteration. Its explicit `render`
option additionally compiles a one-shot canonical Scene.

The default live API is now
`await graphforgeWebviewPayload(owner, input, options)` or
`await owner.render(input, options)`. `owner` is a
`GraphForgeLayoutController`, allocated once per view, and input is either
raw composition input or an existing `GraphForgeComposition`. Raw live input
must omit `render`; expensive composition takes place in the bridge Worker.
An existing document's bytes are decoded there without using its optional
one-shot Scene as a source-position cache.

A live call resolves to its final accepted payload only after both scheduling
and bridge workers have exited. It returns no `Figure`. Each payload contains
`spec`, transferable `buffer`, `nodeTrace`, `edgeTrace`, full source `positions`
(`uuid`, f64 `x`, f64 `y`), `pickData`, `revision`, `jobId`, actual `step`,
`phase`, `alpha`, and bridge `packingMs`. Analytical chart intents have no
source graph positions. `onPayload(payload)` receives the initial, latest
intermediate and final presentations; it may return a Promise for consumer
acceptance. For a one-step/converged job the scheduler may emit only complete.

`spec` and `buffer` alone go to the painter. Positions, UUIDs and `pickData`
stay in the Node host: they are not JSON paint/data wire planes. For a caller
that already has a composition, `graphforgePick(payload, composition, hit)`
accepts live payloads as well as the existing static Figure form. Pick membership
answers are serialized from the existing graph mark's Rust-derived membership,
never inferred from endpoints. `pickData.nodes` is render-indexed: below
Aggregate each entry carries its exact source UUID from `meta.member_of` and
`meta.ids`, plus any existing `Figure.graphNodePick` collapsed-group fields.
It is separate from the full source-indexed `positions` snapshot. A viewport
can map source node 3 to render row 0 even at EdgeSample; render indices must
never index `positions.uuid`. Collapsed visible-subset identities join back to
the composition by UUID, preserving hidden group membership and edge provenance.
Edge identity lookup is cached once per immutable composition from persisted and
existing derived IDs. Picks never rebuild GraphData or copy unrelated node
attributes/result columns; the cache retains one source-edge-size lookup.
Aggregate node hits return a cluster summary, never a source UUID; an index
outside the actual rendered node/segment count returns null at every tier.
A raw-input consumer can resolve exact hits with `pickData.nodes[hit.index]`
after trace, index and tier validation, without synchronous composition; full
result-layer provenance still requires the canonical composition.

Synchronous metadata composition and explicit batch/export remain available:
`composeGraphForge`, `graphforgeChart`, and newly named
`graphforgeStaticPayload(composition, options)` (the former synchronous payload
implementation, including its ready Figure). They must not be represented as
scheduled live rendering. Existing static tests/callers use the explicit name;
VS Code and package-root exports expose the live owner and both payload APIs.
There is no synchronous compatibility overload on the live function. Rollback
before integration is to revert this slice and restore the previous signature
and callers together; no stored data or ABI migration is involved. Mixed old
and new callers must use their matching package version; awaiting an old shape
or omitting the owner is not a supported compatibility mode.

## Scheduling and source contract

The main thread only owns lifecycle, input Worker structured clone, callback
presentation and acceptance. The bridge owns composition, UUID/options
marshaling and synchronous native preset packing. It calls existing
`force_scheduler.js:runForceTicks` with its default dedicated Worker; there is
no alternate tick loop, force policy, LOD, style or selection implementation.
That scheduler still owns the one-tick initial checkpoint, bounded chunks,
ACK-before-next-native-chunk, convergence, force destruction and worker exit.
Default algorithm remains the existing `force`; `layout: "cose"` forwards the
existing native CoSE options. Other explicit layout/analytical work runs in the
bridge and emits one complete payload. Default cap is 300 iterations, chunks
are 10 ticks and wall limit is 30 seconds (configurable through `iterations`,
`chunkSteps`, `maxWallMs` within the scheduler's existing bounds).

For CoSE, document `node.parent` u32 and `node.parent.valid` are forwarded and widened to
the native u64/no-parent sentinel contract; hosts never reconstruct hierarchy.
Topology comes from canonical composed source edges. Other force algorithms keep
their existing non-compound layout behavior; compound frames still use the document.  Authored `positions`
are mapped by full source UUID, require complete coverage, and seed the
scheduler; `pinned`, `cose`, `seed` and hierarchy reach the same Rust handle.
Pins without positions and invalid topology/options fail at the existing native
validation boundary. A live default force request with `positions` advances
from those positions; explicit `layout: "preset"` reuses without force.
This differs from the old static payload's implicit preset reuse behavior.

Each source checkpoint is packed with complete UUID positions and explicit
preset layout. Packing cannot run a second force pass. Source positions remain
full even when Rust produces Aggregate render centroids; those centroids never
become scheduler seeds. Non-force graph layouts call the existing native
`graphLayout` on the complete source graph once, including seed/roots, before
preset packing. Complete supplied UUID positions keep the existing static
non-force preset-reuse semantics (including explicit circle/grid); an explicit
preset requires positions. Every live graph layout requires complete coverage
when positions are supplied. Non-force pins keep their existing behavior and do
not start force. Source f64 snapshots from circle/grid/preset at Aggregate can
seed a later pinned CoSE job without substituting render centroids. Native
layout, collapse, LOD and style policy remain unchanged.

The first presentation is packed immediately. While one presentation awaits
consumer acceptance, the bridge retains only the latest pending checkpoint;
complete replaces pending intermediate state, never initial or an already
presented final. Consumer acceptance releases the pending presentation. Force
ACKs still occur independently at every scheduler checkpoint. Thus callbacks
may skip steps and must use actual step/phase rather than count callbacks.
A slow consumer delays presentation and final settlement, not force progress.

Input cloning, UUID/pick metadata cloning and callbacks still cost caller CPU;
this is not a zero-copy or constant-time main-thread claim. There is one source
input clone per render; source positions and the paint buffer transfer from the
bridge. The scheduler retains its existing checkpoint copies. Native packing
and source-size JavaScript marshaling happen in the bridge, with at most one
presented and one latest pending source checkpoint, plus the scheduler's state.
Full source positions/identity remain source-size host storage under §27;
this does not claim screen-bounded total residency or a scale budget win.

## Cancellation, errors and teardown

Each owner generates its own identity and monotonically increasing nonzero u32
revision. Job identity combines owner identity and revision. Replies must match
both fields; old worker messages and late callback settlements cannot publish
into a new job. Owners never share workers or source positions. A revision
exhaustion requires a new owner. Reload likewise creates a new owner.

`render` supersedes the old job, which rejects with `GF_LAYOUT_SUPERSEDED`.
`signal` abort/pre-abort and `cancel()` reject with `GF_LAYOUT_ABORTED`.
`dispose()` is terminal/idempotent and rejects active jobs with
`GF_LAYOUT_DISPOSED`; it waits for all outstanding job exits. Future renders
reject. `maxWallMs` covers composition, scheduling, packing and presentation;
expiry rejects `GF_LAYOUT_TIMEOUT`. Native/compose errors are observable;
active callback failures reject with the original thrown object. An unresolved
callback cannot prevent cancellation. Revisions are not reused after failure.
Cancellation during signal registration or input getter access is checked
before worker construction. If structured cloning re-enters cancellation while
the worker is being constructed, assignment immediately hands cancellation and
the normal exit grace to that worker. Timers/listeners/job registrations are
cleaned up on both paths; constructed workers must exit before settlement.
No callback begins after cancellation/terminal settlement; a callback already
executing belongs to its original job and the owner refuses its late ACK.

Normal stop/callback failure/supersession/timeout uses the existing scheduler's
cancel message and native `finally` destruction, then waits for force-worker
exit before bridge exit and caller settlement. The bridge has a 2.5-second
emergency termination grace, allowing the scheduler's 1-second emergency grace.
A wedged native call/Worker can require forced termination; no force-destructor
claim is made for emergency termination. Actual worker exits still precede
terminal settlement. No silent fallback to caller-thread force is provided.

## Evidence and remaining boundary

`packages/xy-node/test/graphforge-layout.test.mjs` uses real native Workers,
an ABI force trap outside the existing scheduler Worker, bit-exact positions
and CoSE golden/options, parent planes/pins, aggregate source identity,
concurrent owners, supersession/late callback, reload/disposal, pre-abort,
timeout, callback failure and real destruction/exit ordering. Existing graph,
GraphForge static/analytical/cross-host and worker lifecycle tests remain gates.

`examples/vanilla-ts/graphforge-live.mjs` is a local, bounded four-node property
graph consumer using raw input, native CoSE and local generated painter assets.
The new receipt in
`spec/performance/graph-node-scheduling-35-2026-10-31/` separates cold Node and
browser startup, host checkpoint delivery, actual painted frames/pixels, pointer
pick/UUID response and pan response. A consumer ACK deliberately holds each
frame for inspection, so its final frame interval is not tick cadence. Later
positions replace a whole `ChartView`, following the existing vanilla consumer;
this consumer does not preserve viewport continuity or use retained updates.
The separate explicit S5b attachment is not this live replacement route. No WASM
runtime is used by this proof, and no diagnostic WASM artifact is promoted to
shipping status.

The existing 1k/10k/100k/1M receipts measure scheduler checkpoints, not render
first paint. This four-node functional journey neither replaces that ladder nor
establishes timing thresholds, a competitor win, large-scale interaction,
notebook/browser default progressive attachment, #35/#1015/#36 acceptance,
release qualification or milestone completion.

The append-only review repair receipt is
`spec/performance/graph-node-scheduling-35-review-repair-2026-10-31/`. It covers
the missed executable caller migrations, render/source node identity,
non-force Aggregate source-position retention, and reentrant startup
cancellation. The new browser runner asserts the real click's trace/index
matches the GPU-probed hit and its returned UUID equals `click.detail.row.id`.
It retains initial/final painter specs and binary buffers, screenshots, exact
pick observations, source-position digests and byte counts. It does not retain
full source coordinates or intermediate payloads. The original receipt is
immutable: its phrase “render payloads ... are retained” was broader than its
actual final spec, counts, identities and position digests. Repair evidence
makes no milestone, S5, scale, release qualification or #108 acceptance claim.

The append-only [1k rendered receipt](../performance/graph-node-first-paint-1k-review-repair-2026-11-04/README.md)
contains the current runnable helpers and archived browser captures. The original
1k receipt and parent-sync receipt remain immutable historical records; their
runners are superseded. Their conventional-path hashes do not retroactively
attest the native file actually selected by the loader. The current helper
observes existing `nativeLibraryPath` / ABI exports in the fixture and inherited
bridge/force Workers; the runner independently hashes and ABI-binds that exact
selected path. Origin defaults to unknown, separately from known-parent byte
identity. Held inspection drains each genuine update ACK with a bounded deadline
and matching job/revision/step; camera reset is checked on the first replacement,
which may be an update. Scripted ACK cases test this protocol only and are not
native callbacks or presentation-cadence evidence. The real capture still
uses the historical ring/chord topology, seed 7, default CoSE options and
10-tick chunks through the existing live controller. Its explicit 401-tick cap
matches that rung; the live default cap remains 300. Automatic ACKs follow
normal shared-painter frames and evidence probes, with no deliberate hold.
Only steps 1 and 401 were presented: intermediate checkpoints coalesced while
the initial frame was rendering/probed. The one recorded frame interval is
not evidence of sustained update cadence. Host checkpoint arrival, visible
Canvas2D pixel observation, GPU node-hit readiness and cold startup use distinct
recorded clocks. A trusted final-frame UUID click/pan is outside cadence;
initial trusted click/pan and viewport-reset inspection deliberately hold the
HTTP ACK in a separate run. The latter confirms replacement resets the panned
view to the next payload's ranges. No production behavior or limits changed.

The [accepted-main sync receipt](../performance/graph-node-first-paint-1k-accepted-main-sync-2026-11-04/README.md)
records the normal merge of accepted main `2fbbe5f0` into reviewed repair
`562a2adf`. Within that parent sync, production sources, runnable proof helpers,
raw browser captures and runtime artifact bytes were unchanged. It reused the
recorded observations without a fresh browser, worker-loading or native-build
claim. The parent now reports independent final approval and push of exact
`7c581024`; earlier approval and resolution of both proof-runner findings covered
`562a2adf`. Their immutable receipts retain the status observed when written.

Those captures predate the Node Buffer numeric-copy repair in
`graphforge-container.js` ([codec contract](graphforge-compositions.md#51-container)).
The integrated `packages/xy-node` tree is therefore not source-identical to the
capture tree. Reuse is limited to the individually checked producer, scheduler,
Worker and painter sources and native/client artifact bytes recorded in the
[Buffer finalization receipt](../performance/node-buffer-codec-finalization-2026-11-04/README.md).
The native composition producer returns ordinary `Uint8Array` document bytes;
the Buffer subclass defect is covered separately by the pure codec regressions.
The captures are retained evidence at their recorded state, not new timings or
an execution of the Buffer-fixed tree. Native byte identity still does not
establish the historical artifact's origin or rebuild history.

The combined Buffer sync was committed as `6e240f4b`; the parent reports its
independent final approval and push. The later
[Buffer accepted-main sync receipt](../performance/node-buffer-codec-accepted-main-sync-2026-11-04/README.md)
records the normal merge of actual main `3ebf70c3`, whose tree exactly equals
reviewed `7c581024`. It preserves the Buffer implementation and all earlier
proof bytes, source qualifications and artifact identities without a new
browser run or native/client build. Historical receipts retain their original
review and remote-status text. This new accepted-main sync candidate requires
its own completed independent final review and actual main-based CI before
queueing or integration; earlier `eb9ea4c` CI, prior-head approval and skipped
checks on a conflicted head do not qualify it.

This is partial 1k evidence, not #35 closure: the rest of the rendered ladder,
unheld initial trusted response, public browser progressive scheduling and
Python notebook/widget delivery/cancellation remain acceptance work. The
adopted explicit synchronous `composeGraphForge` contract also needs an
explicit resolution of the issue's literal async-compose wording before
closure. Retained `load.progressive` / opcode 15 mechanisms below do not
supply those public host schedulers.

## Bounded retained-session P1 seam (2026-11-03)

The additive GraphSession ingress in [graph-interaction.md §1.2/§2.6](graph-interaction.md#26-positions-and-relayout)
allows a host to schedule one retained configured CoSE session off its event loop:
`load.progressive.u8=[1]` yields one initial native tick; opcode 15 continues that
same force state. Optional `load.cose.f64[6]` and `load.cose.bounds.f64[4]` use the
existing Rust options validation. Absent/zero progressive retains 300 initial
ticks. Authored positions paint directly and seed a force state only on the first
step; unauthored pins anchor after seeding. `relayout.steps.u64` counts actual
native ticks, including the first checkpoint; callbacks must not infer progress
from callback counts. Selection/hover/camera preserve continuation, while existing
pin/position/visibility/replacement invalidations restart it. This supplies Rust
mechanisms only: the Node scheduler described above is unchanged, Python workers,
widgets/channel, browser controller/public APIs and #35 acceptance remain separate.
No scale or package qualification follows from this bounded seam.

The P1 review repair makes an empty retained session report `done=1` without
inventing a completed tick (native alpha may remain 1). Hosts can terminate
initially empty/all-hidden jobs and empty states rebuilt after visibility changes.
A move Preview/Commit before the first presentation honors the one-tick seed
when opted in, then invalidates the force continuation under the existing move
contract; absent/zero progressive keeps the legacy 300-step seed. Failed wire
requests install neither seed/move/pin state nor sequence/retry changes.
