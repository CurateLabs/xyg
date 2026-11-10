# Notebook graph selection ownership after external local writes

Greptile review of e3301fae found two independently reproduced P1s. With the
`select` interaction disabled, API clear reserved a deferred intent but never
sent its request; masks cleared while durable selection/brush/history remained
old. A newer linked range/polygon/clear also left pending Back/Forward alive,
allowing an older accepted native reply to replace the linked state and camera.

Clear now defers only when its request will actually be sent. Otherwise its
normal local durable/history change completes. Native graph transport exposes
one local supersession operation using the existing selection-sequence barrier:
it revokes queued predicates and cached masks while retaining the actual active
query correlation until its real reply arrives. Linked range/polygon/clear uses
that operation before local application. No forged completion, premature frame
release, native policy change or extra request history is introduced. Existing
API row/state ingress barriers and camera ownership tokens remain in place.
A history clear with disabled selection still completes its own synchronous
camera/history operation.

The regressions load actual mutation, history and linked BroadcastChannel
receiver methods; drawing and the channel carrier are the fixture boundary.
They cover both public API clear paths, linked range/polygon/clear versus held
navigation, frame refresh, queued intent invalidation, real-reply correlation
and disabled-select synchronous Back. The exact parent source control fails
all seven new cases while retaining all 35 earlier passes. An initial combined
Node invocation omitted the explicit native library; its setup failure receives
no wire-test credit. Corrected execution uses the pinned library.

Hosted run42827515646 also exposed an outdated source-contract marker for
`select_clear` and a chunked-browser test reading initial host rows before the
real paint ACK committed the new frame. The marker now requires the deferred
transport signature and both distinct clear/row event gates. The browser test
actually holds the native commit ACK, proves source ownership remains initial,
then releases it and waits for provenance generation matching the exact painted
frame before applying the unchanged full-scan and picking oracle. No product
chunked implementation or tolerance changes. Original failed hosted logs remain
archived. A missing disk TMPDIR initially prevented log download; disk-backed
retrieval succeeded.

Exact commands/exits, current and predecessor source identities, immutable
review findings, native/module/client pins, notebook captures and all failed
attempts are recorded in checks.json. Rust, ABI, Worker and module inputs remain
unchanged. The module stays 1,885,379 raw / 786,379 Node22 gzip6 bytes, 53 bytes
under the unchanged gzip cap. Earlier full-foundation context-loss failures are
retained and unresolved; no reliability fix or final full-green claim follows.

The independently exercised Notebook7 follow-up is saved separately and is not
part of this correction. Final independent review, final-head hosted checks and
the required main merge queue remain gates. Whole #1015/#36 and milestones4–7
remain incomplete for the previously recorded aggregate/categorical/changed-LOD,
frontend/export/accessibility, scale/competitor and global-budget acceptance.
