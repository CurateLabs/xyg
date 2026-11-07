# Automatic temporal replacement in native mounted geographic hosts

Dossier §27/§29/§34. This extends the canonical retained Point/MultiPoint native
binding to existing notebook and Node/VS Code painters. Geometry, temporal
eligibility, reduction, selected identity and camera policy remain in Rust.
The XYGHv2 protocol and existing native signatures are unchanged. The current
combined filtering/catalog source uses native ABI403; its additive ABI
reconciliation does not change mounted geographic operations. This does not complete M6/#50/#39.

## Public lifecycle

Python `widget = chart.widget(...)`, then
`binding = widget.bind_temporal(controller, mode="cursor")` requires a running
asyncio loop. Node uses `host = attachGeoWebview(panel, chart.host(...))`, then
`binding = host.bindTemporal(handle, "cursor")`. `range` copies the exact Rust
controller range into the existing half-open native predicate. Cursor/range
values remain signed i64; source identities and revisions remain full u64.
Controller clamping and range validity are unchanged. Selection/playback-only
notifications with an unchanged effective predicate issue no query.

`when_idle()` / `whenIdle()` waits for the latest admitted intent, including its
successor after supersession. Failure is available as `binding.error`; failed
work does not automatically retry the same intent. A failed frame retains the
accepted picture, membership, selected profile and revisions. A new intent can
recover after definite cleanup. `aclose()` / `dispose()` unsubscribes, invalidates
uncommitted temporal work, drains real acknowledgements, and releases the source
claim. It preserves the accepted mounted picture and independent caller frames.
A failed synchronous delivery of a drain retry restores blocked/error state and
retains the same correlation; a later explicit cleanup call retries again. A
reentrant confirmed drain remains authoritative even if delivery then raises.
Controller disposal initiates the same cleanup; callers await binding cleanup to
prove settlement. Duplicate cleanup is idempotent. An uncertain drain retains
its exact correlation and source claim; cleanup rejects and may be retried.

Snapshot and mounted bindings share the existing one-binding-per-source registry;
there is no independent query pump. Observer removal alone cannot release this
claim. No ready mount and no posted temporal request means premount cleanup can
finish immediately without inventing a native acknowledgement. Otherwise source
exclusion remains until the exact active completion confirms drain, or actual
native mount release/realm destruction settles the admitted operation. Mere
transport disconnect, garbage collection or elapsed time is not release proof.

The host keeps one active intent and one latest pending snapshot. Same-turn
changes coalesce before posting. New intent posts at most one invalidation per
active operation; all later values stay at the host until completion. Superseded
work is explicitly reported as superseded, never accepted. No list of posted
time snapshots or second preparation slot is introduced. The existing native
16-handle/eight-session/eight-Data/128 MiB processor/384 MiB derived budgets and
one staging slot remain unchanged. Small bounded transport copies and GPU memory
retain the existing separate host accounting.

## Exact mounted control

`geo_host_ready` carries the exact bounded mount string, emitted after the real
native open reply has hydrated and drawn. Hosts accept it only for their current
native mount. Release clears readiness; a new mount replays the latest controller
intent after its own handshake. Old ready and completion messages cannot attach
to a new realm. Host request strings increase across rebinding. JSON carries only
bounded type/mount/request strings and completion status/error strings/booleans.

XYHU requires complete explicit authoring revisions; it cannot express a temporal
intent whose camera and revisions must be assigned after pending gestures. The
small XYHT control carries that intent and exact drain correlation instead.
`geo_host_temporal` carries exactly one 56-byte little-endian XYHTv1 attachment:

| Offset | Field |
| --- | --- |
| 0/4 | `XYHT` / version u32=1 |
| 8/12 | operation u32 / reserved zero u32 |
| 16/24 | signed start/end i64 |
| 32/40/48 | publication sequence / time revision / camera revision floors u64 |

Operation1 is Instant (end zero);2 is Window;3 invalidates the exact active
request;4 retries its drain. Operations3/4 have all numeric fields after16 zero.
The floors are native-host admission highwaters, not floating point controller
revisions. An aborted native query still consumes its admitted revision/sequence.
The host retains those highwaters across mounts. The browser generates automatic
publication/time revisions above both the accepted snapshot and the floors; if an
aborted camera query advanced its revision, automatic time reauthors the accepted
camera with a newer revision. Exhaustion fails closed. Explicit `update()` and
XYHU authoring retain caller revisions without rewriting them.

