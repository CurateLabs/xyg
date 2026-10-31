# S1 hierarchy functionality budget and packaged validation

This is a new packaging decision after the two retained failed receipts:
[S1 recovery](../graph-s1-recovery-2026-10-31/README.md) and
[four measured sharing candidates](../graph-s1-size-repair-2026-10-31/README.md).
Neither failed receipt is changed or reclassified. #36 and milestone 4 remain
incomplete; this is not a release cohort or performance acceptance.

## Decision and measured cost

The repository's artifact-size policy requires a deliberate, recorded decision
for functionality growth. Composition v2 adds reachable hierarchy UUID
resolution, forest validation and hidden-parent reattachment to the shared
native/WASM composition path. The session skeleton is not WASM-exported yet.

| Source | Optimized raw bytes | Node gzip6 bytes |
| --- | ---: | ---: |
| Validated combined graph base `465ec0a0` | 1,540,374 | 637,276 |
| Recovered S1 `8878a151` | 1,547,598 | 640,237 |
| Retained sharing repair `8daf6cfa` | 1,546,708 | 639,531 |
| Previous limits | 1,543,168 | 638,976 |
| S1 limits | **1,547,264 (1,511 KiB)** | **640,000 (625 KiB)** |
| Remaining headroom | **556** | **469** |

The sharing repair saves 890 raw / 706 gzip bytes. The net S1 cost over the
combined base is 6,334 / 2,255 bytes. The new gates are the smallest next-KiB
limits that admit the measured module; they reserve no capacity for later
interaction slices. Rust 1.96.0, O3/fat LTO/codegen1/strip, inline threshold
100, pinned Binaryen 132 and `-O3 --all-features` remain unchanged. No runtime
validation, feature, signature or dependency is removed. No speedup is claimed.

Independent policy/patch assessment (`m4_s1_size_policy_review`) recommended this
minimal pair after inspecting all four candidates and the shared resolver/memo
preservation boundary. It found no error-precedence, sentinel or linear-work
regression. Final S1 implementation review and CI remain separate requirements.

## Exact packaged result

On Node **22.23.4**, the real `node js/package-wasm.mjs` succeeds and writes the
manifest, inline payload, browser package copy and Python static copy.
The optimized module is byte-identical to the measured sharing candidate:

- 1,546,708 raw bytes; SHA-256
  `2feaf15adfe770d5ae2f879e38b7495ae3490cd73a79ad6dcc334a66ec0a32c7`.
- 639,531 gzip6 bytes; exact gzip SHA-256 is in [artifact.json](artifact.json).
- `verify_wasm_assets.py` passes paired copies, manifests, inline payload,
  and ABI/Scene/painter versions. Native ABI remains 396 / 529 symbols.

[source.json](source.json) hashes the tracked producer inputs and proves the
Rust inputs remain unchanged from `8daf6cfa`. It includes the new packager
hash. [results.json](results.json) binds the artifact, manifest, environment,
and raw/compressed log hashes. Generated modules and bundles are ignored,
not committed; reproduce them with the commands below.

## Verification

- Real packager and packaged asset verification: passed.
- Actual Node 22 native/WASM GraphForge and CoSE parity, cross-host fixtures,
  and Worker lifecycle: **51 passed, zero failures/skips**.
- Real-browser strict-CSP local-only Worker foundation smoke: passed against
  these newly packaged source-dist assets, using the explicit Chromium path.
- GraphForge cross-host golden and ABI generator checks: passed. The API
  preparation inventory is regenerated; its existing classification and release
  acceptance gaps remain explicit.

The preceding sharing receipt contains before/after 1,830 Rust, 102 focused
Python, 156 Node and 673 ABI checks, byte goldens and render/streaming smokes.
Those results retain their original source binding. This packaging decision
does not change Rust code or claim the full Node/Python suite is green; the
broader baseline failures remain documented in the S1 recovery receipt.

Raw command output is retained losslessly as `*.txt.gz`; use `gzip -dc` to
inspect it. No CI-toolchain size equivalence, interaction latency, accessibility,
consumer journey, exact release freeze or milestone completion is established.

## Reproduce

From the final source checkout, use the pinned repository toolchain and an
actual Node 22 installation:

```bash
export PATH="$HOME/.cargo/bin:$PATH"
cargo build --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
uv run python scripts/verify_wasm_assets.py
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
node --test packages/xy-node/test/graphforge-wasm-parity.test.mjs \
  packages/xy-node/test/cose-wasm-parity.test.mjs \
  packages/xy-node/test/graphforge-cross-host.test.mjs \
  packages/xy-node/test/force-worker-lifecycle.test.mjs
XYG_CHROMIUM=/path/to/chromium node scripts/wasm_foundation_smoke.mjs
uv run python scripts/gen_graphforge_cross_host.py --check
python3 scripts/gen_abi_manifest.py --check
uv run python scripts/check_release_inventory.py
```
