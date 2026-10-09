# Native geographic host journeys

This implementation checkpoint adds immutable native retained-frame presentation
through the existing public geographic composition API. The bounded journeys below are verified; complete #50 massive interactive
acceptance and final milestone closure remain open. The live WASM controller in
[geo-retained-hosts.md](geo-retained-hosts.md) is a separate transport authority.

## Public composition and boundaries

Python `GeoChart.host()` creates a host-neutral adapter. `chart.widget()`,
`chart.show()`, and notebook display use that adapter through `GeoWidget`.
Node `GeoChart.host()` uses the same Rust source/session and Scene lowering;
`@curatelabs/xyg-node/vscode` exports `attachGeoWebview(panel, adapter)` alongside
the existing geographic composition constructors. The browser entry exports
`XygGeoHostView` and its `XygGeoHostComm` transport interface.

The admitted composition is one explicitly configured retained Point/MultiPoint
points layer with a synchronous Python native reader or the Node native bridge.
Query, camera, revisions, temporal predicate, sequence and complete uniform style
are authored through the existing composition contract. Async Python readers,
tiles, static geographic catalogs, multiple retained layers, scalar channels,
state patches and geographic decor are not added by this slice. Additional
views require separate adapters and independent immutable Data handles, within
the underlying protocol's eight-Data limit. Each adapter admits one mount.

Without an explicit frame, only the canonical `RetainedGeoSource` producer is
admitted. Indexed compositions use Python `chart.host(frame=frame)` or
`chart.widget(frame=frame)`, and Node `chart.host({frame})`. The supplied frame
must belong to the composition's exact source object and match its publication
sequence, full camera/time/source/layer/style/state query and uniform style.
Comparison normalizes only the operation and process-local source handle:
indexed command 18 and canonical command 5 express the same authored snapshot.
Camera, time, source identity and revisions are additionally checked directly
against the immutable binary SceneData header, rather than its mutable parsed
convenience metadata. Source info must match that exact header. Private frame
query/style attachment fields are internal adapter metadata, not a supported
public mutation surface. No source query, index read or command-11 preparation
occurs on this path.
A disposed source/index is legal while its immutable frame remains owned.

Construction issues command 26 to create an independent private anchor. Python
construction completes synchronously; Node starts the duplication immediately
and `adapter.anchorReady` resolves void when ownership is acquired. Each mount
uses that private anchor as its active frame, without another native read or
Data-handle allocation. The caller's original
frame remains caller-owned and may close immediately after construction.
Mount release ACK drops frontend views, painter and active mount references,
permitting remount of the same immutable anchor after source/index disposal.
The exact mount string is checked on every ACK; a late ACK from a prior mount
cannot release the new mount even though its Data owner and sequence are equal. Adapter close rejects further mounts and
releases an unmounted anchor; when mounted, the anchor remains charged until
mount release ACK. Node `realmDestroyed()` settles pending work and cleanup.
Each explicit adapter therefore uses one independently charged Data handle,
in addition to the caller's original, within the shared eight-Data cap. Five
adapters plus a caller frame use six handles, leaving two auxiliary slots.
ACK permits no simultaneous frontend copies: each adapter refuses another open
until its old frontend teardown and publication/auxiliary send settlement.
Backend packet remains the original admitted read; one frontend copy per active
mount and its painter retain the existing local transfer ceiling and separate
remote-memory accounting.
Admission failure preserves the caller frame and existing mounted frames.
Other producer kinds and implicit indexed queries remain rejected.

The adapter snapshots the small authored query/style; it never serializes the
whole retained source or canonical source chunks into widget metadata, HTML or
a Reflex render route. Numeric planes, exact u64 identities and signed i64 times
remain raw binary. Python integers and Node/browser bigints preserve their full
range. `build_payload_split()` emits only `{"geo_host": true}`. The 304-byte
canonical query-plus-style authoring key returned by `build_payload()` exists
only for deterministic module-scope Reflex token identity; its source handle is
zero and it is not a painter or a source payload.

