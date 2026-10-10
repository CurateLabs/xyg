# Snapshot-local overview allocation recovery

This contract extends snapshot XYGJ/XYGW v1 through the existing execute ABI.
It is separate from GeoScale command6 (step), GeoScale command47, and the public
26–29/45 allocation bank. Rust owns snapshot births and retirement. Dossier
§17/§27/§29/§34 applies; it introduces no projection, selection or export policy.

## Request grammar

Requests remain exactly256B. Snapshot command6 accepts an optional nonzero
u64 nonce at240. Bytes56..240 and248..256 remain zero. Nonce0 preserves legacy
framing and output. The complete command6 request, including issuer Data handle,
publication sequence, budget and nonce, is the immutable replay identity.

Snapshot command7 controls this namespace only:

| Field | Meaning |
| --- | --- |
| 16 u64 | Original genuine Overview Data issuer handle |
| 24 u64 | Exact original publication sequence |
| 40 u64 | Known Snapshot target, or0 only for a retired birth |
| 48 u32 | 0 Confirm,2 ReleaseBirth,1 Forget |
| 240 u64 | Nonzero command6 nonce |

All other fields except magic/version/command are zero. No host-authored Scene,
query, feature identity or guessed target is accepted. Control receipts are
fixed XYGW v1 with exact sequence and zero lengths, companions and reserved
fields. Live Confirm returns kind0 and the Snapshot target; retired Confirm
returns kind2 and target0. Release/Forget return kind0 and target0.

## Private phases and replay

Each admitted birth retains its full request and allocation receipt. Repeating
exact command6 returns the same Snapshot, or explicit kind2/target0 if it was
retired. It performs no freeze or binary read. Changed bytes, decreasing nonce,
or advancing before Confirm fail before allocation. A confirmed next nonce may
create another independent Snapshot while older snapshots remain live: the
existing eight-Snapshot capacity remains authoritative.

Opted-in binary read20 requires Confirm. Issuer Data disposal does not retire a
Snapshot; its stored private birth and live Snapshot entry define the phase.
Snapshot disposal3 records retirement before removing the entry. Historical
births preserve exact recovery after a newer nonce. Release2 requires confirmed
retirement and frees the historical stamp. Exact replay of an already released
control returns an authority-free zero ACK; that ACK does not prove absence of a
live owner. Confirm of an unknown birth fails.

Owner disposal may complete after retirement and Release2 while its original
Data issuer remains live. Its current highwater stays charged. Forget1 removes
that highwater only after genuine issuer death, no live Snapshot birth and no
unreleased historical stamp. Unknown Forget is an authority-free ACK. Collection
uses the same private predicate for released highwaters before/after allocation
and controls; it never treats Snapshot lifetime as Data lifetime. Lock order is
Snapshot registry → Source registry → derived ledger, with no callbacks or I/O.

## Admission and accounting

The bank has at most16 current issuer records and16 retired historical records.
Live births reside in at most8 Snapshot entries. Births are boxed only for opted-in
Snapshots, so legacy entries do not acquire a512B inline recovery payload. The
persistent bank reserves32768B through the existing shared derived ledger before
allocating its fixed-capacity vectors or boxed births. A checked platform-size
bound covers both banks, eight live births, three temporary birth copies and4096B
of container/alignment overhead. Vectors never grow past their fixed capacities. Before displacing a current
birth, admission counts existing retired stamps plus every older live birth
plus the newly displaced unreleased record against16. Each older live Snapshot
therefore owns a future retirement slot; disposal converts that reservation
into a stamp and cannot be stranded by later allocation pressure.

Each opted-in execute/replay/control additionally reserves1536B (4×256+512) in
that ledger. Command6 subtracts32768+1536 from the caller's existing≤128MiB
budget before ordinary overview freeze admission. Old frames and snapshots retain
their independent existing charges; this is no new free pool. Current-record,
historical-record, shared-ledger or caller-budget pressure rejects before freeze
or mutation and preserves prior owners/retry authority. Released records are
collected only after the original exact Data issuer is genuinely gone; collection
is bounded by16 records and performs no data copy.

The existing8 Snapshot/8 Artifact/16 combined handles, two lifetime reads per
immutable plane, native six-format exports and no-raster WASM Unsupported behavior
remain unchanged. Neither Snapshot20 nor recovery replay restores read slots.

## Proof and adoption gate

`cargo test -p xyg-engine --lib snapshot_recovery -- --nocapture` exercises actual
source→overview→Data fixtures, exact replay after Data disposal, Confirm, two-read
limits, nonce0 binary identity, eight concurrent snapshots, request mismatch,
strict control padding, live/unconfirmed Release rejection, historical retirement,
lost Release ACK, both16-record pressure limits and recovery after release.

The browser captures a private issued attempt synchronously before command6.
An uncertain error carries that owner; `owner.recover()` coalesces exact replay
and Confirm before its single binary read, while `owner.dispose()` resolves the
same birth without reading. Lost disposal3 confirmation is checked through
Snapshot-local ConfirmRetired, then ReleaseBirth2. A lost Release acknowledgement
retries only that authority-free control. Controller disposal drains its uncertain
attempt before releasing the accepted Data; updates remain blocked until the birth
is confirmed or genuinely rejected. Failed cleanup retains a retryable guard.

The existing 4096-byte controller framing reservation covers the canonical request,
control framing, private source header, and bounded outcome snapshots; the Rust
1536-byte request credit covers its four fixed wire-sized request/receipt phases.
The separate existing Snapshot packet accounting and two-read limit are unchanged.
No inspection packet is copied during exact replay. Application-held binary views
must be dropped before disposal; local views become unavailable as soon as close
begins, including when a read is still pending.

Worker request authority is bound at dispatch in a private request-id map owned
by the captured Worker origin, independently of the public TypeScript-private
`pending` table. It is removed on terminal delivery, post failure or fail-all;
the existing FIFO/admission caps bound live entries. Outcome authority is then
recorded in a private WeakMap from a genuine trusted Worker message before public
`onmessage` wrappers run. It binds the original
captured bridge and complete request to a fixed 256-byte reply or primitive
rejection snapshot. A success getter additionally compares the current returned
packet with that snapshot; packet edits, arbitrary errors, and unrelated producer
objects do not authorize phase changes. There is no persistent last-outcome bank.
An execute-then-throw wrapper which loses the genuine object remains uncertain.
The shared narrow capture whitelist also supports selected GeoScale35/36 and
exact272-byte GeoScale47 controls embedding original command35/36; it does
not conflate their GeoScale47 namespace with snapshot7.

The browser fixture extends the existing strict-CSP accepted-frame proof with
lost/corrupt allocation replies, one exact coalesced recovery, controller-close
recovery, and lost retirement/Release acknowledgements. Actual paired/native and strict-CSP browser evidence is recorded in
`spec/performance/geo-overview-snapshot-recovery-2026-10-09`. No completion,
selected overview or massive-interaction claim follows from this recovery slice.

Every completion notification belongs to its captured freeze pin. A prior
successful binary can be disposed after a newer freeze becomes uncertain;
that old notification resolves only its own barrier and must not clear the
newer pin or recovery owner. Controller close retains the newer attempt until
its exact Snapshot retirement and release settle.
