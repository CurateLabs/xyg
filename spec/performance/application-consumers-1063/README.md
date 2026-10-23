# Application consumer removal/migration evidence (#1063)

Source base: `cbf2c0eb3fdc2bb4f1ec8dd1cede8f3f73158342`; the implementation
is the accompanying change. These are local correctness/packaging results,
not a release-candidate or performance qualification. No competitor speedup
is claimed. The full Python suite remains a CI gate; it was not run locally.

Environment: Linux x64; Python 3.12.15; Node v24.21.0; Chromium
149.0.7827.55; Streamlit 1.66.1. Rust/toolchain and dependencies are pinned in
the repository manifests/locks. `report.json` records wheel/npm/native/client/
WASM hashes and scenario outcomes; screenshots show the actual consumer apps.
The npm candidate version `0.0.0-test.1063` is local-only and unpublished.

## Results and contracts

- 358 focused Python tests passed; one optional FastAPI import test skipped
  because FastAPI is outside root dev dependencies. The real FastAPI lifecycle
  smoke separately passed all 19 gallery charts plus drilldown across six
  lifecycle phases and 20 index iframes.
- 578 CI/merge-queue/WASM-asset/required-gate contract tests passed.
- 946 Node tests passed, 2 platform-specific tests skipped, 0 failures.
- C ABI: 673 checks passed. No-NumPy render and append smokes passed; append
  retained tail-only uploads and pixel identity. Three native geographic
  browser journeys passed with exact ownership/recovery and visible pixels.
- Clean installed Python/Streamlit and packed Node/vanilla TypeScript apps
  passed real-browser paint, deterministic update/rerun, documented selection,
  export and cleanup checks. Node admitted Rust ticks from local Worker/WASM;
  an injected missing module failed closed while preserving the valid chart.
- Consumer PATH directories contain only their own executable. Imports and
  native/client assets resolve inside the fresh wheel/npm installs. Development
  native overrides and Python/Node source-path overrides are absent.
- Native wheel and sdist verification, public API/ownership/stale-name checks,
  installed typing consumer, full-worktree hooks and Ruff checks passed.
- Documentation: 77 pages, 179 native previews and 11,139 links verified.

`coverage.md` maps retired framework-only checks and preserved/new shared proof.
Streamlit iframe interaction is browser-local; no Python callback, incremental
streaming or live geographic host support is inferred from a snapshot.

## Reproduction

```bash
uv sync --locked --group dev --group codspeed
cargo build --release
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
npm run build:wasm
npx playwright install chromium
uv run python scripts/consumer_apps_smoke.py --chromium /path/to/chrome
make check-ci
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" npm test --prefix packages/xy-node
python3 scripts/abi_smoke.py
python3 scripts/render_smoke_nonumpy.py /path/to/chrome
python3 scripts/append_stream_smoke.py /path/to/chrome
uv run python scripts/app_lifecycle_smoke.py /path/to/chrome
XYG_CHROMIUM=/path/to/chrome node scripts/wasm_html_ticks_smoke.mjs
make check-docs
uv run python scripts/check_typing.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The consumer gate builds/verifies a wheel, installs lock-constrained test
requirements, stages npm packages with the existing release packer and performs
clean installs before starting the apps. Its default outputs are
`consumer-apps-smoke.json` and `consumer-apps-smoke/`; CI retains both. The gate
also accepts `--wheel PATH` to consume an already built exact wheel. Setup may
need network access; chart/asset requests during the browser proof remain local.

Related #40/#54/#886 requirements explicitly retire Reflex-specific obligations;
shared candidate, WASM and density failure/recovery qualification remains open
under their own scopes. GraphForge-specific Streamlit qualification stays #1016.
