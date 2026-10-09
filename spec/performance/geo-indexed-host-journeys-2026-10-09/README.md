# Explicit indexed-frame native host journeys

This checkpoint presents the immutable result of an actual Rust spatial-index
query through the existing GeoChart notebook, Reflex and VS Code integrations.
The canonical source, canonical frame, index/query session and caller's indexed
frame are disposed before browser mounting. Construction first retains a
private anchor; each exclusive mount borrows the same private immutable anchor.
No source/index query occurs at mount or remount.

Base `2bb21e39` combines the native host and command-26 ownership slices. Native
C ABI 383, Scene32 and XYPB15 are unchanged. Matching release dylib SHA256:
`83b0771d90490e097ba49db5e92056f60d879f68268a4769b5b89660af5cc411`.
macOS arm64, Chrome 155.0.8059.40 (SwiftShader), actual VS Code 1.133.0 Electron,
JupyterLab 4.6.2/anywidget 0.9.21, Python 3.13, Reflex 0.9.8 and Node 26.6.0.
The machine ran concurrent development; these are correctness observations,
not latency measurements or massive interactive acceptance evidence.

| Actual frontend | Raw result | Observations |
| --- | --- | --- |
| JupyterLab/IPython/anywidget | [notebook.json](notebook.json) | Running asyncio loop, 47 red pixels, u64 MAX/i64 MIN, caller/index disposed before mount, release ACK |
| Production Reflex/React/socket.io | [reflex.json](reflex.json) | 47 red pixels, exact pick, actual websocket reconnect preserves owner, ACK leaves zero canvases |
| VS Code extension/WebviewPanel | [vscode.json](vscode.json) | Both mounts 161 red pixels and exact pick; reload acknowledges frontend teardown and reuses anchor; panel disposal releases anchor |

The VS Code probe reads pixels in the same turn as an ordinary shared
`ChartView.draw(true)` call. A WebGL default drawing buffer may be discarded
between presentation and later readback; earlier probes read zero after a
successful presentation. This harness uses the real shared renderer and real
framebuffer, without painting a test rectangle or changing product code.
Notebook warnings record inherited anywidget export deprecation and deliberate
framebuffer-read GPU stalls. No external requests occurred. Reflex had no page
errors. One private Data handle per adapter remains subject to shared eight-Data
and existing CPU/derived quotas; remote IPC, GPU and frontend memory are outside
the native processor ledger.

[Python validation](python-validation.txt) covers 177 actual native/Reflex cases,
including indexed anchor/caller independence, camera/time/style/state revision
mismatch rejection, style and sequence rejection, ACK remount, close while
mounted, full quota pressure, five simultaneous native mounts, delayed old-mount ACK rejection, and repeated unmounted cleanup. [Node validation](node-validation.txt)
covers 18 native/index/lease/host/VS Code contract cases, including immediate
caller disposal after construction and close during pending anchor acquisition. Five adapters plus the caller use six Data handles, leaving two auxiliary slots; a third auxiliary admission fails without altering any frame and recovers after release.
Full typing, Ruff and repository hooks also pass.

Reproduction uses the tracked fixtures and scripts (matching native library and
host-neutral client bundles required):

```sh
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib"
export XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
PYTHONPATH=python:tests .venv/bin/python -m pytest tests/test_geo_indexed_host.py tests/test_geo_host.py tests/test_geo_frame_leases.py tests/test_geo_spatial.py tests/reflex_adapter -q
node --test packages/xy-node/test/geo-indexed-host.test.mjs packages/xy-node/test/geo-host.test.mjs packages/xy-node/test/geo-frame-leases.test.mjs packages/xy-node/test/geo-spatial.test.mjs packages/xy-node/test/vscode_contract.test.mjs packages/xy-node/test/no_browser_globals.test.mjs
XYG_GEO_NOTEBOOK_REPORT=/tmp/xyg-indexed-notebook.json node scripts/geo_notebook_host_smoke.mjs
```

Install the Jupyter dependencies/kernel using the previous
[host fixture environment](../geo-host-journeys-2026-10-09/README.md#reproduction).
`XYG_GEO_JUPYTER` can select that fixture's Jupyter executable; its live kernel
receives this checkout's `PYTHONPATH`. For production Reflex, from
`tests/reflex_geo_host_app`, run `.venv/bin/reflex compile --dry` and
`.venv/bin/reflex run --env prod --single-port` with the repository's absolute
`PYTHONPATH=.../python:.../tests` and library path. Then at the repository root:

```sh
XYG_GEO_REFLEX_REPORT=/tmp/xyg-indexed-reflex.json node scripts/geo_reflex_host_smoke.mjs
XYG_GEO_VSCODE_REPORT=/tmp/xyg-indexed-vscode.json \
 '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code' \
 --user-data-dir /tmp/xyg-indexed-code --extensions-dir /tmp/xyg-indexed-code-extensions \
 --extensionDevelopmentPath="$PWD/tests/vscode_geo_host" \
 --extensionTestsPath="$PWD/tests/vscode_geo_host/test.cjs" \
 --disable-extensions --new-window --disable-workspace-trust \
 --disable-gpu-sandbox --enable-unsafe-swiftshader --use-gl=swiftshader
```

Explicit frames are immutable. Implicit indexed hosts, live native pan/time/state
updates, multiple retained layer composition, orphan recovery after lost ACK,
full-source accessible companion transport in native hosts and #50 massive
interactive timing remain separate gates. This checkpoint closes none of
those gates and makes no #50/#39 or M6 completion claim.

The [pre-capacity-repair checkpoint](../geo-indexed-host-journeys-2026-10-09-checkpoint/README.md) preserves earlier actual observations. Its two-Data-per-adapter design was rejected in review because five adapters would exceed the existing eight-Data cap. Current ACK drops only frontend/painter/mount references while authoring remains open; a mount is exclusive and the same Data owner is safe to reuse only after old frontend teardown and publication/auxiliary send settlement. Exact mount-string authority rejects a late old ACK even when owner/sequence are reused. Adapter close holds the anchor until ACK, then releases it. Remote copies remain outside the native processor ledger.
