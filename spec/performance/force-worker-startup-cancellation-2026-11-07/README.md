# Force Worker startup cancellation

Implementation base: `7e720104f2d3f0508e6c93211980c09808f42bc6`.
Accepted main at preparation: `43c35f67b95ae4e78e3e96f200a0e6be8642199c`.
This repairs Node lifecycle scheduling only. Rust layout, native/WASM ABI,
resource caps, callback acceptance, wall deadline and cleanup grace are unchanged.

## Reproduction and mechanism

The catalog integration retained a failed full Node run: the native timeout
trace created a force handle, entered a tick and then emergency-terminated the
Worker without destruction. Passing later runs did not establish a fix.

The existing private lifecycle wrapper installs a message listener before the
scheduler's asynchronous native-module import completes. A startup cancellation
can therefore be delivered to that listener before the scheduler registers its
own cancellation handler. Its message is consumed, and the subsequently started
scheduler still allocates and ticks. A barrier-controlled native startup case
reproduces the same create/tick/emergency-exit/no-destroy pattern. This establishes
a startup mechanism, not that every historical timeout has this sole cause.
Ordinary emergency termination during a genuinely wedged native chunk retains
its documented weaker destruction guarantee.

A second controlled case cancels from a WorkerData structured-clone getter.
Previously cancellation saw no assigned Worker and settled immediately, while
the constructor continued creating a Worker without cancellation/exit ownership.
A post-create barrier separately proves cancellation before the first tick was
not observed while its port event remained queued.

The parent now latches cancellation in a private four-byte shared atomic flag
before sending its ordinary cancellation message. The same existing loop checks
that flag before native allocation and before each native chunk. Construction
reentrancy records the first failure and waits to install the actual Worker exit
listener before sending pending cancellation and starting the unchanged grace.
An already-created handle is destroyed in the existing `finally`; cancellation
before creation allocates none. Port messaging still rejects pending checkpoints.
No source/painter data or public diagnostics are added to the control flag.

## Regression and qualification

The existing seventeen lifecycle cases retain their allocated-handle, callback
and exit-order assertions. A timeout that expires before allocation now follows
an explicit zero-allocation branch requiring a cancellation receipt, clean real
exit, no tick/callback/termination and only then settlement. It cannot excuse a
created-but-undestroyed handle. Eight new cases
cover startup AbortSignal, startup wall expiry, structured-clone getter abort
and cancellation between create/tick, each with fake and actual native ABI.
Explicit shared-memory barriers control ordering without an assumed startup
speed. They require zero ticks/callbacks, zero handles for startup cancellation
or exactly one destroyed handle after create, a cancellation receipt, actual
exit before public settlement, and no emergency termination.

The exact new tests against the original scheduler produce **17 passes and eight
failures**. The repaired scheduler passes **all25**. All before/after raw traces
and source identities are archived; no failure is relabeled as a pass. The
250ms timeout fixture, default30s public wall budget, configurable300s ceiling
and1000ms emergency grace remain unchanged. No latency or competitor win follows.

Reproduction with Node22 and an explicitly selected source-matching native core:

```bash
TMPDIR=/var/tmp XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" \
  XYG_FORCE_LIFECYCLE_TRACE=1 node --test packages/xy-node/test/force-worker-lifecycle.test.mjs
TMPDIR=/var/tmp XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" \
  npm test --prefix packages/xy-node
uv run pytest -q tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py
python3 scripts/gen_abi_manifest.py --check
uv run python scripts/check_release_inventory.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Normal Node CI already invokes this test file. The successor Core binding
preserves every historical producer, adds this exact scheduler/spec/test source,
and exercises real Git LF/CRLF conversion. Source-matching native/client/WASM
artifacts are reused only after digest verification; no Rust/browser code changed.
Final independent review, source freshness, current-head CI and merge queue remain
parent delivery gates. This is not M4–M7, scale, memory, host, accessibility,
export or whole-issue acceptance.

The first complete Node run after the product repair passes1092 cases but fails
the old native-timeout assertion: its trace contains cancellation and clean
exit with **no allocation**, while that assertion always required one destroy.
The final test distinguishes this newly correct pre-allocation path explicitly;
all allocated-handle destruction requirements and deadlines remain intact. That
initial full-suite run remains failed evidence.

The final complete normal Node command passes **1093 tests**, with two existing
qualified skips and zero failures. The final Core/provenance/inventory batch
passes33 tests, including actual Git LF/CRLF conversion. Generated ABI and the
official preparation-inventory checker pass without regeneration. Shipping
native/WASM/client hashes match the reviewed parent; the nativeABI401 artifact
is explicitly selected for every host run. This repair changes no public
signature or shipping browser source. Full-worktree hooks and both Ruff gates
pass; final nonrecursive gate logs accompany the delivery manifest.
