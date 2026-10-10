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

Trusted selected Point/MultiPoint SceneData is accepted by Build37. The root
indexes all canonical vertices, independent of selection/time; it retains the
private linked Scope Arc. Selected queries fold exactly the existing sparse
Rust state through the shared time-first LOD accumulator. No source-sized mask,
ID reconstruction, host filter or implicit ID join is introduced. Ordinary
unscoped paths keep XYGZ v1 bytes; selected Data uses existing XYGZ v2/XYSE.
Selected latency and massive selected execution remain separate evidence gates.

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
|42 Fork lane|completed hierarchy + its exact immutable creation sequence; empty payload|new independent lane sharing immutable root and Scope, with creation snapshot/style history|
|43 Selected query|scoped lane + common query header and exact8-byte issued State handle|consumes State on successful admission, replacing that handle with query authority|
|44 Selected Data|completed selected query, no outstanding IO, exact sequence and uniform style48|replaces query with independently owned SceneData at the same handle|

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

Code17 UnsupportedSelected applies to command43 on an unscoped root and preserves the issued State. It retains request handle/sequence, with all other
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

The existing direct-browser WASM CI job runs this bounded native/WASM conformance
after packaging, inside the existing Release surfaces aggregate. Merge-group
coverage and the separate scheduled/manual massive-scale policy are unchanged.

## Selected lane authority and resource accounting

A fork initializes transition and painted-style history from the immutable build
snapshot, never another lane's latest camera/time revisions. Source equality
includes complete validated chunk descriptors, geometry/CRS/row count/digest and
generation. Command43 additionally requires identical private Scope Arc, layer,
current canonical sorted IDs and selected paint profile. Commands38 on scoped
roots reject, so a caller cannot accidentally drop selection. Preflight errors
leave State and lane history intact. Successful command43 consumes State and
advances the lane history even if later directory planning falls back or the
query is cancelled. The caller may explicitly reissue identical intent via33
under its existing same-revision equality contract; it must use a newer coherent
query sequence. No State capability is restored from wire bytes.

Command44 first retains/copies semantic result, source, style, snapshot and Scope
under the existing SceneData leases, then atomically replaces the completed
query. Query/session credit is dropped only after new authority owns every
semantic reference. Failed publication leaves the completed query usable.
Command39 keeps its independent Data allocation semantics. The existing exact
pick, membership, original-row paging, retain and frozen selected authority use
these same private guards after Source/lane/query disposal.

Every lane reserves4KiB before allocation. Shared root/Scope/IDs remain Arc-owned;
there are no per-fork metadata or sparse-ID copies. Local admission counts root,
Scope control, the complete retained nonce33 request receipt, current state and
query state (once if pointer-identical), controls,
frontier/cache, accumulator, output counts and publication phases. Query credit
conservatively retains the existing extra LOD-base reservation; selection adds
at most one u64 count per admitted cell plus the sparse state reservation.
Distinct old state and current Scope intent are both charged during overlap.
The shared Scope publication-credit helper includes nonce receipt storage even
after its original State handle is consumed or disposed. Command43 excludes only
the exact query State Arc credited by its selected LOD reservation; command44
also retains the existing result/selection credits. This repairs selected local
admission: tight budgets that previously omitted receipt storage now fail before
State consumption or Data publication. It changes no packet, geometry, global
quota or ordinary unselected38/39 policy. Shared no-State Scope admission for
build/fork also includes its retained intent and receipt; Arc references allocate
no additional ID plane.
Global processor128MiB and derived384MiB credits remain independent of local
preflight, and old Data retains its own credit throughout replacement.

With one shared Scope, five lanes and five displayed Data owners,11 handles are
live. One issued State uses handle12, command43 replaces it with Query12, and44
replaces it with candidate Data12. Six Data are temporarily live, below8. Old
paint is released only after consumer settlement. Five distinct Scope/lane/Data
triples can instead occupy15 handles: State16→Query16→Data16 still fits. Forking
uses the original owner as lane0 plus four forks, not an extra sixth root owner.
Five simultaneous row auxiliaries are not implicitly admitted; pressure fails
closed, and callers must explicitly park/dispose engine owners while immutable
frames/pages remain valid. No cap or ABI signature is increased.

The existing paired native/WASM CI step also runs selected hierarchy conformance
for commands42–44. It reuses freshly built core/artifact and the existing Release
surfaces gate; no separate performance/platform job or quota is introduced.

Nonzero header240 recovery for selected43/44 is specified by
[Recoverable selected hierarchy phases](geo-hierarchy-recovery.md). Nonce0 and
ordinary38/39 remain unchanged; engine recovery is separate from typed host adoption.
