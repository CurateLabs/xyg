# Native live geographic hosts

Dossier §27/§29/§34. The existing `geo_chart(...).host()` / `.widget()` surface
can replace its accepted retained Point/MultiPoint frame. Rust alone applies
camera operations and signed temporal predicates, builds LOD, and picks the
published Scene. This is a bounded native transport slice, not completion of
#50/#39 or the massive interaction thresholds in §17.

## Authority and ownership

The host privately owns its accepted Data, independent of caller frames. It
stages one candidate without changing visual authority or `source.current`.
The frontend validates immutable source, camera/time/layer/style/state revisions
and complete selected XYSE identity before hydrating a detached painter. Commit
compares the exact old owner/sequence, mount, nonce and candidate owner/sequence.
Only after GPU/views and outstanding sends settle does RetireACK release the old
Data. The accepted Data becomes a private anchor for remount; no new query or
additional Data handle is required. New mount identity resets nonce history
only after the previous candidate/retired loans are gone. A prior mount ACK
cannot affect a new mount.

There is one process-wide staging slot through retirement/abort ACK. Existing
16 handles, eight sessions, eight Data and 128/384 MiB engine limits remain.
Five adapters can own five accepted frames plus one candidate, provided caller
originals are explicitly disposed after independently retaining them. Extra
caller ownership is charged and may fail admission; it is never stolen.
Frontend/comm copies and GPU memory remain outside the backend ledger, as in
[geographic-hosts.md](geographic-hosts.md); this does not claim a complete OS/GPU
budget. Each host retains at most a bounded 256-byte preparation request and
last exact 64-byte commit/retire/abort receipt for recovery.

A selected frame requires an explicit caller-issued `selected_scope` (Python)
or `selectedScope` (Node), bound to the same transport/source authority. The
coordinator reissues the exact full-u64 intent and fill profile with unchanged
state revision through commands 35/36, without inferring an ID join. Ordinary
index updates use 18/19 then dispose the independent query; selected 36/19 uses
the documented replacement lifecycle. Unsupported index frontier is explicit,
not an implicit canonical scan or selection loss. Selected export remains
subject to the separate complete frozen-state contract.

## XYGH version 2

Requests are exactly 256 bytes (Prepare) or 64 bytes (Commit/RetireACK/AbortACK),
little endian; all unspecified/reserved bytes are zero. Common header: `XYGH`
@0, version u32=2 @4, operation u32 @8, zero @12, expected old owner u64 @16,
expected old publication sequence u64 @24. Mount and correlation identifiers
remain bounded strings; no numeric data planes are JSON.

| Op | Fields |
| --- | --- |
| 6 Prepare | nonce u64 @32; desired publication sequence @40; camera/time/state revision u64 @48/56/64; time kind u32 @72; signed start/end i64 @80/88; canonical 128-byte XYVC @96; remaining bytes zero |
| 7 Commit | nonce u64 @32; candidate owner/sequence u64 @40/48; bytes 56..64 zero |
| 8 RetireACK | same fields, common header names exact **retired old** owner/sequence |
| 9 AbortACK | same fields, common header names exact uncommitted baseline |

Embedded XYVC operations 0..9 must name the exact accepted canonical camera
bytes. The existing Rust viewport seam applies the operation. Source/style/layer
authority is inherited from accepted private metadata; changing camera/time
requires a new corresponding revision, and state revision cannot change here.
Nonce advances only after successful candidate publication, permitting retry of
an unsuccessful preparation; successful history cannot be replayed as new CAS.

Prepare returns a 64-byte tag (same header/nonce, candidate owner @40 and sequence
@48), immutable SceneData and ordinary XYPB15 painter. Exact repeated Prepare
while that candidate remains uncommitted returns the same authority without
rerunning a source query or native Data read. Lost/malformed replies retain the
small original request; recovery resolves its trusted tag then aborts if it was
not committed. An authenticated correlated `prepareAbsent: true` error is issued
only after callbacks, newly issued Data disposal and slot release settle. A
cleanup failure retains its private owner for exact recovery instead.

Commit retry recognizes only its exact successful receipt and current accepted
candidate, never a second CAS. Retirement/abort retry recognizes only the last
exact settled receipt and cannot release a later candidate. These recovery
operations remain available while closing; new preparation/CAS is prohibited.
Ambiguous Commit retains the staged frontend until confirmation recovery, and
close settles recovery before destroying the accepted realm. Cleanup rejection
is retryable. Native reader cancellation settles callbacks before ACK; cancellation
after Data creation also disposes that unpublished candidate before reporting
terminal absence.

## Authoring and notebook completion

