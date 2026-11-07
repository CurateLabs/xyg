# PR1114 colored-spill CI repair

Continuation from reviewed GPU/native ABI401 head
`174c9ac6a24f91d25d46f3e55c559a5bad854fab`, without importing other candidates.
The actual hosted PR1114 run `42366167292`, job `128384899568`, tested merge
`ecfd8888797c00027af0bed1ccda655ad60a6a44` (feature 174c9ac6, base
`43c35f67b95ae4e78e3e96f200a0e6be8642199c`). Its colored-spill step exited 1
without printing its report-only failure. Earlier tests passed; missing later
uploads are downstream effects. The archived source log is bound in checks.
No hosted rerun or hosted acceptance is claimed here. The CI merge object is
not present locally (a read-only `git cat-file`/diff probe failed); reproductions
use the requested reviewed feature tree, not an invented exact CI merge checkout.

The exact bounded command reproduces `initial instrumentation missing` on real
Python 3.11.17 and 3.12.15. The pre-render hook indexes the raw WebGL context,
but the approved storage ledger returns an owner-accounted proxy to ChartView.
The audit resolves that chart's actual GLHost context for lookup and continues
all chart/oracle operations through the proxy. Missing instrumentation still
fails closed. Two deliberate leak controls also needed to inject actual faults: creating
unreferenced objects through the chart proxy registers them with the owner
ledger, which correctly reclaims them during teardown. Those injections now
allocate through the audited raw context, outside the product ledger. Their
explicit-deletion rejection assertions are unchanged. The initial direct-negative
run records both failures and the subsequent focused repair proof separately.
The supervisor prints failure and host report path only after
saving the final immutable reports. No admission policy, allocation, cap,
transition/pixel tolerance, deadline or rejection assertion is weakened.

The actual accepted-main run `42363845651`, job `128377965829`, had one failure
among 8,583 passes, 178 skips and 85 xfails. Its mutation set an already-main ref
to main, so strict validation correctly returned no error. The same test was
reproduced locally with the real fixture inheriting main. The replacement now
necessarily differs from the actual ref, with an explicit precondition for every
mutation. Four simulated local/PR/main/merge-group contexts over an actual
bounded report prove host/companion mismatch rejection. These are simulations,
not hosted-platform acceptance. Both verifier implementations remain unchanged.

All attempts are retained, including an initial external-native-path setup
failure (the provenance contract requires a repository-relative native path),
the two pre-repair instrumentation failures, the reproduced main mutation failure,
and an exploratory post-lookup run that failed the existing normal adjacent
transition assertion while another actual browser fixture was running. That
run lacks detailed frame observations and is not credited as passing or declared
a flake. Its assertion now includes frame diagnostics without changing its
predicate. A later direct-negative failure retained diagnostic frames showing
only endpoint draws and no intermediate-opacity frame; the unchanged transition
assertion rejected it. No cadence, timing or hosted-platform acceptance is
inferred from successful bounded controls. Subsequent bounded checks run sequentially; commands and exits in
checks distinguish every failed, partial and successful attempt.

Native and WASM artifacts were preserved before work and verified against their
reviewed source and hashes. All Rust/Cargo/toolchain/vendor inputs match the
ABI401 producer fc096e61. Generated browser assets match the reviewed focus
receipt at the base. No JS/product or Rust input changes, native rebuild, ABI
bump or generated client rebuild is required. Existing GPU ledger/admission,
supersession, watcher cancellation, recovery/focus/opaque-canvas and density
upload/stale/malformed/disposal behavior remains byte-identical. Source protection
records all retained base Git identities and explicit changed paths. Historical
performance/release and Core qualification chains remain immutable.

The original CI workload remains 16,384 points, 4,096-point chunks, 180 seconds,
4 GiB RSS and 1 GiB disk. Both actual interpreters run bounded host/browser
controls and report negatives. Raw host/browser bytes, embedded captures,
environment, source, artifacts and raw/archive logs are bound by checks. No
100M, paid hardware, release, issue/milestone closure or remote mutation occurred.
Fresh root independent FINAL review, PR1114 CI and merge queue remain required.
Full #111 and milestones 4–7 remain open.

Final bounded evidence: both original-cap 16,384-row invocations and both paired
host/browser verifiers pass. Both Python report suites pass all 98 tests with an
actual inherited-main fixture and four explicit simulated context controls.
Python 3.11 passes all 25 direct browser controls. Python 3.12 passes 23 direct
controls in the initial batch, then both repaired deliberate-leak negatives in
a focused run; the initial two-failure batch remains archived. All 33 Core and
API-inventory consistency tests, packaged WASM verification and generated ABI401
verification pass. Full-worktree pre-commit and Ruff gates are recorded before
commit. No fresh 32-chart/foundation suite is claimed: their reviewed source and
receipt/artifact identities are preserved unchanged. The phase-after-lookup
harness source is reconstructed from the final source by removing only its
added frame diagnostic; its bytes match the actual pre-mutation browser report's
recorded harness hash exactly, so that intermediate producer is inspectable.
