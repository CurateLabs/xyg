# Live temporal controller to Scene presentation

Base: `bc040379720fc6a04f235d05de0cc947f3ebfba0`.

The public browser `TemporalComposition.attachController` path follows complete
Rust controller range/cursor snapshots through XYTM, cooperative Rust scanning,
canonical Scene, XYPB and the existing ChartView. A composition has one
presentation claim; the caller retains the controller and Worker. The binding
exposes accepted time metadata, the owned view, current error, attempt settlement,
explicit refresh and acknowledged disposal.

Six different chart families share the existing Worker scan lane. Source
preview, scan and painter preparation are one exclusive presentation
transaction. Pure dashboard plans share a reader group while excluding those
transactions. This prevents a later preview or plan from overtaking a deferred
painter request, while allowing a newer budget intent to finish before an older
delayed plan. Plan packets and counts are captured before queuing; their policy
and all residency decisions remain in Rust. Each binding retains one active
attempt and one latest primitive time state. Obsolete queued work checks its
revision before creating or copying packets.

A hidden, connected, inert candidate keeps its GLHost identity across resource
refusal. A complete GPU frame is required before swapping the accepted view and
time metadata. The previous picture remains available on source/preparation or
budget failure. Existing Rust admission can later readmit the retained candidate
without recompilation or a replacement identity. A refused attempt makes
`whenIdle()` reject promptly; it does not wait indefinitely for future resources.
`refresh()` retries that retained stage, or recompiles after an earlier failure.
Controller or composition disposal cancels and drains work and destroys stages
and accepted views. The controller, Worker and external scrubber remain owned by
the caller. The existing `bindScrubber` handles trusted keys and reduced motion.

## Evidence

The actual strict-CSP module-Worker harness exercises event, interval, Gantt,
line, bar and scatter compositions. For every accepted test state it compares
the complete Worker painter with native Rust output and compares every decoded
RGBA byte against the existing renderer consuming that independent host output.
It covers trusted Tab/ArrowRight focus, range/cursor updates, held real reply
supersession, zero-per-chart GPU refusal, stable pending identities, real
readmission, failed painter preparation and refresh, reduced motion, same-group
coordination without a new local revision, foreign-group rejection and cleanup.
Additional terminal-Worker controls preserve the old picture, settle existing
waiters and refuse later source commands. Error observers deliberately throw;
the page records no unhandled product errors.

The normal full source foundation invokes this harness. Focused density and
staged-package scopes retain their existing exclusions. No new workflow, cap,
default, native ABI, WASM export, compiler setting, renderer or tolerance is
introduced. Rust/module inputs remain base-exact; generated client bundles are
rebuilt and bound separately. Exact commands, logs, source/artifact identities,
preserved failed attempts and fresh-versus-inherited checks are in `checks.json`.

Development failures remain recorded. An early harness required all refreshes
to avoid compilation even when an unrelated plan had actually superseded a
source scan. Investigation then reproduced a stale Worker sequence during
initial presentation. The exclusive scan/painter transaction and cooperating
plan reader group fix that ordering, with a delayed-old-plan regression guarding
budget supersession. A later harness incorrectly expected immediate paint from
a refreshed view before asynchronous GPU readmission; the final assertions wait
for the real coordinator and accepted state, while preserving exact data/pixel
and identity checks. The first coordination probe used the wrong method name;
the public method is `applyEvent`. Initial ownership-ledger and inventory
preparation failures are retained separately. Early runs do not have immutable
per-run source snapshots and receive only the explicitly stated development
diagnostic credit; final source-bound controls provide qualification.

The shared-host batch passed nine runtime cases and failed its inherited
source-only guard, which still required the obsolete single-line alpha-only
Canvas2D context call. The updated guard requires transparent alpha and the
reviewed explicit accelerated-copy hint; the pixel/runtime assertions are
unchanged. The isolated final source guard passes. This is split evidence,
not a claimed fresh all-green ten-test invocation.

## Remaining acceptance

This is a live browser presentation continuation, not full #46/#38 or M5
acceptance. Manual membership/viewport operations are refused while attached;
canonical virtualized table and live pick/selection integration require an
accepted-publication lease rather than querying a newer compiled state. Brush
selection, complete cursor/window customization, streaming/update, frozen
bound-state export, installed-host parity, full accessibility, massive/five-view
performance and competitor evidence remain open. Raw Worker mutation APIs keep
their existing supersession semantics outside the cooperating presentation
lane. CPU/source/global memory accounting is not qualified by the screen-bounded
GPU path. Historical Worker/startup/watchdog failures remain unresolved. Final
independent review, hosted checks, merge queue and milestones 4–7 remain open.
