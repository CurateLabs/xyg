# Issued domain-member allocation recovery

This extends the existing [membership adapter](geo-overview-members-hosts.md)
through the [Rust allocation receipt](geo-allocation-recovery.md). Rust45/46,
source predicates, original-row paging, all five revisions and XYOMv1 are
unchanged. It adds no chart constructor, numeric policy, quota or ABI signature.

`frame.members` and issued `page.nextPage` capture an allocation attempt before
45 dispatch: original producer callables, complete private parent receipt,
immutable256-byte header plus24-byte payload, and a per-authentic-parent command45
nonce. The header sequence is the parent publication; the payload sequence is
the new membership operation.47 always uses the latter. Allocation replay uses
identical request bytes. A validated birth receipt is cached before Confirm;
lost Confirm retries47, not45. No Query read, supply or46 occurs until Confirm
settles. Resolved malformed replies and uncertain transport errors keep the guard.

After uncertainty, `error.owner.recover(signal?)` in TypeScript/Node and
`recover()` / `recover_async()` in Python continue exact admission, bounded I/O
and known46 publication to an owned Page. Async recovery is single flight across
the complete operation, not merely allocation. Closing admission prevents a
second recovery/publication. Disposal settles callbacks and outstanding tickets,
waits for publication/read, and drops packet views before authoritative disposal.
Python waits through repeated outer cancellation. Admission coalesces phase
acceptance as well as allocation. Recovery delivery is tracked per shared flight:
one cancelled waiter cannot dispose a Page delivered to another waiter. When all
waiters cancel, the final waiter closes the unreturned Page after the full task
settles; failed cleanup retains the explicit owner guard. A callback still in flight
keeps its loan until exact ACK8; cancellation does not erase a pending cookie.

One unresolved operation per parent blocks a higher nonce. Terminal capacity or
framing rejection does not manufacture an owner. Retired22 confirms a birth
with target0 and releases it; it never restores a Query or invents a handle.
A lost successful Query10 can be confirmed by the private historical birth and
then released with47 action2. Action1 Forget is allowed only after genuine parent
disposal, independently of view-drop. The helper retains retry state through
rejected/lost cleanup acknowledgements. A confirmed46 conversion releases the
Query birth; the owned MemberData remains independently alive and supports its
original private continuation after every original producer has been disposed.

Retirement of45 is **not** proof that the converted MemberData was disposed.
MemberData10 requires its own exact successful fixed reply. A lost-successful
MemberData10 remains a known cleanup guard; arbitrary bridge errors, error
messages and generic WASM stale statuses do not establish absence. No automatic
retry of46 or resurrection of a consumed birth is added.

No source-sized arrays or masks are introduced. Each active attempt retains one
bounded280-byte request and fixed256-byte receipt/control framing. Existing
128MiB processor,384MiB derived,16 handles,8 sessions/8 Data and two owning23
reads remain unchanged. The Page retains the original packet and existing one
bounded inspection copy. A failed Page issuer-Forget keeps a known-disposed
phase and retries that notification without repeating10. Application-retained
inspection views remain caller-owned and must be dropped before disposal.

Proofs include actual native/WASM lost and corrupt45, lost successful Confirm,
exact replay after parent and continuation-page disposal, Query10 uncertainty,
ReleaseBirth rejection retry, full recovery singleflight and callback/ACK close
ordering. Existing signed MIN/MAX, Point/MultiPoint physical-row semantics,
fullu64 IDs, byte parity and8-Data pressure controls remain required. These are
bounded membership proofs. Selected overview membership, public accessibility
UI, lost-successful MemberData10 recovery and massive interactive latency are
separate M6 acceptance gates.
