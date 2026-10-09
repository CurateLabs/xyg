# Recoverable selected-State allocation

Dossier §27/§29/§34. This is an opt-in ownership foundation for command33,
not a new selection policy or a massive-interaction claim. The sequence-zero
command33 payload, reply and canonical selected-State semantics remain unchanged.

## Exact allocation nonce

A nonzero u64 sequence on command33 is an allocation nonce scoped to the
privately issued Scope. The payload remains `revision:u64, fill:RGBA8,
reserved:u32=0, count:u64, ids:count*u64` (24-byte prefix, at most10,000 IDs).
Rust keeps **one** last-issued receipt per Scope: nonce, exact complete request
bytes including all budget words and ID order, issued handle, original state
revision, and an owning processor lease. Neither caller-provided semantic hashes
nor an approximate equality test authorizes replay.

An exact retry of the same nonce returns the same live State handle, code0,
sequence equal to the state revision. This works at the16-handle ceiling and
at exhausted handle-number allocation because it allocates no handle or State.
Changed bytes at the same nonce and regressing nonces reject as StaleSource.
A higher nonce may issue only after the prior receipt's State entry is gone.
Fresh legacy33 or34 also cannot change Scope admission while its nonce-issued
State remains live. Legacy callers on Scopes that never opted in are unaffected.

If that exact receipt's State was consumed or disposed, retry returns the fixed
256-byte `XYGZ` v1 **code20 RetiredStateNonce** response: handle0, sequence equal
to the original state revision, every other byte zero. It cannot reconstruct a
State or grant authority over the Query/Data that replaced it. The tombstone
retains its charged exact request until another permitted issuance or final
Scope destruction. General decoder63 remains unchanged; the selected-attempt
codec alone admits and strictly validates code0/code20.

All fresh issuances preflight handle capacity and next-handle overflow before
changing canonical Scope admission. Invalid input, local-budget rejection,
global-credit rejection and admission failure preserve the previous receipt and
State. A pending unknown State cannot be overwritten by a later nonce.

## Credits and lifetime

The raw receipt is at most80,280 bytes plus128 bytes of charged control. Its
lease is acquired before copying. Fresh issuance preflights old receipt credit,
prior canonical admitted-State credit, new receipt credit and conservative
`2*payload_bytes+1024` new State/temporary credit against the request's existing
processor budget. Actual receipt, canonical State, temporary parsing and Scope
storage also use the **same global128MiB processor ledger**; no pool or quota
is enlarged. Retired receipts and Scope admission retain their charges, even
when the State entry is gone. Disposing the Scope remains prohibited while
issued children or immutable outputs retain it. Eight Scopes and16 total
handles remain the existing bounds; five views serialize visual replacements.

The typed attempt owns a bounded immutable host request. Borrowed wire responses
are fixed256-byte controls. Application input planes and external transport
storage retain their documented caller ownership; this does not claim an OS,
linear-memory or GPU limit. No source-sized selection plane is introduced.

## Typed attempts

`scope.beginState(input, {nonce?})` and Python
`scope.begin_state(revision=..., ids=..., fill=..., budget=..., nonce=None)` are
synchronous: validation and request capture happen **before dispatch**. The
automatic nonce counter belongs to the authentic Scope owner, persists across
mounts, and cannot derive from a resetting renderer nonce. Explicit nonces must
advance that private counter. Native u64 identity and signed time remain typed
integers; no JSON-number wire authoring is added.

An attempt has `recover()/dispose()` in Node and
`recover()/recover_async()/close()/aclose()` in Python. Recovery replays only its
captured request and coalesces concurrent calls. Lost/corrupt confirmation keeps
the attempt recoverable. Only proven atomic initial rejection (native resource-9, stale-10 or fixed
output-capacity-13; WASM resource3) closes it without allocating during cleanup.
Cancellation status6, traps, panic/invalid status-1 and generic exceptions remain
uncertain even if they carry a numeric status. An unknown earlier outcome must
still be resolved.
Cleanup may safely recover a request that never executed, then immediately
release its single issued State. A lost successful command10 is resolved by the
exact nonce's code20 receipt. Consumed-State private ownership also makes
attempt disposal a no-op; consuming operations must settle their own IO and
Query/Data cleanup first. No blind command43/44 retry or State restoration occurs.

Attempts are issued only from authentic Scope producers. Node's private WeakMap
captures the original bridge, owner and handle. Python's WeakKey issuer registry
stores a weak bridge reference, so its value cannot pin a Source→Frame→Scope
cycle; asynchronous opt-in bridges must support weak references. Mutable public
wire or diagnostic fields cannot select another instance's colliding handle.
Repeated Python task cancellation waits for the outstanding response and exact
cleanup to settle before operation completion. Failed recovery or cleanup keeps
its owner/request available for retry.

Legacy `scope.state(...)` remains the existing sequence-zero convenience API.
It does not gain allocation recovery implicitly. Live adapters integrate the
attempt explicitly in their own slice and must keep the staged slot and lane
claim until operation and allocation cleanup are confirmed. This foundation
alone does not close #50/#39 or claim public live integration.

## Validation and release wiring

The native and direct-WASM CI lanes run `geo-selected-state-nonce.test.mjs`
after fresh paired artifact packaging alongside the existing hierarchy owner
controls. The Node package test list includes the same file. Python discovery
includes `tests/test_geo_selected_state_nonce.py`. Generated selected-wire and
declaration identity stays enforced by `scripts/gen_geo_selected_wire.mjs --check`.

The reproducible bounded evidence, pinned artifacts, complete normalized
fixed-reply bytes and raw gate logs are in
[`../performance/geo-selected-state-nonce-2026-10-09`](../performance/geo-selected-state-nonce-2026-10-09).
