# `@curatelabs/xyg-node-darwin-arm64`

Exact-platform optional dependency of [`@curatelabs/xyg-node`](../xy-node).
Ships only `libxyg_core.dylib` for **darwin/arm64**.

Release packaging copies the built cdylib next to `index.js`. Source checkouts
may leave the binary absent; the Node facade then falls back to
`XYG_NATIVE_LIB` or a local `cargo build` artifact — never system library paths.

Windows arm64 is intentionally unsupported (#52).

See GitHub #52 and `spec/design/host-parity.md` §0.
