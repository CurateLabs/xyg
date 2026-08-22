# Shared-context dashboard compositor

**Status:** Phase 4 foundation; partial delivery of issue #111.

## Ownership

One document-scoped `GLHost` owns the browser WebGL2 context and immutable
shader objects. Each chart continues to own its canonical CPU columns, scene,
interaction state, accessible DOM, render targets, buffers, textures, and pick
attachments. TypeScript owns context execution, painting, picking, gestures,
visibility observation, DOM clipping, resize/DPR handling, and lifecycle.

Rust owns every decision that changes which chart-derived resources may remain
resident under a shared byte budget. A host may report measurements and apply
the returned retain/evict bits; it must not reproduce the ordering policy.
Eviction never discards canonical CPU columns or stable chart identity.

## Dashboard resource plan v1

The bounded `XYDP` v1 request contains a 32-byte header followed by at most
4,096 fixed 32-byte chart records. Each record carries a unique stable u64
chart ID, measured derived-resource bytes, a monotonic last-use value, and the
closed `visible`/`interacting` flag pair. Reserved bytes are zero. The global
budget and all byte fields are u64; malformed lengths, duplicate identities,
unknown flags, reserved data, or integer overflow fail closed.

The TypeScript boundary validates every complete resource record before it
allocates the packed request: the three u64 fields are `bigint`, the optional
flags are boolean, and sparse, array, null, or incomplete records fail closed.
Every dashboard-plan status exit consumes the per-instance staging arena,
including a zero sequence rejected before Rust decodes the request, so stale
request bytes cannot survive a lifecycle or validation rejection.

Rust admits whole chart resource sets. Interacting charts rank before other
visible charts, visible charts before hidden charts, more recently used charts
before older peers, and stable chart ID is the deterministic final tie-break.
An item that cannot fit is skipped so a smaller lower-ranked resource set may
use otherwise stranded capacity. The `XYDO` v1 response retains input order,
reports the exact admitted-byte total, and emits one closed `0|1` residency bit
per chart.

The plan governs rebuildable GPU buffers, textures, framebuffers, and related
derived caches. It does not claim that browser drivers expose exact physical
VRAM usage. Hosts account the bytes they request from WebGL and label those
figures as logical allocation diagnostics.

## Applied shared-context admission

The first applied resource class is each shared-host chart's lazily rebuilt
RGBA8 picking attachment. The browser reports its exact requested backing
bytes (`width * height * 4`), visibility, interaction activity, and monotonic
last-use value to the Rust `XYDP` planner. Last use advances on active picking
and hover/interaction independently of visibility observation, so using one of
two already-visible charts makes that chart the more recent admission candidate.
A returned `ChartView` exposes
`applyDashboardResourceBudget(worker, budgetBytes)`; its underlying
`applyWasmDashboardResourceBudget` boundary applies Rust's retain bits to all registered clients on that `GLHost` and
returns frozen logical `beforeBytes`/`afterBytes` diagnostics. An evicted pick
texture and framebuffer are deleted immediately; the next pick recreates them
from the unchanged canonical Scene while preserving source identity.

Planning is asynchronous, so application is conditional on an exact host
snapshot. Membership, byte size, visibility, interaction, or last-use drift
causes that result to be discarded without mutation. The public coordinator
may re-snapshot and re-plan at most three times to cross an ordinary render
transition; persistent churn returns `applied: false` without eviction. Client registration uses
host-local monotonic u64 identities, snapshot/application are capped at 4,096
clients, and removal invalidates any in-flight plan. TypeScript measures and
deletes WebGL allocations but does not rank clients or reinterpret Rust's
residency bits.

## Shared frame scheduling

Charts registered on one `GLHost` submit their next color paint to one
document animation-frame queue. The host coalesces at most one callback per
chart and executes the batch serially against the shared WebGL context; it
does not introduce a host-side priority or admission policy. Rust's dashboard
plan remains the only cross-chart resource-ranking decision. Per-chart input,
DOM chrome, accessibility, clipping, viewport, and DPR state remain isolated.

`GLHost.frameSnapshot()` exposes frozen logical scheduler diagnostics:
completed batch count, executed callback count, maximum batch width, and
currently pending charts. Client removal cancels its queued callback, and the
final client cancels the shared animation frame before releasing the context.
The strict-CSP direct-WASM evidence schedules two real views in one batch and
proves that destroying a queued view executes no GPU work.

## Current slice and remaining closure

The delivered foundation establishes the safe Rust policy, direct-WASM packed
boundary, explicit application to shared pick resources, and one shared frame
queue for multi-chart WebGL execution. It does not yet claim automatic
visibility-driven replanning, a public default budget setting, native
Python/Node orchestration, or the 30-chart acceptance evidence. Those remain
required before #111 can close: complete buffer/texture accounting, context-loss recovery, rapid
mount/unmount and leak coverage, per-chart accessibility/focus verification,
and Chromium/WebKit dashboard reports.
