# Explicit hierarchy host adapters

Dossier §17/§27/§28; protocol `geo-hierarchy-protocol.md` remains the geometry,
filter, LOD and authority policy. Python `_geo_hierarchy.GeoHierarchy.from_frame`
and `from_frame_async`, Node `GeoHierarchy.fromFrame`, and shared TypeScript
`70_geo_hierarchy.ts` service Rust commands37–41 through the existing execute/read
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
selected query43/Data44 routing requires a separate typed host integration.

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
proofs, not massive host/browser latency or1B evidence. Selected hierarchy,
provider durability, live controller routing and massive end-to-end interaction
remain explicit #50 gates.

CI checks mechanical codec generation and executes the hierarchy host suite only
after the fresh native core and paired packaged WASM are available. The WASM
foundation job also runs raw hierarchy conformance against those artifacts. The
Node package test command includes the host suite and requires the same paired
source-checkout artifacts, as do the existing native/WASM package tests. No
pre-package native-only stage invokes the dual-artifact hierarchy suite.

The hierarchy test artifact defaults to a module-relative packaged WASM URL,
so repository-root CI and Node-package test execution share the same artifact.
An explicit XYG_HIERARCHY_WASM override remains supported.
