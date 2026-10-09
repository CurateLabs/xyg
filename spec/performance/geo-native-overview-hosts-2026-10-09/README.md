# Bounded native overview host journeys

Actual privately issued native XYOV Data is mounted through the existing
geographic composition API and XYGH transport. This is functional evidence,
pending integration, not a timing benchmark or a massive-scale readiness claim.
The source specification is [native overview hosts](../../design/geo-native-overview-host.md).

`python.txt` records 26 passing tests (9 new overview controls); `node.txt`
records 18 passing tests (8 new controls). The controls cover independent
retention, exact CAS/retirement, source/index/caller disposal, lost command-26
confirmation and durable same-allocation recovery, pending page-read cleanup,
private producer classification, mutable public metadata, packet aliasing and
transfer detachment. The Python budget control changes the public getter before
mount and during a real pending native page read. The 32769-vertex Python case
checks exact counts and fixed framing; it does not measure interactive scale.

`browser.json` records actual Chromium under strict CSP, no external requests,
800×600 drawing dimensions, shared GL pixels, bounded 32-row counts, exact
temporal count change 1→2, focused ordinal preservation, old counts during
pending preparation, malformed-painter rejection, lost-commit replay and
release after producer disposal. `notebook.json` uses a live JupyterLab kernel
and anywidget comm while an event loop runs. `reflex.json` uses a compiled
production Reflex application, its real socket.io namespace, physical socket
reconnect and release ACK. `vscode.json` uses a real VS Code extension host and
webview panel, including reload/remount, live updates and actual panel disposal.
Native and remote-browser storage are separate authorities. Three canvases in
host journeys include the existing presentation/pick surfaces, not three
independent source policies. Notebook warnings are retained in its raw report.

`environment.json`, `source-sha256.json` and `compiler-inputs.json` pin the
environment, host/bundle sources and all 199 matching compiler inputs. The
explicit donor native library is used throughout; no local editable-build
assumption is made. The matching WASM artifact is recorded only as a dependency
artifact, not as a native-host conformance claim. Root independent reports
include the final 9-Python captured-budget proof and a second reviewer’s
9-Python/8-Node runs, alongside the earlier independent browser checkpoint. `initial-diagnostics.json`
explains observed failures and their corrections, without inventing raw logs.

From the repository root, with Node dependencies and the generated client built:

```sh
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
export XYG_NATIVE_LIB=/absolute/path/to/source-equivalent/libxyg_core.dylib
export XYG_CHROMIUM=/absolute/path/to/Chrome
UV_NO_SYNC=1 PYTHONPATH=python uv run pytest tests/test_geo_native_overview_host.py tests/test_geo_host.py tests/test_geo_live_host.py -q
node --test packages/xy-node/test/geo-native-overview-host.test.mjs packages/xy-node/test/geo-host.test.mjs packages/xy-node/test/geo-live-host.test.mjs
XYG_GEO_NATIVE_OVERVIEW_REPORT=/tmp/overview-browser.json node tests/browser/geo_native_overview_host_test.mjs
```

The browser test uses `XYG_CHROMIUM`, or Playwright's installed Chromium.
For the actual notebook, install the test runtime in an isolated environment
and provide its executable; the kernel imports this checkout through PYTHONPATH:

```sh
uv venv /tmp/xyg-overview-jupyter
uv pip install --python /tmp/xyg-overview-jupyter/bin/python jupyterlab==4.6.2 ipykernel==7.4.0 anywidget==0.11.0 numpy==2.5.1 pytest==9.1.1
XYG_GEO_JUPYTER=/tmp/xyg-overview-jupyter/bin/jupyter-lab XYG_GEO_OVERVIEW_NOTEBOOK_REPORT=/tmp/overview-notebook.json node scripts/geo_native_overview_notebook_smoke.mjs
```

For production Reflex, install the pinned test-only runtime and project
integration, then run the fixture from its own directory. Stop only that
process after the browser has acknowledged release:

```sh
cd tests/reflex_geo_native_overview_app
UV_NO_SYNC=1 PYTHONPATH="$PWD/../../python:$PWD/.." uv run reflex run --env prod --single-port
```

In another shell at the repository root:

```sh
XYG_GEO_REFLEX_ORIGIN=http://127.0.0.1:8143 XYG_GEO_OVERVIEW_REFLEX_REPORT=/tmp/overview-reflex.json node scripts/geo_native_overview_reflex_smoke.mjs
XYG_GEO_OVERVIEW_VSCODE_REPORT=/tmp/overview-vscode.json code --user-data-dir /tmp/xyg-overview-code --extensions-dir /tmp/xyg-overview-code-ext --extensionDevelopmentPath="$PWD/tests/vscode_geo_native_overview" --extensionTestsPath="$PWD/tests/vscode_geo_native_overview/test.cjs" --disable-extensions --skip-welcome --skip-release-notes
```

The default overview `show` remains static; the explicit widget/host route is
live. This slice adds no frozen format, source-feature picking, domain-membership
algorithm, network provider, five-overview-view throughput proof or competitor
win. Existing source/index page stores remain application-owned and available
for updates. Broader M6 readiness gates remain explicit.
