# Native live geographic host journeys — 2026-10-09

Bounded correctness/usability evidence for [XYGHv2](../../design/geo-live-host.md).
The small Point fixture includes literal u64 MAX and signed i64 MIN. Initial
paint uses Instant(MIN); live updates exercise All and Instant predicates through
Rust, exact camera revisions and publication ownership. No massive interaction
latency, physical five-view memory or §17 completion is inferred.

| Actual runtime | Raw report | Assertions |
| --- | --- | --- |
| JupyterLab 4.6.2 / live IPython / anywidget 0.11.0 | [notebook.json](notebook.json) | Real red pixels, trusted keyboard pan accepted as seq2; kernel `GeoWidget.update` seq3 camera/time completes Future only after CAS+RetireACK; acknowledged close |
| Reflex 0.9.8 production / React / socket.io binary | [reflex.json](reflex.json) | Native exact pick, Rust camera/time update, real red pixels, actual websocket reconnect preserves accepted updated authority, zero canvases after ACK |
| VS Code 1.133.0 actual WebviewPanel | [vscode.json](vscode.json) | Camera/time update in both mounts, exact pick and red pixels, reload releases old realm and reuses private accepted anchor, actual panel disposal drains owners |
| Chromium 155 / packaged client / five real native adapters | [browser.json](browser.json) | All five paint, failed hydration keeps old paint; latest same-kind desired update; distinct zoom→bearing and time→center compose via Rust; lost preparation/commit/retire/abort confirmation recovers; definite failed read permits higher-sequence retry |

The notebook report preserves console warnings, including the existing anywidget
named-render deprecation, kernel-name fallback and software-GL readback warnings.
They are not hidden. The application loads no external data/provider/CDN resources.
Pixels are read from the ordinary shared painter; the browser harness invokes its
existing `_drawNow` immediately before readback because default WebGL drawing
buffers may otherwise be discarded. It does not paint a test rectangle.

The binary transport fixture reports five simultaneously mounted adapters, not
a new global five-view limit or complete GPU/OS accounting. It observes unchanged
16-handle/eight-Data/eight-session admission. Caller original frames are explicitly
disposed where retained independently. Native tests also exercise ordinary and
selected indexed repeated updates, full XYSE intent, close during uncertain
commit, stale old-mount ACK, post-Data cancellation and two injected native cleanup
failures followed by exact recovery. Source callbacks settle before ACK.

## Reproduction

Use a normal checkout build (`cargo build --release`, root/Node `npm ci`,
`node js/build.mjs`, `uv sync --extra reflex --group dev`). These recordings borrow
native383 from exact b583f6ab9; engine/core/Cargo/config diff versus this slice was
empty. [source-hashes.json](source-hashes.json) records the actual artifact,
production sources and harnesses. The client is the generated own-checkout bundle.

```sh
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib"
export XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
uv run pytest tests/test_geo_live_host.py tests/test_geo_host.py tests/test_geo_indexed_host.py tests/test_geo_frame_leases.py tests/test_geo_spatial.py tests/test_geo_selected.py tests/reflex_adapter/test_geo_host_journey.py -q
node --test packages/xy-node/test/geo-live-host.test.mjs packages/xy-node/test/geo-host.test.mjs packages/xy-node/test/geo-indexed-host.test.mjs packages/xy-node/test/geo-frame-leases.test.mjs packages/xy-node/test/geo-spatial.test.mjs packages/xy-node/test/geo-selected.test.mjs packages/xy-node/test/vscode_contract.test.mjs packages/xy-node/test/no_browser_globals.test.mjs
node tests/browser/geo_live_host_test.mjs
XYG_GEO_NOTEBOOK_REPORT=/tmp/live-notebook.json node scripts/geo_notebook_live_smoke.mjs
```

Jupyter needs explicitly installed `jupyterlab==4.6.2` and `ipykernel`; these are
test-environment dependencies, not new product runtime requirements. The probe
starts a temporary isolated server/kernel and stops its own server afterward.

For Reflex, use this checkout's `.venv/bin/reflex` with `PYTHONPATH` containing
`python:tests`, from `tests/reflex_geo_live_app`. Run `reflex compile --dry`, then
`reflex run --env prod --single-port` with logs captured. The fixture binds 8141.
From the root run `node scripts/geo_reflex_live_smoke.mjs`. Stop only that owned
production server after collecting the report.

```sh
XYG_GEO_VSCODE_REPORT=/tmp/live-vscode.json \
 '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code' \
 --user-data-dir /tmp/xyg-live-code --extensions-dir /tmp/xyg-live-code-extensions \
 --extensionDevelopmentPath="$PWD/tests/vscode_geo_live" \
 --extensionTestsPath="$PWD/tests/vscode_geo_live/test.cjs" \
 --disable-extensions --skip-welcome --skip-release-notes
```

## Remaining acceptance

This does not establish pointer/wheel geographic gestures, playback UI, mixed
raster/vector signed-time filtering, automatic linked ID mapping, full-source
accessibility, massive five-view memory or low-latency 100M interaction. Selected
Scope is explicitly caller-issued; state changes are not inferred. Hierarchy
routing remains a separate typed processor integration. Lost realms without a
deliverable release acknowledgment remain the existing orphan-lifecycle gate.
#50/#39 and M6 remain open until their full acceptance evidence exists.

Root follow-up review found that Python reader OSError/LookupError escaped the
old exception allowlist. A narrow transport exception boundary now emits the
correlated terminal failure after cleanup. Two actual-native regression cases
prove old-frame preservation, absent candidate/cleanup storage and successful
higher-sequence recovery. The original frontend journey hashes are preserved
as their checkpoint; follow-up hashes and validation are recorded separately.
