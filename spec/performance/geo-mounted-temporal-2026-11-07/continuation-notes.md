# Root continuation findings (2026-11-07)

The saved failed draft is not accepted. Its known races are implementation work,
not an external blocker. Preserve the failure record and patch unchanged.

Authoritative source7e720104 is clean. Native artifact compiled in this worktree
matches b93f21b8f19799897566a5447279f0a79729b7814c0391db302cd31a050a31bd.
Root has no product edits here. Root force cancellation repair0a85b8da has now
been independently approved and pushed toPR1113. Do not merge it merely to get
that unrelated helper; root owns final accepted-main integration.

## Specific requirements for the next implementation

- The draft resolves older temporal waiters as success before their actual
  outcome. Replace this with explicit supersession/rejection and one current
  authoritative completion; never call an unpainted candidate accepted.
- Do not post every controller notification and merely prune the waiter map.
  That leaves unbounded comm messages and copies. Coalesce same-turn changes,
  retain at most one active intent and one latest pending intent, and bound
  transmitted work. One invalidate-current control per active request can
  prevent stale CAS while the newest pending value stays at the native host.
  A bounded detach/invalidate opcode is an option, not a required framework.
- Distinguish source claim from observer subscription. Removing observers or
  setting closed cannot free the source claim while a mounted candidate or
  late intent can still publish. Release only after detach/drain ACK or actual
  native mount-release ACK. Failure retains retryable ownership.
- Closing before any ready mount must settle all idle/dispose waiters without
  waiting forever for ready. No temporal intent was sent, so no fake native ACK
  is needed. Closing after send requires real drain, including repeated caller
  cancellation and controller-initiated cleanup.
- Ready notifications must include/check the exact mount string. Native
  release/remount resets ready state and rejects/settles old-mount waiters.
  Old ready/completion messages cannot attach to a newer mount. Retain latest
  controller intent for a real new mount rather than replaying stale values.
- Python existing GeoWidget RPC is synchronous. Async native binding already
  executes canonical synchronous reads on a worker, but do not move every
  existing widget reader onto a new thread silently. If mounted binding enables
  executor RPC mode, capture the owning loop, cap queued request copies before
  copying, serialize source operations, drain worker ownership on cancellation,
  and order close after admitted native operations. adapter.close may block on
  a worker-held RLock; do not call it synchronously from the notebook loop in
  that case. A single bounded worker/chain is enough, not a parallel query pump.
- Node panel disposal must settle readiness and every pending completion,
  remove subscriptions and drain adapter.realmDestroyed after transport. Reload
  must create a new readiness generation and preserve bounded binding intent.
  A failed postMessage is observable and retryable; no waiter is left pending.
- Browser time/camera races require an explicit ordering contract. Preserve
  each ordered pan; don't reset to template camera or silently discard deltas.
  An obsolete temporal-only prepare must abort before CAS. For camera requests,
  preserve authored order and final latest time; if retry/rebase is used, make
  its revision/operation rules explicit and don't rewrite caller revisions
  silently. Use the existing single native prepare/CAS/retire lane, not a
  second renderer or source query authority.
- Claim exclusion must be shared with snapshot GeoTemporalBinding. Test both
  bind orders, close during pending read, detach ACK failure/retry, and rebinding.
- Use one shared binary framing fixture across Python/Node/browser, exact i64
  times and u64 source identity. Real Jupyter + packaged native Node/webview
  journeys must prove pixels/picks/camera/last-good state and owner cleanup.
  Mock control tests are necessary but not the final mounted acceptance.
