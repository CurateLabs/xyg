# Exact overview domain membership protocol evidence

This functionality proof covers commands45/46 over immutable privately issued
overview authority. Seven raw Rust tests and five actual native/WASM temporal
profiles produce15 byte-identical complete XYOM packets. Packet normalization
removes only the independently validated process-local MemberData owner at16..24;
source digest/generation, full snapshot/time/revisions, full IDs, original rows,
chunk provenance, expected/cumulative/matched counts and all reserved bytes remain.
`packets.json` retains normalized complete bytes and SHA256 values.

The literal MultiPoint fixture has a duplicate coordinate in the first row and
source IDs UINT64_MAX,2^53+1,7, repeated across two authenticated canonical chunks.
Membership includes each original row once, with exact matching vertex counts.
All,InstantINT64_MIN,Instant0,Instant10,and Window[INT64_MIN,0) prove nullable
endpoints and half-open filtering. Core tests additionally cover continuation
following original Source/index/OverviewData disposal, forged cell/sequence,
eight sessions/eight combined Data pressure,16-handle same-handle publication,
corrupt read/private ACK/cancel settlement, and failure-atomic retry.

Publication46 is nonallocating: a lost successful receipt is resolved by exact6
at the known handle; Query completion21 differs from converted Data receipt0.
The allocating45 lost-reply recovery gate remains unresolved. This proof does
not expose a new Python/Node/browser host factory or claim massive latency.
Canonical external chunk storage remains caller owned. Membership is exact for
the immutable data-space cell, including offscreen rows; the overview remains
nonfinal and does not become exact screen-bin geometry or Scene source-picking.

Reproduce from this checkout (standard unchanged build/profile/package gates):

```sh
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
cargo test -p xyg-engine domain_members --lib
cargo test -p xyg-engine geo_membership --lib
cargo clippy -p xyg-engine --lib --tests -- -D warnings
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  XYG_GEO_DOMAIN_MEMBERS_REPORT=/tmp/domain-members.json \
  node scripts/geo_overview_domain_members_conformance.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  node scripts/geo_overview_membership_engine_conformance.mjs
```

The last command verifies unchanged legacy projected-membership full packets
through the shared driver. Linux CI uses the fresh `.so` instead of `.dylib`;
the new proof runs in the existing DirectWASM paired native block and uploads its
raw report in the existing artifact. Missing explicitly supplied artifacts fail.
The environment file pins the actual native/WASM paths, hashes and deterministic
compression levels, not a borrowed earlier build. ABI383/WASM33 remain unchanged.

The full engine suite passed1459/1459, strict library/test Clippy passed, and
required repository hooks/Ruff/ownership461/generated ABI/CI checks passed.
