# Dashboard recovery and CI correction — PR1114

This corrects the reviewed GPU candidate `df742dcfe92a547b085d68edab2b689038eccca2`.
The three Greptile findings are saved-picture loss during under-reserved
rebuild, context recovery after one-shot admission, and inactive recency for
retained graph paints. This receipt does not establish full #111 acceptance.

Shared ChartViews retain a decorative Canvas2D stand-in before eviction or
context loss. A failed rebuild cannot replace it; a complete restored paint
retires it. Context loss invalidates GPU objects while retaining Rust-approved
reservations, so an unchanged resource set can recover without a budget
watcher. Growth remains subject to fresh Rust admission. Retained graph paint
requests report use before the host checks admission; Rust still ranks and
admits charts. Resource caps, ABI, WASM, planner policy and tolerances are unchanged.

## Regression evidence

The real 32-chart browser journey now appends 4096 rows while a chart is
suspended, forces a rebuild under its old reservation, checks the exact last
accepted picture, and then admits and paints the new payload. It selects the
least-demanding actual owner rather than a chart whose earlier intentional
capacity refusal left a large high-water demand. A separate one-shot call with
all watchers disposed precedes actual WebGL context loss and automatic rebuild.
The retained temporal journey adds two equal-demand graph fixtures: a refused
refresh on the evicted older graph must update recency and lead to readmission
under a single-graph budget. Its later zero-cap refusal baseline is captured
*after* this successful activity journey.

The exact prior client fails the corrected picture control with `lost:true`,
no stand-in and zero retained ink; the candidate passes. The prior client also
fails the isolated one-shot recovery control at its lifecycle timeout and the
graph control at the second refresh after the expected initial eviction.
Earlier growth and graph controls used inappropriate demand allowances; those
failed setup runs are retained and do not establish regression coverage.

Hosted CI exposed two stale literal source assertions and two upload probes
that assigned methods after the client proxy cached its GL wrappers. The
assertions now require the existing expanded loss/admission guards. Upload
observation attaches to the real WebGL prototype *before* wrapper creation;
all original upload-count, pixel, physical-alpha, malformed, stale and disposal
assertions remain. No production accounting bypass was introduced for probes.
The first local physical-alpha invocation lacked `XYG_CHROMIUM` and skipped;
the explicit-browser rerun passes. The first tile probe lacked the task-local
native file and failed setup; the verified explicit artifact is now selected.

## Reproduction

Use Node22, the recorded Chromium, disk TMPDIR and the explicitly verified
native library. Build the browser client before running the final journeys.

```bash
node js/build.mjs
uv run python scripts/check_release_inventory.py
XYG_CHROMIUM=/path/to/chromium node scripts/dashboard_gpu_smoke.mjs
XYG_CHROMIUM=/path/to/chromium XYG_GRAPH_TEMPORAL_ONLY=1 node scripts/graph_session_controller_wasm_smoke.mjs
uv run python scripts/density_tile_smoke.py /path/to/chromium
uv run pytest -q tests/test_shared_glhost.py tests/test_benchmark_environment.py tests/test_density_physical_alpha.py tests/test_static_client_security.py tests/test_graphforge_contract_corpus.py tests/test_release_inventory.py
XYG_CHROMIUM=/path/to/chromium node scripts/wasm_foundation_smoke.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

`checks.json` records actual commands, outcomes, environment and artifact/raw-log
hashes. `current-bindings.json` advances the current source binding and retains
the previous receipt and its historical chain unchanged. Real Git CRLF checkout
coverage protects current bound sources. Failed attempts are retained, not
reported as passes. The old client bundles are archived solely as historical
regression producers; generated shipping distributions remain untracked.

The logical GPU cap excludes Canvas2D stand-ins and opaque driver memory.
Global CPU/source/WASM budgeting, defaults, full host/WebKit and mixed-scale
qualification, keyboard/accessibility completeness, scale/latency and competitor
acceptance remain open. Hosted final-head checks, independent final review and
the required merge queue remain delivery prerequisites.
