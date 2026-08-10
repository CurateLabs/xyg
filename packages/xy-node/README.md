# @xy/node

Thin Node.js bindings for the shared `xy_core` C ABI cdylib. Uses
[`koffi`](https://koffi.dev/) to load the same `libxy_core.so` as Python
`ctypes` — graph/Sankey layout and LOD decisions stay in Rust
(`spec/design/host-parity.md`).

## Setup

```bash
cargo build --release   # from repo root
cd packages/xy-node && npm ci && npm test
```

## Native library search order

1. `XY_NATIVE_LIB` (absolute path to `libxy_core.so`)
2. `../../target/release/libxy_core.so` (relative to this package)
3. `process.cwd()/target/release/libxy_core.so`

```bash
XY_NATIVE_LIB=/path/to/libxy_core.so npm test
XY_EXPECTED_ABI=51 npm test   # optional ABI golden override
```

## Exports

| Function | Role |
|---|---|
| `abiVersion()` | `xy_abi_version` |
| `graphLayout(layout, nNodes, sources, targets, opts?)` | one-shot layout → `{x, y}` |
| `graphForceCreate` / `graphForceTick` / `graphForceDestroy` | progressive force |
| `graphLodDecision` / `graphClusterAggregate` / `graphBuildRender` / `graphSampleEdges` / `graphBuildCsr` | LOD + render graph + CSR |
| `sankeyLayout` | Sankey placement when `xy_sankey_layout` is present |

Layout names match Python `_native.py`: `preset`, `grid`, `circle`, `force`,
`breadthfirst`, `auto`, `radial`, `concentric`; aliases `dagre` /
`hierarchical` → `breadthfirst`.
