# Automatic temporal replacement in native mounted geographic hosts

Dossier §27/§29/§34. This extends canonical retained and spatially indexed Point/MultiPoint native
binding to existing notebook and Node/VS Code painters. Geometry, temporal
eligibility, reduction, selected identity and camera policy remain in Rust.
The XYGHv2 protocol and existing native signatures are unchanged. The current
combined filtering/catalog source uses native ABI405; its additive ABI
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

Mounted admission accepts the exact issued `RetainedGeoSource` or
`GeoSpatialIndex` class. Arbitrary subclasses are not admitted. Indexed hosts
still require an explicit matching initial immutable frame and the existing
native transport; automatic binding does not relax either gate. Both ordinary
and selected indexed frames use the existing XYHT/XYGH lane: Rust operations18
and19 for ordinary index queries, or33/36/19 for immutable selected queries.
Rust alone owns external-page tickets, temporal membership, cancellation,
admission and full-scan refusal. A `GeoSpatialFullScanRequired` failure preserves
the accepted picture and never starts a canonical fallback. Failed external
page reads likewise preserve the accepted frame; a later intent can recover
after definite cleanup. Index disposal during a page read waits for admitted
storage settlement and cancellation. Independent caller Data and accepted paint
survive disposal of the index. Binding cleanup still requires actual drain or
native realm release before dropping source exclusion.

This admission is mounted-only. Indexed snapshot `chart.bind_temporal` /
`chart.bindTemporal` remains refused; in particular this does not qualify Node
index snapshot publication suppression.

After selected indexed19 confirms independent Data, the Python operation
confirms retirement of its distinct36 Query birth and releases that exact birth,
as the Node operation already does. Preparation retains its publication guard
if this confirmation or release fails; retry reuses the original47 correlation.
Explicit operation cleanup can instead retire the known Data and then retry
the same Query-birth release. Closing an operation after successful preparation
does not dispose its caller-owned Data. The mounted lane keeps any failed
cleanup owner and the source claim until settlement. Repeated replacements
therefore reuse the fixed birth bank without changing its16-entry capacity.

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

Canonical and indexed mounted bindings and canonical snapshot bindings retain
source-wide exclusion. Mounted selected hierarchy adapters instead claim their
validated, privately issued lane. Distinct explicit `fork()` / `fork_async()`
lanes may bind independently while retaining the same original source and Scope.
Same-lane binding and canonical/snapshot collisions remain refused; mutable
public metadata, subclasses and unissued lanes do not grant this exception. Observer removal alone cannot release this
claim. No ready mount and no posted temporal request means premount cleanup can
finish immediately without inventing a native acknowledgement. Otherwise source
exclusion remains until the exact active completion confirms drain, or actual
native mount release/realm destruction settles the admitted operation. Mere
transport disconnect, garbage collection or elapsed time is not release proof.

Automatic mounted work uses a process FIFO before posting XYHT. Each ready
binding has at most one queued entry and one latest intent; new notifications do
not move its queue position. Premount bindings do not enter the queue, and close
removes a waiting entry. Python protects admission with a thread lock and posts
at most one coordinator wake to the selected owning loop; no asyncio primitive
crosses loops. The existing protected notification inbox is unchanged.

The admission reservation belongs to the exact binding through actual native
Abort/Retire ACK and its correlated completion, or real realm release. A claimed
`drained` completion cannot release a still-owned native staging slot. Failed
delivery keeps the reservation for explicit exact drain retry. Manual native
preparation still fails explicitly on occupied staging, including a reservation
for another adapter. Resource errors do not trigger polling or automatic retry.
The reservation adds no native owner, cap, or data-policy decision.

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

The live host also retains the highest structurally valid desired publication
sequence, independently of the accepted frame and the original source's query
counter. XYHT advertises the maximum of that retained floor and the source
counter. This includes selected hierarchy preparations that were aborted or
failed before visual publication: their issued native query sequence may already
be consumed while the original source and accepted frame remain unchanged.
Releasing and reopening a browser mount resets request correlation, not this
floor. The next automatic cursor/range request advances above it. This is
bounded authoring bookkeeping; Rust still admits every query, and no aborted
frame becomes accepted paint or changes the caller's source publication.

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
sources. `XYG_GEO_INDEXED=1` selects external-page indexed fixtures in the same
packaged browser, Jupyter and VS Code entrypoints; `XYG_GEO_SELECTED=0` selects
ordinary indexed Data, and1 selects immutable selected Data. Jupyter requires
JupyterLab installed. The normal pytest and Node mounted suites include indexed
admission, bounded control, exact drain retry, native temporal membership,
full-scan refusal, independent leases and repeated replacement past the fixed
selected birth-bank capacity. The browser indexed journey additionally checks
real page-read supersession, failure-retained framebuffer pixels, ordered camera
gestures, index disposal while reading and zero canonical fallback reads.

