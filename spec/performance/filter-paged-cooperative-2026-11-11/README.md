# Native paged filtering and cooperative Worker transactions

This bounded continuation adds issued native XYGC columns to the public
Python/Node filter sessions and makes resident Worker build, prefix, exact
fallback and membership work cancellable between Rust-controlled turns.
It does not complete #112 or milestones 4–7.

The source parent is `d547f24680ba300b4b2b2184dfc82332a5cbd747`.
Earlier performance receipts, Core producers, complete binary fixtures and
their historical sources remain preserved. The successor binding chain keeps
their identities separate from the newly compiled source.

## Implemented path

- `ChunkedColumns.column("x"/"y")` issues native source references. Rust pins
  immutable file/metadata ownership without retaining a viewport cache, reading
  complete numeric columns, filtering nonfinite rows or renumbering identities.
  Source ingress remains u32-row-bounded; absolute row/source identities are u64.
- Native open uses the shared Rust layout reader. Rust issues header,
  metadata and overview byte intervals, admits the complete layout/read envelope,
  and validates fulfilments atomically. It does not read canonical numeric rows
  during layout acquisition. Browser file registration is not implemented.
- Source access and row kernels are shared by resident and native paged builds,
  exact fallback scans and membership. Paged read workspace stays within 2 MiB,
  independent of canonical row count. Native append to an issued source refuses.
- A dedicated Worker uses XYFJ controls over the existing filter export. Rust
  owns bounded work, private candidates, cancellation, capacity refusal and atomic
  publication. Indexed serving still reads zero canonical rows. Array ingress and
  configuration parsing remain synchronous.
- Suspended jobs share the immutable source and take ownership of already private
  configuration/predicate replacements. They borrow unchanged accepted state only
  after revision/source checks. They do not clone source columns or make additional
  capture-only copies of configuration/masks. Per-job peak history survives
  unrelated malformed requests and includes transient staging on every turn.
- Worker claims precede initialization. Failed claims preserve foreign work;
  constructor failure waits for release ACK, and repeated close shares that ACK.
  Filter and incompatible retained authorities refuse coexistence before mutation.

This is logical operation/instance accounting, not a global process, browser,
driver or GPU budget. The native legacy open API still has no caller budget.

## Module fit and source sharing

The normal official packager passes with **1,875,741 raw / 786,020 Node 22
gzip-6 bytes**, leaving **412 gzip bytes** under the unchanged caps of
1,927,168 raw / 786,432 gzip bytes. There is no automatic future allowance.
Native ABI 405 retains 551 declarations; WASM 38 retains 68 function exports.
No compiler, profile, optimizer, export, cap or validation gate was weakened.

Current selected artifacts:

| Artifact | SHA-256 |
| --- | --- |
| Native core | `e808cd07bca7c08548ff4bcc40a7fcb1065fe4630d3ea564602e8d60a8892386` |
| Optimized and normally packaged WASM | `84451fa2f9008d14cbbb004c1c534ff0f992c93549e65dbf66e820a01aabcc78` |
| Compiler WASM | `21f28be9882992527281a8d4df62dd6081e0d1a9458d9071779eddb58a33124d` |

The 327 compiled inputs and generated client/static artifacts are recorded
separately in the qualification data. The final normal-module checks use no
diagnostic override. Earlier over-cap diagnostic runs receive only their
explicitly bounded functional credit.

Shared source work removes duplicated filter callback/work/query/parser bodies,
uses the existing stable scalar/coordinate sorters for bar-width and clipping
scratch, and replaces the capped 64-clause list's general sorter with bounded
insertion. Geographic density memberships and directed clipping edges retain
derived u32 pairs as arithmetic u64 keys through sort/dedup/consumption. These
keys preserve lexicographic order and complete payloads; canonical coordinates
and u64 identities are not packed or narrowed. Existing admission estimates
remain conservative and unchanged. No extra canonical allocation is introduced.

## Fresh verification

The current matching-source executions pass:

- Rust workspace: **2,070 tests**; owned engine Clippy with warnings denied.
- Focused properties include 15 filtering, 23 density, 43 viewport and the pair-key
  ordering/round-trip test. Layout coverage includes split windows, exact budgets,
  stale tickets, cancellation/callback failure and late malformed records.
