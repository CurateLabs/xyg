# Snapshot-local overview recovery: bounded correctness evidence

The source baseline is helper986 `7f062ada5a34dfbd8da0558ddac8b9c1112f43eb`.
This slice changes Snapshot Rust6/7 and browser ownership, without ABI changes,
quota increases, another build profile, or chart/geometry policy. All200 compiler
input paths and hashes are recorded. The fresh native/WASM pair and full versions
are in `environment.json`; WASM is1,503,895 raw /616,946 gzip6 bytes, below the
unchanged1,507,328 /622,592 caps (3,433 raw bytes headroom).

`initial-red.txt` records actual opt-in6 rejection before implementation.
`engine.txt` records all1,474 safe-engine tests passing; `clippy.txt` records
strict engine lib/tests Clippy. Seven new Snapshot recovery cases cover complete
request identity, Confirm/two reads, nonce0 identity, eight snapshots, independent
issuer lifetime, both16-record limits, and older live Snapshot retirement through
history saturation. `native-wasm.json` and the separate parent
`independent-native-wasm.json` execute the actual paired binaries and compare the
frozen bytes, replay identity and lifecycle controls. These are small fixtures.

`browser.json` records real packaged Chrome155 under strict CSP: accepted-frame
binary/count/time identity, oldpaint barriers, lost/corrupt6 exact coalesced replay,
Confirm before read, lost3 and Release2 ACK retries, controller-close recovery,
public pending-table tampering, and genuine termination despite mutable disposed
and terminate decorations. It also preserves borrowed callbacks, source/index
independence, two-read/eight-Snapshot quotas, foreign producers and all six WASM
artifact formats remaining Unsupported. No external requests, page errors or CSP
violations occurred. The Worker outcome getter records original trusted delivery
before public wrappers and never grants authority from arbitrary public errors.

Reproduce from this exact input set:

```bash
npm ci
npm ci --prefix packages/xy-node
cargo build --release -p xyg-core -p xyg-wasm
cargo build --release --target wasm32-unknown-unknown -p xyg-wasm
node js/build.mjs
node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  node scripts/geo_snapshot_recovery_conformance.mjs
CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  node scripts/geo_overview_binary_smoke.mjs
cargo test -p xyg-engine --lib
cargo clippy -p xyg-engine --lib --tests -- -D warnings
```

XYGXv4 remains inert, temporally exact/data-domain/spatially nonfinal. No selected
overview, source-feature picking, browser artifact-format renderer, massive
interaction performance or complete M6/39 journey claim follows. Application-held
binary views and reply objects are application ownership; no GPU/OS heap bound is
asserted. The separate GeoScale35/36 Worker capture whitelist only provides
original outcome provenance; adoption/union-artifact proof is another slice.
