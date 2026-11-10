# Private Python native graph-session transport

Status: **P0 internal S6 foundation for #1015 / #36 only**. This does not
establish acceptance for #108, M4, a public Python session wrapper, notebooks,
or the browser painter. The authoritative protocol remains
[graph-interaction.md §3](graph-interaction.md#3-abi--wasm); the original foundation used native ABI 398. The loaded core must exactly match the current generated native ABI contract
(`python/xyg/_abi_generated.py`); the transport tests use that contract, including
subprocess callback checks. The R2 notebook consumer changes no ABI export or
generated declaration.

## Boundary and ownership

`python/xyg/_graph_session.py` provides `GraphSession` only by explicit import
from this private module. `xyg` does not export it. Construction forwards an
XYGF document, a complete XYGI Open request, and the caller's unsigned-u64
instance/group scalars to the already registered
`_native._lib.xyg_graphforge_session_create`. Python neither allocates nor
infers graph identity. Rust validates the document, opening request, matching
identities, admission, layout, selection, geometry, revisions and operation
sequence. `_native` retains its existing required-library and ABI checks;
there is no Python or NumPy algorithm fallback.

The wrapper's methods map directly to registered generated ABI functions:

| Private method | Existing native export |
| --- | --- |
| constructor | `xyg_graphforge_session_create` |
| `update(request)` | `xyg_graphforge_session_update` |
| `render(request)` | `xyg_graphforge_session_render` |
| `interact(request)` | `xyg_graphforge_session_interact` |
| `poll_event(request)` | `xyg_graphforge_session_poll_event` |
| `bind_temporal(request)` | `xyg_graphforge_session_bind_temporal` |
| `unbind_temporal(request)` | `xyg_graphforge_session_bind_temporal` |
| `coordinate_deliver(request)` | `xyg_graphforge_coordinate_deliver` |
| `close()` / context exit | `xyg_graphforge_session_destroy` |

Unbind takes the caller's complete Bind request containing `temporal.u64[0]`.
It is an opaque forwarding convenience: Python does not inspect or enforce
the operation or temporal section. The caller supplies all requests, stamps
and sequences. Every successful command returns the complete native XYGR as
immutable `bytes`. No production encoder, parser, selection dictionary,
provenance heuristic, trace-index inference, renderer, or alternate
`layout_render` path is added. Importing the module does not import widgets,
channel attachment, graph-layout scheduling or keyboard controllers. It uses
the existing `_native` module, which itself imports NumPy; this is not a
dependency-free native loader claim.

## Host buffer contract and exact retries

Inputs accept `bytes`, `bytearray`, or a live, one-dimensional,
C-contiguous, one-byte-item `memoryview`. Non-byte typed views,
multidimensional/strided/released views and non-buffer values fail before
FFI. Buffer lengths must fit both Python's host allocation index and C
`size_t`. Instance/group scalars must support integer indexing, exclude
booleans, and fit unsigned u64 without truncation. Zero identities, empty
buffers, wire schema and all Rust product limits remain Rust validation.
Type/bounds exceptions have fixed, value-free messages.

Constructor identity normalization and document/opening snapshots run before
acquiring the lifecycle lock. Integer-indexing scalars can execute caller code
in `__index__`; supported buffer subclasses can likewise execute Python buffer
callbacks. Neither callback may run under the non-reentrant lifecycle lock.
Commands first check local closure under the lock, release it to snapshot the
request, then reacquire it and recheck the handle before any FFI. Thus initially
closed wrappers still refuse before input conversion, and a callback or another
thread closing the wrapper during conversion cannot leave a usable stale
handle. Native alias revocation continues to be validated by Rust as Unbound.

Each input is snapshotted once into a private ctypes u8 allocation. A command
holds that same allocation, byte length, native handle and request bytes
throughout its query and copy retries. Python never consumes, increments or
rewrites `op_seq`, even after refusal. The first call uses null output and
capacity zero. On native Capacity (-5) with a strictly larger required length,
the wrapper allocates exactly that length and calls the same export again.
Further growing Capacity results follow the same rule; a non-growing
Capacity is surfaced rather than looping. This accommodates native poll's
non-consuming sizing calls without imposing a guessed output ceiling or
host-side protocol state. A length beyond host allocation bounds fails
locally; successful output lengths must fit the allocated capacity.

Rust alone retains complete replies and decides byte-identical replay,
failed-command atomicity, poll consumption and stale/bound-owner behavior.
A host allocation failure after a successful native sizing call can leave
the operation applied; callers may retry the identical bytes. Python does
not roll back or recompile. The wrapper makes one input snapshot and copies
the complete native output into immutable Python bytes; it is not zero-copy.
The ctypes output allocation and returned bytes coexist during that copy.
It retains no graph buffers or result cache after return (dossier §27/§29).

## Serialized lifecycle and failures

One module-level lock serializes native handle creation, complete
query/copy transactions and close calls, including calls on different Python
wrappers. This intentionally conservative P0 boundary prevents a close or
another operation from intervening between sizing and exact copying. It
also covers byte-identical Open retries, which Rust may resolve to the same
native handle. No identity or graph-state registry is maintained in Python.
Independent native handles retain independent graph state and lifetimes;
this foundation makes no concurrent throughput claim. Direct raw-ABI or
other-language callers are outside the Python lock; native locking and
validation remain authoritative.

Native Open retry semantics are preserved: wrappers opened with identical
active-instance bytes alias the same native lifetime. Closing either revokes
that handle; the other observes native Unbound (-10). A conflicting Open is
rejected by Rust. This is not Python reference-counted shared ownership.
Use explicit `close()` or a context manager; no finalizer or background work
is installed. Close waits for an in-progress transaction. Successful destroy
or already-Unbound destroy marks the local wrapper closed. Repeated close
is a no-op. Every subsequent command/context entry fails consistently with
`GraphSessionError("graph session is closed")`, `status=None`, before buffer
validation or native access. Other destroy failures remain observable and
leave the wrapper available for an explicit close retry.

`GraphSessionStatus` names the existing codes 0 through -11; it adds no
protocol status. Native refusals raise the private `GraphSessionError` with
the unchanged numeric `.status` and the fixed message
`native graph session request failed`. Messages contain no request bytes,
labels, identities, stamps, coordinates or derived values. Local lifecycle
and impossible-output failures also use this private error with
`status=None`; invalid input types/bounds use `TypeError`/`ValueError`.
No XYGR status parser or error reply synthesis exists in Python. A bound
owner disposed in Rust remains observable as -10, including on replay; a
caller-authored unbind request can recover as the native contract permits.

## Proof and explicit remaining work

`tests/test_graph_session_python_transport.py` exercises the actual native
398 library: create/render/update; retained complete bytes across
query/short/exact/replay; mutable-input snapshot identity; poll delivery;
stale, wrong-instance/group, malformed and conflicting replay refusals;
unchanged sequence/cache after refusal; independent lifetimes; native Open
aliasing; bound-owner disposal and unbind recovery; deterministic threaded
close ordering; repeated close; input boundaries and private import isolation.
Bounded subprocess regressions also exercise indexable constructor scalars and
supported buffer callbacks that close/open/render other native sessions, plus
closure during command conversion. Timeout kills and reaps a regressed child,
so a deadlock cannot strand a thread holding the parent test process's lock.
The existing raw ctypes proof remains in `tests/test_graph_session_abi.py`.
The original append-only local receipt is
[graph-python-session-transport-2026-11-03](../performance/graph-python-session-transport-2026-11-03/README.md).
The independent-review reentrancy repair has a separate append-only
[repair receipt](../performance/graph-python-session-transport-reentrancy-repair-2026-11-03/README.md).

P1 design is still needed for full selection/per-layer identity projection
missing from XYGR and the fast-seed seam. P2+ still owns widgets, channel and
session attachment, scheduling, keyboard control and public notebook
integration. S5 GPU wire/painter/browser work belongs to the parent. This
foundation does not prove performance leadership, chart breadth, complete
selection projection, or publication readiness; it changes no capability or
competitor acceptance claim, ABI/WASM/source policy, package gate, workflow,
dependency, generated API inventory, or public API.

## Public notebook scheduling through the existing Figure channel (R2, 2026-11-06)

R1's geometry-only default renderer is superseded. Its immutable
[historical receipt](../performance/graph-widget-progressive-2026-11-06/README.md)
records the rejected regression; it is not acceptance. The current
`graphforge_chart(composition).widget()` / widget-mode `.show()` route uses
`GraphWidget`, a `FigureWidget` consumer, for **every graph composition**, including
layers, explicit themes/styles, CSS dimensions, legends, annotations and axis
controls. Non-graph GraphForge charts retain their existing hosts.

### Why this seam

The existing notebook contract is the declarative Figure compiler plus
`ChartView` and `channel.handle_message`: it already owns all accepted generic
presentation, hover/click, pan/zoom, keyboard readout, selection, programmatic
view/row selection and event callbacks. The explicit WASM attachment in
`63_graph_controller.ts` uses a separate GPU-v1/companion presentation contract;
replacing ChartView with it would still lose authored notebook presentation.
The notebook therefore reuses `GraphLayoutController`'s retained native
`ForceState` and the ordinary presentation stack. The later typed identity slice
below adds an optional GraphSession readout without replacing that renderer or
layout owner. Full retained interaction and scale acceptance remain separate
#36/#1015 work.

### Data and scheduling

`_graphforge._graph_chart` attaches the original declarative mark and defers
composition legend installation until explicit Figure compilation. `Chart.widget`
passes its ordinary callbacks and optional WASM tick configuration to GraphWidget
without calling `Chart.figure()`. Mount starts the existing native layout
controller on its dedicated worker, using the mark's algorithm, seed, iteration
count, CoSE options and pins unchanged (default force, 300 iterations).

Rust returns immutable complete source-f64 checkpoints: one tick initially,
then existing eight-tick chunks, with the original completion/wall-budget rules.
The asynchronous progress observer is awaited. A separate single-worker executor
compiles the **same** declarative chart from a copied mark/data descriptor with
those source positions and `layout="preset"`; this performs no second force run.
The existing Rust graph render/LOD, multigraph routing, style, labels, membership
and offset-f32/u8 payload kernels remain the only product implementation.
Theme/style, composition legend and all other children use the existing compiler.
The original chart and static Figure cache are not mutated. The latest accepted
picture is mirrored into ordinary saved-widget spec/buffer state without a
second buffer transfer: Python uses the widget property lock and the browser
updates its local model silently. Reloaded outputs can paint that snapshot
while a fresh mount establishes ownership. Checkpoint metadata
records the actual algorithm, scheduled native ticks and native alpha. Step
numbers retain the existing controller's requested-tick counter; this route does
not expose opcode-15 exact completed-step reports for empty/settled states.

The kernel loop only publishes the complete spec and raw split buffers. The
browser uses the existing ChartView mount and full affected-trace append refresh,
which retains view navigation, keyboard/modebar, legend state and callbacks.
Cached selection masks are reused only while the ordered native identity and
membership planes compare equal; changed row spaces revoke the old mask rather
than guessing new identities. Complete source selection persistence through a
changing Aggregate row space is not established by this bounded slice.

Only one frame publication is outstanding: its paint ACK releases the next
native chunk. An in-flight exact readout or geometric selection may retain that one pending frame until
the matching reply returns; there is no inspection hold or accumulating position
queue. The existing 30-second native job budget includes host delivery waits;
the paint wait also refuses after 30 seconds. Slow/hidden frontends may therefore
fail explicitly rather than continue unbounded work. No budget is increased.

### Ownership, callbacks and lifetime

Each widget has an explicit random instance token; each frontend mount has a
fresh epoch; each publication has a monotonically increasing revision. Every
control, generic request and reply carries these stamps. A displayed Figure and
one pending Figure are retained at most. An event resolves against its exact
compiled snapshot until the replacement's ACK retires that snapshot. Afterwards
its revision is rejected. The browser rejects foreign epochs/instances/replies,
and never applies an older reply to a newer picture. Replacing GPU traces clears
the old hover/neighborhood handles before drawing and rebinds the target only
when the ordered native row space is unchanged; no freed GPU handle survives
a refresh. Routed segment identity
uses the existing Rust route and source-edge membership planes; callbacks retain
the existing `id`, `edge_id`, provenance and `Selection.rows()` contracts. No
Python/JS UUID matching or inferred per-layer identity policy is added.

Jupyter comm/cell execution can enter different event loops. Mount records the
owning loop; subsequent messages, cancellation and Python-origin mutations are
marshaled with `call_soon_threadsafe`. This matters for asyncio Event wakeup,
not just locking: R2 reproduced an ACK recorded by another loop that only woke
the layout observer at the old timeout. Callback execution now stays on the
owner loop. Programmatic mutations before the first picture queue until it is
published. View-state reads remain eventually consistent: before the first
computed picture they return the version-1 state with empty ranges, and during
a remount they retain the prior committed cache. They do not run layout merely
to guess an initial domain. Once a picture exists the ordinary Figure view-state
cache is used.

Rerender invalidates the old epoch, cancels its controller/task and starts a
fresh native lifetime. Disposal cancels before first paint as well as during
progress; closure rejects further host work and shuts down the build executor.
Native work is cooperatively retired at bounded chunk boundaries. Failure emits
only `XYG_GRAPH_WORKER_FAILED`, retains the last picture and uses no layout
fallback. Two widgets have separate controllers, native state, builders,
revisions, callbacks and caches. This establishes isolation, not a throughput
leadership or unlimited concurrency claim.

### Proof and remaining acceptance

[The append-only R2 receipt](../performance/graph-widget-progressive-r2-2026-11-06/README.md)
records real JupyterLab/IPython/anywidget/Chromium evidence: two public widgets,
nonterminal screenshots, trusted keyboard/pointer/navigation input while native
steps continue, exact kernel node callbacks, Python-origin row selection and
closure. Native tests cover every source edge including loops/parallel edges,
layered/custom presentation, final batch parity, stale/foreign ownership,
rerender, cancellation, failure and the cross-loop regression. The bounded smoke
and receipt verifier run in the existing CI `test` job under Release surfaces;
no new required status is added.

At the R2 checkpoint this did not close #1015/#35/#36/#108. Subsequent typed
and routed identity qualification is specified below. Remaining exact box/lasso UUID
sets, selected/annotated export parity, Notebook 7 and VS Code qualification,
trusted routed-edge notebook pointer coverage and the required 1k/10k/100k/1M
rendered ladder remain. The five-node property fixture and current composition
ceilings do not establish any ladder rung, first-paint budget, scale win or
competitor lead. Static `.figure()` / `.to_html()` and HTML-mode `.show()` remain
explicit synchronous batch snapshots; HTML has no kernel return channel.


### Notebook mutation ordering and remount state

Python view/selection/append commands wait for the intended published frame's
paint acknowledgement; commands arriving during compilation wait as well. A
queued command belongs to its mount epoch and is cancelled when that mount is
superseded. Commands authored before a mount target its first accepted picture.
Generic readout replies retain their original revision. Older messages propagate
only facets they actually changed, and cannot replace a facet already owned by
a newer Python mutation. Selection clears participate in the same browser
request backpressure as box/lasso selection, so a pending checkpoint cannot
restore a mask while the clear's exact reply is outstanding.

Streaming append uses the existing Figure append and browser refresh contract,
retains the graph notebook state envelope, and carries appended native canonical
columns into later checkpoint compilation. No host append-history replay or
layout/identity implementation is added. Restored committed ranges and durable
geometric selection are applied before the first remounted picture is ACKed;
opaque row-selection markers are not reconstructed into a durable mask.
The deterministic ordering regressions run in the existing notebook CI step.


Remount also retains each trace's legend visibility and hidden categories, which
are renderer controls outside the durable ranges/selection document. Native
Figure visibility is restored before compiling the first replacement payload.
The same exact trace IDs seed the replacement browser's legend maps, GPU state
and row controls before its paint acknowledgement. Legend changes update saved
widget snapshots as well, including changes after terminal layout. The bounded
notebook proof requires a new exact kernel callback after the final pointer
baseline; earlier keyboard or pointer callbacks cannot satisfy that check.


### Notebook typed identity slice (2026-11-06)

The ordinary Figure compiler and ChartView remain authoritative for painting.
Each compiled checkpoint owns a private identity adapter. A native GraphSession
is created only when identity callbacks or a UUID command need it; a chart
without these requests does not open the extra session. Callback preparation
runs in the existing compile executor and no initial session render is requested.
A derived-reference companion query may prepare native companion data. Any
session render revision is private and distinct from the displayed notebook
envelope revision. The ordinary Figure remains the renderer. Native admission
still uses the existing 384-MiB envelope and 10,000-ref selection cap; neither
limit is increased to accommodate the identity adapter.

Identity admission cannot reject an otherwise supported Figure frame. If the
extra identity envelope is unavailable, callbacks still receive their ordinary
row or full canonical Selection, with `graphforge=[]` and
`graphforge_error="XYG_GRAPH_IDENTITY_RESOURCE_LIMIT"`. The normal reply and
subsequent layout frames continue. This explicitly signals unavailable typed
metadata; it is not a successful empty identity result or complete #1015 scale
acceptance. An explicit UUID command that cannot be admitted fails before
applying a view mask; ordinary rendering and row/geometric selection remain
available. Closed/retired adapters cannot lazily open a new session.

The adapter encodes canonical kind-qualified refs from the composition and the
original compiler's Rust source/render membership planes. SelectRefs resolves
callback identity and all per-layer rows in Rust; SelectUuids resolves Python
UUID input in Rust. Python decodes selection refs, indices and provenance CSR
without matching UUID strings or inferring result rows. Derived refs transport
the exact canonical result id/layer/path/order. Non-graph traces project no
GraphForge refs. The readout session's private selection is scratch resolution
state, independent of the public view's ordinary selection masks.

Ref and UUID resolution uses at most 1,000 transport inputs per request, each
replacing the scratch selection. Rust still enforces its original caps on each
operation; the adapter never accumulates a native selection beyond them. The
callback merges native-sorted runs using only Rust-returned binary reference
keys and deduplicates repeated keys across batches. This preserves the single-
request Rust order: node UUID bytes, persisted edge UUID bytes, then exact
derived optional result-id bytes/layer/path/order. Per-reply string-pool offsets
are never merge keys, and absent versus empty result IDs remain distinct.
Python does not infer identities or provenance during this transport merge.
Explicit UUID masks apply only after all batches succeed. Node source/render joins cache an inverse
of the existing Rust member plane, preserving its one-to-one highlight refusal
without rescanning all source rows for each selected element. Host projection
and callback output memory is additional and is not qualified at scale here.

Callback dictionaries add a `graphforge` list; Selection objects add the same
attribute. Each entry has kind, UUID (null for derived edges), composed index,
and layer/result_id/row records. These four fields match the corresponding
Node graphforgePick composition identity projection; Node's additional edge and
compound detail fields are not promised by this callback projection. No public
GraphForgeComposition API or ABI signature changes.

The existing instance/epoch/displayed-revision guard runs before resolution.
Displayed old checkpoints resolve against their own session until replacement
paint ACK; that ACK closes retired sessions. Remount, dispose and close release
sessions even when application callbacks retain old Figure/Selection objects.
Late compiler completion is discarded and its session finalizer releases it.
UUID masks use ordinary selection_rows and are non-durable across remount;
exact aggregate/compound highlight routing, graph-specific box/lasso edge policy,
remaining browser/host pointer journeys, accessibility and the full ladder remain open.

Focused tests and the public notebook proof are recorded in the
[identity receipt](../performance/graph-notebook-identity-2026-11-06/README.md).

### Notebook identity report contract

The bounded typed-identity notebook proof records its node/edge UUID request
and Rust composition identity records as `uuidSelection`. The report verifier
requires that distinct canonical pair and exactly two delivered browser rows.
Historical row-only reports retain their original one-row requirement; typed
callback reports without request metadata cannot satisfy the new proof. This
checks request identity and delivery cardinality, not complete geometric UUID
sets or scale/frontend/export acceptance. The append-only correction and fresh
capture are in [the report receipt](../performance/graph-notebook-identity-report-2026-11-06/README.md).

### Routed notebook identity qualification (2026-11-09)

The normal JupyterLab/IPython/anywidget journey additionally clicks all five
persisted relationships of the property fixture, including both parallel
relationships and its self-loop. Trusted pointer input targets the existing
Figure/ChartView segments. The test reads accepted geometry only to locate a
stroke; it does not call a picker to manufacture its expected identity. Kernel
callbacks must match the fixture's canonical source UUIDs and the compiler's
source/render membership. A second layered graph verifies the exact
`notebook-rank` result ID, layer 0 and result row 0.

The property fixture has a distant isolated node. The additional identity
exercise uses the public Python `set_view` range patch to inspect its connected
nodes; it does not claim that every subpixel parallel stroke is distinguishable
at the full home extent. Unfinished-layout input and default presentation remain
checked separately before that range patch. Targets avoid DOM controls through
normal hit testing. No forced clicks, synthetic callback messages, picker
replacement or new native/browser rendering path is used.

Python UUID selection is checked both at the existing two-row delivery event
and by reading the actual node/edge GPU selection buffers. Public Node
`graphforgePick` replays each callback's trace/index against the exact binary
composition and final canonical positions, using the same native artifact.
Only the documented Node `resultId` / Python `result_id` spelling is normalized;
UUIDs, kinds, composed indices, layer order and result rows must agree exactly.
Both private notebook identity sessions must be released after widget closure.
The required CI receipt verifier uses `--require-routed`; historical receipts
retain their original explicitly admitted contract.

This is bounded identity qualification, not full #1015/#35/#36 acceptance.
Graph-specific box/lasso edge policies, derived/aggregate/compound routing,
VS Code Jupyter, selected/annotated exports, full accessibility,
and the required 1k/10k/100k/1M notebook ladder remain open. GPU masks establish
selection delivery, not a whole-image antialiasing or export-pixel comparison.
See [the append-only receipt](../performance/graph-notebook-routed-identity-2026-11-09/README.md).

### Notebook7 frontend qualification (2026-11-10)

The same public fixture and strict routed-identity harness run in actual
JupyterLab 4.6.5 and Notebook 7.5.8, with ipykernel 7.4.0 and anywidget
0.11.0 in the recorded environment. `--frontend notebook7` launches the Notebook
application and opens `/notebooks/graph.ipynb`; the existing default opens the
Lab application and `/lab/tree/graph.ipynb`. Both retain every native progress,
trusted input, exact callback/UUID mask, layered provenance, Node parity,
isolation and cleanup assertion from the routed identity qualification above.
There is no second widget, renderer, notebook adapter or layout path.

The harness reads the real frontend page configuration and observed static
resource URLs. Application name, namespace, semantic major version, route and
static namespace must all match the requested frontend. CI invokes the receipt
verifier with the explicit expected frontend and `--require-routed`. A Lab page
or legacy receipt cannot satisfy the Notebook7 gate by changing only a label.
Notebook7 lacks Lab's textual Idle status, and its initial execution indicator
can say idle before a kernel is selected. Both applications must expose a named
nonempty kernel and an idle execution indicator before first submission; Lab
also retains its textual Idle check. Actual native output and subsequent kernel
callbacks establish execution. This closes the observed premature-readiness
gap; the earlier unexecuted-cell attempt does not establish a general startup
reliability fix. Existing output/interaction deadlines
remain unchanged. Each bounded invocation retains the existing four-minute
step ceiling and runs in the existing Release surfaces `test` job.

The first isolated setup lacked pytest, which the repository fixture helper
imports; that failed execution and its diagnostic remain recorded. It is not a
product failure or a successful Notebook7 journey. The earlier Idle-label wait
also remains failed. The later actual applications pass without forcing clicks,
replacing callbacks or disabling default notebook virtualization.

[Qualification and immutable environment/captures](../performance/graph-notebook7-2026-11-10/README.md)
cover the bounded source-checkout frontend path. VS Code Jupyter, the full
notebook size ladder, graph-specific geometric edge policies, selected/annotated
exports, complete accessibility, broader platforms and competitor acceptance
remain open; #1015 and milestones 4–7 are not complete.

Notebook 7.6.4 remains **unqualified** by this receipt. Its real widget journey
returns the expected identities and masks, but the strict verifier rejects an
unhandled exception in the stock notebook's bundled shortcuts settings registry.
The captured stack/offset identifies the shortcuts plugin's own missing registry
entry; the triggering event is document-manager loading. This matches the open
[upstream Notebook issue 7862](https://github.com/jupyter/notebook/issues/7862).
The actual failing report is retained, and a normal regression continues to reject
it. No page error is filtered and no notebook asset/plugin is patched or disabled.
The passing stock Notebook 7.5.8 uses its compatible JupyterLab 4.5.11 dependencies
in an isolated test environment; Lab 4.6.5 remains separately qualified. Broader
Notebook7 version coverage remains open rather than being inferred from one pin.
