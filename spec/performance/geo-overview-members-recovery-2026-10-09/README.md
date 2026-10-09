# Public domain-membership allocation recovery

Actual bounded native and real packaged WASM proofs for command45 exact replay
and47 confirmation. `source-sha256.json` pins the changed host/fixture contracts;
all199 Rust compiler inputs match the reviewed retirement donor. No Rust build,
ABI, quotas or geographic policy changed in this slice.

`node.txt` records118 tests (17 new recovery cases); `python.txt` records53
(8 new recovery cases, including a running notebook loop, gated async close,
cancelled/live and all-cancelled recovery waiters, and overlapping admission).
`recovered-packets.json` compares entire first-page XYOM packets after lost and
corrupt45, normalizing only process owner16..24. The existing membership tests
also compare complete multi-page walks; new continuation recovery keeps literal
physical rows and matching MultiPoint vertex counts after all original owners
have been disposed. These are correctness/lifetime proofs, not latency evidence.

```sh
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \
XYG_GEO_OVERVIEW_WASM=$PWD/packages/xy-client/dist/xyg-wasm.wasm \
XYG_GEO_MEMBERS_RECOVERY_REPORT=/tmp/recovered-packets.json \
node --test packages/xy-node/test/geo-overview-members-recovery.test.mjs \
  packages/xy-node/test/geo-overview-members.test.mjs \
  packages/xy-node/test/geo-overview-source.test.mjs \
  packages/xy-node/test/geo-overview-recovery.test.mjs
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib uv run pytest \
  tests/test_geo_overview_members_recovery.py tests/test_geo_overview_members.py \
  tests/test_geo_overview_source.py tests/test_geo_overview_recovery.py -q
node scripts/gen_geo_overview_hosts.mjs --check
node js/build.mjs
uv run ty check
```

Use the exact artifact hashes in `environment.json` or rebuild matching sources.
Client build regenerates ignored files; restore/repackage the reviewed WASM
before the real-WASM command. Generic lost-successful MemberData10 remains a
known cleanup guard. Selected membership, public accessibility UI, massive
interactive latency and full M6 host journeys are not claimed complete.

`shared-waiter-failing.txt` preserves the independently reproduced pre-repair
Page disposal failure. `shared-waiter-fixed.txt` records the same actual-native
reproduction passing after per-flight delivery ownership was repaired.

Captured logs retain their output and normalize line-ending trailing whitespace
for the repository whitespace gate. Original /tmp logs remain unchanged.
