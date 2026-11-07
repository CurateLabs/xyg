# Local native chunked-chart viewport continuation (#110)

Status: implementation candidate; full milestones 4–7 and #110 remain open.
The authority for chunk admission, paging, exact predicates, generation cancellation
and canonical cache retention is rust-engine.md §5.1/5.1a/5.1b. This continuation
changes no native ABI, artifact format, canonical-byte cap, or WASM package cap.

`ChunkedColumns.chart()` preserves the snapshot/export surface. Python notebook
widgets additionally open an independent native handle on widget construction.
Node snapshots expose `chart.liveHost(send)`; its `payload()` supplies the initial
split paint and its `message(control)` consumes the existing anywidget-shaped
browser model messages. Applications carry those messages and binary attachments
through their existing transport. `close()` drains the active asynchronous native
call before freeing that handle. Closing the source that constructed the snapshot
does not close the independently mounted native owner.

Each owner has one active native read and one replaceable latest viewport intent.
Every newer valid intent immediately advances Rust's generation watermark. Python
coalesces before scheduling its owning event loop; Node uses the generated Koffi
function's `.async` entry so main-thread cancellation remains available. Results
are discarded on generation or mount mismatch. Each browser model assigns a
monotonic mount epoch; late earlier mounts and unsubscriptions cannot retire a
replacement mount. Teardown cancels before draining, including outstanding reads
whose Rust Arc would otherwise survive removal from the handle registry.

A successful read compiles through the ordinary scatter composition and offset
paint encoding. The browser stages trace resources against the candidate spec,
retains the original home domains, camera, and history, then replaces the retained
paint payload. Failed native reads leave the last accepted frame intact. A real
browser replacement emits `chunked_painted` with mount, intent and frame strings;
only its exact matching staged host frame becomes the pick/selection authority.
Picks and selections carry the accepted frame string and stale frames fail closed.
`source_row_id` is a decimal string in scalar pick rows. Python selections expose
`source_row_ids` as u64 arrays; selection message identity attachments are raw u64
buffers. Local vertex indices retain their existing meaning and are never renamed
artifact identities. Numerical source columns and ID lists never enter live JSON.

The native budget remains canonical admission, not total process RSS. The host
allocates three capacity planes (u64 IDs, f64 x, f64 y): 24 bytes per capacity row,
where capacity is `floor(budget_bytes / 16)`. One accepted frame, one staged frame, and one completed result waiting for
its publication slot can coexist with active output. Original overview, encoded paint, GPU staging,
metadata and Rust result vectors are additional; this candidate does not establish
a total host/GPU memory ceiling. Actual `chunks_read`/`bytes_read` are Rust physical
read provenance; they are not inferred from selected counts. Revisit reuse depends
on the existing per-open/page-budget LRU, not a host memoization cache.

Focused regressions live in `tests/test_chunked_live.py` and
`packages/xy-node/test/chunked-live.test.mjs`. The browser test uses real Chromium
wheel gestures through the public renderer/model and native Python or Node host,
with a test-only binary carrier. It is not an installed Jupyter kernel proof.
Configure `XYG_TEST_CHROMIUM` and optionally `XYG_NODE`; `XY_REQUIRE_BROWSER=1`
requires the browser. Python Playwright is development-only.

Remaining acceptance includes installed Jupyter/VS Code remount integration,
Node lasso and complete selection callback integration, cross-loop and adversarial teardown/rebind
coverage, full-scan pixel oracles and negative controls, malformed/corrupt/partial
and budget failure matrices, complete host buffer accounting, larger-than-physical-
RAM backing and resource/latency/fetch/export comparisons, remote sources and
browser/WASM staging. The unchanged combined-WASM over-cap result is not qualified
by these native tests. No milestone closure or shipping readiness follows.
