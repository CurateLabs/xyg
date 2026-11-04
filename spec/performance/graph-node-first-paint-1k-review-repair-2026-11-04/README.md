# Current Node 1k first-paint helpers: PR #1093 review repair

This versioned append-only directory is the **current runnable proof**. It repairs
Greptile's two accepted P2 findings against
`c3d2e4aa19bcfbf9940775819f03c71cc0934472`: held UPDATE acknowledgements and actual
selected-native identity/origin reporting. It changes no production implementation,
loader precedence, scheduler, force policy, painter, #36 contract, budget, tolerance,
compiler, dependency, module gate or release acceptance.

The earlier `graph-node-first-paint-1k-2026-11-04/` and
`graph-node-first-paint-1k-parent-sync-2026-11-04/` directories are immutable
historical records, including all runners, raw measurements and manifests.
Their old runnable paths are superseded; use this directory's commands below.
Their conventional-path hashes **do not retroactively attest which native file
was actually selected**. No historical capture is relabelled or repaired in place.
`before-repair.json` and `preservation.json` bind that exact preservation.

## Held presentation ACK repair (P2A)

`inspection.mjs` still deliberately holds the initial genuine HTTP ACK for
invalid-ACK rejection, trusted initial UUID pick and pan inspection. After release,
`ack-drain.mjs` accepts each intervening genuine UPDATE ACK until COMPLETE, using
an overall 30 s drain deadline, bounded ACK arrival waits, exact job/revision/step
matching, increasing safe steps within the authored 401 cap, and explicit phases.
It does not wait for COMPLETE while leaving an UPDATE held. The final COMPLETE
ACK remains held for final inspection and is then released. Worker lifecycle,
cancellation, default chunking and native force math remain unchanged.

Camera reset is checked on the **first replacement**, whether UPDATE or COMPLETE.
That frame's `previousView` must equal the inspected panned view, and its new view
must equal its own payload ranges. Later COMPLETE can legitimately follow one or
more replacement views, so it is not required to report the original panned view.
All actual presented specs/buffers/full-source positions are archived.

`ack-drain.test.mjs` provides a **labelled test-only scripted ACK protocol**:
initial -> UPDATE -> UPDATE -> COMPLETE. The corrected shared drain acknowledges
steps 1/11/21 and checks camera reset at 11, leaving 31 for final inspection. The
historical wait-for-COMPLETE algorithm times out on that same ACK-gated sequence;
its completion observer does receive COMPLETE after the missing UPDATE ACKs are
provided. The test also shows the historical final-only camera assertion fails
on this valid sequence. Stale jobs/revisions, invalid phases, nonadvancing or
out-of-cap steps, wrong ACKs and missing ACK deadlines are negative cases.
These scripted frames are **not Rust callbacks, rendered geometry or cadence
measurements**. They are necessary protocol coverage when real 1k jobs coalesce
straight from initial to complete.

## Actual selected native file and origin (P2B)

The new fixture imports the existing `nativeLibraryPath` and `abiVersion` exports
from the module instance used by its normal production GraphForge calls. Its HTTP
evidence reports the selected path, resolved path, SHA-256, byte count and bound ABI.
A read-only `--import` observer inherits into the real bridge and force Workers,
imports those same existing native/ABI modules before each entry module, and logs
thread/role/job identity with selected-file observations. Every primary job must
have direct bridge and force observations. This adds no product export or API.

Both runners independently reopen/hash **that reported file**, ABI-bind that exact
path with koffi, and require matching observations from fixture/main, primary
bridge and primary force Worker. This is not a hash of the runner's own loader
choice, `XYG_NATIVE_LIB` text, or a presumed `target/release` file. The normal
production resolver still tries an exact-platform package before the explicit
development override. The observer does not replace that resolver or choose a
library on its behalf. Attestation adds measured startup/I/O overhead.

Observation scope is explicit: the existing module's exported selected path,
file bytes at observation and independent recheck, and the ABI bound from that
file. This is not hashing mapped executable pages or protection against arbitrary
concurrent file replacement. The fixture also rechecks its file at evidence reads.
No extra force pass or fallback implementation is used.

