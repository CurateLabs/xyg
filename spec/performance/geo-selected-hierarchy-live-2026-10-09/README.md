# Selected hierarchy live host evidence

This is bounded functional and ownership evidence for the explicit caller-owned
Scope/lane route described in `../../design/geo-live-hierarchy-host.md`.
The live routing slice changes no Rust, ABI signature or fixed quota. Its
reviewed dependency adds recoverable nonce33 allocation; the paired artifacts
include that dependency and the shared capture-input repair. The browser
transaction remains the existing XYGHv2 CAS/recovery path;
`environment.json` records their hashes and the actual host/harness sources.

`python.txt` records 39 passing native tests; `node.txt` records 27 passing tests.
`typed-native-wasm.txt` records 24 passing real native/packaged-WASM
owner tests on the same pair, including publication ambiguity and full-byte
interaction/freeze parity. `nonce-native-wasm.txt` adds23 actual native/WASM
State-attempt tests, including exactnonce recovery and retired tombstones.
These cover actual43/44, independent lane histories, five accepted frames,
16-handle admission pressure, lost/corrupt33 replies on canonical, indexed and
hierarchy routes, exact same-State replay, cleanup10 rejection/retry, lost43/44
mutation confirmation, retryable cleanup,
post-publication cancellation, null-row intent and exact signed time. Old paint
remains accepted until CAS. No hidden canonical/flat-index query is permitted.

`browser.json` records five simultaneously mounted native adapters through the
packaged Chrome155 client: selected green paint, failed hydration, source read
failure, lost preparation/commit/ACK replies, absolute edit composition and
retirement. `notebook.json` is an actual JupyterLab4.6.2/ipykernel7.4.0 journey with
binary anywidget0.11 comm, keyboard camera input, signed-time Future completion
and native retirement ACK. `reflex.json` uses actual production Reflex0.9.8,
React and socket.io reconnection. `vscode.json` uses actual VS Code1.133.0 panels,
reload, independent private anchor remount and panel disposal. All three use
selected hierarchy queries after original Source registry disposal; caller
frames are independently released after adapter retention. Native source reader
callbacks and explicit lane/Scope owners remain available until final cleanup.

Reproduce from this worktree with the paired native artifact:

```sh
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib"
export XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
uv run pytest tests/test_geo_host.py tests/test_geo_live_host.py tests/test_geo_indexed_host.py tests/test_geo_live_hierarchy_host.py tests/test_geo_hierarchy_static_selected.py -q
node --test packages/xy-node/test/geo-webview.test.mjs packages/xy-node/test/geo-live-host.test.mjs packages/xy-node/test/geo-live-hierarchy-host.test.mjs
node --test packages/xy-node/test/geo-selected-hierarchy.test.mjs
node js/build.mjs
# Restore the recorded paired WASM artifact after build clears dist.
node tests/browser/geo_live_hierarchy_host_test.mjs
.venv/bin/python -m ipykernel install --sys-prefix --name xyg-geo-proof
node scripts/geo_notebook_live_hierarchy_smoke.mjs
```

For Reflex, install its fixture requirements, compile from
`tests/reflex_geo_live_hierarchy_app` with `PYTHONPATH` naming this worktree's
`python` and `tests`, then run `reflex compile --dry` and
`reflex run --env prod --single-port`. Run
`node scripts/geo_reflex_live_hierarchy_smoke.mjs` against port8157 and stop the
owned server afterward. VS Code reproduction uses the real `code` executable
with isolated user/extension directories, `--disable-extensions`, and
`--extensionDevelopmentPath`/`--extensionTestsPath` naming
`tests/vscode_geo_live_hierarchy` and its `test.cjs`; set
`XYG_GEO_VSCODE_REPORT` to an output file. The generated adjacent client copy is
ignored and created by the test. Runtime reports may be redirected with the
corresponding `XYG_GEO_NOTEBOOK_REPORT`/`XYG_GEO_REFLEX_REPORT` variables.

These are small fixture journeys, not performance benchmarks or massive-data
interactive claims. Native ownership quotas exclude frontend/GPU/OS storage.
Jupyter emitted a documented anywidget render-export deprecation warning and
GPU readback performance notices; no external requests occurred. Pointer/wheel
input uses the separately reviewed shared-capture dependency. This evidence
adds no new input policy. Uncertain35/36 mutation admission is not claimed fixed
by the allocation seam. Selection editing, automatic joins,
playback UI, mixed hierarchy routing and #50/#39 completion remain unclaimed.