`XygGeoHostView.update` accepts explicit revisions, signed time, camera operation
and arguments. Incremental pan (3) must be serialized and rejects overlapping
programmatic pan. Trusted arrow keys use a bounded serial queue and report errors
through an alert. Absolute operations each edit a component; different operation
kinds serialize, and only pending requests of the same kind may supersede each
other. A time-only operation (0) followed by center (8) preserves both edits in
order. A superseded Promise rejects with AbortError. This does not implement
time playback UI.

Trusted primary-pointer dragging and vertical wheel input also use these Rust
operations. Each accepted drag sample sends the opposite screen delta through
pan (3), scaled from the actual canvas CSS rectangle to the authored camera CSS
viewport. Pointer capture persists across painter replacement and clears on
up, cancel, lost capture or close. The container temporarily uses
`touch-action:none`; disposal restores its prior value unless a caller changed
it while mounted. Synthetic events cannot issue geographic updates.

Wheel input sends set-zoom (4), computing the target from the latest accepted
camera after prior programmatic/gesture updates settle. Pixel, line and page
delta modes normalize to pixels (one line=16 CSS pixels, one page=canvas CSS
height);480 pixels correspond to one zoom unit. Zoom is centered on the
accepted camera center; there is no cursor-anchor inference. Rust validates
camera limits. A rejected zoom leaves old paint accepted and reports an alert;
the next valid input can recover.

At most16 ordered gesture samples are admitted, including the active sample.
Accepted pan samples are not summed or reordered: Rust wrap/polar policy applies
to each. Further samples at capacity are rejected with one reused alert;
they are not silently admitted as a different path. Gesture dispatch waits for
the existing programmatic update chain, retaining exact signed time/state
revisions. Closing releases pointer capture immediately, prevents new dispatch,
then settles the existing candidate/CAS/ACK ownership before destroying paint.
This is bounded input plumbing, not same-frame or massive interaction evidence.

`GeoWidget.update(...)` returns a concurrent Future. Its success means visual CAS
and exact retirement ACK have completed, not merely native preparation. It works
inside a running IPython asyncio loop via `await asyncio.wrap_future(...)`.
At most 16 pending Futures are admitted; close rejects outstanding Futures.
The binary authoring envelope XYHU v1 is exactly 128 bytes:

| Offset | Field |
| --- | --- |
| 0/4 | XYHU / version u32=1 |
| 8/12 | camera operation / argument count u32 (0..5) |
| 16/24/32/40 | publication sequence / camera/time/state revision u64 |
| 48/52 | time kind u32 / zero |
| 56..96 | five f64 camera arguments; unused slots zero |
| 96/104 | signed start/end i64 (Instant uses start; All both zero) |
| 112..128 | zero |

The widget sends `geo_host_update` with bounded string correlation; frontend
completion is `geo_host_updated` with an optional string error. Camera/time
numbers remain binary. No browser projection or default LOD policy is introduced.

Explicit selected query comparison permits only validated XYSE requests of op
35/36 with exactly 264 bytes and payload length eight @232: it normalizes the
command/source handle and consumed-State trailer, including length eight→zero,
against the authored canonical 256-byte query. Other bytes remain exact.
Ordinary extra/truncated payloads cannot gain this exception.

## Evidence and remaining gates

Actual native and packaged-browser tests cover five mounted frames, staged CAS,
old-frame preservation, exact stale ACK rejection, cancellation after Data
creation, read failure recovery, corrupt hydration, lost preparation/commit/ACK
confirmation, remount ownership, serial Rust camera composition and same-kind
latest desired intent. Actual JupyterLab, production Reflex and VS Code journeys
are recorded in [the report directory](../performance/geo-live-host-journeys-2026-10-09/README.md).
These small fixtures establish ownership and usability, not 100M latency, massive
five-view memory, all geometries, automatic linked selection, full-source
accessibility, mixed time filtering or playback completion.

The bounded [pointer/wheel report](../performance/geo-live-pointer-2026-10-09/README.md)
adds actual Chromium primary dragging, CSS viewport scaling, trusted wheel input,
programmatic/gesture ordering, Rust zoom-limit/read-failure recovery,16-sample
overflow and close during a held reply. It does not establish touch/pen behavior,
all browser delta modes, cursor-centered zoom or massive p95 latency.

The Python transport converts ordinary source-reader exceptions, including I/O
and lookup failures, into correlated error replies after callback/loan cleanup.
An exact `prepareAbsent` terminal outcome permits higher-sequence recovery while
preserving the old frame; exceptions cannot leave a notebook RPC awaiting a reply.

The existing native Node CI job runs the live-host lifecycle regression suite.
The existing Chromium job also runs the bounded five-small-view lifecycle probe;
notebook, Reflex and actual VS Code journey recordings remain reproducible
artifacts rather than additional platform jobs. Massive benchmarks stay separate.

Authentic hierarchy frames may mount statically. The private hierarchy marker
rejects live preparation before acquiring replacement credit or scanning the
canonical source; dedicated hierarchy routing remains a separate gate.
