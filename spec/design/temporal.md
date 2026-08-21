# Temporal columns and interval indexes

**Status:** foundation locked for M5 (#43). Controllers are defined in
[temporal-controller.md](temporal-controller.md) (#44); the first identity-safe
graph filtering slice is defined in [temporal-graph.md](temporal-graph.md)
(Part of #45), while host timebar integration and compositions remain #45–#46.

**Authority:** design dossier §16 (time is i64 end-to-end). This document is the
host-neutral contract for canonical storage, Arrow ingest, and visibility
indexes. Playback UI and visual marks are out of scope here.

## Canonical representation

```text
TemporalColumn {
  values:    i64[]   // signed UTC microseconds since Unix epoch
  validity:  u8[]    // 0 = null, 1 = present (byte plane, not Arrow bitpack)
  timezone:  str     // required, non-empty UTF-8, ≤128 bytes, no NUL
  precision: enum    // source unit: second | millisecond | microsecond | nanosecond
}
```

- Product wire and ABI never carry temporal values as f64 milliseconds or JSON
  numbers.
- Pre-epoch (negative) values are first-class.
- Nanosecond inputs truncate toward zero to whole microseconds after range
  checks; other units multiply with checked overflow (`TemporalError::Overflow`).

## Arrow / host ingest

Hosts accept Arrow timestamp/date/time/duration buffers as tightly packed i64
planes plus an explicit validity plane, then call `xyg_temporal_column_create`
with a descriptor:

| Field | Meaning |
|---|---|
| `unit` | Source precision (0 s, 1 ms, 2 µs, 3 ns) |
| `timezone` | Required interpretive zone id (`UTC`, fixed offset, or IANA name) |
| `naive` | 0 = values already UTC instants; 1 = naive local civil times |
| `disambiguation` | 0 reject, 1 prefer-earlier, 2 prefer-later (folds only) |
| `dst_status` | Per-row 0 unique / 1 gap / 2 fold (required when `naive=1`) |
| `offset_seconds` / `fold_later_offset_seconds` | UTC offsets for unique/fold rows |

Timezone-aware Arrow timestamps are UTC-normalized by Arrow; hosts pass
`naive=0` and retain the timezone string as metadata. Naive local timestamps
require an explicit timezone and DST classification from the host (or a tz
helper). Gaps always fail (`DstGap`). Folds fail under reject, or resolve to the
earlier/later offset under the prefer policies.

## Half-open intervals

Intervals are `[start, end)`:

- Null start → unbounded past; null end → unbounded future.
- Finite `start >= end` fails at index build (`ReversedInterval`) before any
  visibility output.
- Visibility at instant `t`: `(start null || start ≤ t) && (end null || t < end)`.

Event filters use the same half-open rule over an optional `[range_start,
range_end)` window (`xyg_temporal_events_in_range`).

## Indexes and budgets

`IntervalIndex` copies endpoints into Rust, sorts a deterministic start order,
and emits host-owned `u8` visibility bitsets. Source columns are never mutated.
Queries accept a row `budget` and an optional cancel flag; over-budget work
returns `BudgetExceeded`, cooperative cancel returns `Cancelled`.

Documented soft ceiling: `IntervalIndex::MAX_ROWS = 50_000_000`.

## Stable ABI errors

| Code | Name |
|---:|---|
| -1 | InvalidArgument |
| -2 | CapacityExceeded |
| -3 | Overflow |
| -4 | TimezoneRequired |
| -5 | DstGap |
| -6 | DstFold |
| -7 | ReversedInterval |
| -8 | StaleHandle |
| -9 | OutputCapacity |
| -10 | Cancelled |
| -11 | BudgetExceeded |
| -12 | UnitUnsupported |

## Host surfaces

- Python: `xyg._native.temporal_column_*` / `temporal_interval_*` /
  `temporal_events_in_range` (ctypes over the same cdylib).
- Node: `packages/xy-node/src/abi.js` `temporalColumn*` /
  `temporalInterval*` / `temporalEventsInRange` (koffi).
- Browser/WASM (#59): typed-memory must carry signed i64 micros + validity +
  timezone + precision without f64 ms conversion; TypeScript may own clocks but
  must submit revisioned commands to Rust for filtering policy (#44+).

## Wire

Temporal attachments travel as raw i64/u8 buffers beside JSON metadata (see
[wire-protocol.md](wire-protocol.md)). Never serialize temporal samples as JSON
numbers.

## Parity fixtures

Python and Node must produce byte-identical `values`, `validity`, `timezone`,
`precision`, and interval membership for the same Arrow-like fixtures, including
sub-millisecond micros that are not exactly representable as f64 milliseconds,
pre-epoch values, nulls, DST gap/fold outcomes, and reversed-interval failures.
