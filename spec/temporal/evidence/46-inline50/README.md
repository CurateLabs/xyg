# Temporal catalog unchanged-cap packaging qualification

This successor to `1e585261d40d3113d7f41e7b739cd5b254cc7723` keeps the
six-family compiler and native artifact unchanged. It changes only the wasm32
LLVM inlining threshold from 100 to 50, retaining O3, toolchain, dependencies,
optimizer, exports, validation and the 1,927,168 raw / 786,432 gzip6 byte caps.
The original failed candidate and receipt in `../46/` remain unchanged.

The original optimized module is reproducibly recovered from its archived raw
module using the pinned optimizer. It is exactly SHA256
`18337bf17ea649bba23e99a8f045917cf85addc05575780f55ca7cac0b1dce4d`,
1,942,827 raw / 793,095 Node 22 gzip6 bytes. The successor is
`82e32ff4c9d67433d1af4c54b6643c130fcfc49951b78b77fc0df5af81922169`,
1,886,204 raw / 771,728 gzip6 bytes: 40,964 / 14,704 bytes of headroom.
All 69 export names and kinds remain identical. The native ABI402 library
remains `8f1b7a544bdefab946099fbeab11e658e73c1262381113637baa7e131c561aa5`.

The new normal foundation proof uses public binary framing, the actual
packaged Worker, Rust Scene preparation and the existing ChartView painter.
For each of event/interval/Gantt/line/bar/scatter it checks exact request and
complete Scene hashes against native oracles, actual source-colored painted
pixels, exact u64 identity metadata, and disposal. The normal Node tests
independently verify the same native oracle fixture. This is not a trusted
pointer pick, temporal playback, accessibility or dense-LOD qualification.

The existing ABBA harness covers GraphForge composition, geographic Scene,
viewport, catalog and interaction at 100, 10,000 and 100,000 source rows.
Every admitted result is byte-identical; 100k interaction retains the exact
status-3 `XYG_GEO_RESOURCE_LIMIT` refusal. All samples, including slower
cases, are retained. Timing ratios range around parity on this shared VM,
with other agents building concurrently. No speed or competitor win follows.
The profile harness's artifact gzip field uses its own compression setting;
the package gate and measurements above explicitly use Node 22 gzip level 6.

Reproduce with Rust 1.96, Node 22.23.4, the repository dependencies and short
disk-backed `TMPDIR=/var/tmp` (the VM's `/tmp` quota is exhausted):

```sh
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
export TMPDIR=/var/tmp
CARGO_BUILD_JOBS=2 npm run build:wasm
node scripts/temporal_catalog_wasm_parity.mjs packages/xy-client/dist/xyg-wasm.wasm
node --test packages/xy-node/test/temporal-catalog.test.mjs
XYG_WASM_FOUNDATION_REPORT="$PWD/target/temporal-foundation.json" node scripts/wasm_foundation_smoke.mjs
uv run pytest -q tests/test_temporal_catalog.py tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py
uv run python scripts/verify_wasm_assets.py
uv run python scripts/gen_abi_manifest.py --check
```

For ABBA replay, decompress `before-optimized.wasm.gz` to a task directory and
each entry in `profile-input-archives.json` to its indicated relative path
under a new input directory. Verify decoded lengths/hashes from that manifest,
then run:

```sh
node benchmarks/bench_wasm_profiles.mjs target/before-optimized.wasm packages/xy-client/dist/xyg-wasm.wasm target/profile-inputs target/profile-abba.json
```

`checks.json` records exact command outcomes, environment, source/artifact
hashes and archived/raw logs. `profile-inputs.json` binds the retained input
files; the copied Arrow fixtures and old optimized module have their own
archives for replay. `current-bindings.json` extends the prior Core provenance
chain; historical producers and receipts are preserved. A genuine Git CRLF
checkout tests the pinned bytes rather than merely normalizing hashes.

The first root cargo invocation returned exit 1 despite a final compiler
"Finished" line; it receives no success credit. A subsequent complete npm
build/package invocation exited 0. The first ABBA launch omitted the native
path and failed; its corrected run is retained separately. Initial catalog
packaging/quota failures remain failures. Native builds and the original
84 Python/22 Node/six offline HTML results remain original producer evidence;
the successor records its fresh checks separately.

This is a bounded candidate, not #46, M5 or milestones 4–7 completion. Dense
LOD, complete membership, controller/transport attachment, exact live picks,
streaming, customization, timezones/DST, keyboard/assistive journeys, full
hosts and scale/competitor evidence remain outstanding. Current-main union,
independent final review and delivery are still required.
