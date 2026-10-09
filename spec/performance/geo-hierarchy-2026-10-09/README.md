# Geographic hierarchy release evidence

This native engine tracer measures privately authenticated external hierarchy
construction and exact narrow camera/time refinement. It uses source revision
`61867587a`, the repository release profile, constant default geographic style,
and selection **None**. It measures neither browser/WASM, GPU paint, interaction
transport, exports, linked selections, competitor wins, nor 1B runtime latency.

The default grid is 1024. Explicit grid 256 is a tradeoff, not an automatic tier
change. At 10M it saves cold storage and native directory/seek overhead at the
cost of more candidate vertices. World queries return explicit
`FullScanFrontier` before payload reads; this is not a massive-world interaction
improvement or a substitute for the separately labelled temporal overview.

## Reproduction

```sh
python3 scripts/bench_geo_hierarchy.py --rows 10000000 --grids 1024 256 --kinds point multipoint --label release10m --write-cap-gib 48
python3 scripts/bench_geo_hierarchy.py --rows 100000 --grids 1024 --kinds point multipoint --distribution dense --label dense-cluster --write-cap-gib 1
python3 scripts/bench_geo_hierarchy.py --rows 100000 --grids 1024 --kinds point multipoint --distribution dense --reduced-kind density --label dense-density --write-cap-gib 1
python3 scripts/bench_geo_hierarchy.py --rows 100000000 --grids 256 --kinds point multipoint --label release100m --write-cap-gib 48 --timeout 1800
```

Each child runs serially under uncontrolled local load. Environment files record
revision, compiler/platform, invocation, executable SHA256 and source hashes.
`*.raw.jsonl` and Darwin `*.stderr.txt` retain native output and `/usr/bin/time
-l` measurements; `*.result.json` adds exact Scene SHA256 and owned cleanup
confirmation. First query timing is retained; twenty total samples per
camera/time case produce nearest-rank p50/p95. The full-source oracle between
first and later samples regenerates source chunks; reference timing includes
that work and serves correctness, not an apples-to-apples speedup denominator.
A camera query creates a fresh engine query session; OS/file caches remain warm.

`source_sha256` refers to the exact measured harness bytes. Frozen copies under
`sources/` preserve measured 10M/100M runner and binary source where subsequent
reporting or subprocess-safety edits changed the final maintained script. To
reproduce that exact harness, restore those copies to their canonical paths in
an isolated checkout of the recorded source revision, then use the recorded
build/invocation. Engine algorithms were not changed by this evidence slice.

The original 10M cold formatter reported valid *rows* in its `vertices` field
for MultiPoint. Raw evidence is retained unchanged; the explicit correction in
`metadata-correction-release10m.json` records 19,980,000 canonical vertices for
10M MultiPoint source rows. Two vertices per valid row were generated and
checked throughout Scene/oracle comparison. The maintained formatter and
later measurements print vertex count correctly.

## Source and output contract

The world dataset reuses `geo_index_bench.rs` SplitMix64: lon is
`(mix(i)>>11)/2^53*360-180`, lat is
`(mix(i xor 0xabcdef)>>11)/2^53*160-80`. Each 65,536-row chunk is regenerated
independently. Row `i%1000==999` is null geometry. IDs use full u64
`u64::MAX-i`, with `u64::MAX` duplicates at multiples of 23. MultiPoint emits
two vertices for each valid row, separated by 1e-7 longitude (clamped at 180).
No source-sized arrays, row masks, page maps or membership CSR are retained.

Intervals have signed start `i%1000*1000-500000`, end=start+25000, null start at
multiples of 7 and null end at multiples of 11. Rows 0/1 explicitly exercise
MIN..MIN+1 and MAX-1..MAX. Queries are All, Instant(0), and Window(-5000,5000).
Time exclusion remains in shared Rust folding before projection. The dense
calibration instead puts points near zero with modular 1e-7 offsets; its All
queries exercise actual two-pass Cluster and Density output. It is not a
massive-density timing claim.

The cameras use EPSG4326, 800×600 CSS pixels, zero pitch/bearing, world-wrap:
zoom(0,0,z8), pan(1,0,z8), deep(1,0,z12). Each first result is compared with
canonical Rust full-source LOD: exact key, direct FeatureRefs/vertex/f64 values,
reduced count/centroid bits and XYGS Scene bytes. Counted candidate work differs
from full-source work by design. Scene compile time is separate from query time;
actual UI/painter/ABI packet framing is outside this tracer.

## Bounded storage and memory

