# Typed retained geographic selected-state hosts

This internal foundation follows dossier §27/§29/§34 and the
[Rust linked-state protocol](geo-linked-state-protocol.md). It adds no chart
builder, selection mapping, geometry/LOD policy or implicit cross-source join.
The public linked interaction controller and selected frozen exports remain
separate release gates. Selected snapshot/export returns Unsupported before
allocation until XYGX carries complete XYSE authority.

## Explicit ownership

Shared TypeScript `68_geo_selected.ts` and its mechanically generated Node
`geo-selected.js/.d.ts` expose `createGeoSelectedScope`, `scope.state`,
`scope.link`, `state.begin`, `operation.drive`, `operation.prepare`, cancel and
explicit disposal. The caller supplies an existing immutable SceneData handle,
exact publication sequence, namespace, layer, explicit budget, full query and
exact style. State ingress is a bounded BigUint64Array and RGBA bytes. All IDs,
revisions and signed times remain bigint. Python `_geo_selected` exposes the
corresponding synchronous methods and `*_async` methods, with NumPy little
endian u64 ingress. Its synchronous native path works inside a running notebook
event loop; it never invokes `asyncio.run` internally.

Command35 consumes State only after successful canonical begin. The returned
operation borrows the caller-owned SourceSession and never disposes it.
Command36 explicitly replaces State with an indexed Query, and selected19
replaces that Query with independently owned SceneData at the same handle.
The operation records successful replacement before reading/decoding Data,
including failed transport after mutation, so its later disposal cannot dispose
the resulting frame. Rust mutation failure preserves Query/State ownership.
Fallback code10 returns the still-live State and explicit reason1 frontier or
reason2 leaf-work budget; no canonical fallback, engine parking or disposal is
performed automatically. The caller can retry or explicitly choose canonical35.

Typed asynchronous owners must use one shared bridge object for linked views.
Cross-bridge State linking/begin is rejected before transport; numerically equal
handles in separate WASM instances do not authorize a join. Synchronous native
Python owners share the process-native registry. The raw byte codec remains
transport neutral and does not claim to authenticate arbitrary host handles.

Scope close is retryable while Rust refuses release of a referenced Scope.
Source/index lanes, State, immutable SceneData and private Rows continuation
retain their Rust Arc authority. No host mask or automatic baseline reset is
introduced. Consumers drop all packet-derived views and painters before frame
disposal. Existing Scene/auxiliary owners invalidate getters before cleanup,
coalesce an in-flight disposal and clear the cached promise/task only after an
actual failure. Repeated outer Python cancellation settles the transport first;
it does not clear a still-running release task. Successful release stays
idempotent, and a retry never restores borrowed views.

## Strict borrowed selected planes

Ordinary None Scene/Rows remains XYGZ v1 with zero footer size. Selected output
requires XYGZ v2 with a complete, exact-length XYSE v1 footer. Mutation,
membership and hit replies continue to reject v2. Shared Scene and Rows parsers
retain original storage and expose on-demand full-u64 intent IDs and per-cell
selected counts; Python borrows NumPy planes rather than constructing lists or
source-sized masks. The maximum input intent is10,000 IDs before dedup, cell
count196,608 and original-row page4096, matching Rust's existing bounds.

Parsers validate reserved fields, exact full source digest/generation/shape,
layer/state/CRS binding, strictly ascending canonical IDs, selected counts no
larger than total cell counts, exact selected visible-vertex totals and Rows bit7
membership in full intent. Fingerprints are retained as identity hints and never
substitute for canonical contents. Direct selected totals count vertices;
MultiPoint reduced totals also count vertices. Original Rows may carry selected
intent for null, offscreen or time-excluded rows independently of eligibility.
Private RowsData continuation remains a Rust-issued handle, never host ordinal
or forged cursor bytes.

Bounded readers retain private ticket bytes and authorized length before calling
user I/O. Callback dictionaries are separate; changing their length or raw
ticket cannot expand copy admission or change supply/ACK authority. Outstanding
reads settle before cancellation ACK. A failed read preserves accepted paint and
old RowsData, and subsequent explicit work can recover.

## Reproduction and limits

`node scripts/gen_geo_selected_wire.mjs --check` validates shared JS framing and
actual TypeScript-generated Node declarations while preserving native suffixes.
Build native383 and wasm32 ABI33 from the recorded source, run
`node js/build.mjs && node js/package-wasm.mjs`, then:

```sh
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib node scripts/geo_selected_conformance.mjs
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib uv run pytest tests/test_geo_selected.py -q
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib node --test packages/xy-node/test/geo-selected.test.mjs
```

Actual native/packaged wasm32 conformance covers direct2 and reduced40,000
MultiPoint vertices, canonical/indexed complete selected Scene packets,
i64MIN/u64MAX, independent original-row continuation after engine disposal,
outstanding-read cancellation/ACK/recovery and five-view ownership pressure.
Effective-alpha controls independently verify transparent selected direct marks,
opaque selected marks over a transparent baseline, and invisible fully selected
cluster/density cells against exact picking on both runtimes.
Five Source+Scope+displayed Data uses15 handles; State16 is consumed by35;
candidate Data uses16 until the caller disposes old paint. Rows publication
fails closed at that pressure. Explicitly parking two engines preserves all five
frames and allows old-page/replacement-page overlap within16 handles and8 Data.
The proof tests failure of the replacement read before successful recovery.
No quota increase, massive latency result, browser selected controller or
notebook/Reflex/VSCode selected journey is claimed by this bounded fixture.
