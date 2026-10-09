# Retained paged geographic hierarchy protocol

This private child of `geo_scale_protocol.rs` uses XYGQ/XYGZ v1 and existing C
ABI/WASM execute/read exports. Integers are little-endian typed bytes. Shared
limits remain eight active sessions, sixteen total handles, eight Data handles,
128MiB processor and384MiB derived credit. Hierarchy sessions count in the same
canonical admission helper as source, rows, members, flat index and overview.
No new pool, filesystem, provider or browser policy is introduced. The4KiB
child control lease is subtracted before core build admission; query admission
also subtracts the retained4KiB hierarchy-owner control lease. SceneData
publication subtracts the live root, owner/query controls, session/result credit
and new semantic copy before canonical Scene scratch/output admission. Local
processor limits therefore do not acquire extra wrapper allowances on top.

This first public integration accepts unselected Point/MultiPoint authority.
A trusted SceneData with linked scope or selection returns code17
`UnsupportedSelected` before allocating, advancing state or reading storage.
Unknown/selected payload flags reject. State revisions alone do not mean a
selection: monotonic unselected revisions are admitted under normal snapshot
rules. Exact selected hierarchy folding remains an explicit #50 gap; no state
is silently discarded and no selected-frame speed claim derives from the
unselected release tracer.

## Commands

All requests retain the256-byte canonical common header. Reserved bytes must
be zero. Common budget/camera/time/source/revision grammar is unchanged.

| Command | Owner and payload | Result |
|---|---|---|
|37 Build|immutable source SceneData + exact nonzero publication sequence;24 bytes: grid u32, zero4, max vertices u64, cumulative max write bytes u64|new build session|
|38 Query|private completed hierarchy + strictly newer nonzero sequence; no payload; common cmd5 camera/time/LOD/source/revisions/work|new exact query session|
|39 Data|completed query + exact sequence; uniform style48 bytes|ordinary immutable SceneData receipt, shared cmd11 serialization|
|40 Write bytes|build + exact sequence + exact128-byte pending write ticket|pure length/copy of admitted pending bytes|
|41 Write ACK|same private write ticket after host storage/copy settlement|release write loan|

Common commands6 Step,7 Supply,8 Read ACK,9 Cancel and10 Dispose operate on
hierarchy owners using their exact nonzero sequence. Data disposal uses command10
with sequence zero. Data reads use existing command23 with sequence zero and
its unchanged two-copy lifetime allowance. Repeated pure length probes consume
no copy quota; write byte copies are limited to two per pending write. ACK must
follow dropping host input/copies. Storage is immutable and namespace-scoped;
host ACK is not proof of durability, so later reads authenticate exact bytes.

Build walks every canonical chunk, then bounded external sort/merge and paged
directory construction. Explicit max-write bytes includes every tentative or
final issued page and cannot reset on ACK. Source and old SceneData may be
disposed after admission; private owning source/index/result guards keep
semantic authority alive. A corrupt page, cap error or cancelled operation
cannot publish a partial root or SceneData. Cancellation with an outstanding
read/write returns AwaitRelease; exact ACK is required before final disposal.

Query reuses shared projection/time-first source-order LOD without changing
screen bins, counts, centroid order, full-u64 IDs or original source ordinals.
The common max_rows_examined means cumulative decoded vertex records, including
repeat passes. max_chunks independently caps directory reads and payload reads;
max_read_bytes caps their combined authenticated bytes. All are hard runtime
limits; no field is ignored. Conservative256-cell frontier or work planning can
return explicit fallback. Broad final bins require the canonical path; a
fallback reply is not a complete frame. Query admission consumes its monotonic
sequence and snapshot history before authenticated directory traversal can
discover fallback. Cancel/fallback does not roll that admitted history back:
reusing the sequence or changing camera/time/layer semantics under a reused
revision rejects. A newer coherent query may retry. Previous immutable Data
remains independently valid; command39 cannot publish from a fallback.

The hierarchy owner keeps admitted sequence/snapshot and painted style history.
Reuse/regression of source identity or revision semantics rejects before a new
query mutates its history. Same style revision cannot change the48 style bytes;
style history commits only after a complete admitted SceneData is inserted.
Completed immutable Data retains exact source/result/style/snapshot under its
own lease, so rows, hit/membership, retain and frozen export retain their
existing authority after query/hierarchy/source disposal.

## Replies and tickets

Code17 UnsupportedSelected retains request handle/sequence, with all other
fields zero. Code18 HierarchyReady uses digest bytes40..48 and namespace u64 at48.
Code19 HierarchyComplete has directory reads u64 at160, payload reads u64 at168,
read bytes u64 at176, decoded vertex records u64 at184, passes u32 at192 and
selected cells u32 at196; remaining unused bytes are zero. Code10 fallback has
reason u32 at48:1 frontier,2 work, with no complete/partial Data publication.
Existing read1, write7, AwaitRelease2 and Cancelled9 retain their meaning.

Tickets are128 bytes at reply64..192 and must return byte-for-byte:
owner u64@0, storage namespace u64@8, serial u64@16, operation sequence u64@24,
kind u32@32, zero4, page id u64@40, authorized exact bytes u64@48, digest8@56.
For canonical reads, generation u64@64, chunk index u32@72, rows u32@76,
first source row u64@80, encoded bytes u64@88, digest8@96; other fields are zero.
Reserved104..128 is zero. Page/storage IDs are not source feature IDs. Exact
private comparison rejects a forged namespace, serial, kind, length or digest
before accepting data or settling credit.

## Evidence and limits

Focused tests exercise actual engine execute/read framing, authenticated pages,
signed time, full IDs, immutable disposal-independent authority, stale revisions,
copy quotas, cancellation/ACK and cap pressure. Native-versus-actual-wasm32 host
codec/driver and browser integration remain separate gates. Native release
performance evidence is `../performance/geo-hierarchy-2026-10-09/README.md`;
it is not WASM, painter or selected-state latency evidence. 1B runtime remains
unverified; sparse cold amplification and broad-frontier fallback are explicit.
