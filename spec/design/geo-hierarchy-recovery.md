# Recoverable selected hierarchy phases

Dossier §17/§27/§29/§34. This engine-only opt-in extends the existing
[allocation receipt bank](geo-allocation-recovery.md) to43/44. It adds no ABI,
command, pool, quota, geometry policy or public host adoption. Header240=0
continues through the original hierarchy admission/publication policy.

## Exact wire and logical births

43 accepts the existing264-byte request (common query header + issued State
handle8) with a nonzero monotonic nonce at240. Its issuer is the private scoped
hierarchy lane; successful admission consumes State and installs Query at that
same handle. The journal stores the complete original request, including all
budgets, source/camera/time/revisions and State handle. Exact replay precedes
kind lookup, so a consumed State is never reconstructed from wire.

44 accepts the existing304-byte request (header + Style48), restricted to a
completed selected replacement Query with no outstanding IO. Its issuer is the
Query and its target is independently owned immutable selected SceneData at the
same handle. Exact replay returns the original256-byte publication receipt,
including its Data length and query association, without compilation or copying
again. Data is not Query authority merely because the numeric handle is equal.

Same-nonce different bytes, lower nonce and replacement before confirmation
reject. The existing16 receipt slots,16 historical stamps and8192 control bytes
remain fixed. Admission preleases a stamp, exact request and
`4 * request_bytes +512` transfer credit before State consumption/history/style
mutation. The bank subtracts all held controls/receipts and new transfer credit
from local processor budget before the unchanged hierarchy budget helper.
That helper counts root, controls, Query/result and complete Scope children,
including nonce33 receipt and distinct newer intent; Arc-identical State credits
remain excluded only where the existing selected LOD/result already charges them.
Failed admission or publication preserves State/Query, lane/style history,
old immutable Data and ledger totals. No17th handle is required for44.

## Liveness and retirement

A43 birth is live only for the exact selected Query sequence, with the lane's
current transition still matching, and a session neither cancelled nor failed
nor in terminal frontier/work fallback. Completion preserves the birth until
publication, cancellation or supersession. A stored completed result alone
cannot make a cancelled operation live. A44 birth is live only for its exact
immutable selected Data publication sequence; it survives lane, Source and
original Query disposal independently.

43 fallback is discovered during6 *after* State consumption and history advance.
Code10 remains an explicit nonpublication decision. Exact journal replay after
fallback returns22/handle0; it never restores State or changes history. An
explicit reissued intent with a newer coherent query sequence is required.

47 accepts original command tags43/44 under its existing272-byte grammar.
Confirm authenticates exact issuer/nonce/operation sequence/target birth.
A matching retired phase returns22/handle0, never a Data/Query owner. Current
retired unknown targets may use target0 Confirm then ReleaseBirth2 before receipt
replacement; historical known targets use exact47 directly, not lower-nonce
allocation replay. ReleaseBirth settles only a confirmed retired birth. Forget
requires the genuine issuer phase to be gone: for44, Query→Data replacement ends
the issuer Query even while its independently stamped Data remains live.

Retirement is separate from cleanup. Cancelled/failed Query read tickets and
parser/transfer credit remain held until callback buffers settle and exact8 ACK
succeeds. Receipt release cannot ACK a loan or dispose a Source, lane, later Data,
or an operation at another sequence. Retain26, Rows16, membership12 and selected
snapshot authority continue to use the ordinary immutable Data guards.

## Evidence and remaining adoption

Focused tests cover lost admission/publication replay, full-u64 selected footer,
independent retained frame lifetime, cancellation before/after completion,
authenticated read failure, disposal with pending loan and forged ACK, superseded
lane history, frontier/work fallback, whole-request mismatch, local resource
failure and fixed16 historical birth pressure. Native/WASM whole-packet proof,
nonce0 before/after comparison and unchanged package gates are recorded separately
in the slice's performance evidence.

This is an engine recovery foundation. Existing public hierarchy owners still
need private immutable allocation attempts before43/44, Confirm before phase
advance, exact historical retirement, callback/ACK settlement and closing fences.
It does not prove mounted sparse linked intent, selected massive interaction,
cross-source linked fanout, overview selection or1B latency.
