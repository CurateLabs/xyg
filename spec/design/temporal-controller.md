# TemporalController and linked-view protocol

**Status:** native and direct-browser/WASM controller lifecycle, Part of #44.
Coordinated selection payloads remain required before #44 can close. Graph
timebar (#45) and compositions (#46) consume this contract.

**Authority:** [temporal.md](temporal.md) for canonical i64 micros; this document
for lifecycle-safe scrubbing, playback, and opt-in coordination.

## Ownership

| Concern | Owner |
|---|---|
| Range / cursor / window validation, revision, dispose, stale/self-echo rejection | Rust (`xyg-engine::temporal_controller`) |
| Playback clocks, keyboard, focus chrome, reduced-motion preference read | Host (Python / Node / browser TypeScript) |
| Scene / filter application of range+cursor | Rust (later consumers under #45/#46) |

Browser TypeScript owns a coalesced `requestAnimationFrame` clock and accessible
scrubber controls, but every state transition is a packed command to the same
Rust controller. The direct-browser seam uses `XYTC` commands and `XYTR`
snapshots with raw little-endian i64/u64 fields. JavaScript exposes those exact
values as `BigInt`; it never converts temporal state or revisions to JSON
numbers or duplicates range policy.

Python exposes an ergonomic, context-manageable ``xyg.TemporalController``
that owns the native handle and returns itself from range, cursor, playback,
rate, direction, loop, and reduced-motion state-changing commands.
The low-level Python and Node functions remain thin ABI projections for host
integrators. `XygWasmTemporalController` is the browser lifecycle wrapper: it
serializes commands, coalesces in-flight animation ticks, stops its clock and
DOM listeners on disposal, and emits typed coordination events for an explicit
caller transport.
Both native hosts validate exact integer widths and boolean types before the C
ABI call; oversized integers, unsafe JavaScript Numbers, and truthy substitutes
are rejected rather than wrapped or coerced.

## State (UTC microseconds)

```text
TemporalController {
  instance_id, group_id,     // group_id 0 = unlinked
  domain: [start, end),
  range:  [start, end),      // selected window
  cursor, window, step,
  direction ∈ {-1, +1},
  rate_milli,                // 1000 = 1.0× (integer ABI; no f64 on the wire)
  loop_enabled, playing, reduced_motion,
  revision, disposed
}
```

Selected ranges are half-open. `set_cursor` recenters `window` inside `domain`
when possible. `step` / `tick` respect direction, loop, and domain clamps;
reaching a bound with loop off pauses playback. `tick` reports true only when
the cursor actually moved; an already-clamped boundary tick returns false while
still stopping playback.

## Commands

`create`, `set_range`, `set_cursor`, `step`, `play`, `pause`, `set_rate_milli`,
`set_direction`, `set_loop`, `set_reduced_motion`, `tick(dt_micros)`,
`poll_event`, `apply_event`, `dispose`, `destroy`.

- **Reduced motion:** `play` is a no-op (playing stays false); explicit `step`
  and range/cursor changes remain available; `tick` never advances.
- **Dispose:** clears playing, drops outbound/pending remote state; further
  commands return `Disposed` (−13). `destroy` removes the handle.

## Coordination protocol

Opt-in only (`group_id != 0`). After a local mutation that changes range/cursor,
Rust queues one outbound event:

Normalized no-op `set_range`, `set_cursor`, and boundary `step` calls do not
increment the revision or emit an event.

```text
CoordinationEvent {
  group_id, source_instance, revision,
  range_start, range_end, cursor, window
}
```

Hosts either:

1. **Same process:** `xyg_temporal_coordinate_deliver` applies the event to every
   live peer in the group except the source; or
2. **Cross process / browser:** `poll_event` → transport → peer `apply_event`.

Same-process delivery visits peers in stable handle order and prevalidates every
eligible peer before applying to any. A malformed event or mixed-domain peer
therefore fails the delivery without partially updating the group; stale peers
are deterministic no-ops. The transport-level event shape (nonzero source and
revision, ordered range, contained cursor, and canonical window) is validated
before group membership, peer availability, self-echo, or stale-revision
filtering, so malformed events never become successful no-ops.

Every live controller in a nonzero exchange group must have a unique nonzero
`instance_id`. Creating a controller whose identity collides with another live
controller in that group fails with `InvalidArgument`; the identity becomes
reusable after the earlier controller is disposed or destroyed. Controllers
outside exchange groups (`group_id == 0`) do not participate in this uniqueness
constraint.

`apply_event` rules (after transport-shape validation):

- Wrong / zero group → no-op (false).
- `source_instance` and `revision` must both be nonzero.
- `source_instance == self` → `SelfEcho` (−15).
- `revision <= last_seen[source]` → `StaleRevision` (−14).
- The event range must remain inside the controller domain, the cursor must be
  inside that range, and `window` must be canonical: zero only for a
  single-instant range, otherwise exactly `range_end - range_start`.
- Success updates range/cursor/window **without** bumping local revision or
  emitting outbound (no echo storms).

This foundation coordinates temporal range/cursor state only. Selection-mask
payload coordination is deferred to the remaining #44 slice and is not implied
by either native ABI or packed WASM seam.

## Accessibility (host obligations)

- Keyboard: arrow / Home / End map to `step` / domain extremes; Space toggles
  play/pause when reduced motion is off.
- Focus: the time scrubber exposes a single tab stop with a live summary of
  cursor and selected range (host-formatted from i64 micros).
- Reduced motion: honor OS/user preference via `set_reduced_motion(true)` before
  autoplay. The browser wrapper reads `prefers-reduced-motion` by default and
  never starts automatic playback when Rust reports reduced motion.

`bindScrubber(element)` installs one focusable `role="slider"` surface. Arrow
keys step in the chosen direction, Home/End move to exact domain bounds, and
Space toggles playback. `aria-valuemin`, `aria-valuemax`, `aria-valuenow`, and
an overridable `aria-valuetext` formatter are refreshed from each Rust
snapshot. Unbinding or disposal removes the key listener.

## Wire

Coordination events travel as typed i64/u64 fields beside JSON metadata —
never as JSON numbers for temporal samples ([wire-protocol.md](wire-protocol.md)).

## Error codes (extends #43)

| Code | Name |
|---:|---|
| −13 | Disposed |
| −14 | StaleRevision |
| −15 | SelfEcho |
