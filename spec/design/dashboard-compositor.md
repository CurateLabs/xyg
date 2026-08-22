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

## Current slice and remaining closure

This slice establishes the safe Rust policy and direct-WASM packed boundary.
It does not yet claim automatic `GLHost` eviction, a public budget setting,
native Python/Node orchestration, or the 30-chart acceptance evidence. Those
remain required before #111 can close: compositor application, byte-accounted
resource hooks, visibility-driven replanning, context-loss recovery, rapid
mount/unmount and leak coverage, per-chart accessibility/focus verification,
and Chromium/WebKit dashboard reports.
