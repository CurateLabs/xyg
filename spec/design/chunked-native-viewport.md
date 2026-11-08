# Local native chunked-chart viewport refinement (#110)

Status: native local end-to-end candidate qualified by the installed and HTTP
journeys below. Full milestones 4–7 and #110 remain open. Rust owns artifact
validation, admission, exact viewport membership, paging, generation cancellation,
canonical row identity and cache retention (rust-engine.md §5.1/5.1a/5.1b).
This continuation changes no native ABI, artifact format, canonical admission
budget, renderer governor, timeout, tolerance or WASM package cap.

`ChunkedColumns.chart()` preserves snapshots and exports through the public scatter
composition API. Notebook widget construction opens an independent native handle;
Node `chart.liveHost(send, callbacks)` does the same. Its `payload()` supplies split
paint and `message(control)` accepts the shared browser protocol. Callbacks are
`onHover`, `onClick`, `onSelect` and `onViewChange`. The repository-only
`examples/vanilla-ts/chunked-native-host.mjs` carries ordinary controls and raw XYBF
attachments over local HTTP. No service, framework or renderer is added to the
package. Closing the constructing source or one chart leaves other owners intact.
Chart composition remains lazy, including public width/height customization.

Each owner has one active native read and one replaceable latest intent. Every
newer valid intent advances Rust's generation watermark immediately. Python
coalesces foreign-thread/cross-loop ingress before scheduling the owning loop;
Node calls the generated Koffi function's `.async` entry. Generation and mount
mismatches discard results. The renderer uses a document-monotonic mount epoch
seeded by the host's synced floor, including recreated anywidget proxies. Old
unmounts, callbacks and unsubscriptions cannot remove a replacement mount. Close
cancels first, drains the read whose Rust Arc may survive registry removal, then
frees the handle. Constructor failures release the new owner. Python `when_idle()`
and Node `whenPainted({signal})` settle only after an accepted paint or a terminal
error; Node `whenIdle()` waits for native work. Waiters are bounded to 16 and a
cancelled observer does not cancel another observer or strand teardown.

Refinement replaces data through the existing renderer while preserving the exact
camera, ranges, original overview home domains, geometric selection and navigation
history. Candidate GPU resources are staged transactionally. The actual draw must
succeed before `chunked_painted` acknowledges matching mount/intent/frame strings;
failed reads, allocation/draw failures and rejected stages retain the last accepted
paint and identity. Incorrect/late ACKs cannot publish another row map. Native
provenance accompanies that accepted frame. A frame event follows token advancement
and ACK, so event observers cannot send picks using the preceding frame identity.

Picks and box/lasso selections require the accepted frame; stale picks and masks
fail closed. Scalar `source_row_id` is an exact decimal string. Python selection
`source_row_ids` and Node `sourceRowIds` are canonical u64 arrays. Live selection
attachments are raw u64 buffers, decoded before publishing masks and browser
selection events. Local indices keep their vertex-index meaning. Node delegates
box/raycast membership to the existing native range/polygon functions. Numerical
source columns and identity lists never enter live JSON. The >2^53 codec regression
is an explicit injected codec control, not a claim of a physically huge source.

The canonical budget is not a total process or GPU cap. Let C=floor(budget/16),
O=24C (three native output capacity planes), P=64C+65536 (validated raw paint
serialization bound). At most one accepted, staged and completed result and one
active output coexist, in addition to the original overview and its six-u64
(48-byte) native statistics plane. Capacity accounting
uses underlying backing buffers, deduplicated by owner; slot bounds conservatively
allow 4*(2O+2P) plus original overview capacity. Node compacts views of the existing
256 MiB trace materializer arena into P-bounded owned buffers before retention.
The arena remains a transient allocation with its existing limit. Python reports
its existing arena too. Selection may temporarily allocate two u32 candidate
planes, u64 identity output and up to 2048 paired-f64 polygon vertices per callback;
the ingress queue and its delivery snapshot each hold at most 16 controls
(combined at most 32 copied notifications), before any foreign-thread callback
can run. Admission remains 16 pending entries; this accounting includes both
bounded snapshots. Native cache
payload is bounded by min(page_bytes, 8 MiB), cache entry count by that value/16;
metadata, zone maps and native result vectors are additional. The aggregate plus current page native result vector backing is conservatively
accounted at max(4O,192), including Vec minimum-capacity floors. Native metadata
records are bounded by file_bytes/48 and the overview by 2048 records. Access and
eviction records are additional: a conservative count bound is
4*(C+524288), at at most 64 bytes per record on this qualified 64-bit target.
This includes trimming a previously full 8 MiB cache. Raw/decode page scratch and
cache payload are additional page-sized allocations; allocator overhead is not
reported as logical array capacity. File size is reported, not charged as a
resident allocation. Browser observations include retained raw payload backing,
actual WebGL buffer sizes and canvas RGBA8 bytes. The existing shared-host
GPUStorage ledger supplies all requested per-client texture/buffer bytes and shared
canvas/storage bytes, including the separately identified pick RGBA8 subset. These
subsets overlap ledger totals and must not be added twice. Opaque driver bytes
remain explicitly unknown. The HTTP consumer caps each serialized frame at 8 MiB,
its pending replies at 16 and controls at 64 KiB. Process RSS and Node memoryUsage
are observations, not hard bounds. Global accounting #111 remains open.

Required discovery uses the existing Release surfaces Python job and the normal
Node `npm test --prefix packages/xy-node` command. Python explicitly runs
`test_chunked_live.py`, `test_chunked_lifecycle.py` and `test_chunked_installed.py`
once, then excludes them from the remaining suite. The installed test builds the
normal wheel, installs it into an isolated Python 3.11 environment, starts actual
JupyterLab/ipykernel and drives anywidget with trusted Chromium gestures. The Node
browser test runs the public liveHost through the example's binary HTTP route.
Both compare exact source predicates and actual canvas RGBA pixels with independent
full-scan composition oracles and show the old overview control differs. Actual
click/box identities, Node lasso, cache revisit, failed-stage rejection, storage
missing/corrupt/partial and budget failure, retained-picture oracles, stale masks,
remount and history, two handles, source leases, cross-loop ingress, native active
cancellation and teardown are covered. Linux inotify establishes a real active
positioned read for close/drain proof. No fabricated ACK or relaxed timeout is used.

Receipts and original-minimum acceptance mapping are in
`spec/performance/chunked-native-installed-2026-11-07/`. Earlier checkpoint and Root
producer receipts remain immutable and are linked by the successor bindings.
Root's normal combined-WASM producer fits the unchanged caps (1,897,244 raw /
784,226 Node 22 gzip6 bytes, all 68 exports); this native continuation reuses its
verified unchanged Rust inputs. Larger-than-physical-31-GiB-RAM backing,
remote/direct-browser-WASM sources, complete massive-data resource/latency/fetch/
export/competitor qualification and the remaining issue-wide acceptance are still
open. These native proofs do not imply shipping or milestone closure.
