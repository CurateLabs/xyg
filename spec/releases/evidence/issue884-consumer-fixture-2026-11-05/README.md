# Canonical installed-consumer fixture repair

The Python/Node consumer CI step on317d82ab failed because its repository
harness still staged0.0.0-test.1063, rejected by canonical release admission.
Release surfaces subsequently failed because downstream wheels were skipped.
The new source-extracted consumer staging regression reproduces that refusal.
The sole runtime harness change uses0.0.0-rc.1063, an unreserved local fixture.
The parser, upload guards, release candidate selection and public package code
are unchanged. No registry write or publication occurs.

The staging regression shares its real native/facade/browser staging assertions
with the workflow caller controls. All220 focused tests pass, zero skips.
An AST scan of repository operator scripts and workflow callers found no other
literal local test/dryrun versions passed to these staging functions.

The earlier rc42 wheel did not contain WASM and correctly failed the complete
consumer verifier; that failure log is retained. A fresh WASM/client producer
and complete fixture wheel were therefore built once in this owned workspace.
The existing rc42 bytes were preserved. The complete consumer smoke consumes
this exact new wheel via --wheel rather than rebuilding per consumer:

```bash
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
UV_DYNAMIC_VERSIONING_BYPASS=0.6.0rc1063 XYG_SKIP_CARGO=1 XYG_REQUIRE_WASM=1 uv build --wheel --out-dir .artifacts/consumer-fixture
uv run python scripts/consumer_apps_smoke.py --chromium /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome --wheel "$PWD/.artifacts/consumer-fixture/xyg-0.6.0rc1063-py3-none-linux_x86_64.whl"
```

Use Node22.23.4 and Cargo on PATH. The focused pytest command uses these eight
modules: test_release_version, test_check_release_version, test_stage_node_packages,
test_stage_browser_package, test_publish_node_packages, test_verify_release_cohort,
test_graphforge_contract_corpus and test_xyg_package_identity (uv run --with dunamai).
The preceding dry-run receipt's wording of nine modules was a counting typo.

The actual smoke passed13 installed Streamlit AppTests with zero skips, all9
packaged tick/failure/density cases, Node/vanilla and Streamlit browser journeys,
local assets, cleanup and host-path isolation. consumer-report.json is the raw
report; selected subreports/XML/screenshots are retained. Its Git commit field
names317d82ab because the repaired harness was not yet committed; the working
source hash in qualification_source_sha256 identifies the executed repair.
Result bindings also record the exact fixture wheel and generated artifact hashes.
Installed npm archives were temporary fixtures; their measured hashes are retained
in the report, not promoted to a publication cohort. Python wheel0.6.0rc1063 and
npm0.0.0-rc.1063 are deliberately local harness identities, not a matched release
version cohort. No real selected-Core or full platform qualification follows.

No CI workflow, kernel behavior, ABI, resource cap or visual tolerance changes.
New-head CI and independent review still gate merge. #884/#936/#108 remain open.
