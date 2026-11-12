# Exact private count-prefix storage — 2026-11-12

Parent: `57b1091a73ae262ea245bb0e5143b38054bc9bed`. This bounded #112 continuation changes Rust's disposable count-prefix storage; it does not complete #112 or milestones 4–7.

## Contract and decision

Resident ingress, issued-XYGC ingress and append already admit at most `u32::MAX` canonical rows. Each row contributes at most once to any prefix channel, and each cumulative entry counts a subset of those rows. The private prefix therefore uses `Vec<u32>`; totals, base totals, selected totals, absolute source/row identities and every wire count remain u64. Range differences widen to u64. Supporting more canonical rows later requires revisiting this proof.

Retaining Vec<u64> would preserve a representation that causes the pixel-resolution 128 MiB refusal. Packed lanes and dual-width storage would add arithmetic/dispatch and package complexity for a row-count regime the protocol does not support. A plain u32 vector is the reversible internal-cache choice. Allocation reservations use the smaller exact slab size; retained/pending diagnostics charge actual vector capacities. Old-plus-candidate admission and failure atomicity remain mandatory. There is no eviction-to-make-a-replacement-fit, cap increase, bin reduction, source sampling, new ABI signature or protocol version.

## Fresh functionality

The explicit pixel mode of `scripts/filter_native_callback_browser.mjs` ran the existing fully materialized 100M source through the actual native callback and five public composed density views. It asserted one active cell per actual CSS plot pixel:346, with five 100×100 passive grids, the existing renderer, and128 MiB session budget. Index storage is70,206,940 bytes, retained session storage70,505,004, and logical build peak72,610,972. These are Rust-accounted scopes, not process RSS, source-file size, V8, caller buffers or GPU memory.

The independent full scalar oracle checked 100,000 exact total/selected counts, 400,000 actual texture channels and 40 high-u64 membership identities. Indexed range/paint read zero canonical rows. Five renderings, source rows 100,000,000, close ACK, zero pending transport and no page errors passed. The same pixel harness with the parent native fails at the128 MiB budget refusal. The earlier failed diagnostic lost the custom browser error and then failed cleanup; explicit structured failure reporting now preserves the primary status2 refusal. Substantive count/pixel/lifetime assertions are unchanged.

```bash
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" \
XYG_CHROMIUM=/path/to/chromium XYG_FILTER_ACTIVE_CELLS=pixel \
TMPDIR=/var/tmp /path/to/node22 scripts/filter_native_callback_browser.mjs \
  target/task-tmp/filter-100m-fixture/materialized-100m /path/to/output
```

The fixture recipe and verification remain `scripts/gen_filter_paged_fixture.py`; generated 6.4 GB files are not committed. Manifest SHA256 remains `616229518a5b58e10ebbeb54de84350b8e6de7fcb8ecd32f8de27799890a8219`. The generator's original unqualified scope string is historical; this continuation binds its actual100M usage without modifying the fixture.

Synthetic Rust boundary tests exercise cumulative counts through `u32::MAX`, odd channel widths, one-element cooperative prefix turns, empty ranges, and exact old-plus-new one-under/exact-limit admission. These are boundary controls, not a claim to have materialized 4B rows. Public native tests refuse oversized resident and issued-paged row counts before publication and recover afterward. The public callback test now discovers both four-cell and pixel-resolution small-source modes in normal pytest.

Official generators retained all 104 complete request/reply packets. Every request and every non-memory reply byte is parent-identical; only index/resident/peak diagnostics change. Both JSON case/oracle manifests remain byte-identical. Earlier fixtures and sources are preserved through successor bindings and exact Git predecessor archives.

## Performance and remaining qualification

The private manual CodSpeed build fixture registers the genuine100M source outside measurement and evicts outside each measured build. The initial attempt measured replacement while retaining the old wide index; it correctly refused old-plus-new above256 MiB and its private input reader failed to close. That failed attempt remains failed. The corrected bounded protocol closes its reader and has explicit reply/teardown deadlines.

Wide-parent baseline: CodSpeed run `6af51a86e7145a941f725998`, 31.23 s best, three iterations, 0.76% relative standard deviation. CodSpeed reported unavailable profiling data; no flamegraph attribution is claimed. Candidate run `6af51d2ce7145a941f7259f4` measured 32.32 s best; CLI classification is No Change (-3.4% throughput). The existing four-row full-pipeline run `6af51d87c9bcb54e7068e1bc`, compared with `6af50211cca4517c4307b1f4`, reports query 5.03→4.88 ms (No Change), density 11.69→11.93 ms (No Change), update 33.21→35.66 ms (No Change), and cached 8.39→7.24 ms (Improvement). The cached result is preserved without causal attribution to this Rust change; there is no general speed-win claim. The accepted benefit is reduced logical index storage and128 MiB admission. The existing full-pipeline benchmark retains256 MiB for comparison, excludes source/index/browser setup and measures programmatic synchronized SwiftShader paints. It cannot establish trusted-pointer/RAF cadence, hardware GPU, p95, ≥50FPS or a competitor win.

The shipping single module freshly measures 1,875,197 raw / 785,725 Node22 gzip6 bytes, leaving 707 gzip bytes under unchanged 1,927,168 /786,432 caps. It retains 68 function exports, zero imports and ABI 38; native declarations remain ABI 405. Matching native/WASM/client artifacts are recorded in `checks.json`. Only the native library, WASM module, inline module and module manifest change among the eight runtime pins; both paint clients and both worker programs remain parent-identical.

Initial Rust compilation failed because the accounting method was private to a child module; moving it to the index implementation resolved the visibility error. The first native batch had four stale wide-byte assertions (21 passes); their corrected exact four-byte formula passes in the26-case batch. These failures are retained, not counted as passes.

Fresh checks include 2,074 Rust workspace tests, 32 focused checks on each actual Python 3.11/3.12 interpreter, 23 Node native/WASM tests, 673 ABI checks and full shipping browser foundation. The newly built exact Pyodide 314 wheel passes 47 complete packets, cooperative progress/cancellation/reuse, four Scene/painter cases and 17 filesystem-stub controls. Its nonpublishing version identifies the parent commit plus the source-bound uncommitted correction; it is not a release.

`checks.json` records final provenance/real-CRLF, local CI-contract, hooks/Ruff command exits and all raw/archive hashes. Complete command records distinguish fresh checks from inherited parent evidence. Parent historical proofs inherit only over verified equality; no broad Python or default Node rerun is claimed. Final independent review and delivery gates remain required. Hosted CI on PR #1122 and the required merge queue remain separate; no shipping, issue closure or milestone acceptance follows.