Rust validates and prepares immutable Scene32 and XYPB15. The client uses the
ordinary shared Scene painter and ChartView, without acquiring a Worker or
claiming native Scene bytes have the private WASM FrameData authority. No host
implements projection, LOD, cell membership or pick policy. Pick and membership
requests address the exact visible native frame Data handle; disposing the
source or publishing another frame does not invalidate that immutable frame.

Static native presentation preserves immutable camera authority. Capture listeners suppress
ChartView's ordinary pan/zoom gestures, which would otherwise move paint without
updating the native geographic camera used for picking. Tab navigation remains
available. The newer [native live update slice](geo-live-host.md) adds explicit
Rust camera/time replacement, trusted serial keyboard pan and bounded primary
pointer/wheel authoring. These inputs use Rust camera operations and cannot
reinterpret immutable paint as a new geographic camera. The existing WASM
`XygGeographicChart.fromSource` controller retains its own live-update contract.

## XYGH v1 internal host transport

All request/reply headers are 32 little-endian bytes:

| Offset | Field |
| --- | --- |
| 0 | `XYGH` magic |
| 4 | u32 version 1 |
| 8 | u32 operation |
| 12 | u32 reserved zero |
| 16 | u64 owner Data handle |
| 24 | u64 publication sequence |

Only the envelope's type, request correlation and mount identity are strings.
Request and mount strings are bounded to 1–96 characters. One binary request
attachment is 32–256 bytes. Version, reserved bytes, operation, exact length,
mount, owner and sequence are validated before the native operation.

| Operation | Request | Successful reply attachments |
| --- | --- | --- |
| 1 open | Header only; owner/sequence zero | Header, typed SceneData packet, XYPB painter |
| 2 pick | Header + f64 x/y/tolerance + u32 mode/max hits | Header with auxiliary owner, typed hit packet |
| 3 membership | Header + u32 cell/cursor-presence + u64 work; optional 208-byte cursor | Header with auxiliary owner, typed membership packet |
| 4 release frame | Header with frame owner | No numeric attachments |
| 5 release auxiliary | Header with auxiliary owner | No numeric attachments |

Membership work cannot exceed the committed frame query's work bound. Rust
supplies cursor framing, cell membership, provenance and pick records. The
client copies small returned records/cursors, then drops the packet and typed
views before auxiliary release. Only one auxiliary packet may be outstanding;
a frame release is rejected until it has been acknowledged. The client and
Node transport admit at most 16 queued small requests. This is internal host
framing and does not change the Rust ABI or geographic source protocol.

## Ownership, acknowledgment and memory scope

The native immutable Data handle owns the backend packet. Python sends its exact
immutable `memoryview.obj` backing; Node sends the existing exact ArrayBuffer.
There is no additional backend full-packet `bytes()` or `slice()` for sending.
One browser packet copy is admitted per adapter. XYPB is independently bounded
by the authored transfer ceiling; the existing retained point Scene reservation
covers its point painter lowering. The adapter rejects a frame when two packet
lengths plus the painter exceed the source processor transfer ceiling.

The native 128 MiB source/query and 384 MiB derived ledgers retain their existing
scope. This does **not** extend the 512 MiB live-owned native-process claim to
remote frontend processes, framework IPC scratch, GPU memory, DOM, OS RSS or
committed WASM linear memory. The two-read allowance is not permission to clone
one backend packet into arbitrarily many frontends. Multi-view use requires
independent admitted Data ownership; the browser shared-Worker five-view policy
has separate authority and accounting.

A consumer destroys the ChartView/GL resources, clears packet-derived views and
buffers, then sends release. Sender references are held until their real
transport send promise settles: the Reflex registry operation lock spans emit,
and the VS Code transport queue spans `webview.postMessage`. Repeated handler cancellation shields and fully settles the native thread
and publication task before the registry guard is released. Their temporary
reply references are cleared before a queued acknowledgment can drop the Rust
lease. Failed rebuild cleanup also refuses active or mounted native owners. Ready/disposal/transport chains retain void results rather than packets.

