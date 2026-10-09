# Bounded overview domain-cell membership engine

This evidence supports the new pure Rust exact domain-cell membership API and
preserves legacy projected membership after extracting its bounded lifecycle.
It does **not** expose the new overview member API through native/WASM framing,
claim viewport visibility, or establish massive interaction latency.

The coherent implementation is `57299ec2c`; combined Rust source freeze is
`12c0d09636d389a3fb96b5ff197cc240093e88be`. `environment.json` records all four
normal dependency merges, owned source hashes, exact release artifact paths and
hashes. The later conformance script, CI invocation and evidence do not change
that Rust source. No ABI signatures, quotas, compiler profile, or artifact gate
were changed.

## Engine proof

`rust-overview.txt`: all26 overview foundation/protocol/member tests pass,
including nine new membership tests and the existing million-row external
sort/prefix tracer. The nine new tests cover literal All/Instant/Window signed
extrema/null endpoint goldens, Point/MultiPoint in both source CRSs, all256 Point
cells, duplicate full-u64 IDs, source-order private continuations, source/index
owner disposal, row-atomic work limits, local one-byte/global admission pressure,
owning ticket drop/ACK, corrupted input, count reconciliation and final
cancellation. The million-row tracer is existing overview construction evidence;
it is not a new membership latency measurement.

`rust-legacy-membership.txt`: all six unchanged projected membership tests pass.
`clippy.txt`: strict engine lib/tests Clippy passes. Hooks, ownership457,
ownership-verifier tests, stale-name checking, CI verification and generated ABI/
WASM/host framing checks also pass.

## Native/WASM and pre-extraction control

`geo_overview_membership_engine_conformance.mjs` exercises the **existing**
projected membership product path through the extracted driver. Two canonical
nullable MultiPoint chunks each have seven rows and45,000 vertices. Explicit
null/empty rows, repeated u64MAX IDs, a >2^53 ID, high-bit IDs, null interval
endpoints and i64MIN/MAX are preserved. Five literal temporal profiles check
independent expected complete source-row lists. Rust builds a reduced frame;
Source disposal precedes membership pagination. The All profile spans three
pages. No JavaScript geometry, bin assignment, or count policy is implemented.

`current-packets.json` and `baseline-packets.json` retain **all12 full normalized
packets** as base64, literal typed row identities, both original native/WASM raw
packet hashes, and both exact artifact hashes. Strict typed parsing validates
owner, key/cursor binding, source ordinals and framing. Only the two repeated
process-local membership-session owner fields16..24 and80..88 are normalized,
after asserting they equal the authentic issued Member handle. Every other byte,
including the complete key, cursor, full IDs, sequence, counts and scan work
statistics, remains exact. Data handles are independently checked against the
mutation reply; mutation reply sourceHandle must equal the Member owner.

Both actual targets agree on all12 packets. A separate process using the
[pre-extraction painter artifact pair](../geo-overview-painter-snapshot-2026-10-09/README.md)
also agrees on all12 packets and complete row identities **before/after** the
extraction (`before-after.txt`). The old native hash is
`cd909fec769aaf34d230c8ab35a7bd1512006b1dbc8b04316e61b38f566d71dc`;
the old wasm32 hash is
`36a1ef20dba7bd161bef5d12b12674c383cbf854ea038c6c582c851737c67708`.
The baseline script uses the current thin mechanical host framing with these old
compatible binaries, rather than maintaining a second membership engine.

`legacy-native-wasm.txt` additionally records existing frame-lease conformance:
direct/reduced Scene and frozen snapshot bytes, full IDs, picking, Source disposal,
original rows, independent copy quotas, native six-format export and explicit
WASM raster-export rejection. `node-parity.txt` records the existing packaged
retained/frozen/indexed-row byte test. These establish legacy compatibility;
they do not imply transport proof for the new engine-only domain member API.

Fresh combined optimized WASM is1,468,284 bytes, gzip level6 is603,987 bytes
(level9 separately603,219). Its hash is
`f5c3cd1f86f35445bf72c445ddf603f6f85a3b4a5c6abe6b312209908f86c469`.
The native hash is
`11665749c798c80c4fbd7a6d18c03e064430c943530b2fc326090c89ed550e06`.
Packaging passes the unchanged1,507,328 raw/622,592 gzip6 gates. The raw/gzip
difference from the baseline includes approved combined dependencies; no
isolated size-benefit or speedup attribution is made.

## Reproduction

From the combined source on the matching platform:

```sh
cargo test -p xyg-engine geo_temporal_overview --lib
cargo test -p xyg-engine geo_membership_session --lib
cargo clippy -p xyg-engine --lib --tests -- -D warnings
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
node js/package-wasm.mjs
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib"
XYG_MEMBERSHIP_REPORT=current-packets.json node scripts/geo_overview_membership_engine_conformance.mjs
XYG_FRAME_LEASE_WASM="$PWD/packages/xy-client/dist/xyg-wasm.wasm" node scripts/geo_frame_leases_conformance.mjs
node --test packages/xy-node/test/geo-scale-wasm-parity.test.mjs
```

Use `.so` on Linux. The new script fails if a supplied artifact is missing. Its
CI invocation is in the existing direct-WASM paired-artifact block after fresh
core and package builds; baseline artifacts are not CI prerequisites. Supply
`XYG_MEMBERSHIP_WASM` and `XYG_NATIVE_LIB` pointing at the exact old artifacts to
reproduce `baseline-packets.json` in a separate process. Compare each pair's
`normalizedPackets` and `rows` with current JSON using strict deep equality;
original owner-handle-dependent `*RawSha256` values need not match.

Host dependencies and the Python tooling environment were borrowed through
ignored dependency directories; native and WASM artifacts were freshly built in
this worktree. Build/test elapsed times reflect uncontrolled development load,
not product latency. Canonical/external storage remains caller-owned. This engine
is a bounded linear authenticated scan, not a massive interactive index or
selected overview path. Commands45/46, public member adapters and issue50/39
closure remain separate gates.
