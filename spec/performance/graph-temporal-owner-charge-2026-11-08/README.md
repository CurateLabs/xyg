# Temporal composition owners in graph admission

Base: `b007e2d7cafac6d107d6bb409eac89f8a79ee4c9`.

Independent source review of combined checkpoint `78cf455a` found a P1: the
ordinary WASM graph adapter omitted already-issued XYTJ job retention from its
external charge. The reviewer parked twelve jobs in a16 MiB instance, then graph
work succeeded until even zero-byte staging refused. Root independently
reproduced that failure against the original shipping module, not only the
over-cap combined diagnostic module.

The shared graph adapter now adds the exact instance-owned jobs' retained source,
pending work and accepted Scene capacities through checked arithmetic. All graph
operations use that external charge before the existing Rust wire admission.
There is no byte-cap, default, ABI, physics, tier, feature, compiler or optimizer
change. Opaque unrelated active jobs retain their existing coexistence refusal.
Ordinary temporal commands remain unavailable while GraphSession is open; callers
close that session before explicitly reusing or closing its earlier temporal jobs.

## Bounded regression

The new native Rust test uses actual XYTJ/WASM-adapter commands and verifies
Open refusal at a deliberately constrained available budget, then graph
transaction refusal under retained-owner pressure. Graph positions, revision,
cached reply and foreign job ownership remain unchanged. Restoring the budget
permits the identical refused force request; graph close then permits actual job
cleanup. Removing only the production charge makes the final test fail.

`scripts/graph_temporal_owner_conformance.mjs` executes the shipping module.
Twelve parked15k-row jobs share a16 MiB instance with a real canonical1k peer
request. Cheap Open acknowledgement fits; Render refuses with graph budget-4.
The script checks zero-byte staging after every accepted or refused graph command, including thirteen real force requests. Resource refusal may occur at a different phase after legitimate memory improvements; it never permits overcommit. The complete opening retry remains unchanged.
Closing the graph and the actual temporal owners allows the identical Open/Render
sequence, whose full reply equals an independent unpressured instance. Foreign
jobs in that other instance are never charged to it. The exact final assertions
reject the pinned predecessor immediately after its accepted Render strands staging. This fixture never allocates100M/1B rows.
The normal full source foundation invokes the conformance script; its failures
propagate. Existing focused-density and staged-package exclusions remain explicit.

The first draft incorrectly required Open itself to refuse at the public16 MiB
pressure. Measurement showed ingress acknowledgement legitimately fits and Render
is the first operation needing the unavailable work envelope. Its failed run is
retained. The final invariant checks continued staging after each operation, opening
retry, foreign-owner cleanup and the full subsequent reply without freezing a
particular budget-refusal phase.

## Builds and provenance

Official native release and ordinary WASM packaging passed. The standalone
corrected module is **1,895,754 raw /786,405 Node22 gzip6 bytes**, below unchanged
1,927,168 /786,432 caps with **27 gzip bytes spare**. Its SHA256 is
`08e3d5db67555b2e55d971a32589d04566505f311f7306510d70e5a78b7b8ab5`.
Native405/551 declarations and WASM38/68 function exports remain unchanged; there
are zero ambient imports. Native library SHA256 remains
`1ac386f0d7af618a757fb51cca883f0c409f3991c976f7a9df0562f69524d316`.
Only the WASM adapter input changes among the parent324 compiled/config inputs.

`checks.json` and successor bindings record exact sources, artifacts, commands,
logs, producer inputs and failures. Historical receipts remain byte-identical.
The final Rust crate run passed77 unit tests and five integration cases; the
actual native/shipping-WASM wire suite passed nine cases. Other executed checks
and their fresh/receipt distinctions are recorded separately.

## Reproduction

Use pinned Rust1.96 and Node22, an explicit current native library, matching
packaged assets, and disk-backed `TMPDIR=/var/tmp`.

```bash
cargo test -p xyg-wasm
cargo build --release
npm run build:wasm
node scripts/graph_temporal_owner_conformance.mjs
XYG_NATIVE_LIB=/path/to/libxyg_core.so node --test packages/xy-node/test/graph-session-wire.test.mjs
XYG_CHROMIUM=/path/to/chromium XYG_NATIVE_LIB=/path/to/libxyg_core.so node scripts/wasm_foundation_smoke.mjs
```

The original command without Cargo's toolchain path failed before compilation.
Early native test drafts used an invalid Open revision and attempted ordinary
commands after graph acquisition; those setup failures remain separate from the
passing corrected test and final pre-fix negative. An exploratory temporal UI
draft was saved and removed before this correction; its client was restored from
verified parent archives. No UI draft or its artifacts are part of this repair.

## Remaining qualification

This is graph/temporal per-instance logical ownership admission, not total
allocator, process RSS, WASM linear-memory or GPU-budget qualification. The
reported linear-memory high water is a distinct diagnostic scope. Retained
filter/ordinary-operation and frozen-export coexistence, global budgets, all
hosts, scale, accessibility and competitor acceptance remain separate work.
The combined graph/dense source checkpoint still exceeds gzip by1,716 bytes and
has a separate module-fit continuation; this standalone passing package does not
qualify that future union. Both reviewer100k watchdog failures and earlier
startup/Worker/timer/antialiasing failures remain unresolved. Independent exact
correction review, current-main integration, hosted CI/queue and milestones4–7
remain open.
