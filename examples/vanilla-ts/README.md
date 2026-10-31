# Node / vanilla TypeScript consumer

Use Node 22.13+ with the root build dependencies and `packages/xy-node`
dependencies installed. Build the native core, client and WASM assets first:

```bash
cargo build --release
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
npm run build:wasm
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node examples/vanilla-ts/server.mjs
```

Open the printed loopback URL (port 3000 by default; override with `PORT`). The
Node host compiles four chart families using the public Node Figure API. The
vanilla TypeScript browser mounts the shared painter, reads local Worker/WASM
assets, observes browser selection, and explicitly destroys views on replacement
and disposal. Updates replace the full view; shared streaming tests cover
incremental append separately. No Python process or web framework is needed by
this consumer. Runtime TypeScript stripping is provided by Node; check types with:

```bash
node node_modules/typescript/bin/tsc --noEmit --skipLibCheck --target ES2022 --module ESNext --moduleResolution bundler --lib ES2022,DOM examples/vanilla-ts/app.ts
```

The server is a bounded synthetic-data example, bound to loopback. JSON carries
specification metadata only; numerical columns move in the binary response.

The browser gate also stages and packs the Node facade, exact-platform native
package and browser client, installs their archives into a clean directory, and
runs this server with `XYG_CONSUMER_INSTALL` pointing at that install. The host
then resolves the installed package exports and assets rather than source paths;
no development native override is set.

The independent `graphforge-live.mjs` fixture uses one
`GraphForgeLayoutController` with the asynchronous default live payload API.
It serves local painter assets and raw binary checkpoints from a four-node
GraphForge property graph. Its acceptance handshake lets the functional browser
runner inspect initial/final pixels, GPU picks and pan before acknowledging each
presentation. Run the reproducible proof from
`spec/performance/graph-node-scheduling-35-2026-10-31/README.md`; no WASM build is
needed for this native/painter journey. It replaces the whole view, with the same
viewport reset limitation as this example; it is not a retained graph controller.
