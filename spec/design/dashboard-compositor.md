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

All shared ChartView and retained graph painter buffer/texture storage goes
through the host's object-identity ledger. It records requested buffer capacity
(including stream reallocation), RGBA8/R8 density and tile textures, integer
graph references, LUTs and picking. Aliases do not create allocations. Zero-byte
object counts include client programs, VAOs and FBOs; shader driver storage is
opaque. Shared quad storage and the grow-only RGBA canvas backing are charged
once to the host. Depth and stencil backing are disabled. Physical VRAM,
implementation padding, driver retirement and Canvas2D presentation storage are
not measured by this GPU logical-storage budget.

`applyDashboardResourceBudget(worker, budgetBytes, perChartBudgetBytes?)` and
`watchDashboardResourceBudget` apply hierarchical whole-chart admission using
the existing Rust XYDP planner. Where a per-chart cap is tighter than the
available global capacity, Rust first admits each whole chart against that cap,
then ranks eligible charts against the remaining global capacity. TypeScript
only maps these decisions back to the original exact snapshot.

Activation freezes allocation growth synchronously before sending a plan.
Allocations made before opt-in are reported in `beforeBytes`; activation is not
retroactive hard-budget compliance. After successful application, reservations
plus the shared backing fit the global budget. Each storage request must fit
its chart reservation **before** WebGL sees it, conservatively reserving both
old and new stores during replacement. Larger demand is reported for a fresh
Rust plan and the chart is suspended. This prevents unbounded allocation while
the worker is delayed. A budget below existing grow-only shared backing fails
explicitly. A larger host backing requires enough budget for that backing plus
all outstanding chart reservations before canvas growth can occur.

Eviction quiesces the existing context-loss lifecycle, deletes all client
objects (including unpublished partial builds), and retains canonical payload,
view and accessible DOM. The Canvas2D picture remains until a complete fresh
paint. Suspended charts cannot return stale picks. Active use updates Rust's
recency input even while suspended. Retention reuses the existing restore
lifecycle and schedules the current view again. Desired capacity is a
conservative high-water reservation until chart removal; it is deliberately
distinct from resident bytes. `storageSnapshot()` exposes resident requested
storage, object counts, shared bytes and context count, with opaque driver bytes
explicitly unknown. The registry protocol is v2 because old duplicate bundles
cannot satisfy this storage contract.

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
Child-frame governance evidence runs as a hosted Playwright page with its
explicit Rust/WASM tick sidecars on the same origin. Its two complete srcdoc
charts must reach their own governed/shared-host states in real time; the gate
does not depend on Chromium's dump-DOM virtual-time controller for workers.

Grow-only presentation evidence compares every alpha byte exactly before and
after host-buffer capacity changes and permits at most one least-significant
bit of per-channel RGB rasterization variance at high device-pixel ratios.
This is the measured Chromium GPU rounding boundary; arbitrary hue, opacity,
or geometry drift still fails. Once capacity is fixed, forward and reverse
client draw orders must reproduce the complete RGBA framebuffer byte-for-byte.

## Automatic admission coordination

A shared host can opt into continuous enforcement with
`ChartView.watchDashboardResourceBudget(worker, budgetBytes)`. The returned
controller performs an initial Rust `XYDP` plan, observes measured resource and
lifecycle changes on that host, and can be disposed independently of the
charts. Visibility transitions, active pick use, pick-target allocation and
eviction, client registration, and removal invalidate the current snapshot.

Notifications coalesce in a microtask and only one Rust plan may be in flight.
If state changes while Rust is planning, the coordinator schedules exactly one
fresh pass after the current bounded application finishes. This is lifecycle
coordination, not a second admission policy: TypeScript neither sorts resources
nor predicts retain bits, and every mutation still passes through the exact
snapshot check and Rust-returned residency vector. Invalid budgets fail before
a listener is installed; disposal removes the listener and prevents later
plans. The explicit one-shot application remains available for hosts that own
their scheduling.

## Current slice and remaining closure

The GPU spine now applies whole-chart eviction and pre-allocation capacity
reservations, rather than pick-only eviction. The focused hosted 32-chart
pressure test is `scripts/dashboard_gpu_smoke.mjs`; it checks an independent
GL-facing allocation oracle, hidden yield, active rebuild, refused capacity,
per-chart caps, context loss and teardown. Existing fixed-capacity RGBA and DPR
RGB/alpha assertions remain unchanged.

Issue #111 remains open: native CPU/source/WASM accounting and hierarchical
budgets, default budget selection, supported host parity and WebKit evidence,
representative mixed-scale/LOD/tile/graph/selection/ARIA pressure journeys and
interaction latency are not established by the small scatter pressure probe.
The issue's historical Reflex requirement conflicts with the current supported
consumer contract; it does not authorize a Reflex product surface. No competitor
performance win or full milestone closure is claimed.


### Admission ownership and watcher cancellation

Each accepted global/per-chart budget request captures one host admission
identity. Every Rust reply, retry and residency mutation validates that identity.
A superseded request rejects with `xy: dashboard admission was superseded` and
cannot restore its old budgets. Watchers retain the identity of their original
budget intent across automatic passes. A later request supersedes that watcher
and removes its subscription after rejection.

Watcher disposal immediately cancels its pending coordinator work. After each
asynchronous Rust stage, cancellation is checked before further commands or
residency application. A delayed reply cannot evict or rebuild charts after
disposal. Existing and future work uses the most recent admitted budget intent.
The normal 32-chart allocation oracle covers held real-WASM replies, different
global budgets, per-chart zero caps, cancelled per-chart plans and superseded
watcher notifications.
