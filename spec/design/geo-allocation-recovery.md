# Recoverable geographic allocations

Dossier §27/§29/§34. This Rust opt-in covers commands26/27/28/29/45.
It adds no ABI signature, memory pool, handle quota or temporal/geometry policy.
**Existing typed public owners still use nonce0:** unknown allocating replies
remain poisoned until a private client allocation attempt adopts this protocol.
This engine foundation alone does not repair public-host recovery.

## Opt-in and exact replay

XYGQ v1 header240 is a u64 allocation nonce for these commands. Header248–256
stays zero; nonce0 preserves all legacy requests, replies and publication paths.
The complete request is at most280 bytes, including budgets and payload.
A fixed sixteen-slot private registry bank keys the last receipt by historical
issuer handle and command. It stores monotonic nonce, exact whole request,
original reply, confirmed flag and private target birth/phase. Changed request
bytes at the same nonce, lower nonces and replacement of an unconfirmed receipt
reject before any admission mutation. Receipts are never silently evicted.
An exact retry precedes parent lookup, new-handle allocation and quotas.
It returns the original reply while the allocated phase survives, even after
its parent is disposed. Private canonical authority remains with the target;
the receipt retains no whole parent/source clone.

If the allocation was consumed/disposed, exact retry returns fixed code22
`RetiredAllocation`: handle0, original operation sequence, all remaining fields
zero. It cannot reconstruct an owner or grant authority over a replacement.
IDs never reuse. A missing historical parent prevents fresh allocation after a
receipt was explicitly forgotten; old nonces cannot resurrect allocations.

## Confirmation and sharing one parent

Command47 payload is exactly16 bytes: original command:u32, action:u32,
captured target:u64. Header16 names the historical issuer,24 the original
**returned operation** sequence,240 the allocation nonce. Actions are0 Confirm,1 Forget and2 ReleaseBirth. Other authoring fields remain zero.

Confirm matches the retained issuer/command/nonce/operation sequence/target and
private birth/phase. If the original allocation reply was lost and exact replay
returns22, target0 Confirm is accepted only for that matching current receipt
whose allocation is actually retired. It marks the receipt confirmed without
guessing or granting any handle; live or unknown target0 Confirm rejects.
Retired target0 Forget releases only a confirmed orphaned receipt. It returns code0 with known live target and sequence, or
code22 for its consumed/disposed allocation. Confirmation grants no newly
allocated authority. Exact ACK retry is safe after parent disposal and after
target consumption/disposal while that receipt remains current.
The client must privately capture the target before confirming, and must not
advance phases or issue another nonce until the Confirm ACK settles. A lost ACK
is retried as47, never as a fresh allocation. Once confirmed, a higher nonce may
replace the last receipt while earlier targets remain live. Therefore five26
retains or five27 indices from one seed do not block each other. Older live
target stamps allow redundant confirmation after receipt replacement. A retired
historical stamp also confirms code22 after the last receipt was replaced, so
a lost10 acknowledgement can be settled without replaying a stale allocation.
An older consumed phase cannot be reclaimed by confirmation.

Forget requires a confirmed current receipt and absence of its original issuer
phase. It releases an orphaned receipt; repeated missing Forget is an
idempotent, authority-free response (handle0), never confirmation of an owner.
A live issuer's highwater/tombstone remains until another confirmed issuance or
issuer disposal plus Forget. Unknown confirmations reject.

## Historical retirement acknowledgement

The separate fixed sixteen-slot birth bank retains both live and unacknowledged
retired phases. A stamp includes exact issuer/command/nonce/returned operation
sequence/target, confirmation and forgotten flags. It retains no whole source,
request or Scene. Historical Confirm requires a known nonzero captured target;
a matching consumed/disposed phase returns22 with handle0, while the exact newer
receipt and owner stay intact. A changed target, sequence or issuer cannot
confirm historical retirement. Target0 remains limited to the matching current
receipt for a lost original allocation; settle its release before replacement.

Action2 ReleaseBirth requires a confirmed matching phase which is actually
retired. It removes that birth stamp and returns fixed code0, handle0, original
operation sequence, all remaining fields zero. It never removes the current
issuer receipt or its nonce highwater, even while the issuer is live. A live
or unconfirmed matching birth rejects. A missing historical birth is an
idempotent authority-free response, permitting exact retry after the successful
release reply was lost; it never confirms or recreates an owner. Clients must
settle ReleaseBirth before dropping their known retirement descriptor, then use
Forget1 after issuer death to release an orphaned current receipt. Forget1 may
mark an existing stamp forgotten while its target remains live; collection drops
that stamp only after its phase dies, preserving existing Forget behavior.

Stamp capacity is checked before canonical mutation, including same-handle29.
Sixteen unacknowledged retired births reject the next allocation even with free
handles; exact birth release permits admission again. Nothing is silently
evicted. A28 Query consumed into29 Data retains a separate retired28 birth until
release; its confirmation cannot grant authority over the29 Data at that same
numeric handle. The same distinction applies to45 Query consumed into46 Data.

## Phases and publication

27 Build→Index preserves its allocation birth. 28 Query→29 Data consumes the
Query allocation birth:28 replay returns22, never the new Data. Opt-in29 uses
its completed known Query handle for Data publication; its original code16 Data
receipt remains replayable while that Data lives. Legacy29 continues allocating
an independent Data handle. Failed opt-in29 budget/quota/compile admission
preserves the completed Query. Five indices + five old Data + seed + five
completed Queries use sixteen handles;29 does not ask for a seventeenth handle.
45 Query→46 MemberData also consumes45's Query birth. Existing46 known-handle
receipt probing and MemberData's separate capability restrictions are unchanged.

## Complete credits and quotas

The bank/stamp arrays are fixed16-slot storage, with an8192-byte processor lease
acquired before its first admitted allocation. A compile-time size assertion
covers both arrays/control. Each exact receipt acquires `4*request_bytes+512`
before copying, covering stored request, adjusted admission copy and transfer/
reply scratch. Fresh/replacement admission subtracts bank control, **all live
receipt leases**, and the new receipt allowance from the caller's existing
processor budget before invoking the canonical allocation policy. Old and new
receipt leases coexist until replacement; no per-phase budget doubling occurs.
The fixed sixteen birth slots bound live and unacknowledged retired phases.
Controls remain charged while any receipt or birth stamp exists, and drop only
after both are gone. The compile-time assertion includes retirement flags. Receipt/source/result/Scene/transfer leases share128MiB processor and
384MiB derived ledgers. Eight sessions/eight Data/sixteen handles are unchanged.
Sixteen receipt-slot or birth-slot exhaustion rejects before canonical mutation. No public
wire stamp, digest or numeric handle can mint a private owner.

## Separate gates

The existing Direct browser Rust/WASM foundation job runs
`scripts/geo_allocation_recovery_conformance.mjs` alongside the retained-frame
and typed-overview native/WASM proofs. Its existing foundation artifact includes
`geo-allocation-recovery-ci.json`, containing six complete normalized packet
comparisons and the bounded allocation/confirmation controls. This is engine
opt-in evidence; it does not establish public-owner adoption.

35 mutates an existing Source and consumes State;36 replaces the known State
handle with IndexedQuery, while fallback preserves State. Recovering either
requires exact consumed State plus operation/birth authority. Nonce33's retired
receipt alone cannot prove which35 Source mutation succeeded. They remain a
separate mutation-recovery slice. Public owner adoption, unknown transport
reset, browser presentation and massive latency remain separate gates.
