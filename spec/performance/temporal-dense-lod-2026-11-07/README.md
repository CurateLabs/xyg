# Dense temporal composition candidate

Parent: c4f16778fd2551c439a6883daf0e9891f9b2fc11. Prepared checkout only;
no root artifacts, issue state, PRs or publication are changed.

The XYTM v2 implementation and exact resource/coverage contract are documented
in `spec/design/temporal-catalog.md`. Public Python, Node and browser composition
methods invoke the existing native/WASM compiler and ordinary Scene painter.
Canonical source IDs remain exact and queryable in bounded pages; lattice IDs
are explicitly aggregate IDs. This is partial progress on #46, not issue or
milestone closure. Retained source memory remains data-sized; admitted 100k
fixtures fit, a 1M working set refuses. No massive FPS or competitor claim.

Reproduce with TMPDIR=/var/tmp, Node 22.23.4, Rust 1.96.0 and the repository's
pinned Binaryen 132 O3/function-name-order/strip-debug producer:

```
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so uv run pytest tests/test_temporal_catalog.py -q
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so node --test packages/xy-node/test/temporal-catalog.test.mjs
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so node scripts/temporal_catalog_wasm_parity.mjs target/wasm32-unknown-unknown/release/xyg_wasm.wasm
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/wasm_foundation_smoke.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

When reusing the prepared environment's editable installation, set
`PYTHONPATH=$PWD/python` explicitly. The pytest conftest already selects the
checkout's Python source. The root checkout's old ABI403 library was never used.

Fresh and inherited evidence are distinct: the original six-family fixture
hashes, ABI405 native declarations and WASM38 exports are inherited contracts;
new source is freshly rebuilt and checked against them. Logs retain initial
failures as failures. No historical receipt or generated declaration is edited.
The successor Core bindings preserve the predecessor pointer and compressed
exact predecessor files; the original IPC producer/manifest stay unchanged.

Remaining acceptance includes cooperative scan cancellation/chunked retained
Rust source, source-language object residency qualification, brush/controller
binding, tables/accessibility/reduced motion, streaming, richer customization,
100M+/out-of-core evidence, competitor comparisons, five-view applications and
the full installed-host matrix. Root owns independent review, integration,
current-main checks, PR/CI and queue delivery.

Root notified this worker of Greptile's PR1116 P1: the inherited direct line
compiler culls support vertices outside the viewport. Root owns that repair;
this candidate does not duplicate it. Integration of its reviewed clipping
behavior into dense line envelopes is a remaining requirement. The newer
root proof-only base `da1f500b` is not this candidate's runtime producer.

Large raw HTML/Scene/wire captures are preserved as gzip archives; the original
raw byte lengths/hashes and exact archive mapping are in
`raw-capture-archives.json`. Restore any original path with
`gzip -dc <archivePath> > <rawPath>` before replaying a captured HTML file.
