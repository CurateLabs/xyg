# Explicit hierarchy host adapters

Dossier §17/§27/§28; protocol `geo-hierarchy-protocol.md` remains the geometry,
filter, LOD and authority policy. Python `_geo_hierarchy.GeoHierarchy.from_frame`
and `from_frame_async`, Node `GeoHierarchy.fromFrame`, and shared TypeScript
`70_geo_hierarchy.ts` service Rust commands37–44 through the existing execute/read
ABI. These import-only adapters add no chart constructor, geometry engine,
implicit fallback, page cache, filesystem or network policy.

The caller supplies the original validated retained source, an independently
leased source SceneData, explicit grid/work/cumulative-write limits, and an
immutable page store. `read_page/readPage` and `write_page/writePage` identify
storage by `(namespace, page)`; page IDs alone are insufficient. Durable storage
owns its own capacity, cleanup and lifetime. It may be file-backed, remote or
bounded application storage. No adapter retains a source-wide page array or
membership mask. Source chunk callbacks remain caller-owned even after source
registry disposal and must remain usable while admitted queries or rows need
canonical bytes.

Before command37, an internal producer registry verifies the original source
and transport identity. Mutable frame metadata and equal numeric handles do not
authorize a frame from another source or WASM instance. Node captures the
producer bridge once; Python registry values use weak references so source/frame
cycles can be collected.

The typed codec reuses canonical command5/6 framing and changes only the command
number. It validates hierarchy reply reserved fields,128-byte ticket shape,
full u64 ownership/namespace/serials and exact authorized lengths; signed i64
camera/time identity is preserved by the shared canonical encoder. Node's wire
implementation is mechanically erased from the TypeScript source using
`scripts/gen_geo_hierarchy_node.mjs`; the native owner only connects storage and
existing frame APIs.

Before invoking a read callback, the driver admits four complete transfer copies
against the processor budget. Returned storage must have both logical and backing
length exactly equal to the privately captured authorized length. Callback
mutation of its public ticket cannot change the private ACK, kind, size or
namespace. All storage callbacks settle before supply or ACK. Python task
cancellation shields transport/callback settlement; Node AbortSignal cancellation
notifies Rust while awaiting the outstanding callback. Each driver drops transient
input, encoded supply and write views before exact read8/write41 ACK, including
failure/cancellation. Applications must drop their own borrowed callback views
before returning; persisted immutable copies remain application storage. ACK does
not grant trust in durability: future Rust reads authenticate every page.

Build creation sequence is retained separately from newer query sequences. Owner
cleanup uses that creation sequence; each query session is disposed using its
own sequence. SceneData uses existing zero-sequence disposal and lifetime-copy
rules. Cleanup coalesces pending calls and permits retry after a rejected
pre-Rust cleanup; disposed views remain unavailable during retry. Failure/fallback leaves prior independently leased frames usable and does
not silently run the canonical path. `GeoHierarchyFallback` reports Rust's
frontier/work reason. Selected source authority reports
`GeoHierarchyUnsupportedSelected`; the adapter checks the authentic parsed
selection footer before command37 and performs no build dispatch. This preserves
the import-only unselected API when newer Rust can build scoped hierarchies;
explicit selected query43/Data44 routing is described below.

A successful query returns ordinary independently leased SceneData with existing
Rows, picking, paged membership, retain and frozen export. The original validated
source remains `frame._source` for these immutable operations. Its actual command38/index-handle authoring
request is retained for exact identity comparison; static hosts normalize only
the operation and process-local source handle. This does not assert that the
original mutable SourceSession executed the hierarchy query. Private WeakSet
provenance marks authentic hierarchy frames and all retained clones.
`is_hierarchy_frame` / `isHierarchyFrame` are internal read-only dispatch checks.
Explicit static mounting may consume these frames. Live updates must reject
hierarchy provenance until a hierarchy-aware live route is implemented; original
source association does not authorize an implicit full-source scan.

Actual adapter tests exercise native and packaged wasm32 storage tickets, exact
Scene/Rows bytes, full IDs and signed time, old-frame lifetime, backing capacity,
callback mutation and cancelled durable writes. These are bounded functional
proofs, not massive host/browser latency or1B evidence. Massive selected hierarchy interaction,
provider durability, live controller routing and massive end-to-end interaction
remain explicit #50 gates.

CI checks mechanical codec generation and executes the hierarchy host suite only
after the fresh native core and paired packaged WASM are available. The WASM
foundation job also runs raw hierarchy conformance against those artifacts. The
Node package test command includes the hierarchy and selected-hierarchy host suites and requires the same paired
source-checkout artifacts, as do the existing native/WASM package tests. No
pre-package native-only stage invokes the dual-artifact hierarchy suite.

The hierarchy test artifact defaults to a module-relative packaged WASM URL,
so repository-root CI and Node-package test execution share the same artifact.
An explicit XYG_HIERARCHY_WASM override remains supported.

## Explicit selected hierarchy operations

The default factories continue rejecting selected SceneData before command37.
An explicit opt-in `GeoHierarchy.from_selected_frame` / `from_selected_frame_async`
(Python) or `GeoHierarchy.fromSelectedFrame` (Node) builds a scoped root from an
already issued selected frame. `fork` / `fork_async` creates command42 lanes with
independent transition histories and the original creation sequence. Storage and
immutable source authority are shared; no source-wide host state is allocated.

