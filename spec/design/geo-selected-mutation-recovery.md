# Recoverable selected geographic mutations

Dossier §17/§27/§29/§34. This engine-only opt-in extends the existing
[allocation receipt bank](geo-allocation-recovery.md) to35/36. It adds no ABI
signature, pool, quota, geometry/selection policy or host adoption. Nonce0
continues through the original canonical admission path and packet contract.

## Exact admission journal

Header240 is a nonzero monotonic nonce. The complete264-byte request includes
all camera/time/source/revision/budget words and the eight-byte issued State
handle. The existing16-slot bank keys its last receipt by historical issuer
handle and command. It preleases8192-byte fixed controls, a birth stamp and
`4*request_bytes+512` before any selected admission or State consumption.
Exact replay precedes consumed State lookup and returns the original256-byte
receipt while its logical phase survives. Changed bytes at the same nonce,
lower nonce, or replacement before Confirm reject without mutation.

Command47 retains its exact272-byte Confirm/Forget/ReleaseBirth grammar.
Command35/36 are now accepted original-command tags. Confirmation binds the
private issuer/nonce/returned sequence/target birth. A matching retired phase
returns22/handle0, not State, Source or SceneData ownership. Lost-original
retirement permits target0 only for the exact current retired receipt; settle
ReleaseBirth before replacing it. Historical known-target confirmations never
replay a lower-nonce mutation. No generic error proves consumption or absence.

## Different logical phases

35's issuer and returned target are the caller-owned Source handle. Its birth
is the *operation*, not the Source allocation. The operation is live only while
its exact sequence equals the last admitted sequence, is not cancelled/disposed,
and has an active matching job or matching current published result. Completion
preserves that operation phase. Cancellation, processing failure, newer accepted
work or Source disposal retires it. `current_sequence` alone is insufficient:
cancellation keeps that sequence and can keep the published result.

Retiring or releasing35's stamp neither disposes Source nor releases read loans.
Cancelled/failed work retains exact pending or retired tickets and their charge
until host buffers settle and command8 acknowledges the private ticket. Old
immutable SceneData and its selected row/source authority remain independent.
A cancelled completed result may still exist under the legacy Source policy;
its presence does not make the cancelled35 receipt live again.

36's issuer is Index; its target is the consumed State's handle, now containing
a selected IndexedQuery with the exact operation sequence. Cancellation, processing failure, disposal-start or selected19 replacement
retires36, even when its Query entry remains to own outstanding loans.
Retirement never releases those loans or grants the caller-owned Index. Selected19 creates independent Data at the same numeric handle;
36 replay/Confirm returns22 and cannot claim that Data. Lost19 publication
recovery remains a separate gate.

## Fallback and rejection

36 code10 is non-admitted and non-journaled. It preserves State and Index
transition history. Exact retry uses the canonical fallback/admission policy
while State still exists; corrected work limits may admit the same operation
sequence and nonce because the previous fallback committed no receipt.
An old fallback reply is not current State authority. Successful mutation is
always journaled before returning, so recovery never fabricates a replacement
State after lost accepted mutation. Invalid/stale/resource rejection does not
consume State or overwrite the prior journal.

## Complete local and global credits

The bank subtracts all live receipt controls and the new request allowance before
calling canonical selected admission. Opt-in35 additionally subtracts the held
Scope control, nonce receipt and any distinct retained admission State; the
selected State already included by LOD/result credits is excluded only by exact
Arc identity. Its shared Source policy checks the minimum of constructor budget
and this per-call limit. That limit is stored only on the new job and applies
again before subsequent read/parse loans. It never permanently changes Source's
constructor budget or legacy operations. Existing Source metadata, old/current
results, active job and pending/retired read loans remain in its local sum.

Opt-in36 subtracts the same complete Scope credits, retained validated index, IndexOwner and4096-byte Query
wrapper before the shared indexed constructor preleases frontier/LOD/result.
State storage remains in the existing selected LOD reservation. Controls and
all source/selection/query/read/result credits share128MiB processor; SceneData
continues through384MiB derived admission. Sixteen handles/eight Data/eight
sessions/eight scopes and fixed16 receipt/birth banks are unchanged. Five indexed
lanes retain fifteen baseline owners; State16 becomes Query16 then Data16.

## Proof and separate gates

Focused raw Rust tests cover consumed-State replay, whole-request and47 identity
rejection, cancellation/completion/newer-operation retirement, failed authenticated
read and exact ACK charges, local exact-boundary/one-byte-under and unchanged
legacy admission, fallback preservation, sixteen retained birth pressure and
five-view same-handle publication. Fresh paired native/WASM full-packet evidence
and nonce0 comparisons are recorded separately before integration.

This document specifies engine opt-in recovery. Public selected35/36 owners now
adopt it through [captured mutation attempts](geo-selected-mutation-hosts.md);
raw nonce0 requests retain their legacy contract. The separate
[selected publication journal](geo-selected-publication-recovery.md) specifies
engine19, while public19 adoption, hierarchy43/44 recovery, progressive
scheduling and massive interaction latency remain gates. Snapshot-local6/7
recovery is specified separately in [accepted binary snapshots](geo-overview-binary.md).
