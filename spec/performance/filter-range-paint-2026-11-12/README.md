# One range-and-paint transaction

This bounded continuation starts at reviewed commit
`5989ddcbff0813ecc5702fb3f17385e86f9d6a3d`. Rust accepts XYFC v3 opcode 5,
computes selected counts once, emits the existing XYFR/XYFP density payload,
and publishes intent only after output, scratch and cancellation admission.
The existing renderer consumes that reply. Public Python `range_paint` and
Node/browser `rangePaint` retain their host's transport shape. There is no
native/WASM export, ABI, default, budget, resolution or quality change.

Compatibility is explicit: an older peer may refuse the unknown version before
admitting its watermark. Only that source-matching refusal, with no newer local
intent or disposal, enables the old range-then-paint path. Admitted malformed
payloads, boundary/source/capacity failures, transport failures and truncated
responses never enable a retry. The legacy follow-up paint also checks that its
range has not been superseded. Commit/cancel barriers retain their later paint;
an earlier reply is never reused across such a barrier.

## Measured scope

CodSpeed walltime run `6af5380bc9bcb54e7068e45b` compares with
`6af51d87c9bcb54e7068e1bc` on the same materialized 100M fixture, five 400×260
CSS carriers, 346 active cells, five 100×100 passive grids, fixed SwiftShader
and explicit 256 MiB benchmark budget. Source/index/browser setup is excluded.
Every measured query/paint retains tier3, zero canonical rows read and one
source build. All measurements use the CodSpeed CLI; no raw stopwatch results
are used as performance evidence.

| Row | Parent best | Candidate best | CodSpeed classification |
|---|---:|---:|---|
| Complete five-view update |35.66 ms|30.63 ms|Improvement (+16.4% throughput)|
| Cached synchronized paint |7.24 ms|7.81 ms|No Change|
| Range query |4.88 ms|5.05 ms|No Change|
| Density reply |11.93 ms|11.82 ms|No Change|

[CodSpeed comparison](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af51d87c9bcb54e7068e1bc..6af5380bc9bcb54e7068e45b).
The update capture replaces 400,272+1,200,568 reply bytes with one 1,200,568-byte
reply. This is a bounded pipeline improvement, not ≥50FPS, p95, hardware-GPU,
arbitrary-boundary, competitor or whole-issue qualification. The three other
rows do not establish improvements. The exact native/client measurement pins,
profiles, raw CLI output, setup and completion records are archived in
`checks.json`. Later changes to that pinned Rust file affect only its test
module; final native/client equality is checked separately.

## Correctness and compatibility

- Twenty Rust filtering tests include exact-capacity success, one-byte-under
  refusal, unchanged accepted state, exact-boundary refusal and complete legacy
  packet fixtures. Capacity refusal still consumes its admission sequence.
- Thirty Python filtering tests pass on actual CPython 3.11.17 and 3.12.15.
  Thirty-five Node 22.23.4 tests cover sync/async clients, complete shipping-WASM
  parity, old-peer compatibility, source/boundary/capacity/transport refusals,
  held replies, newer intents and disposal. Normal test discovery includes the
  new Python file and the extended existing Node file.
- Actual packaged Chromium Worker conformance retains pointer/keyboard hash
  and pixel equality, 102 lifecycle oracle groups, 400 exact texture texels,
  19 canvas-coordinate probes, upload-failure rollback and GPU recovery. Added
  cooperative range-and-paint scans cancel before intent publication, recover
  exact selected density, and release their private owners.
- Actual native callbacks paint five views from 100M materialized rows at both
  four-cell and 346-cell resolutions. Both independently check 100,000 counts,
  400,000 texture channels and 40 high-u64 membership bits. The346-cell path
  retains the unchanged 128 MiB Rust logical budget: 70,206,940 index bytes,
  70,505,004 resident bytes and 72,610,972 build peak bytes. Query rows read = 0;
  membership separately reports 40 reads. No canonical arrays enter the browser.
- Full shipping browser foundation and 673 ABI smoke checks pass. The native
  ABI remains 405/551 symbols; WASM remains 38/68 function exports with zero
  imports. The single module is 1,875,498 raw /785,812 Node 22 gzip6 bytes,
  below unchanged 1,927,168 /786,432 caps, leaving 620 gzip bytes.

The old copied native library exercises real unsupported-version replies for
both sync and async clients. Discoverable tests additionally route v3 requests
to the real Rust unknown-header rejection to preserve CI coverage without an
old library dependency. Parent fixture bytes and all earlier receipts remain
unchanged. Source, compiled inputs, static copies and runtime identities are
bound separately in the successor receipt.

## Reproduction and evidence boundaries

Use Rust 1.96, Node 22.23.4, explicit Chromium 149, `TMPDIR=/var/tmp`, checkout
`PYTHONPATH=python` and the matching explicit `XYG_NATIVE_LIB`. Commands and
terminal exits are recorded in `checks.json`; compressed logs bind both raw and
archive hashes. The unchanged macro harness is
`benchmarks/test_codspeed_filter_dashboard.py`; its authoritative invocation is
in `spec/benchmarks/methodology.md`. Set the same materialized source directory,
`XYG_FILTER_ACTIVE_CELLS=pixel` and `XYG_FILTER_BUDGET_MIB=256` for comparisons.
For correctness, run `scripts/filter_native_callback_browser.mjs` with the
materialized fixture directory and a distinct output directory; pixel mode uses
the same active-cell environment flag and a 128 MiB session.

Preserved failed attempts: the first new Python membership assertion addressed
row 0 instead of the source's actual high-u64 first row; the corrected assertion
passes. The added Rust one-under test initially reused an admitted sequence and
correctly received Stale; it now uses distinct newer sequences. A validation
command named a nonexistent inventory script; the official release-inventory
command passes. Earlier uncredited weaker probe logs remain archived. None of
these attempts is credited as a pass or as a product repair.

Earlier workspace, installed-host, Pyodide, competitor and broad CI evidence is
historical and receives credit only over verified unchanged identities. This
continuation does not claim a fresh Pyodide wheel or full workspace run.
Whole #112 and milestones 4–7 remain open, including real five-view ≥50FPS,
massive/all-host/accessibility, portable Worker file sources, global memory,
prefetch/materialized masks, broader compatibility and competitor acceptance.
Independent final-diff review, current-main freshness, hosted checks and the
required merge queue remain delivery requirements.
