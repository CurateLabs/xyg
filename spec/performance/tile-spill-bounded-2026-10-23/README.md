# Bounded tile-spill and pan-reuse evidence

This Linux x64 worktree run exercises the native ABI 395 tile store through
Python and Node. It is integration evidence for #10/#11, not an accepted
release candidate or a 100M/1B larger-than-RAM result.

Each host generates one million canonical rows, spills a 1024² count pyramid,
and checks 32 spilled compositions against its in-memory oracle. It frees the
in-memory pyramid before the 32-frame keyed pan sequence; the canonical input
columns remain in RAM. An independent fetch-all sequence must reproduce every
active tile hash and exposure. The configured 2 MiB tile-residency budget does
not include canonical columns, host arrays, process overhead, or GPU memory.

Both hosts transferred **2 tiles / 143,272 reply bytes**, compared with
**56 tiles / 3,737,056 bytes** when fetching every frame's active tiles. Both
reported 475 hits, 5 misses, 1,311,200 resident bytes, and 7,606,272 spilled
bytes, with identical oracle results and no over-budget flag. Reply sizes
include binary framing and tile descriptors. These counters establish reuse
for this deterministic fixture only.

[Python raw results](python.json), [Node raw results](node.json), and
[environment and hashes](environment.json) retain advisory timings, commands,
the native binary hash, and relevant source/harness hashes. The artifact was
built from the worktree over the recorded base commit; the base commit alone
does not identify the changed source. Python uses NumPy's default linear
percentile interpolation; Node uses nearest rank. Their reported p95 values
are not a comparative latency claim.

These reports retain their original host-source hashes. A later Node host
viewport/control repair has a separate
[bounded Node rerun](../density-tile-cache-2026-10-23/review-followup/node-bounded.json)
and [current source provenance](../density-tile-cache-2026-10-23/review-followup/validation-provenance.json).
That rerun preserves the same transfer, residency, and oracle results; it is
still bounded correctness evidence with advisory timings.

The [I/O-repair follow-up](io-followup/README.md) retains schema-1 reports
with raw samples and per-report native/source identity, checked by the
independently pinned bounded-report verifier. It supersedes neither these
historical measurements nor the outstanding dedicated scale requirements.

Reproduce from a checkout containing this change:

```bash
cargo build --release
npm ci --prefix packages/xy-node
uv run python benchmarks/bench_tier3_pyramid.py
node benchmarks/bench_tier3_pyramid_node.mjs
```

The existing CI jobs run these scripts. Every call must return CPU tile
residency within budget, at most 256 descriptors, and the Rust-defined
eight-screen texture budget for the actual pixel format. Physical texture
allocation and visual parity require the separate real-browser tile smoke.
Remaining corrupt-I/O, host, scheduled-performance, 100M colored memmap,
competitive, and final candidate requirements remain under
[the #11 acceptance mapping](../../design/tier3-testing.md#remaining-11-acceptance).
