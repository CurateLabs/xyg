# Public selected mutation adoption

Dossier §17/§27/§29/§34. This bounded adapter slice adopts the exact35/36
[engine journal](geo-selected-mutation-recovery.md). It changes transport
ownership, not selection, geometry, time filtering or LOD policy. Integration
remains pending required CI and merge; final paired Worker evidence is linked below.

## Issued attempts and distinct phases

`GeoSelectedState.begin` retains the complete264-byte request and claims the
issued State before dispatch. A nonzero nonce is shared by the original
producer/issuer/command, rather than reset for a new State or Scope. The
existing successful-operation and nonjournaled-fallback return shapes remain.
An uncertain attempt is available as `pendingOperation` (Python
`pending_operation`); recovery replays its exact bytes and nonce. Confirm47
must match the original issuer, returned operation sequence, nonce and target
before the adapter consumes State or drives work. No replacement State is
manufactured after uncertainty.

35 grants an operation on the caller-owned Source. Cancelling or retiring that
operation never sends Source10.36 grants the consumed State's same-handle
IndexedQuery. A retired36 acknowledgement grants neither Query nor the Data
that selected19 may later place at that number. Successful publication keeps
the independent Data owner and releases only the retired36 birth stamp.
Old SceneData, literal full-u64 intent, Source identity and previously accepted
paint remain immutable while attempts fail or settle.

## Genuine per-call outcomes

Public reply fields and error attributes are not phase authority. Each selected
mutation or47 control opens a bounded capture for the private producer and its
immutable canonical request. Canonical dispatch records the latest matching
dispatch token before returning through application callbacks. Matching clones
also replace that token. Success requires the returned packet to remain equal
to the privately captured256-byte response; JavaScript also requires its exact
returned object. Rejection requires the actual latest native/Worker Error
identity and its original captured status. A synthetic ResourceLimit, cloned
fallback, modified response, saved prior-call Error, or reject-then-cloned-success
followed by the older Error cannot clear State ownership. A wrapper that loses
the current outcome remains uncertain and uses exact replay.

Python keeps bytes as the public return type. Python and Node use bounded
active-call registries: every matching canonical dispatch invalidates all
matching active captures, including nested callbacks and dispatch from another
thread or asynchronous context. Python locks token invalidation and outcome
recording, without holding the lock across C ABI execution. Worker transport
captures only genuine issuing Worker events. Captures keep only the latest response or Error, and
drop all request/token/outcome references in `finally`. At most16 captures are
active per native authority or Worker issuer. There is no persistent response
history or public-field rejection shortcut in the35/36 path. Typed selected
adoption requires canonical native or genuine Worker dispatch. Arbitrary raw
WebAssembly callbacks may author Rust nonce0 directly but cannot manufacture
authenticated recovery authority. The existing raw-WASM Scope33 test fixture
uses that direct prerequisite, preserving its typed33/43/44 assertions.

Genuine pre-admission ResourceLimit and stale-source rejections preserve State
and release its claim. The exact captured Worker code/status pair is required;
mutable public errors do not prove rejection.

36 code10 is accepted only as the genuine latest original response, with the
exact issuer, operation sequence and canonical fallback grammar. It preserves
State and transition history, and creates no journal birth. Corrected authoring
may retry that sequence; fallback is not a cleanup receipt for earlier work.

## Bounded issuer and cleanup ownership

Numeric JavaScript ingress remains supported. One private token per captured
bridge/issuer shares monotonic nonces across States and Scopes; the bank has16
issuer tokens and each token tracks at most16 unsettled births. Capacity is
checked before State is claimed. Settled rejected/fallback/released attempts
are pruned before a new attempt. A genuine original Source/Index disposal hook
or Scope cleanup may probe settled receipts and try exact ReleaseBirth2 and
Forget1. A live original issuer keeps its token charged. Source6 Stale never
proves Source absence, and Scope cleanup never disposes a caller Source.

Whole-flight cleanup settles active work, reader/storage callbacks and exact
read/write ACKs before retiring a birth. Repeated asynchronous cancellation
cannot release those loans early. Known cleanup failures remain retryable.
Before mutation dispatch, admitted operations capture original transport
methods, handle, sequence, budget, and chunk/page reader callbacks. Acceptance
after a response or recovery await never re-reads caller decorations to route
Query/Data work or cleanup. Indexed operations may
finish from their retained private authority after original Index disposal.

The existing engine reservation supplies8192 fixed control bytes plus
`4*request_bytes+512` per admitted request. Canonical request, dispatched request
and scoped request snapshot fit the four-request allowance. The latest256-byte
reply and its private immutable snapshot fit512 bytes; an authenticated getter
returns a validation token for the original reply and adds no copy. JavaScript parses authenticated receipts synchronously while the
capture is
active and keeps only private scalar authority across later awaits, preventing
queued microtasks from retagging a public reply. Python immutable receipt bytes
and fixed Confirm/Release/Forget framing use the existing fixed control
allowance, not a new pool. Captures are dropped before
the next control dispatch. Existing16 handles,8 sessions,8 Data and128MiB
processor/384MiB derived pools are unchanged; application-held arbitrary error
objects or copied packets are outside product-owned retained bytes.

## Publication boundary and evidence

The original35/36 checkpoint deliberately left selected19 uncertain. The
separate [selected publication adapter](geo-selected-publication-hosts.md) now
adopts its engine journal with exact replay/Confirm before Data read and cleanup;
36 retirement still never grants Data authority. Scope33, legacy allocation
26–29, hierarchy43/44, arbitrary transport reset and massive latency remain
separate gates. The original evidence below retains its historical scope.

Actual native tests in `tests/test_geo_selected_mutation_hosts.py` and
`packages/xy-node/test/geo-selected-mutation-hosts.test.mjs` cover lost35,
corrupt36 fallback, forged rejection/Confirm, exact replay, original Source
protection, independent Data after36 retirement, successive numeric Scopes,
Index disposal, repeated cancellation during reader and ACK, and genuine older
ResourceLimit errors from both prior calls and same-call cloned success.
Final raw reports, source/artifact hashes and independently executed Worker
controls are recorded in
[the bounded evidence](../performance/geo-selected-mutation-hosts-2026-10-10/README.md).
Integration remains pending the pull request and required CI. These are bounded lifecycle
proofs, not massive-data interaction or performance claims.
