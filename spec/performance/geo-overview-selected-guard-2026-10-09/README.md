# Temporal overview selected-input guard

Base `3cb13bb9a`; branch `feature/50-geographic-overview-selected-guard`.
This is a bounded authority repair, not final overview interaction evidence.

The source-only temporal index previously accepted privately selected SceneData
and discarded its sparse intent/profile/count authority. Command27 now returns
fixed code17 before a builder lease or source clone for both nonempty selection
and an empty selected profile. Rust inspects private selection/Scope ownership;
host `None` annotations cannot bypass it. Ordinary unselected input is unchanged.
The frame-aware TypeScript/Node `encodeGeoOverviewBuild` and Python
`builder_request` are internal encoders, because the existing raw numeric codec
cannot inspect frame intent before dispatch. They acquire no ownership, create
no asynchronous cancellation lifecycle and add no public chart constructor.

`conformance.json` records four actual native/WASM controls with complete raw
Unsupported receipts: full/empty IDs,4096-byte local-budget rejection, repeated
rejection, old packet/read quota, independently issued State reuse, forged host
`None`, zero typed dispatches and ordinary framing identity. IDs include MAX u64
and duplicate-ID union. `node-tests.txt` and `python-tests.txt` contain passing
outputs; Python also runs the six existing temporal lifecycle controls.

The Rust test asserts unchanged global processor credit during rejection and
final drop recovery, plus State/source-history survival. All six protocol tests,
strict engine/test Clippy and full workspace53 core/1436 engine/65 WASM/2
doctests passed (`workspace-tests.txt`, `clippy.txt`). `ordinary-conformance.json`
contains the eight established temporal cases; `validation.json` records exact
equality with the committed baseline's complete count/Scene hashes and lengths.
This proves ordinary None semantics, rather than a timing or performance claim.

Fresh release native and packaged wasm32 artifacts were built in this isolated
worktree. `environment.json` records absolute paths, toolchain/source hashes,
raw1,458,205 bytes, gzip6/mtime0 599,360 bytes and exact artifact hashes. Existing
O3/postlink/profile and1472KiB raw/608KiB gzip limits remain unchanged. The new
Node regression defaults to two native controls in npmtest; explicit
`XYG_GEO_OVERVIEW_WASM` enables all four paired controls and fails if that
requested artifact is missing. Both existing post-package CI lists provide the
artifact path; this adds no job. CI workflow verification, source ownership, TypeScript,
Python typing, full hooks and Ruff checks passed before handoff. GitHub exact-head
CI and integration remain pending.

Reproduce from this worktree:

```sh
uv sync --extra reflex --group dev
npm ci
npm ci --prefix packages/xy-node
node scripts/gen_geo_overview_wire.mjs --check
node js/build.mjs
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
node js/package-wasm.mjs
cargo test -p xyg-engine --lib geo_temporal_overview_protocol_tests
cargo test --workspace
cargo clippy -p xyg-engine --lib --tests -- -D warnings
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  XYG_GEO_OVERVIEW_WASM="$PWD/packages/xy-client/dist/xyg-wasm.wasm" \
  node --test packages/xy-node/test/geo-overview-selected.test.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  uv run pytest tests/test_geo_overview_selected.py tests/test_geo_overview.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  node scripts/geo_overview_conformance.mjs
make check-ci check-ownership
```

Linux uses the corresponding `.so`. Final overview browser paint, export and
exact domain-cell membership remain open. Counts remain temporal-exact,
data-domain and nonfinal; selected overview output, massive latency, automatic
linked-input routing and1B execution are not claimed. Issue50/M6 remain open.
