# Exact overview domain membership transport

This private retained protocol implements the engine contract in
[geo-temporal-overview-membership.md](geo-temporal-overview-membership.md).
Dossier §27/§28 authority remains an immutable exact-temporal, data-space,
nonfinal overview result. Membership includes offscreen rows and exposes no
Scene, source hover identity, `GeoLodKey`, or projected-bin capability.

Commands use XYGQ v1's 256-byte header and unchanged ABI383/WASM33 entrypoints.
45 creates a new query from an authentic OverviewData or a prior MemberData.
Header handle and sequence identify the exact issuer. Its 24-byte payload is
new nonzero operation sequence u64, cell u32 (0..255), zero u32, and maximum
examined vertices u64. Resume requires the private prior page's same result,
same cell, nonterminal cursor, and newer sequence. Decoded cursor bytes cannot
mint continuation. Source, index, and original OverviewData may be disposed;
canonical chunk storage is still caller owned and must remain readable.

Commands6–10 use the query's exact operation sequence. Read cookies are private
128-byte authorities: owner/serial/sequence u64 at0/8/16; kind1 u32 at24;
zero28; generation u64 at32; chunk index/rows u32 at40/44; original first row,
encoded byte length u64 at48/56; digest8 at64; zero72..128. Reply cookies occupy
64..192. Supply7 carries cookie+exact authenticated bytes; release8 carries only
the cookie after callback input/copies drop. Cancel9 and dispose10 retain loans
until exact ACK. A pending dispose returns AwaitRelease2. No ACK can be forged
from a public mutable ticket or a different owner.

Query6 completion21 contains row count, expected cell count, cumulative matching
vertices u64 at32/40/48; has-next u32 at56; zero60; examined rows/read bytes u64
at64/72; chunks read/considered u32 at80/84; zero88..256. Completion21 is not a
Data receipt.46 publishes the completed query **at the same handle**, only after
all quota, local-budget, global-credit, and encoding checks succeed. Failure
preserves the completed query for retry. Its ordinary receipt0 carries byte
length at32 and its own handle at40. After a lost successful46 reply, exact6
returns that same Data receipt; callers must probe, rather than replay46 blindly.
A lost allocating45 reply remains an unresolved recovery gate; this slice does
not claim durable allocation recovery.

MemberData23 requires exact publication sequence. Length probes are pure and
consume no copy slot. Two successful owning reads are permitted per Data lifetime;
a third fails ResourceLimit. Dispose10 uses sequence0, not publication sequence.
MemberData counts toward the combined eight Data/16 total handle ceiling but
cannot be used by Scene/LOD/Rows/snapshot APIs. Queries count toward eight active
sessions. No new memory pool is introduced.

XYOM v1 has a 256-byte header followed by at most4096 32-byte records. Header:
magic/version at0/4; flags3 at8 (temporal_exact/data_space, finalfalse); resolution16
at12; owner/sequence/record count u64 at16/24/32; cell/has-next u32 at40/44;
expected/cumulative vertex counts u64 at48/56; source rows/generation u64 at64/72;
source/overview digests8 at80/88; layer ID u64 at96; source CRS/geometry u32
at104/108; camera CRS/wrap u32 at112/116; seven camera f64 bit patterns at120..176;
five camera/time/layer/style/state revisions u64 at176..216; time kind u32 at216,
zero220; signed start-or-instant/end i64 at224/232; page matching vertices u64
at240; zero248. Each record is literal feature ID/source-row u64, chunk index/row
u32, matched vertices u64. Duplicate IDs remain distinct original rows;
MultiPoint contributes once per row with every matching vertex counted.

Query controls reserve4096 bytes before core creation and deduct that reservation
from its local processor allowance. Publication preflights all held source,
result/index, page and query-control credits plus four complete wire copies and
output-control allowance before encoding. The shared source128MiB and derived
384MiB ledgers remain unchanged. A lazily created empty derived cache is removed
on publication failure. Data owns its page/result authority, encoded bytes and
credits until disposal; outstanding ticket copies retain their loan separately.
This is a bounded canonical scan, with no massive interaction latency claim.
