# Chunked camera publication and benchmark catalog correction

This bounded continuation repairs two actual hosted failures on PR1122 head
968c5588bf5a0d92d96ec983f272e7a06c408daa (run 42990711462). It does not
complete #110, public100k notebook acceptance, shipping, or milestones 4–7.

The native Python job failed the exact chunked row oracle: its 3,860 rows were
precisely the first wheel predicate, while the reported camera required the
second predicate's 2,653 rows. A controlled genuine native result reproduces the
mechanism: camera mutation happens before the queued view-change notification
advances the transmitted intent. A matching old intent could therefore paint
and ACK data for a different camera. The hosted schedule itself was not captured.

The shared client now copies the query's x/y ranges when transmitting each
intent, then compares those ranges with the current camera before staging GPU
resources. A mismatch uses the existing rejection/retirement path. The native
policy, frame tokens, original paint ACK, source membership, event cadence,
resource limits, timeouts, and accepted-picture behavior remain intact. No ABI
or protocol change is introduced; no mutable host state is used as query proof.

The required Python/Node browser regression delays a real first-wheel end and
holds its genuine native reply. It delivers that reply synchronously after the
second wheel changes the camera but before its queued event sends. Assertions
require an unchanged payload, trace objects, spec, exact canvas pixels, native
owner and zero paint ACKs or frame events, plus the normal rejection. Releasing
successor work then retains the original complete row, provenance and exact-pick
oracles. The identical assertions reject the immutable parent client for both
hosts. Ordinary non-delayed paths remain exercised too.

The Python3.11 floor job separately failed the benchmark catalog gate. The old
AST counter ignored parameterized fixtures. Actual pytest collection has 163
rows, including selection's existing 16 rows and the new tooltip (6) and
semantic validation (14) modules. The counter now follows shared/transitive
module-local fixtures once per test and handles test parameter overrides;
nonliteral fixture parameters refuse static counting. The methodology records
the actual nine-module catalog. No benchmark ID, measured workload or fixture
materialization changed, and no dashboard archive action was taken.

`checks.json` binds commands, raw/archive logs, browser reports/captures, source
history and matching artifacts. All 324 compiled inputs and native/WASM bytes
remain parent-exact; the browser client is freshly rebuilt. WASM caps/defaults
remain unchanged. Full foundation was attempted and FAILED at the packaged
density no-refinement probe with a lost GPU context, before later journeys.
That failure receives no full-foundation pass credit and does not establish a
reliability repair. Earlier public100k and GPU/startup failures remain open.

Independent final-diff review, final-head hosted checks and the required GitHub
merge queue remain delivery gates. Focused successes do not qualify complete
all-host, scale, accessibility, memory or competitor acceptance.