`matchesKnownParentArtifact` compares bytes with
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`.
The bounded real-force captures here admit only that known parent digest, rejecting
alternate/checkpoint artifacts before starting the force job. Matching bytes do
**not** establish whether someone rebuilt or copied that file before this run.
Default `origin.declaredKind` is therefore **unknown**. No native build or client
build was invoked during this review repair. Existing client files are independently
hashed; their earlier build history is not inferred from matching bytes.

For an explicit origin declaration, set `XYG_NODE_NATIVE_ORIGIN_RECORD` to a JSON
record with `kind` (`reuse`, `copied`, or `rebuilt`), `selectedPath` and
`expectedSha256`. Identity/path mismatch fails closed. `copied` additionally needs
a distinct `sourcePath` with matching bytes; `rebuilt` requires an inspectable
`buildRecord` path whose bytes are hashed. The declaration and record identity
are preserved as an **operator declaration**, not independent proof that the
historical operation occurred. A rebuild producing the known digest can be
accepted with that explicit declaration/record; a different digest is recorded
as different but is not admitted for this task's force capture. A new artifact
requires a separate parent decision and receipt.

`native-provenance.test.mjs` covers actual alternate selections without using them
for force/cadence claims. A test-only library is the known parent bytes plus a
non-executable UTF-8 trailer, preserving its executable code and ABI while giving
it a different file digest. The real fixture selects that override, while the
conventional target digest differs; independent wrong-file attribution fails.
The real unmodified default loader also chooses an exact-platform package over a
different override in an isolated copy of the host sources. The installed checkout
platform symlink is untouched; the copied source hashes are retained. These are
actual FFI/loader cases, not a replacement resolver implementation.

Additional cases cover known bytes with unknown origin, wrong declared reuse
identity, alternate-byte rejection for this capture, claimed ABI mismatch, and
explicit reuse/copy/rebuild declaration validation. Scripted rebuild records are
plainly labelled test-only: **no rebuild occurred in those tests**. The retained
`native-provenance-cases-admitted.json` contains paths/digests/results and the precise
parent-plus-trailer construction recipe, avoiding duplicate full native binaries.
Temporary case paths can be reproduced with the tests; they are not shipping assets.

## Real browser captures and scope

The latest real captures are `raw/unheld/` and `raw/held/`. They keep the original
1k ring + deterministic chord topology, 2k edges, seed 7, Rust-seeded CoSE defaults,
401 authored ticks, omitted default 10-tick chunking and 30 s wall limit, width
720 / height 480 and legend disabled. No position/mask/pin/LOD override was added.
Rust produces the buffers; the normal shared WebGL painter presents visible
Canvas2D pixels. Two rAFs precede readback and real GPU node-hit readiness probing.
The unheld consumer automatically accepts after those evidence probes; held
inspection remains entirely separate. Trusted real pointer UUID/pan, synthetic
click trust rejection, cancellation and disposal observations remain in the raw
records. Source snapshots, payloads, screenshots and worker observations are bound
by exact hashes.

Fresh environment and observations, including exact executable/CPU/native/client
identities and all presented frames, are recorded in the raw JSON. Selected native
origin is **unknown**, ABI 399, with a matching known-parent digest; this attests
selection now, not in the historical captures. Startup, pixel/GPU probing, PNG
encoding and native attestation overhead are included in their stated clocks.

Node checkpoint arrival uses host performance time from `/start`; visible-frame,
GPU and ACK times use page performance time from `beginGraph`; startup and pointer/
pan observations use the runner clock. No cross-clock subtraction is performed.
Paint is an observation upper bound after two rAFs/readback, not scanout timing.
These fresh observations are **not compared as an optimization experiment** with
older captures or preparatory runs. No numerical performance acceptance is invented.

`observations.json` summarizes only the latest actual captures. If they contain
only steps 1 and 401, their one interval is not sustained progressive cadence;
scripted UPDATE coverage does not fill that evidence gap. Initial GPU readiness
is not unheld initial trusted input. Trusted initial pick/pan remains held,
and trusted final interaction is outside unheld cadence. The larger rendered
ladder, public browser progressive attachment/scheduling, Python notebook/widget
delivery plus rerender/dispose cancellation, and explicit resolution of literal
async `composeGraphForge` wording all remain open. No #35/#36/#108/M4, competitor,
scale, release, PyPI or npm qualification follows.

Preparatory successful captures remain under `raw/provisional-*` and
`raw/pre-admission-*`, with the exact then-current helper/test sources in
`source-snapshots/`. They were followed by stronger provenance admission and
ACK-observer regression checks. An archive assertion was corrected to compare
frame identities rather than post-ACK timestamps added after held snapshots.
No preparatory measurement was rewritten or promoted into a performance comparison.
The initial native-platform test stopped at an existing package-symlink guard;
its raw failure, cases and exact source are in `failed-attempts/`. No installed
package or production resolver was changed to make it pass. The preservation
helper initially mislocated root-level `AGENTS.md`; its raw failure and exact
source are retained, and the corrected lookup verifies the same recorded digest
without a waiver or changed historical file. A subsequent resource check
initially assumed every raw observer record was a WORKER event; NATIVE records
have a different shape. Its failure/source are retained and the corrected check
requires known audit types and balances only WORKER resources. Raw `workerAudit`
retains both observer record types; `nativeProducerObservations` selects NATIVE
records explicitly. No observed data was discarded or rewritten.

## Reproduce current runners

From this checkout, use the existing Node 22 and repository Playwright workflow:

```bash
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
# Platform package still wins if installed: inspect reported selected path/hash.
# This repair's force captures admit only the known parent native digest above.
node spec/performance/graph-node-first-paint-1k-review-repair-2026-11-04/run.mjs
node spec/performance/graph-node-first-paint-1k-review-repair-2026-11-04/inspection.mjs
node --test spec/performance/graph-node-first-paint-1k-review-repair-2026-11-04/*.test.mjs
node --test spec/performance/graph-node-first-paint-1k-2026-11-04/protocol.test.mjs spec/performance/graph-node-first-paint-1k-2026-11-04/verify-receipt.test.mjs
```

Runners default to new timestamped directories under `target/task-tmp/`, refusing
existing outputs; `XYG_NODE_PAINT_OUTPUT` and `XYG_NODE_INSPECTION_OUTPUT` may select
new directories. Do not write reruns into archived receipts. Override/platform
selection is attested, never assumed. The pure provenance tests may inspect other
valid ABI-matching bytes, but actual force captures fail closed on a different
digest. Use explicit origin/build records when asserting an operation history.

Current four design documents link here and mark old runners historical. Official
API inventory regeneration is provenance/body-hash only; capability generation
and checks leave capability facts unchanged. All 685 review gaps, contracts,
classifications and unaccepted preparation freeze remain unchanged. `checks.json`
and adjacent raw command records contain final required check outcomes.

Parent owns a **new completed independent review of the final diff**, pre-push
hooks, push/PR body update, replies and resolution of both P2 threads. This child
performs no GitHub writes, push or PR update and does not mark either thread
resolved. Earlier c3d2 review is not approval of this repair. A suggested body
update is saved locally as `PR-BODY.md` for parent use.