- Node: **65 tests**, including complete synchronous/native/cooperative legacy
  and linked-edit/base-mask packets, actual WASM, geographic processor parity,
  output-capacity refusal and source/lease lifecycle.
- Python 3.12: **60 tests**, including the four complete decoded-image/oracle
  comparisons. Actual Python 3.11: **59 passed, one optional Arrow skip**; its
  required image comparisons pass. The borrowed 3.11 environment was not synced.
- ABI smoke: **673 checks**; official native/WASM generators stay current.
- Normal-package Chromium filter conformance: 44 legacy successful packets,
  56 density successful packets, five painted views, 102 oracle groups,
  400 exact texture texels and 19 canvas-coordinate probes. Pointer/keyboard,
  refusal, eviction and recovery checks remain intact.
- The separate 150,003-row cooperative programmatic case is explicitly
  `rendered:false`: 256 progress observations, 36,451 selected rows, 40,001 exact
  membership bits, malformed-header preservation, cancellation/recovery,
  constructor/repeated-close ACKs, foreign-owner preservation and disposal.
- The complete browser foundation passes on the normal package, including
  existing graph/temporal/GPU/frozen-export and aggregate proof paths.
- Four density/clipping transactions compare every native output byte against
  the sealed pre-packing library, retaining high-u64 identities and topology.

These runs use Rust 1.96.0, Node 22.23.4, CPython 3.12.15/3.11.17 and the supplied
Chromium 149. Source/artifact/log hashes bind the individual executions; none of
these totals is a whole-milestone or all-platform acceptance claim.

## CodSpeed comparisons

Measurements use the existing CodSpeed harness, excluding source framing/setup.
There was no concurrent CPU-heavy work during the measured executions. Both
native C processors retain their normal capacity-query/copy calls.

| Work | Mode | Baseline → head | Disposition |
| --- | --- | --- | --- |
| 1/8/32/64-clause edit round trip | Simulation | `6af4c358d1706c334bea35e7` → `6af4c544ced81646aeeefb0d` | Four No Change |
| Same | Walltime | `6af4c3a6ced81646aeeefab6` → `6af4c5c9d1706c334bea3628` | Four No Change; 64-clause sample 2.9% slower retained |
| Density 1k/10k, clipped 64/256 polygons | Simulation | `6af4c7f69c0b923757c59aa3` → `6af4ccb09c0b923757c59b2a` | Four No Change; slower clipping samples retained |
| Same | Walltime | `6af4c9119c0b923757c59abf` → `6af4cd759c0b923757c59b45` | Four No Change |

No speed win, competitor lead, 100M throughput or input-to-pixel result is
claimed. The initial geographic simulation used a hardcoded ABI 405 setup guard;
the measured callables were unchanged when that guard was generalized to the
generated ABI authority and a fresh paired baseline was recorded. The earlier
run remains preserved. Clause baseline walltime reported 41 lost profiler events
and per-case variation up to 17.01%; it is not promoted to a reliability result.

## Failures and limits

Preserve the failed build/source-sharing trials and their exact logs. Earlier
diagnostic modules exceeded the cap; a pending-vector trial increased module
size and was reverted. The first query-helper extraction missed an active-axis
reference; the first ownership extraction placed a borrow outside its closure.
Both compile failures remain failures. The first layout Clippy run found an
obsolete constant; two unqualified builds were stopped before correction.
Initial layout Python batches skipped the browser due to the wrong environment
variable; explicit required-browser reruns subsequently passed. The early
insufficient peak regression passed because the parser envelope dominated;
the enlarged test reproduced the actual defect before the correction.

Read-only frozen-source audits found no concrete new blocker in private-proposal
ownership or layout acquisition. These audits do not replace independent review
of the final complete diff. Current-source qualification passes four Core checks,
including the real Git LF/CRLF checkout, with 3,505 current sources, 1,720
historical bindings and 54 parents. Full-worktree hooks, Ruff and typing pass.
Final external review, new-head hosted CI and merge queue remain required.
The reported Python runs precede an AST-identical formatting correction;
that formatting identity is recorded rather than claiming another browser rerun.

Portable Worker `File` registration/numeric read tickets/attachment, exact
inclusive-boundary index extensions, materialized masks/prefetch, real 100M
five rendered views at ≥50 FPS qualification, global budgets, remaining hosts,
accessibility, CodSpeed/competitor/scale acceptance and whole issues remain open.
