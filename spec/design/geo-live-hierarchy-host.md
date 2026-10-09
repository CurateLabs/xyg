# Explicit selected hierarchy live hosts

Dossier §27/§29/§34. This extends the existing geographic host transaction, not
chart construction or selection policy. Use an original retained-source
composition and explicitly pass its owned selected hierarchy frame, issued Scope
and ready selected hierarchy lane:

```python
adapter = chart.host(frame=frame, selected_scope=scope, hierarchy_lane=lane)
widget = chart.widget(frame=frame, selected_scope=scope, hierarchy_lane=lane)
```

Node uses `chart.host({frame, selectedScope: scope, hierarchyLane: lane})`.
The lane comes from the explicit selected factory; callers create independent
lanes with42 when sharing an immutable index across views. No host forks a lane
or substitutes a canonical/flat-index scan. The original source's private
producer association remains the frame origin even after source registry
cleanup. Its bounded chunk callback must remain usable for canonical boundary
reads and full-source rows.

## Authority and lane lifetime

The constructor validates the existing exact immutable packet/query/style
identity and authentic hierarchy provenance. Only a validated selected43 request
of264 bytes, with payload length8, gets the existing consumed-State trailer
normalization; all other canonical256-byte fields remain exact. The private
issued-lane registry binds original source, exact bridge, selected mode and
immutable build creation sequence. Equal numeric handles and mutable public
metadata cannot authorize another producer. The Scope must be issued on the same
transport; Rust43 validates its complete private source/layer/namespace and
current canonical ID/profile binding before consuming State.

A private weak registry exclusively claims one lane for an adapter lifetime,
including unmounted remount intervals. Claims do not globally pin Python
adapters or source cycles. The host independently retains the caller frame once
and reuses that private anchor across mounts. Caller frames, Scopes and lanes
remain caller-owned. Closing a caller lane prevents new live queries while the
independent accepted Data remains usable for static paint and immutable
interaction. The claim is released only after adapter-owned frame/operation
cleanup settles; failed cleanup remains retryable.

## Update and uncertainty

XYGHv2 and the existing65 frontend CAS/recovery path are unchanged. Camera
operations use Rust XYVC, signed time remains exact i64, and state revision
cannot change through camera/time updates. For each update the host issues33
using the accepted footer's **complete** sparse IDs and fill profile, including
null, offscreen and time-excluded intent. It calls the lane's issued43 operation,
drives its authenticated128-byte storage tickets and publishes44 by replacing
the completed Query handle with Data. There is no source-sized mask, geometry
policy, inferred join or visible-ID reconstruction in the host.

Before dispatching33, the host captures the Scope's issued nonce allocation
attempt. Its exact immutable request replays to the same State handle when a
reply is lost or malformed; consumed/disposed nonce tombstones prevent a retry
from creating another State. This common helper also protects the existing
canonical35 and flat-index36 live routes. Cleanup settles the query operation
first, then the allocation attempt and issued State. Failed cleanup keeps the
attempt reachable and the global staging slot claimed. Legacy35/36 admission
confirmation ambiguity is not repaired or claimed by this allocation seam.

The typed hierarchy operation owns an attempt before awaiting43 or44. If admission or
publication confirmation is lost, the host retains that operation and the
process staging slot until its public retryable disposal confirms the actual
State/Query/Data cleanup and all callback/loan ACK settlement. It never blindly
reissues43/44 or disposes a converted Data as a Query. Successful44 transfers an
independent frame; the closed operation needs no separate Query disposal.
A Rust fallback remains an explicit error; admitted State/history consumption
is not rolled back. Callers may explicitly reissue the same complete intent
under the documented33 rules for a subsequent coherent query.

Only confirmed cleanup permits a correlated `prepareAbsent:true` outcome. Exact
XYGH6 replay,7 commit recovery,8 retirement and9 abort preserve their existing
mount/nonce/old/new owner checks. Old paint remains accepted until visual CAS;
`lane.current` is not a visual commit. Failed hydration, cancelled reads,
uncertain publication or failed cleanup never trigger a hidden alternative
query. A candidate's old frame retires only after GPU views, auxiliary packets
and sends settle.

## Bounds and remaining gates

One original lane plus four explicit forks provides five independent transition
histories. Shared Scope1 + lanes5 + accepted Data5 uses11 handles; transient State
becomes Query then candidate Data in the same twelfth slot. Five separate Scopes
use15 handles and transition in the sixteenth. Candidate Data raises five
accepted frames to six, within the existing eight-Data cap. There is still one
process staging slot through RetireACK,16 total handles,eight sessions and the
existing128/384 MiB resource ledgers. Caller originals must be explicitly
disposed after independent adapter retention; extra ownership fails admission
rather than being stolen. Row/auxiliary pressure fails closed. Frontend/GPU
storage remains outside this backend ledger as documented for ordinary hosts.

Actual native Python/Node tests and five-view packaged-browser proof, plus
JupyterLab, production Reflex reconnect and VS Code remount journeys, are
recorded in `../performance/geo-selected-hierarchy-live-2026-10-09/README.md`.
Synchronous Python storage callbacks remain noninterruptible; cancellation
generation rejects a candidate after callback/publication settlement. Node
cancellation waits for the issued operation and exact storage ACK cleanup. This slice does not add selection-edit gestures, automatic linked
joins, playback UI, massive selected latency, mixed
hierarchy routing or a complete OS/GPU memory ledger. #50/#39 remain open.
