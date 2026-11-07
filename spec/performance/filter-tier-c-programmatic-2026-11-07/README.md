# Filter Tier C programmatic checkpoint — #112 remains open

This candidate delivers the [bounded programmatic contract](../../design/filter-tier-c.md),
not whole #112 acceptance. Rust owns retained canonical source/intent, checked
count-prefix slabs, exact range resolution/refusal/fallback, membership pages,
budgets, cancellation and publication. Native ABI 402/WASM ABI 36 and the public
Python/Node/browser methods share XYFC/XYFR v1. No renderer or GPU producer
candidate was merged or modified. Pointer/keyboard, 2D passive density grids,
selected-count painting, spill, composed predicates, full compatibility and
massive qualification remain parent-owned next steps.

## Exact bases and source provenance

- Accepted main at task start: `084b3c1b7c393e135476aab9610bf8334767b2ac`.
- Supplied reviewed ABI401 head, integrated by fast-forward and retained as the
  checkpoint parent: `2cb7f0a13ec0af3a00b9dcfd2b104a2c579b7ac9` (parents
  `084b3c1b7c393e135476aab9610bf8334767b2ac` and
  `6c81d68e93378429c4549442b8700091e22e128d`).
- Final read-only fetch observed `ae104cf35316e10e56e345c225acef2604e487a1`
  (`#1111`) on main. It was not merged into this explicitly based checkpoint.
  ABI401/#1110 was not assumed merged.
- GPU coordination input `254cafd313494c409971f4545bac69e3b53085aa` was read only.
- `current-bindings.json` advances the global current Core binding append-only;
  the previous snapshot and all its historical bindings are immutable.
- `abi401-predecessor/` preserves every complete official ABI401 fixture file;
  `fixture-transition.json` binds the ABI-only 401→402 refresh. Existing 401
  receipts are unchanged. Historical notebook verification requires explicit
  `expected_abi=401`; the CLI/default still requires the generated current ABI.
- LF attributes and the real Git `core.autocrlf=true`/CRLF checkout test protect
  all hash-bound current inputs. Artifact/environment identities live in
  `artifacts.json`, `environment.json`, `checks.json`, and `rust-sources.json`.

`tests/fixtures/filter_tier_c/session.bin` contains 47 complete request/reply
cases, including three failed output-capacity publications. An independent
Python full scan generates/validates counts and membership; Node/actual WASM
also run an independent scan from canonical ingress. Public Python randomized
oracles cover empty/nonfinite sources, cut boundaries and row-independent
index storage. Newer-request tests and a reproduced malformed-header watermark
mismatch prove atomicity and fail-closed lifecycle behavior. Controls/errors
expose unavailable selected totals as None/null, not measured zeros.

## Validation and reproduction

Use the pinned Node 22 path in `environment.json`, `CARGO_BUILD_JOBS=2`, a disk
`TMPDIR`, and explicit `XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so`.
Chrome is also pinned there. The build outputs are generated/ignored per §33;
their actual bytes/hashes are recorded rather than committing distributions.

```bash
uv sync --group dev
npm ci
npm ci --prefix packages/xy-node
CARGO_BUILD_JOBS=2 cargo build --release
node js/build.mjs
CARGO_BUILD_JOBS=2 npm run build:wasm
python3 scripts/gen_abi_manifest.py --check
python3 scripts/gen_wasm_abi.py --check
python3 scripts/check_abi_parity.py
python3 scripts/abi_smoke.py
CARGO_BUILD_JOBS=2 cargo test --workspace
CARGO_BUILD_JOBS=2 cargo test -p xyg-engine filter_tier_c
CARGO_BUILD_JOBS=2 cargo clippy -p xyg-engine -p xyg-core -p xyg-wasm --all-targets -- -D warnings
uv run python scripts/gen_filter_tier_c_fixture.py
uv run pytest -q tests/test_filter_tier_c.py tests/test_cross_host_abi_transition.py tests/test_graph_notebook_report.py tests/test_graphforge_contract_corpus.py tests/test_verify_ci_workflow.py
node --test packages/xy-node/test/filter-tier-c.test.mjs
node scripts/filter_tier_c_conformance.mjs --chromium "$XYG_CHROMIUM"
python3 scripts/render_smoke_nonumpy.py "$XYG_CHROMIUM"
python3 scripts/append_stream_smoke.py "$XYG_CHROMIUM"
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The normal explicit Node package test list includes `filter-tier-c.test.mjs`.
The existing Node-host CI step runs the bounded Chromium Worker journey under
the existing Release surfaces aggregate; there is no new aggregate. Its active
command is protected by CI mutation tests. All existing deadlines/guards stand.
Exact commands, exit results, pass counts and raw log hashes are in `checks.json`.
The browser result reports `rendered:false`: 44 real Worker packet replays plus
five passive programmatic views, not five painted coordinated views.

## WASM size experiment and retained failures

The original inlining threshold 100 with the added feature exceeded the
unchanged caps (1,882 KiB raw / 768 KiB gzip). Initial packaging failed at
793,530 gzip bytes. We retained that failure and the alternative optimizer
measurements. No exports or capabilities were removed and neither cap changed.

The selected wasm32-only LLVM inlining threshold is 50; native remains O3 with
its existing flags. The shipping optimized module is 1,886,400 raw bytes and
fits the original gzip cap; exact default-gzip bytes and headroom are bound in
`artifacts.json`. O3 Binaryen and its existing pinned version remain unchanged.
Same-source ABBA results compare threshold 100 with 50 using the existing
`bench_wasm_profiles.mjs` at 100/10k/100k rows, with byte-identical outputs and
preserved rejection of the existing 100k geographic-interaction resource case.
`profile-isolated.json.gz` retains every sample and environment, including
slower small-workload results. This is a compiler size tradeoff, not a product
performance/competitor win. No guard, tolerance or deadline was loosened.

```bash
uv run python benchmarks/gen_wasm_profile_inputs.py --out target/ftmp/filter-profile-inputs
CARGO_TARGET_DIR="$PWD/target/filter-inline100-final" \
CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS='-C llvm-args=--inline-threshold=100' \
CARGO_BUILD_JOBS=2 cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
# Optimize this comparison-only raw module with js/optimize-wasm.mjs;
# it is not a size-qualified shipping artifact.
node benchmarks/bench_wasm_profiles.mjs \
  target/ftmp/filter-inline100-shipping-source.wasm \
  packages/xy-client/dist/xyg-wasm.wasm \
  target/ftmp/filter-profile-inputs target/ftmp/filter-isolated-profile-abba.json
```

The final native malformed-header watermark repair changed native-only gate
code. Both freshly rebuilt wasm32 raw profiles and their optimized artifacts
remained byte-identical (`wasm-gate-fix-neutrality.json`), so the same hash-bound
ABBA evidence applies. Rejected draft, stale-fixture, CI-test-fixture, browser
transport-guard, missing-environment and malformed-watermark failures are kept
as logs, with their corrected checks, rather than discarded or called green.

## Remaining issue acceptance

No 100M/five-rendered-view ≥50 FPS, CodSpeed index/build/query, competitor,
accessibility, selected-density, spill, composed-predicate, or full-platform
acceptance is claimed. Source-bound comparisons across all required scales
and libraries remain required, including Falcon/Mosaic methodology. The
programmatic checkpoint must not close #112 or milestones 4–7. Parent independent
review of the final diff is required before any PR; none was opened or pushed.
