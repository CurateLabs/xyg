# Issued overview domain membership hosts

This adapter adds `frame.members(cell, {sequence, maxVertices, signal})` in the
shared TypeScript/Node owner and `frame.members(cell, sequence=...,
max_vertices=...)` / `members_async` in Python. It uses the existing
[45/46 Rust protocol](geo-overview-membership-protocol.md); geometry, signed-time
eligibility, physical-row deduplication and domain-cell predicates remain Rust
policy. It adds no chart constructor or source-feature camera picking.

A returned owned Page exposes literal FeatureRef records on demand, the exact
matching vertex count, cumulative count and an opaque `nextPage` / `next_page`
continuation. MultiPoint contributes one physical row with its matching vertex
count; repeated feature IDs in separate source rows remain separate records.
Each page has at most4096 records and131328 bytes. Domain membership is temporally
exact and data-space based; `final` stays false. It is not membership in the
final projected screen image. The source, generation, complete camera/time and
five revisions, layer, cell and expected count must match the privately captured
2304-byte overview receipt. Cumulative counts advance by the independently
summed records, terminal counts equal the authenticated cell count, and physical
row ordinals increase across continuations. Point rows must match exactly one
vertex. No public cursor constructor or host-authored source ordinal exists.

The original issuing execute/read callables, exact Data owner/publication
sequence and canonical chunk reader are captured before dispatch. Public frame
fields and public packet edits do not retag membership. MemberData retains the
private continuation authority after the source, index and original frame are
disposed; the adapter retains only the bounded callback reference and snapshot,
not a source-sized mask. Confirmed page disposal releases its callback context.

The asynchronous driver retains the immutable128-byte Rust cookie and its
primitive authorized length independently of the callback's copied ticket.
It validates generation, original-row range and exact owning backing-buffer
length before supply. Callback buffers, supply framing and local views are
released before ACK8. Python waits through repeated outer cancellation until the
callback and native mutation settle. An unresolved ACK retains its exact cookie
for retry. After a lost successful ACK, only an exact cancel9 terminal receipt
with no pending cookie proves release; a cancelled step6 alone is insufficient.
Cancel/dispose/supply/ACK success receipts require exact owner/sequence and zero
reserved fields. Resolved rejection or malformed cleanup does not close owners.

46 is a same-known-handle conversion. Lost/corrupt confirmation is probed by6
before any retry; completed-query21 permits retry, Data receipt0 permits one
owning23 read. Preparation is single flight; disposal waits for publication/read
settlement, drops views, and uses Data10 sequence0 after conversion. Pressure
keeps the completed query and old frame usable. Unknown allocating45 confirmation retains the private operation and blocks
further allocation; `error.owner.recover()` / `recover_async()` replays its exact
issued request through the [durable allocation helper](geo-overview-members-recovery.md).
There is no guessed numeric disposal. Exact47 Confirm must settle before Query
I/O or46, and Query birth retirement does not prove MemberData disposal.

## Memory and copy scope

No quotas increase: eight Data, sixteen total handles, eight sessions, source
128MiB and derived384MiB remain shared. Chunk staging is admitted before callbacks
against four framing-sized copies. Rust46 preleases four complete output wires
plus control bytes while holding source/index/page authority. A typed page makes
one owning23 read and retains that original packet, without a constructor clone.
TypeScript permits exactly one optional bounded `copyBytes()` inspection copy;
records continue reading the private canonical packet. During the typed path the
four-wire reservation covers stored Rust wire, native/WASM output, owning host
packet and that inspection copy. Python retains the immutable returned bytes and
exposes a readonly view, requiring no inspection copy. Views/packets are dropped
before Data10; failed disposal remains retryable. Application-retained inspection
copies and separately requested raw second23 reads belong to the caller and must
be released by that caller; they are not additional tracked typed-owner leases.
The raw protocol still allows exactly two successful owning23 reads and rejects
a third. No total frontend/application memory or massive latency claim is made.

## Proof and remaining gates

Actual native and packaged WASM tests compare complete multi-page XYOM bytes,
normalizing only the process owner field16..24. Tests cover full u64 IDs, repeated
IDs, MultiPoint row/vertex distinction, null geometry, two canonical chunks,
All/Instant/Window predicates including signed MIN/MAX, producer disposal,
private snapshot mutation, eight-Data pressure, uncertain45, known46 probes,
callback cancellation/ACK failure, lost successful ACK, and disposal during
publication. Python additionally proves synchronous use within a running
notebook event loop and repeated async cancellation before callback settlement.

These are bounded membership adapters. Public domain-cell accessibility UI,
selected overview membership, recovery of lost-successful MemberData10, massive interactive
latency and complete M6 host journeys remain separate acceptance gates.
