# Historical geographic allocation retirement

A confirmed newer allocation from the same issuer replaces its last receipt.
Previously, a lost10 reply for an older target then left no authenticated
retirement proof: replaying the older allocation was stale. This checkpoint
retains fixed16 private live/retired birth stamps until explicit acknowledgement.
Historical47 Confirm returns22 with no owner after the exact old phase dies;
ReleaseBirth action2 drops its confirmed retired stamp while preserving the
current receipt and nonce highwater. Lost ReleaseBirth ACK retries are
idempotent and authority-free. Legacy nonce0 and Forget1 behavior remain intact.

Eight focused Rust cases, all1467 engine tests and strict Clippy pass.
Verbatim build and Rust test logs with ANSI or trailing blank lines use
base64 JSON with SHA256, preserving the exact raw output. Independent
source review and actual native/WASM conformance are green. Six complete
normalized packet byte arrays are identical to the pre-extension981 baseline;
only the separately validated process-local output owner16..24 is masked.
Actual controls include newer nonce plus old lost10, wrong sequence/target,
known live/unconfirmed release rejection,16 unacknowledged retired births,
preflight before canonical mutation, release retry, parent death and five-view
sixteen-handle sameQuery publication. Existing51 Node native/WASM owner/member
cases,21 Python cases and the actual accepted-frame browser binary journey pass.
Public clients have not adopted this extension in this checkpoint.

The fresh pinned native4aa35fb4fd2513b6aa758a0680985da6f2f74dd7380bc23f8b6f2d7d770d4d3e
and WASMe0f09f8454242e82eaa1db36d1d4ae87e1726e7621f7eb1485c12641557c06f2
pair uses unchanged release/O3/inline100 settings. Raw1,494,781 and deterministic
gzip6mtime0 613,121 bytes pass unchanged limits; ABI383/WASM33,8192 control
credit,128MiB processor/384MiB derived pools,8 sessions/Data and16 handles do not
increase. Compiler input and source hashes are recorded. Retired stamps consume
one of the existing16 slots; missed release blocks new admission rather than
silently discarding recovery authority. Receipt/control leases remain charged
until both receipt and stamp banks empty.

The initial focused-test diagnostic is preserved. Earlier fixture cleanup
assumed automatic collection of retired births; the cases now explicitly
ReleaseBirth for historical allocations and preserve the original assertions.
The actual raw saturation fixture also removes its previously live stamped Data
before isolating16 retired births; a live birth counts toward the same bound.
No resource limit or acceptance assertion was weakened.

Reproduce:

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
XYG_NATIVE_LIB=target/release/libxyg_core.dylib node scripts/geo_allocation_recovery_conformance.mjs
XYG_GEO_OVERVIEW_WASM=packages/xy-client/dist/xyg-wasm.wasm node --test packages/xy-node/test/geo-overview-source.test.mjs packages/xy-node/test/geo-overview-members.test.mjs
uv run pytest tests/test_geo_overview_source.py tests/test_geo_overview_members.py -q
node scripts/geo_overview_binary_smoke.mjs
```

Use the platform's native filename and explicit `XYG_CHROMIUM` as needed.
Known45 Query retirement after46 is not evidence that its independent MemberData
was disposed; those are distinct phases. Public-host adoption,35/36 mutation
recovery, unknown snapshot6 recovery and massive latency remain separate gates.
