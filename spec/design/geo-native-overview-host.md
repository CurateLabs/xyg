# Native overview live host transport

Dossier §27, §29 and §34. This bounded route reuses the existing geographic
composition and [XYGH candidate protocol](geo-live-host.md). It is an adapter
for privately issued native `GeoOverviewIndex`/`GeoOverviewFrame` owners, not
another chart builder or an independent renderer.

`geo_chart(geo_layer('density', source=index, layer_id=..., query=...,
sequence=...), camera=...).host(frame=...)` and its Node spelling mount one
immutable overview Data owner per adapter. A supplied caller frame is retained
before mount and remains independently owned. The native producer predicate
uses the issuer captured when the index was created; changing a public bridge,
handle or native-looking method cannot authorize a foreign/WASM index. The
complete encoded query, issuing index and sequence must match the composition.
The original processor budget is captured privately at adapter construction:
Python captures the canonical budget descriptor at module initialization; Node
uses the private index authority. Public budget or descriptive route-property
changes cannot redirect query identity, transfer checks or owner disposal.
Static overview `show` remains the existing inert export route.

Without an explicit frame, initial mounting either independently retains an
exact matching current frame or uses the canonical exclusive overview update
helper. A retained copy is captured by the canonical private `onIssued` hook
before command 26; a correlated error cannot discard that initiating copy
guard. A supplied-frame constructor failure also leaves the exact private
copy guard on its initiating frame. No host infers ownership from an arbitrary
exception's public `owner` field. The update helper registers its operation
with the host **before** command 28
admission and suppresses publication into `index.current`. Live camera/time
updates use that same helper after the shared Rust XYVC camera transition.
There is no host temporal filtering, projection, grid construction, palette or
LOD decision. External chunk/page storage must remain available while querying.

Preparation returns the actual immutable XYOV packet plus the existing native
Rust XYPB painter. `flags=3`, the 256 exact u64 counts, complete source/camera/
time/revision identity and the nonfinal notice remain authoritative. Stage does
not replace accepted paint. Exact XYGH CAS installs the candidate; old native
Data remains held until the frontend drops its old painter/packet references
and sends the exact retirement ACK. Lost stage/commit/ACK replies reuse the
existing exact replay guards. Abort, failed painter admission and cancellation
preserve accepted paint. Unknown command-28/29 admission remains an owned
operation guard; no guessed numeric disposal or early `prepareAbsent` is sent.
Operation cleanup drains captured reads and ACKs before the global candidate
slot can be released. Close blocks new authoring and waits admitted operations;
a mounted accepted frame remains owned until a release ACK or genuine renderer
realm destruction. Caller/index/source disposal does not retire a mounted
independent frame.

The browser hydrates the same painter through the existing GL renderer. A
separate noncanvas companion has 32 rows per page, eight pages, cell ordinals
0–255 and exact decimal u64 temporal vertex counts. Page and focused ordinal or
paging control survive accepted replacements; old counts stay with old paint
while a candidate is pending. Companion events do not invoke camera gestures
or feature picking. The fixed camera-sized ChartView root remains separate
from the companion, so table content does not resize its viewport. The notice
is literal: “Temporal-exact data-domain overview; spatial refinement pending.”
These ordinals are not feature IDs or `GeoLodKey` cells. Source-feature pick,
point membership and source record access fail before RPC; domain membership
uses its distinct issued overview API.

The existing global one-candidate slot, one mount per adapter, 16 bounded host
requests, eight Data owners and 16 total engine handles remain unchanged.
Overview Data owns its existing persistent 16 MiB allowance for packet/painter/
ChartView storage. The host caches one bounded inspection copied from privately
admitted bytes, independently of the caller's mutable inspection. It drops
this cache before native retirement. The overview native-host transfer guard
requires three wire lengths plus painter bytes for private, public and host
inspection storage. Node additionally admits a fourth outgoing wire copy
before returning attachments; it never returns or transfers its cached packet
backing. Python may share its immutable `bytes` backing safely. These phases
fit the existing four-wire admission; painter failure retains the cached
inspection and exact owner for cleanup/retry, without another read or copy.
The legacy point transfer guard stays unchanged. Native engine accounting and remote browser/app storage are
separate authorities: arbitrary websocket/app copies or retained external page
stores are not claimed inside the native engine ledger. Multiple mounts must
have independently admitted owners, and capacity pressure fails closed.

## Validation boundary

The [bounded actual-host evidence](../performance/geo-native-overview-hosts-2026-10-09/README.md)
records 9 new Python and 8 new Node native controls, the existing native host
regressions, strict-CSP Chromium rendering with exact temporal count changes,
JupyterLab running-loop/kernel/anywidget transport, production Reflex websocket
reconnect, and a real VS Code extension-host panel reload/disposal. The medium
32769-vertex case checks fixed count framing and exclusive ownership, not
interactive throughput. These proofs are pending integration. No integrated milestone,
large/massive interaction, throughput or competitor-win claim follows from
this adapter. Public accepted-frame export and ordinary overview membership
are specified separately; this transport introduces no frozen format.
