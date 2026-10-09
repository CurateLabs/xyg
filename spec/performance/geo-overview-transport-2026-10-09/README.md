# Typed overview transport evidence

`conformance.json` records actual native Rust and optimized release WASM executions of the shared typed driver. `environment.json` binds transport sources, native library and the artifact-reuse proof; the existing overview artifact decision records release compiler/optimizer configuration. Engine/core/Cargo/config trees are identical to the native build source.

Reproduce from this source tree:

```sh
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
node js/package-wasm.mjs
node scripts/gen_geo_overview_wire.mjs --check
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
XYG_GEO_OVERVIEW_WASM="$PWD/packages/xy-client/dist/xyg-wasm.wasm" \
XYG_GEO_OVERVIEW_REPORT=/tmp/xyg-overview-conformance.json \
node scripts/geo_overview_conformance.mjs
```

Use the platform native-library suffix on Linux/Windows. Eight temporal cases compare whole count planes and Scene bytes; negative controls cover malformed framing, private ACKs after callback mutation, cancellation during an unsettled read and a delayed real terminal reply, owning Data disposal, explicit retry after a bridge rejection, retained frames after engine-owner disposal, two-copy quota and source-pick rejection. These are correctness/lifetime proofs; no browser paint, membership, Python overview host or large-data latency claim follows from them.
