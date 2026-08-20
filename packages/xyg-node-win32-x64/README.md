# `@curatelabs/xyg-node-win32-x64`

Exact-platform optional dependency of [`@curatelabs/xyg-node`](../xy-node).
Ships only `xyg_core.dll` for **win32/x64**.

Release packaging copies the built cdylib next to `index.js`. Source checkouts
may leave the binary absent; the Node facade then falls back to
`XYG_NATIVE_LIB` or a local `cargo build` artifact — never system library paths.

Windows arm64 is intentionally unsupported (#52).

See GitHub #52 and `spec/design/host-parity.md` §0.