Closing a Python widget retires authoring and asks its mounted browser to close.
The native frame stays charged until the browser's release acknowledgment. A
socket disconnect is not an acknowledgment: a disconnected frame remains
charged and another mount is refused. Same-entry Reflex reconnect keeps the
same client view and frame without taking another copy/read. Registry removal,
replacement and expiration cannot silently reclaim a mounted frame; replacement
also rejects active geographic transport operations.

An actual disposed VS Code WebviewPanel destroys its renderer realm and may
release its owned native frame after pending transport settles. Reload instead
waits for browser release acknowledgment before assigning new HTML. VS Code's
[Webview API](https://github.com/microsoft/vscode/blob/1.103.0/src/vscode-dts/vscode.d.ts)
explicitly distinguishes successful posting from delivery; this adapter does
not treat `postMessage(true)` as the browser release signal. It uses the binary
ArrayBuffer transport supported by the fixture's declared VS Code floor.

Loss of a widget/Reflex realm without a deliverable acknowledgment is a remaining
orphan-recovery gate. The adapter preserves its bounded charged owner rather
than making an unproved reclamation claim. No GC callback or timeout substitutes
for ownership acknowledgment.

## Host recipes and actual evidence

Reflex receives a `@reflex_xy.figure` token or a module-scope
`reflex_xy.inline(chart)` token. A literal retained GeoChart created only during
page compilation is rejected with an actionable message: its native reader
cannot be recreated in the separate backend process. State-owned recipes are
preferred for per-user adapters; a module-scope inline adapter still has the
single-mount limit. Numeric messages ride the app's actual socket.io namespace.
Core `xyg` remains free of a Reflex runtime dependency.

The notebook uses anywidget's binary-buffer argument to
`model.send(message, undefined, buffers)`; the callback parameter is not a
buffer argument. The tracked notebook verifies compilation inside IPython's
already-running asyncio loop and waits for browser release acknowledgment.

[Raw results, environment and commands](../performance/geo-host-journeys-2026-10-09/README.md)
cover the same native canonical fixture in:

- actual JupyterLab/IPython/anywidget: real red pixels, running-loop use and
  release acknowledgment;
- actual production Reflex/React/socket.io: exact u64 MAX/i64 MIN, authoritative
  pick, real red pixels, physical websocket reconnect retaining the same owner,
  and acknowledged release with zero remaining chart canvases;
- actual VS Code extensionDevelopmentHost/WebviewPanel: exact identity/pick,
  real red pixels, acknowledged reload with a fresh immutable Data owner, and
  native release after actual panel disposal.

The native test adds a 32,769-record reduced fixture, bounded paged membership,
stale-owner/mount rejection, source-disposal survival and exact sender-backing
identity. The installed Reflex ASGI/socket.io test exercises authenticated
registry-miss rebuild and reconnect in addition to the production frontend.

These are bounded correctness and lifecycle proofs, not quiet-host latency
comparisons, massive interactive evidence or a competitor performance win.
[Explicit indexed-frame mounting evidence](../performance/geo-indexed-host-journeys-2026-10-09/README.md)
adds actual journeys after canonical source, query/index and caller-frame disposal.
This proves adapter ownership independent of the caller and exclusive acknowledged mounts, not new indexed query policy.

Cross-worker orphan recovery, multiple retained layer
composition and the full #50 scale gate remain
separately tracked requirements.

## Native live retained updates

The bounded Point/MultiPoint native camera/time replacement path is now specified
in [geo-live-host.md](geo-live-host.md). Its private candidate/CAS/retirement
protocol extends these immutable mounting guarantees; source.current remains
separate from accepted visual authority. Existing static indexed mount proofs
remain valid. The bounded pointer/wheel input proof is recorded separately;
playback UI and massive interactive acceptance remain open.
