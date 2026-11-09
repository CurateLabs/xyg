# Geographic temporal drain retry and notification ingress repair

Repair parent: `2c67a5638265ed6881d6aa50ea466b860cd2195f`.
The independent complete mounted-host review found a failed drain-retry send
cleared the blocked flag, causing subsequent cleanup to wait forever, and
foreign-thread controller notifications queued one copied snapshot per event
before coalescing. Both block parent delivery. This receipt covers their
correction, not whole#50/#39/M6 or milestones4–7 completion.

A failed operation4 send now restores blocked/error state when an active
correlation remains, wakes waiters and propagates the failure. Another explicit
cleanup retries the same mount/request/generation. Successful delivery alone
does not release source exclusion; only matching drain or actual release does.
A reentrant confirmed drain is preserved even if the send subsequently raises.

The same foreign-thread queue defect was independently reproduced on snapshot
bindings: a real1000-update burst retained1000 callbacks. Both Python binding
paths now use one private notification inbox, one copied pending native state
and one queued owning-loop wakeup. No bound callback stores a separate state
argument. Owner-loop updates consume/replace older nonterminal pending input.
Terminal state takes precedence over late nonterminal snapshots. Enqueue
failure resets admission, and detach clears input and rejects later arrivals.
The inbox has no permanent bound-parent callback or new native owner.
Geometry, eligibility, membership and revision policy remain in Rust.

Final regressions cover repeated failed retry delivery, subsequent real drain
correlation, no early source release and rebinding;1000 real foreign-thread
native updates for cursor/range and mounted/snapshot modes; latest owner-loop
ordering and actual retained Data time identity; terminal precedence; recovery
after failed wakeup enqueue; and reentrant drain acknowledgement plus delivery
exception. Native fixture revisions are normalized to leave room for real
snapshot updates; the generic wire fixture intentionally uses max-u64 values.

The original production module is process-only loaded for negative controls,
with the exact parent source/hash archived. No source swapping, native rebuild
or artifact replacement is used. Old failure captures and the initial abandoned
implementation remain immutable. Development assertion failures are retained
separately: an initial test compared the legitimately changing invalidation
flag, a mock initially treated close messages as temporal attachments, and the
first snapshot extension used the generic max-revision wire fixture. Those
attempts receive no qualification credit. Final new assertions and exact
parent-source negatives are recorded separately.

The previously reviewed72Node, packaged direct/aggregate browser and actual
VSCode paths are unchanged source/artifact evidence, not freshly repeated by
this Python repair. Actual Jupyter/Python3.11 and both Python runtimes must
qualify the final inbox. Existing C ABI401/native and browser assets are reused
only after digest/source verification; no ABI, cap, timeout, pipeline or pixel
tolerance changes. Current-main/combined-ABI integration, independent exact
correction review, hosted CI and merge queue remain parent delivery gates.
Indexed/hierarchy/overview/mixed-tile automation, full attributed exports,
accessibility, massive/five-view resources and competitors remain open.

## Fresh final-source evidence

The shared correction passes105 lifecycle/controller/native-identity tests on
CPython3.12.15 and105 on actual CPython3.11.17. The exact parent production
module passes nine cases and fails12: repeated retry-delivery settlement, both
binding kinds' cursor/range queue bounds and latest owner ordering, and both
binding kinds' terminal precedence. Wakeup failure recovery and reentrant ACK
controls pass on both versions; they preserve surrounding behavior. No source
file is swapped to run the old-code control.

Actual JupyterLab/anywidget, using the verified unchanged client and native
ABI401, passes native time/camera replacement, foreign-thread dispatch, failed
read retention, rebinding, caller survival and release. Phase pixels are47/0/47;
page errors are empty and native release is acknowledged. Existing color/GL
warnings are retained rather than hidden. The42-case Core/inventory/ownership
check includes real Git CRLF conversion across283 current sources and44
historical bindings. Binary archives/images remain -text; only previously
unpinned norm documents receive additional LF pins. Native/C ABI/245 Rust
inputs and six runtime/declaration assets match the parent. Public API contracts
and all686 preparation gaps are unchanged; inventory refresh records source
provenance only. Final type/naming/hook results are separate bound logs.
