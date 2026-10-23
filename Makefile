PYTHON ?= .venv/bin/python
CHROMIUM ?=
UV_CACHE_DIR ?= /tmp/xy_uv_cache
WHEEL_EXPECT ?=
SDIST ?=
WHEEL ?=
BENCHMARK_JSON ?= benchmark.json
BENCHMARK_KIND ?= auto

.PHONY: help setup setup-browser check check-full check-browser check-conformance check-docs check-examples check-security check-errors check-api check-import check-ci check-release-evidence check-bench-oracles check-ownership check-host-parity check-graph check-benchmark-harness check-pyplot check-pyplot-speed check-sdist check-wheel check-artifacts check-benchmark-report list-checks test lint format typecheck public-api python-floor js-check rust-check abi-generate abi-check abi-smoke

help:
	@printf '%s\n' \
		'xy developer shortcuts' \
		'' \
		'  make setup            create .venv, install the dev group, and build the native core' \
		'  make setup-browser    install the pinned Playwright browser-test driver' \
		'  make check            run the fast local verification gate' \
		'  make check-full       run JS, Rust, and ABI gates too' \
		'  make check-browser    run browser smokes (set CHROMIUM=/path/to/chrome)' \
		'  make check-conformance run accessibility + Chromium/Firefox/WebKit conformance' \
		'  make check-docs       build and validate the Starlight docs and documentation examples' \
		'  make check-examples   run canonical API examples and consumer app checks' \
		'  make check-security   run standalone HTML safety and client text-sink checks' \
		'  make check-errors     run public error, LOD, and mutation-safety tests' \
		'  make check-api        run lazy public API and type-surface checks' \
		'  make check-import     run import-time and dependency-boundary checks' \
		'  make check-ci         run CI/release workflow invariant checks and contract tests' \
		'  make check-release-evidence block on unresolved scheduled/main CI failures; read back live ruleset' \
		'  make check-bench-oracles run every benchmark body once (divan --test + pytest, no timing)' \
		'  make check-ownership  validate the production-source ownership ledger' \
		'  make check-host-parity run M2 host-parity landing gates (inventory + cross-host + ABI)' \
		'  make check-graph      run Node/Python graph tests and chart-scale/pyramid smokes (build core/client/WASM first)' \
		'  make abi-generate     regenerate the typed ABI contract and host declarations' \
		'  make abi-check        verify generated ABI artifacts and host parity' \
		'  make check-benchmark-harness run benchmark metadata/report/regression tests' \
		'  make check-pyplot      run the matplotlib-shim suite and compatibility corpus' \
		'  make check-pyplot-speed enforce the per-family 10x static-PNG target (requires matplotlib)' \
		'  make check-sdist      build and verify the source distribution' \
		'  make check-wheel      build and verify a wheel (set WHEEL_EXPECT=--expect-native)' \
		'  make check-artifacts  verify prebuilt artifacts (set SDIST=... WHEEL=...)' \
		'  make check-benchmark-report validate BENCHMARK_JSON (scatter-vs, pyplot-vs-matplotlib, line-decimation, install-footprint, core-2d, scatter-native, heatmap-native, kernel-native, interaction-browser, dashboard-browser, workflow-native)' \
		'                        override UV_CACHE_DIR if your uv cache lives elsewhere' \
		'  make list-checks      list verifier check names' \
		'  make test             run pytest' \
		'  make lint             run ruff check' \
		'  make format           run ruff format --check' \
		'  make typecheck        run ty over the shippable package' \
		'  make js-check         build the render client from source' \
		'  make rust-check       run cargo test and clippy'

setup:
	uv sync --group dev --group codspeed
	cargo build --release

setup-browser:
	npm install

check:
	$(PYTHON) scripts/verify_local.py --quick

check-full:
	$(PYTHON) scripts/verify_local.py --full

check-browser:
	@if [ -z "$(CHROMIUM)" ]; then \
		echo 'Set CHROMIUM=/path/to/chrome for browser smoke checks.' >&2; \
		exit 2; \
	fi
	@node -e "require.resolve('playwright')" >/dev/null 2>&1 || { \
		echo 'Playwright is required for the standalone worker probe. Run: make setup-browser' >&2; \
		exit 2; \
	}
	$(PYTHON) scripts/verify_local.py --browser --chromium "$(CHROMIUM)"

check-conformance:
	@node -e "require.resolve('playwright')" >/dev/null 2>&1 || { \
		echo 'Playwright is required. Run: make setup-browser && npx playwright install chromium firefox webkit' >&2; \
		exit 2; \
	}
	node scripts/browser_conformance.mjs

check-docs:
	npm ci --prefix docs/app
	npm run check --prefix docs/app
	npm run build --prefix docs/app
	npm run test --prefix docs/app
	$(PYTHON) scripts/verify_docs_quickstart.py
	$(PYTHON) scripts/verify_local.py --only examples

check-examples:
	$(PYTHON) scripts/verify_local.py --only examples

check-pyplot:
	$(PYTHON) -m pytest tests/pyplot -q

check-security:
	$(PYTHON) scripts/verify_local.py --only security_export

check-errors:
	$(PYTHON) scripts/verify_local.py --only error_safety

check-api:
	$(PYTHON) scripts/verify_local.py --only public_api,api_surface

check-import:
	$(PYTHON) scripts/verify_local.py --only public_api,import_budget