The host store is two files: append-only variable-size page bytes and a disk
16-byte/page offset/length index. Reads allocate only an exact owning ticket
length; Rust authenticates page/run bytes. No N/page-count resident map exists.
Acknowledgement follows the owned write, and read bytes drop before ACK. Files
are process-local immutable evidence storage, without fsync/crash durability
claims. TemporaryDirectory removes all external pages and temporary Scene
artifacts after the child settles; only hashes and bounded logs remain.

Construction uses the existing global128MiB engine ledger and explicit 48GiB
cumulative issued-write cap (including all temporary merge passes). The harness
also records disk index bytes and reserves their bound separately. Admission
requires free bytes >=cap+8GiB+index bound. The writer samples free disk every
64MiB with128MiB safety margin and stops if minimum8GiB headroom is threatened.
Source metadata authoring reserves96MiB; reference oracle reserves96MiB and
shrinks to actual owning output allowance before Scene compilation. Engine
credit is not OS RSS, file-cache size or external storage size. Darwin RSS and
peak footprint are recorded independently. All engine leases must return to
zero at child completion.

The maintained runner starts a private process group and kills/settles the
whole group on timeout or interruption before removing storage. A focused
nested-child timeout control verifies prompt pipe closure/settlement. A failed
or timed-out cold build is recorded without private publication; temporary
storage cleanup is explicit. A source/cap that cannot satisfy the pre-I/O
forecast is recorded as rejected without claiming a successful measurement.

## Measured 10M results

All four world cases passed, including nine camera/time oracle comparisons and
20 samples per case. Numbers below are native engine/file-cache observations;
local load is uncontrolled.

| Source | Grid | Cold build s | Issued writes GiB | Zoom All p50/p95 ms | Pan All p50/p95 ms | Deep All p50/p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| Point |1024|67.90|3.720|3.405 /3.624|3.361 /3.466|1.835 /1.928|
| Point |256|32.23|3.447|1.881 /4.792|1.228 /1.288|0.530 /0.606|
| MultiPoint |1024|85.66|8.936|3.303 /4.974|3.753 /3.989|1.926 /1.961|
| MultiPoint |256|69.29|8.663|0.934 /1.089|2.084 /3.206|0.500 /0.507|

Default1024 Point build ledger peak was56,109,312B, with81,504B retained root
credit; MultiPoint build peak63,967,440B. Sparse page/wrapper amplification is a
real cold cost; warm results alone do not establish overall product superiority.

## Measured 100M Point results

Explicit grid256 passed with99,900,000 valid vertices. Cold construction took
481.800s after9.804s manifest authoring, issuing46,456,935,360B (43.266GiB)
across830,041 pages. The separate disk offset index was13,280,656B. Canonical
source reads totalled4,298,595,328B; all authenticated build reads totalled
42,716,716,032B. Sparse storage and repeated merge I/O remain material costs.

All nine camera/time cases matched the canonical full-source result and Scene
bytes; each has20 samples. All-time results were:

| Camera | Query p50/p95 ms | Directory /leaf reads | Candidate /visible vertices | Scene bytes |
|---|---:|---:|---:|---:|
| Zoom |5.943 /13.456|20 /20|13,817 /6,209|447,456|
| Pan |7.764 /10.162|24 /30|20,769 /6,142|442,632|
| Deep |2.859 /4.387|12 /10|6,845 /22|1,992|

Instant/window p50 ranged1.423–6.572ms. These narrow world-distributed cases
were direct outputs; the separate dense calibration proves reduced two-pass
Cluster/Density semantics. Broad world returned frontier fallback in2.546ms,
with5 directory reads and zero leaf reads, without publishing final world bins.

Retained root credit was224,296B; cold build credit peak56,252,104B. The full
tracer, including its independently admitted reference/Scene stages, observed
102,477,056B credit peak. Darwin reported43,368,448B maximum RSS and43,762,048B
peak footprint. Engine credit returned to zero, and the runner removed all
external files before recording cleanup. No large artifacts remain in evidence.

The runner measured763.312s elapsed for the child, whereas Darwin time reported
1686.72s real (577.59s user/25.28s system). Both raw measurements are retained;
the differing wall clocks are unresolved, so no total-duration performance
claim derives from their disagreement. Per-phase and query values are the
native tracer's recorded durations under uncontrolled concurrent local load.

## Remaining gates

Default1024 at100M is untested. 100M MultiPoint has twice the vertices and its
forecast exceeds48GiB; a pre-I/O rejection is evidence of this run policy, not
a runtime failure or completed100M MultiPoint benchmark. 1B remains unverified.
Protocol/host/immutable frame receipt integration, actual wasm32 parity, UI
first paint, brushing/membership/rows latency, whole-world final screen bins,
linked state, failure recovery and competitor/end-to-end interaction remain
separate acceptance gates.
