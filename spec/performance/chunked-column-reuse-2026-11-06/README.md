# Local canonical chunk reuse candidate (#110)

This bounded continuation follows accepted main
`c3152d97bdb3a1efd61686b21d84385ee0f8de9e` and reviewed repair
`82fab9c1239e8df3d4e065c0a7fbcf98759ec9e7`, both normal-merged with
`--no-commit` and full-worktree hooks before merge commits. Implementation base
is `7093ea3f` (the combined merge). Historical receipts remain unchanged.
The two stale-parent documentation conflicts in the first merge took the
accepted-main versions; the repair merge was conflict-free.

The Rust-owned per-open cache reuses structurally validated canonical f64 slabs
through both existing native read modes. Exact oracle tests retain physical row
IDs across duplicate coordinates and nonfinite omission. Instrumentation counts
actual positioned-read calls, and cache accounting asserts exact byte sums and
LRU order. Overlap requires one new chunk, then repeated reads require zero;
warm admission still counts all selected bytes. Tests cover generation
supersession while waiting for the cache lock, cancellation after actual I/O and
on hits, failed I/O, structural corruption, budget reduction, eviction and an
8 MiB + 16-byte slab that bypasses retention without changing admission.

The normative contract is [rust-engine §5.1a](../../design/rust-engine.md#51a-bounded-local-canonical-chunk-reuse-110).
The 8 MiB cap covers retained canonical slab payload per handle; request budgets
also bound raw in-flight slab payload. Metadata, cache bookkeeping, provenance,
results and host output are additional allocations as documented there. There
is no total-RSS measurement or larger-than-RAM performance claim in this proof.
Artifacts must remain immutable while open. Cancellation can retain validated
slabs from completed steps and does not roll back the cache.

No ABI or file-version change is needed. Existing Python/Node stats count actual
miss I/O. Detailed row IDs, chunk metadata/hits, evictions and resident bytes are
recorded in the Rust result, not exported through new host APIs. Cross-work
integration risk is limited to the changed meaning of read counters on warm
calls and the additive native cache residency/provenance allocation; host
selection/admission and page boundaries are preserved. The module is excluded
from `target_family = "wasm"`; no WASM artifact was reused or rebuilt for this
native-only change. The raw 1,927,168-byte and gzip6 786,432-byte WASM gates remain
unchanged. No JavaScript product source changed or bundle was reused.

See `receipt.json` for source, artifact, environment and log hashes; raw test and
build output is retained alongside it. Reproduction commands are in that receipt
and [tier3-testing](../../design/tier3-testing.md#bounded-canonical-chunk-reuse-proof-110).
The parent must independently review the final diff and handle delivery. No push,
PR, tracker mutation, publication or milestone closure was performed here.

## Remaining acceptance

#110 remains partial: larger-than-RAM open/first meaningful paint within committed
RSS/latency budgets; integrated overview, pan/zoom, filter and chart lifecycle;
full host parity including browser/WASM orchestration; unordered spatial
localization; missing/stale/partial/malformed and cancellation evidence across
those integrated journeys; local/memmap scale and remote/range-readable evidence
if remote access is supported. This proof establishes local native chunk overlap
reuse only, not browser tile reuse or all overview navigation acceptance.

#109/#113 still depend on #5/#11 successful accepted-main accelerated 100M evidence
under unchanged hardware guards, #111 shared-context/global-GPU-budget dashboards,
#112 indexed Filter Tier C linked views, and the complete larger-than-RAM,
100M/multi-view/recovery/export/offline/platform journey matrix with measured
memory, latency and frame-rate evidence. M4–M7 closure remains with the parent.
