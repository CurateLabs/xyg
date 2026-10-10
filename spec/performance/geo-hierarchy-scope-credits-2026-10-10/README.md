# Hierarchy local Scope credit repair

Engine-only correctness evidence; no host adoption, massive latency or milestone closure claim.
Base: `2f208f8f2fe896b65e2fa330efd9d1c7e6d04dfd`.

The failing authentic protocol fixture observed zero local-budget difference
when a nonce33 receipt grew by79,992 bytes. Complete Scope accounting now uses
the existing receipt/admission helper, includes each distinct State Arc once,
and preserves conservative hierarchy session/result reservations. Selected
local admission is intentionally stricter; ordinary unselected38/39 policy and
all successful wire layouts remain unchanged.

Three focused tests cover exact command43/44 local success and one-byte-under
failure, same-Arc exclusion, newer10,000-ID intent plus nonce receipt alongside
old Data, unchanged State/query/history on failure, and complete ledger drop
recovery. Existing hierarchy fixtures include nonce0 canonical/selected bytes,
Rows, cancellation/ACK and five-lane ownership. Independent source review and its three focused tests passed. Fresh release
native/WASM conformance passes direct/cluster/density, Point/MultiPoint, full IDs,
time, membership, Rows and disposal controls. The test-only audit wrapper
validates every Data-read packet issuer against its genuine creation request and
publication sequence against the creation reply, then retains complete packets.
All84 native packets are exactly identical to a separate pinned baseline process:
no byte normalization is used in the before/after comparison. Existing native/WASM
conformance has its separately documented process-local owner normalization.
Full engine1,487 tests and strict all-target/all-feature workspace Clippy pass.
The package cap passes without configuration/profile changes.

```sh
cargo test -p xyg-engine scope_credits --lib
cargo test -p xyg-engine hierarchy_protocol_tests --lib
cargo clippy -p xyg-engine --lib --tests -- -D warnings
python3 scripts/verify_ownership.py
```

Production changes are limited to `scope_charge`: state-present calls share
`Scope::publication_retained_bytes`; no-state build/fork captures the existing
current Arc under admission lock, releases that lock, then uses the shared
receipt→admission lock policy and restores the excluded current State credit.
The registry serializes changes; no sparse-ID copy or new lease is allocated.

Release reproduction:

```sh
cargo build -p xyg-core --release
cargo build -p xyg-wasm --target wasm32-unknown-unknown --release
node js/build.mjs && node js/package-wasm.mjs
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \
XYG_SCOPE_PACKETS=/tmp/current-packets.json \
XYG_SELECTED_HIERARCHY_REPORT=/tmp/current-pair.json \
node scripts/geo_hierarchy_scope_credit_conformance.mjs
cargo test -p xyg-engine --lib
cargo clippy --workspace --all-targets --all-features -- -D warnings
```

For baseline proof, run the same command in a separate process with explicit
`XYG_NATIVE_LIB` and `XYG_SELECTED_HIERARCHY_WASM` pointing to the pinned old pair
in environment.json; write separate reports and compare complete packet JSON.
Application-owned packet evidence is bounded test output, not product cache.
No host adoption, selected edit gesture, linked mounted selection, massive
performance or M6 closure follows from this accounting repair.

Complete packet JSON is retained as deterministic gzip9/mtime0 files to bound
repository evidence size; decompression reproduces the complete raw JSON.
