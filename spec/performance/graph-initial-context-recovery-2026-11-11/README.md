# Retained graph initial context recovery

Source parent: `56efd4fb654b617c99ab80fecfe1b4cbd2af6fd0`.

A real context loss before the first Worker publication caused the graph painter
to reject readiness. The controller then disposed its only GLHost client before
the shared host's 250 ms replacement timer could run. Its accepted paint was
still null, so the ordinary accepted-frame restoration callback could not help.
The read-only diagnosis reproduces this mechanism under explicit loss; its
natural narrow run passes. The original broader failure has no GL trace and
therefore does not establish why that context became unavailable.

The painter now distinguishes a transient lost namespace from admission,
capacity and protocol refusal. Before its first accepted publication, the
controller retains its native owner while awaiting the real shared-host restore
callback. It then renders current Rust state with a fresh operation sequence.
The original temporal intent checks suppress superseded membership. Snapshot,
companion, camera and publication still change only after successful complete
paint; no unpainted candidate becomes accepted restore state.

Disposal and terminal Worker errors cancel the waiter immediately. A recovery
wait uses the existing generated 30-second scheduler wall-limit constant;
expiry rejects readiness and drains the owner. Hard failures and admission
refusals retain their previous behavior. Later accepted publications retain the
existing repaint/refusal path. Rust, native/WASM ABI, budgets, defaults,
optimizer and package caps are unchanged.

## Functional proof

`scripts/graph_initial_context_smoke.mjs` runs through the normal source
foundation gate. Real module Workers exercise temporal and ordinary startup,
two successive lost namespaces, loss during the texture-capacity query, newer temporal intent while awaiting recovery,
disposal and same-Worker reuse, Worker failure, the actual deadline callback,
and malformed GPU bytes coincident with loss. A lost-context null texture
limit is recognized before the ordinary capacity check; genuine capacity
refusals remain hard errors. Successful initial publications
must paint nonblank pixels and preserve exact membership; failed/cancelled
startup publishes nothing. All Workers are retired in every successful test.
The same final assertions reject the archived parent client at the first lost
startup. Deadline injection invokes the real callback without changing the
production constant or waiting 30 seconds.

The original aggregate fixture additionally exposes its pending handle for
these lifetime controls; its normal default authoring, membership and export
oracles are preserved. No caller-provided publication replaces Rust output.
The density specification also clarifies the prior review's P3: the outer
60-second foundation deadline covers ESM, while IIFE follows it with bounded
individual context waits.

`checks.json` records exact commands, exits, hashes, archived raw logs, reports,
source/runtime identities, development failures and inherited evidence. The
full-worktree hooks and Ruff commands remain mandatory before commit/push.
No benchmark or compiler-policy claim is made by this browser lifecycle repair.

## Limits

Historical startup/context-loss, Worker, timing and notebook failures remain
failures. A passing controlled recovery does not identify every spontaneous
loss, establish reliability, qualify whole images/AA, or complete global
CPU/GPU memory accounting. The parent independent readiness review's exact
focused run failed its retention assertion; diagnostic-copy success does not
supersede that failure. Its original full foundation attempt also failed later
at aggregate startup. No original failure is reclassified as a pass.

Massive-data filtering and global admission, reliable graph/notebook scale,
complete temporal table/brush/group/export workflows, all-host accessibility,
competitor evidence, final-head hosted CI and required merge queue remain open.
This continuation does not complete an issue or milestones 4–7.