# Workflow triggers, the Release surfaces aggregate's hard-job dependencies and
# applicability, the merge-queue ruleset, and the executable contract tests
# (injected-failure propagation, every applicability branch, WASM asset gate).
check-ci:
	$(PYTHON) scripts/verify_local.py --only ci_workflow
	$(PYTHON) -m pytest -q tests/test_verify_ci_workflow.py tests/test_release_surface_gate.py tests/test_verify_wasm_assets.py tests/test_check_scheduled_evidence.py

# Read-only: blocks readiness on unresolved scheduled-evidence or main-CI failures,
# and compares the live ruleset/branch protection with the checked-in contract.
check-release-evidence:
	$(PYTHON) scripts/check_scheduled_evidence.py
	$(PYTHON) scripts/verify_ci_workflow.py --ci-only --live-readback CurateLabs/xyg

# Benchmark bodies carry correctness assertions; run each once with no timing or
# instrumentation, exactly as the last steps of the CI `test` job do. Needs the
# `codspeed` dependency group (pytest-codspeed provides the `benchmark` fixture):
# `uv sync --group dev --group codspeed`.
check-bench-oracles:
	cargo bench -p xyg-engine --bench kernels -- --test
	cargo bench -p xyg-wasm --bench aggregate -- --test
	cargo bench -p xyg-wasm --bench typed_series -- --test
	$(PYTHON) -m pytest benchmarks/test_codspeed_*.py -q

check-ownership:
	$(PYTHON) scripts/verify_ownership.py
	$(PYTHON) scripts/audit_python_host_core.py >/dev/null

check-host-parity:
	$(PYTHON) scripts/audit_host_parity_landing.py

# Requires the release core, generated JS/WASM client, and both npm installs.
check-graph: export XYG_NATIVE_LIB ?= $(CURDIR)/target/release/$(shell node -p "process.platform === 'win32' ? 'xyg_core.dll' : process.platform === 'darwin' ? 'libxyg_core.dylib' : 'libxyg_core.so'")
check-graph:
	@test -f "$(XYG_NATIVE_LIB)" || { echo 'Build the release core first: cargo build --release' >&2; exit 1; }
	@for asset in packages/xy-client/dist/index.js packages/xy-client/dist/standalone.js packages/xy-client/dist/xyg-wasm.wasm; do \
		test -f "$$asset" || { echo "Missing $$asset; run node js/build.mjs && npm run build:wasm" >&2; exit 1; }; \
	done
	$(PYTHON) scripts/verify_wasm_assets.py
	$(PYTHON) scripts/abi_smoke.py
	$(PYTHON) -m pytest tests/test_graph.py tests/test_sankey.py -q
	npm test --prefix packages/xy-node
	$(PYTHON) benchmarks/bench_dual_host_graph.py --sizes 1000
	$(PYTHON) benchmarks/bench_parity_kernels.py --sizes 100000 --no-baseline
	$(PYTHON) benchmarks/bench_scale_all_charts.py --profile smoke
	node benchmarks/bench_scale_all_charts_node.mjs --profile smoke
	$(PYTHON) benchmarks/bench_tier3_pyramid.py
	node benchmarks/bench_tier3_pyramid_node.mjs

check-benchmark-harness:
	$(PYTHON) scripts/verify_local.py --only benchmark_harness

check-pyplot-speed:
	PYTHONPATH=python $(PYTHON) benchmarks/bench_pyplot_vs_matplotlib.py \
		--profile standard --reps 21 --warmups 3 --target-speedup 10 --require-target

check-sdist:
	@set -e; \
	OUT=$$(mktemp -d); \
	echo "building sdist in $$OUT"; \
	UV_CACHE_DIR="$(UV_CACHE_DIR)" uv build --sdist --out-dir "$$OUT"; \
	$(PYTHON) scripts/verify_sdist.py "$$OUT"/xyg-*.tar.gz

check-wheel:
	@set -e; \
	OUT=$$(mktemp -d); \
	echo "building wheel in $$OUT"; \
	UV_CACHE_DIR="$(UV_CACHE_DIR)" uv build --wheel --out-dir "$$OUT"; \
	$(PYTHON) scripts/verify_wheel.py "$$OUT"/xyg-*.whl $(WHEEL_EXPECT)

check-artifacts:
	@if [ -z "$(SDIST)" ]; then \
		echo 'Set SDIST=/path/to/xyg.tar.gz for artifact verification.' >&2; \
		exit 2; \
	fi
	@if [ -z "$(WHEEL)" ]; then \
		echo 'Set WHEEL=/path/to/xyg.whl for artifact verification.' >&2; \
		exit 2; \
	fi
	$(PYTHON) scripts/verify_local.py --packaging --sdist "$(SDIST)" --wheel "$(WHEEL)" $(WHEEL_EXPECT)

check-benchmark-report:
	$(PYTHON) scripts/verify_benchmark_report.py "$(BENCHMARK_JSON)" --kind "$(BENCHMARK_KIND)"

list-checks:
	$(PYTHON) scripts/verify_local.py --list

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m ty check python

public-api:
	$(PYTHON) scripts/check_public_api.py

python-floor:
	$(PYTHON) scripts/check_python_floor.py

js-check:
	node js/build.mjs

rust-check:
	cargo test
	cargo clippy --all-targets -- -D warnings

abi-generate:
	$(PYTHON) scripts/gen_abi_manifest.py --write

abi-check:
	$(PYTHON) scripts/gen_abi_manifest.py --check
	$(PYTHON) scripts/check_abi_parity.py

abi-smoke:
	$(PYTHON) scripts/abi_smoke.py