`begin_selected` / `begin_selected_async` or `beginSelected` accepts an issued
State from the captured original producer bridge. A private registry captures
State handle/issuer at construction; a raw packet, forged instance or a numeric
handle from another WASM module cannot authorize command43. The host captures an
operation guard **before** awaiting43. Successful admission consumes the State
into a Query on the same handle. `drive` / `drive_async` services only Rust-issued
private tickets; `prepare` / `prepare_async` issues44 with exact48-byte style and
replaces that Query with independent Data on the same handle. `update_selected`
/ `aupdate_selected` / `updateSelected` is a convenience composition of these
steps. Rust owns temporal filtering, selected joins, LOD, geometry and all limits.

`pending_operation` / `pendingOperation` remains available after ambiguous43/44
transport failure or malformed successful receipt. A definite native/WASM Rust
rejection of43 preserves the issued State. Unknown failure does not restore it.
After a failed44, retry requires Rust6 to confirm a completed Query (reply19);
a replaced Data never receives44 again. Exact cleanup accepts State/Data sequence0
or Query publication sequence after a definite Rust kind rejection. An uncertain
cleanup keeps the guard and permits retry; outstanding callbacks and ACKs settle
first. Late cancellation after44 retains the known Data guard if cleanup rejects.
Old independently leased paint/Rows/frozen frames remain valid throughout.

The internal read-only `hierarchy_lane_authority` / `hierarchyLaneAuthority`
reports the captured original Source/bridge/creation sequence/selected flag.
Python registry values use weak references and do not globally retain
Source–Frame cycles. `cancel_generation` / `cancelGeneration` increments at
cancellation/disposal admission. These helpers supply authentic binding to a
future explicit live route; they do not mint mutation authority or enable an
implicit full scan. Successful frames retain their actual43 authoring packet
and private hierarchy marker through retained clones.

Five scoped lanes plus five immutable Data and the shared Scope fit the existing
16-handle/8-Data limits; an issued State is replaced by Query then candidate Data,
rather than allocating a further owner. Additional owners fail within the same
caps. Caller storage remains separate and explicitly bounded; no cache or
resource pool is added by the typed adapter.

`tests/test_geo_selected_hierarchy.py` and
`packages/xy-node/test/geo-selected-hierarchy.test.mjs` exercise actual native
and packaged wasm32 commands42–44, original rows/full IDs, Point/MultiPoint direct
and reduced membership, independent five-view camera/time, exact packet parity,
private issuer collisions, cancellation/ACK and ambiguous publication cleanup.
The evidence is a bounded host-functional proof. Massive selected latency,
provider durability and explicit live notebook/Reflex/VSCode routing remain
separate #50/#39 gates.

## Captured hierarchy admission context

Each lane captures its original producer identity, execute/read functions,
source origin, phase budget and storage callbacks before its first asynchronous
build dispatch. Forks inherit those captured functions. A selected operation
copies its canonical264-byte command43 authoring packet before dispatch;
mutable bridge functions, public lane fields and callback containers cannot
redirect that operation to another producer. The original bridge identity is
retained separately for genuine State claims. The shared TypeScript capture is
an opaque token privately bound to that bridge; a raw transport object cannot
substitute a foreign producer. Python keeps the captured context on its owning
lane and uses weak registry values, avoiding a global Source/Frame retention
cycle. These are fixed control records, with no source-wide data copy or cache.

## Public43 exact admission recovery

Selected admission uses the existing fixed journal bank and nonzero nonce240.
The authoring packet exposed by the operation and attached to its Frame remains
canonical nonce0; the immutable private264-byte execution packet is replayed
exactly. The genuine original Worker or native C-ABI dispatch must authenticate
the synchronous reply/error before yielding. Numeric error decoration or raw
WASM callback functions confer no admission authority. Command47 Confirm must
settle before the Query reads a page or source chunk. Only a captured genuine
atomic rejection restores the State. Unknown accepted43 consumes the host State
claim and retains the issued pending operation; recover coalesces the complete
admission and confirmation flight and returns that same owner.

Issuance callbacks cannot dispatch recovery before they settle, capture the
private constructor token, or replace canonical initial admission/rollback
methods. A callback or bounded host preflight failure before dispatch closes the
unissued guard and restores State usability. Disposal admitted during recovery
waits the original43/47 flight, borrowed callbacks and exact ticket ACKs. Python
repeated task cancellation is re-raised only after those owners settle.

A later Query failure, cancellation or frontier/work fallback never restores
State. Authentic47 retired22 describes the logical43 birth, **not** physical
Query absence. Cleanup first requires strict known Query10 with its original
handle/sequence, then authentic retired43 and ReleaseBirth2. Failed or lost
Query10 remains guarded; neither generic Stale nor22 clears it. Lane10 followed
by genuine issuer Forget1 reclaims bounded journal controls. Confirmed Query or
Data disposal is remembered before birth release; failed47 retries do not send
another10. Twenty distinct sequential fork lanes exercise bank reclamation.

The existing16-handle,8-Data,16-birth and captured128-MiB phase bounds remain.
Fixed authoring/execution/receipt controls add no source-wide copies, pool or
parser. Storage remains externally owned and bounded by the existing exact
loan/transfer admission policy; callback settlement precedes ACK.

Public44 remains a separate legacy publication-uncertainty guard. This slice
adds no durable44 Data factory and does not expand Query6/10 capture purposes.
Its historical generic-error fallback and unresolved publication/Query-disposal
paths remain readiness gaps. Raw nonce0 engine packets and ordinary38/39 policy
remain unchanged. The actual Worker fixture proves43 replay/Confirm,
foreign-State rejection, twelve reply mutation timings, borrowed ACK settlement
and the deliberately retained lostQuery10 guard. Point/MultiPoint, reduced
membership and frozen-output native controls are retained; unchanged paired
engine packet evidence is the separate cross-target oracle, not a claim that a
raw callback WASM bridge is an authenticated public issuer. No new massive,
linked-view, browser static-mount or performance claim follows from this slice.
