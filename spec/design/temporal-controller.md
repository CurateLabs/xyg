# TemporalController and linked-view protocol

**Status:** locked for M5 (#44). Graph timebar (#45) and compositions (#46)
consume this contract.

**Authority:** [temporal.md](temporal.md) for canonical i64 micros; this document
for lifecycle-safe scrubbing, playback, and opt-in coordination.

## Ownership

| Concern | Owner |
|---|---|
| Range / cursor / window validation, revision, dispose, stale/self-echo rejection | Rust (`xyg-engine::temporal_controller`) |
| Playback clocks, keyboard, focus chrome, reduced-motion preference read | Host (Python / Node / browser TypeScript) |
| Scene / filter application of range+cursor | Rust (later consumers under #45/#46) |

Browser TypeScript may own `requestAnimationFrame` clocks and accessible
controls, but it **must** submit revisioned commands to native/WASM Rust rather
than reimplement coordination policy.

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
reaching a bound with loop off pauses playback.

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

`apply_event` rules:

- Wrong / zero group → no-op (false).
- `source_instance == self` → `SelfEcho` (−15).
- `revision <= last_seen[source]` → `StaleRevision` (−14).
- Success updates range/cursor/window **without** bumping local revision or
  emitting outbound (no echo storms).

## Accessibility (host obligations)

- Keyboard: arrow / Home / End map to `step` / domain extremes; Space toggles
  play/pause when reduced motion is off.
- Focus: the time scrubber exposes a single tab stop with a live summary of
  cursor and selected range (host-formatted from i64 micros).
- Reduced motion: honor OS/user preference via `set_reduced_motion(true)` before
  autoplay.

## Wire

Coordination events travel as typed i64/u64 fields beside JSON metadata —
never as JSON numbers for temporal samples ([wire-protocol.md](wire-protocol.md)).

## Error codes (extends #43)

| Code | Name |
|---:|---|
| −13 | Disposed |
| −14 | StaleRevision |
| −15 | SelfEcho |
