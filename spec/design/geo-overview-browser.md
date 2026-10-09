# Browser temporal-domain overview controller

This design adds the explicit temporal-domain overview route to the existing
`XygGeographicChart` surface. It reuses issued typed overview owners, the retained
Worker painter and the shared Scene/DOM painter. Rust owns time predicates,
domain cells, camera projection, palette, counts and publication validation.
Dossier §17/§27/§28/§29/§34 applies. This route adds no source-feature picking,
Rows, domain membership, selected overview, final spatial refinement or massive
interactive performance claim.

## Public transport and chart route

`Worker.geoScaleBridge()` returns the same frozen source transport object issued
by that genuine Worker constructor. The issuer and captured native post/ready/
dispatch chain live in private WeakMaps/module closures. Public dispatch method
replacement, lookalike closures and colliding handles from another Worker do
not confer producer authority. The original backing Worker is checked again
following ready/queue waits before posting. A replaced backing Worker fails
closed. The existing source codecs/driver/immutable SceneData preparation are
available as lowlevel authoring transport; they add no chart/LOD/layout policy.

The browser chart entry is:

```ts
const chart = await XygGeographicChart.fromOverview({
  mode: 'temporal-domain-overview',
  el, worker, index, query, sequence,
  // Optional application-owned custom layer; no provider/network dependency.
  layer,
});
await chart.ready;
await chart.update(nextQuery, {sequence: nextSequence});
await chart.dispose();
```

The index is caller-owned. The controller owns only its independently issued
immutable frame and painter. Internal canonical publication does not assign that
owner to caller-owned `index.current`; public `index.update/current` behavior
remains unchanged. Disposing a caller current frame cannot release the controller
frame or its persistent Data credit. It verifies private index/bridge
provenance before query allocation and the returned frame's private bridge/index/query/publication
snapshot before preparation. Full camera/time/source/revision framing remains
explicit. Nonfinal temporal-exact/data-domain flags stay3; a domain ordinal0..255
never becomes a GeoLodKey or source feature ID.

## Publication, bounded storage and accessibility

At most16 accepted active+pending updates are serialized. Query authoring fields
are copied only under the existing Worker host credit and released after the
operation settles. One active query per Index is explicit. A second controller
using a busy Index receives a busy failure; there is no hidden retry or shared query queue. This
first public slice does not close five-view or massive interactive acceptance.

Current paint, companion and frame stay unchanged until the
new privately issued owner, retained painter and detached DOM candidate pass
validation. Ordinary and borrowed views use the same Rust buffers/shaders. Borrowed
`setPrepared`/`releasePrepared` methods are captured once at admission. A borrowed
`setPrepared` callback must fail before changing its accepted buffers; the shared
MapLibre custom layer provides that atomic handoff. The controller cannot roll
back an arbitrary callback that partly mutates external state before throwing.
Borrowed layers must release prepared CPU/GPU consumers before Data disposal.

The exact nonfinal Scene notice remains visible. A paged companion shows at most
32 of the fixed256 domain ordinals and their exact-u64 temporal vertex counts.
Its labeled focus controls describe domain cells, not selectable feature Rows.
Counts come from the private fixed2304B XYOV header/count snapshot, not mutable
public parser decorations. Before first acceptance the table is empty and paging
controls are disabled. Companion state commits with paint and preserves
focus/paging where possible. Observer errors cannot undo an accepted frame.

A failed preparation destroys only the candidate painter, drops its packet and
DOM references, then disposes its known Data owner. One pending retirement/
candidate cleanup owner blocks new allocation until exact disposal succeeds;
rejected cleanup promises may be retried explicitly. Closing aborts active work,
settles source/page callbacks and exact read/write ACKs, settles preparation,
releases painters before Data, and clears controller-owned DOM/callbacks.
The index, external immutable page store, source chunks and Worker remain
application-owned. Source chunks/pages must remain available for future queries.

Unknown confirmations for27/28/29 poison the typed issuer: no guessed numeric
owner, automatic allocation retry, fake absence or source-scan fallback is
allowed. Old published paint remains available. Durable allocation recovery is
an explicit remaining gate; this route does not claim a fully recoverable
Worker protocol. Existing128MiB source/384MiB derived,16/8/8 caps and the persistent
16MiB overview Data profile remain unchanged. Each queued query reserves4096B
within the Worker host FIFO before fixed-field authoring copies; digest length
is checked before copying and extra camera/time/query fields are not traversed.
The current Data credit covers its private bounded header, painter, ChartView
and companion count storage; the painter/snapshot specification gives the
worst-case profile proof. Returned summary copies belong to the application.
The512MiB scope remains live owned CPU bytes per WASM module, not OS RSS, committed
linear memory, GPU/DOM memory or arbitrary application input/copies.

## Required executable controls

* Public ESM bundle imports build a privately issued seed frame/index and paint
  through `fromOverview`, including full-u64 IDs/i64 temporal boundaries.
* Two actual Workers with colliding handles/different source digests reject a
  foreign index before query allocation; forged lookalikes and edited public/
  underlying dispatch methods cannot redirect an issuer.
* Actual strict-CSP Worker painting matches the existing ordinary/borrowed GL
  pixel oracle; no provider, network request or second renderer is introduced.
* A changed time/camera/revision commits paint and accessible domain counts
  together. Failed/unknown candidate preparation preserves the prior pair.
* Pre-abort, pending source/page callback, pending ACK/preparation, repeated
  cancellation, observer errors,16-update overflow and retryable disposal retain
  ownership until settlement, with bounded DOM and explicit final cleanup.
* Focus/pager labels are truthful, and disposing removes owned DOM without
  destroying the application-owned Worker or borrowed canvas/context.

The small actual Worker/Chromium fixture is
[`geo_overview_controller_smoke.mjs`](../../scripts/geo_overview_controller_smoke.mjs),
using only the public ESM bundle imports. Its ordinary and borrowed WebGL2
domain-cell oracle is `[55,155,255,255]`; it preserves the prior painter/count
table on page, borrowed handoff and uncertain allocation failures, and waits for
callback loans before closing. Source/Index/caller current-frame disposal,
mutated public dispatch and parser decorations, initial unpublished counts,
bounded focus/paging and retryable borrowed cleanup are executable controls.
No timing comparison or massive claim follows from this fixture. Static/native six-format export and inert XYGXv4
metadata remain defined by `geo-overview-painter-snapshot.md`; native public composition
and final geographic issue closure are separate gates. The browser controller
returns a copied summary; an accepted-frame browser export wrapper is not part
of this paint slice. Existing native frozen export and raw Worker mode6 remain
separately specified.

Actual small-fixture evidence, artifact/source hashes, commands and a visual
example are committed in [geo-overview-browser-2026-10-09](../performance/geo-overview-browser-2026-10-09/README.md).
This implementation checkpoint is pending PR integration; it does not mark
issue50, issue39 or M6 complete.
