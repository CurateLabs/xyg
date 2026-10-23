# Bounded spill evidence after I/O failure repair

These [Python](python.json) and [Node](node.json) reports measure the working
tree over `fdf7a374fa6d59f331050f4cf80b100f0d154a9c`, including the tile-store
I/O repair. Their native library SHA256 and producer/harness hashes identify
the measured bytes; the base commit alone does not. The reports are schema 1
bounded host evidence, not candidate qualification or a 100M/billion result.
Earlier reports in the parent directory remain historical and unchanged.

Both hosts again transfer 2 tiles / 143,272 bytes rather than the fetch-all
56 tiles / 3,737,056 bytes. Their 32 compose oracles and 32 keyed painter
frames pass. Both report 475 hits, 5 misses, 1,311,200 resident bytes under
the 2,097,152-byte CPU budget, 7,606,272 spilled bytes, at most 2 descriptors,
and at most 133,128 GPU bytes under the 524,288-byte R8 texture budget.
Canonical input arrays remain in RAM; this fixture does not claim mapped or
larger-than-RAM source storage. Timings are advisory and were collected while
other validation was active, so they do not establish a comparative speedup.

The independently pinned report validator passes both reports with source and
native identity checks. The new Rust negative fixtures separately prove failed
read cleanup, dirty-source retention on failed writeback, retry correctness,
generation invalidation on partial append, and spill-file cleanup. Python and
Node fixtures cover the shared process budget and count/mean-color goldens;
Python additionally covers predicate bypass and lazy colored-store rebuild.
See [the testing contract](../../../design/tier3-testing.md) for exact limits,
including the lack of a checksum for same-length bit corruption.

```bash
cargo build --release
uv run python benchmarks/bench_tier3_pyramid.py > target/tier3-python.json
node benchmarks/bench_tier3_pyramid_node.mjs > target/tier3-node.json
uv run python scripts/verify_tier3_pyramid_report.py target/tier3-python.json \
  --check-local --native target/release/libxyg_core.so
uv run python scripts/verify_tier3_pyramid_report.py target/tier3-node.json \
  --check-local --native target/release/libxyg_core.so
```

Use the platform's native library name on macOS/Windows. Source identity checks
must be run against the measured source revision; later changes appropriately
fail `--check-local`. The dedicated colored-spill authority, real browser
continuity and competitive evidence remain separate #11 requirements.
