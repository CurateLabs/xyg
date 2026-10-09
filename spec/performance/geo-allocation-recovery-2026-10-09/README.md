# Geographic allocation recovery foundation

Raw opt-in Rust recovery proof, **not public-owner adoption**. Existing Python,
Node and browser overview/domain owners still send nonce0 and retain their
explicit unknown-allocation poison guards. No35/36 mutation recovery, browser
presentation or massive latency claim follows from this evidence.

The fresh native383/WASM33 pair uses unchanged O3 / target inline-threshold100
and existing optimizer. Raw1,496,127 and deterministic gzip6mtime0 613,427 bytes
pass unchanged1472KiB raw/608KiB gzip gates; no quota/profile/cap changes.
`environment.json` pins actual paths/hashes and reviewed source. `artifact-inputs`
pins all tracked Rust/Cargo/config inputs; incoming b4 dependency changed only a
wire generator and README after the builds, with no Rust/Cargo/config drift.

Six complete native/WASM count/Scene/XYOM packets compare byte-for-byte after
validating process-local output owner16..24 and normalizing **only that field**.
Full source/layer u64MAX, above2^53 IDs, signed-i64MIN time, temporal counts,
source-row/matched-vertex membership and every Scene byte remain unmasked.
Controls cover five live26 retains and five ready27 indices from one parent,
exact allocation and lost47-ACK replay, parent disposal, unconfirmed rejection,
completed29 retry after failed budget, publication at sixteen handles,28 phase
retirement,45→46 phase retirement and source/output lifetime, lost-original
retired target0 confirmation, and sixteen-receipt pressure/drop recovery.
Callbacks use bounded external page storage only for this small fixture.

Root independently ran the six Rust tests and actual paired conformance;
verbatim results are included. Full engine1465 tests and strict lib/tests
Clippy passed. Existing twelve projected-member packets (including raw hashes)
and eight ordinary overview count/Scene outputs are identical before/after
against the pinned pre-recovery be47/66e pair. Domain15-packet controls also pass.
There is no timing or competitor comparison: this changes ownership recovery,
not geometry or performance.

Reproduce from the source checkout:

```sh
cargo test -p xyg-engine allocation_recovery --lib
cargo test -p xyg-engine --lib
cargo clippy -p xyg-engine --lib --tests -- -D warnings
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
node js/package-wasm.mjs target/wasm32-unknown-unknown/release/xyg_wasm.wasm
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node scripts/geo_allocation_recovery_conformance.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node scripts/geo_overview_membership_engine_conformance.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node scripts/geo_overview_conformance.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node scripts/geo_overview_domain_members_conformance.mjs
```

`XYG_GEO_RECOVERY_WASM` overrides the explicit artifact path;
`XYG_GEO_RECOVERY_REPORT` retains full packet evidence. Missing supplied artifacts
fail, rather than skipping. Baseline processes used the exact absolute paths
under `t3code-m6-geooverviewmembershipprotocol` recorded by the earlier domain
slice, with `XYG_NATIVE_LIB` and the scripts' explicit WASM environment overrides.
No baseline artifact is required for the current paired conformance invocation.