A mounted temporal request waits for previously admitted gestures, then uses the
existing serialized XYGH Prepare/CAS/RetireACK lane with camera operation0.
It reads the current accepted camera when that lane runs, never the composition
template. All admitted incremental pans remain ordered. Gestures admitted later
continue from the newly accepted frame and exact time. Generated gesture requests
also advance above admitted sequence/time floors when an aborted preparation
consumed revisions, reauthoring the same accepted predicate with a newer revision.
This preserves every ordered pan instead of letting a stale revision reject it. Programmatic explicit
updates retain their existing distinct-kind/supersession rules and native stale
revision rejection; callers must serialize their explicit authoring and provide
valid revisions. Automatic time does not silently rebase explicit camera deltas.
An invalidated temporal candidate aborts before CAS. An already admitted Commit
settles through recovery and exact retirement, followed by the latest intent.

`geo_host_temporal_done` echoes exact mount/request and reports status
`accepted`, `superseded` or `failed`, plus `drained`. Acceptance follows visual CAS
and retirement ACK. Supersession follows abort ACK. On failure the browser
recovers pending Prepare/Commit and drains Abort/Retire before reporting true.
False retains ownership and blocks successors. A drain retry also handles a
request whose delivery failed before any browser token existed, by settling the
existing lane before confirming absence. A false `postMessage` return is an
observable delivery failure. Panel destruction drains native ownership before
settling waiters; failed destruction remains retryable through host disposal.

## Notebook executor and selected query retirement

Binding explicitly enables executor RPC for that widget's lifetime. Unbound
widgets retain synchronous callback threading. The binding captures its owning
loop. Foreign-thread controller and comm notifications dispatch there before
changing intent, tasks or completions. Snapshot and mounted controller ingress
share one protected latest-state inbox and at most one queued owning-loop wakeup,
so a busy owner does not retain a snapshot/callback for every foreign update.
Owner-loop intent supersedes older queued nonterminal snapshots. A pending
terminal snapshot cannot be replaced by a late nonterminal snapshot; detach
discards retained input and prevents further notification admission. Native
predicate/revision policy and the one-active/one-latest transaction lane remain
unchanged. Foreign comm ingress admits at most16
small notifications before copying; native RPC admits at most16 requests including
the active request, each at most256 bytes. One serial executor chain owns native
callbacks; repeated cancellation drains the synchronous worker before reporting
cancellation. Reader-originated CancelledError becomes a correlated failure after
native callback/loan cleanup. Widget close orders adapter close after admitted
RPC and waits for actual browser release before dropping the comm.

Notebook kernels which serialize comm dispatch behind an executing cell should
launch the async flow with `asyncio.create_task(...)` and return from the cell.
The included actual Jupyter journey uses that pattern and a status widget; it
does not manufacture completion or pump private kernel messages.

Canonical selected replacement produces an independent immutable Data owner.
After preparation, the host cancels the now-finished source query through the
existing operation guard and releases its exact selected birth via47. Data and
caller frames survive; the source stays caller-owned. A failed cancel/retirement
retains `cleanup_canonical` / `cleanupCanonical` for exact retry before another
query. This prevents repeated live selected35 operations from exhausting the
fixed16 birth bank. It does not relax the bank or retire caller-owned Data.

Native membership has its own issued session owner. The mounted browser validates
its complete160-byte Rust provenance key against the accepted SceneData (source,
camera, time, selected state/style, reduction/grid identity), plus exact sequence
and correlated native transport. It does not mistake that independent session
handle for the accepted painter's Data handle. Auxiliary release still uses the
exact returned Data owner and native ACK. A forged key is rejected.

## Qualification and remaining work

The successor receipt in `spec/performance/geo-mounted-temporal-2026-11-07/`
binds source, native/client artifacts, commands, raw logs and captures. Existing
pytest/Node tests discover lifecycle regressions; the existing Chromium CI step
runs the packaged mounted journey for selected direct and ordinary aggregate
sources. The Jupyter journey is separately reproducible with JupyterLab installed.

Indexed, hierarchy, overview and mixed-tile automatic binding, full attributed
frozen exports, full-source accessibility, massive/five-view latency and memory,
and competitor qualification remain open. Existing static/indexed/hierarchy,
explicit live mounts and snapshot/export evidence remain distinct. The packaged
Node22/native bridge and real VS Code1.103.2 (embedded Node22.17.0) application
journey exercise the same painter. A separate VS Code1.145.2/Node24.22.1 probe is
recorded distinctly. Neither implies new pinned-focus UI: this host exposes
immutable selected profiles and exact picking, not a pinned-focus controller.