Ordinary hierarchy, overview and mixed-tile automatic binding, full attributed
frozen exports, full-source accessibility, massive/five-view latency and memory,
and competitor qualification remain open. Selected hierarchy uses the existing
canonical source plus an explicit `hierarchy_lane` / `hierarchyLane`; this indexed
slice did not change or newly qualify it. The later
[selected hierarchy remount follow-up](../performance/geo-hierarchy-temporal-remount-2026-11-08/README.md)
qualifies the bounded packaged Node/native browser lane: temporal cursor/range,
private hierarchy publication authority, complete selected intent, supersession,
storage failure, drain retry, remount and acknowledged cleanup. Python native
regressions verify the same exact control bytes after a real hierarchy abort and
remount. The subsequent
[selected hierarchy application follow-up](../performance/geo-hierarchy-application-remount-2026-11-08/README.md)
qualifies bounded actual Jupyter/anywidget and VS Code remount journeys using the
same native source and painter. `XYG_GEO_HIERARCHY=1` selects their dedicated
fixtures in the existing application operators. The notebook uses trusted
keyboard camera input, a real held native preparation/abort, Output clear with
release ACK, redisplay and exact full-canvas RGBA restoration. VS Code uses a
public programmatic camera update, native read supersession/failure, actual
prepared abort and WebviewPanel reload/disposal, with full-canvas RGBA retention.
Both retain private hierarchy authority, exact u64 selection and independent
caller leases. Application-test transport holds must be disarmed and any held
reply released before awaiting failure teardown. The VS Code harness has an
explicit held-preparation failure injection; it preserves the failed exit while
separately asserting actual native-owner cleanup. See the
[held-reply cleanup correction](../performance/geo-hierarchy-held-reply-cleanup-2026-11-08/README.md). These are source-checkout tests in installed applications, not
installed-XYG-wheel acceptance. The separately started notebook server must
serve the exact committed input; this does not qualify cold startup.

Five issued automatic lanes now have direct/reduced source-checkout Node22/native
strict-CSP browser qualification, with exact complete membership and RGBA checks,
half-open empty/restored predicates, independent cameras, shared/linked/independent
controllers, page failure, stale genuine receipts, cancellation, uncertain Abort
ACK retry, and actual five-view release/remount. One Source and one Scope serve
one original lane plus four forks. The16/eight-Data/one-staging and128/384 MiB
native bounds are unchanged. No source copy or new data policy is introduced.

The installed JupyterLab4.6.5/anywidget journey also mounts five public widgets,
holds actual native preparation through supersession, verifies every independent
ready handshake, changes each camera with trusted keyboard events, and clears
and redisplays five Outputs through actual release ACKs. Complete per-view RGBA
is restored. It runs both on one owning loop and on two concurrent owning loops
in separate threads. Python3.11.17 and3.12.15 lifecycle checks are separate from
the installed Python3.11 application proof. Current raw qualification, diagnostic
controls, executable identity correction, and remaining milestone criteria are in
[the successor evidence](../performance/geo-five-temporal-successor-2026-11-08/README.md).
The [initial candidate](../performance/geo-five-temporal-2026-11-08/README.md)
remains immutable historical evidence, including its failures.

These remain source-checkout application tests, not published-wheel, five-view
installed VS Code, massive/performance, mixed-tile or all-browser qualification.
Existing static/indexed/hierarchy,
explicit live mounts and snapshot/export evidence remain distinct. The packaged
Node22/native bridge and real VS Code1.103.2 (embedded Node22.17.0) application
journey exercise the same painter. A separate VS Code1.145.2/Node24.22.1 probe is
recorded distinctly. Neither implies new pinned-focus UI: this host exposes
immutable selected profiles and exact picking, not a pinned-focus controller.
