# Native/actual-WASM paged hierarchy protocol proof

`scripts/geo_hierarchy_conformance.mjs` exercises real native C ABI and the
fresh standard wasm32 artifact using the existing thin Node bridge and typed
common headers. Commands37–41/replies17–19/tickets are test-only raw framing,
not a new public host driver. Rust owns all geometry, counts, bins, filtering,
selection rejection, authentication, admission and publication.

```sh
npm ci
npm ci --prefix packages/xy-node
cargo build -p xyg-core --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
XYG_HIERARCHY_REPORT=spec/performance/geo-hierarchy-protocol-2026-10-09/native-wasm.json \
node scripts/geo_hierarchy_conformance.mjs
```

The native filename is platform-specific; use the canonical platform library on
Linux/Windows. `environment.json` records source/compiler/config identities;
`native-wasm.json` records artifact/native/script hashes, sizes and34 exact
packet hashes. The artifact gate passed unchanged:1,399,920B raw and572,663B
gzip against1,441,792B/589,824B caps. No compiler/profile/budget change was made.

Sixteen direct Scene cases span Point/MultiPoint, All/Instant/Window with signed
MIN/MAX and null endpoints, duplicate full-u64 IDs, null geometry and4326/3857
cameras with pitch0/60. Each hierarchy Scene is also byte-compared with a fresh
canonical source Scene through Rust. Two source-row packets remain exact after
query owner changes. Dense32769-Point and16385-MultiPoint fixtures prove actual
two-pass reduced Scene parity and complete original-row membership: every
4096-row page and final singleton is compared, including MultiPoint row dedup,
source order and literal feature IDs after source/index/query disposal.

Only operation-owner handle bytes16..24 are normalized for cross-module
packet comparison. Membership packets additionally normalize their redundant
owner field80..88 after the shared decoder verifies equality to field16.
Camera/time/source/revision, cursor, count, centroid, Scene, style and identity
bytes are retained. Source/hierarchy storage namespace is not normalized into
fake provenance; private tickets are authenticated separately in each module.

Failure controls exercise cancelled outstanding reads/writes with exact ACK,
forged namespace/serial rejection, two-copy write/Data quotas, malformed framing,
local budget rejection, corrupt authenticated pages, stale/reused revisions,
explicit work fallback without partial Data, old immutable retain/rows authority,
and real selected canonical state returning UnsupportedSelected. Rust unit
proofs additionally pin exact local-budget boundaries and one-byte-under
rejection, shared8session/16handle/8Data admission and broad frontier before
leaf reads. These are functionality/admission proofs, not timing measurements.

This does not prove browser paint, production callback/controller integration,
selected hierarchy folding, end-to-end interaction or1B latency. World fallback
is explicit and is not a final world Scene. Native release hierarchy timings
remain separate in `../geo-hierarchy-2026-10-09/README.md`; no performance ratio
is derived from this small conformance fixture.
