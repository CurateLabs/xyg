# Application consumers and framework support

Status: normative replacement for the retired Reflex integration (#1063).

## Supported boundaries

XYG ships Python native authoring, Node native authoring, the notebook widget,
HTML/static export, and the shared browser client with bounded Rust/WASM APIs.
The public declarative composition API and `Chart.chrome_components()` remain.
Rust alone owns layout, LOD, encoding, selection policy and canonical data.

Reflex support is removed as a breaking change. Wheels and sdists contain no
`reflex_xy` namespace or JSX wrapper; no `xyg[reflex]` extra or compatibility
shim ships. `Chart.reflex_components()` is removed. Applications using that
integration must move to the supported host APIs; no automatic migration of
Reflex state, socket.io routes, registry tokens or event handlers is promised.
Upstream attribution, legacy documentation redirects and immutable benchmark
records remain historical evidence, not current support claims.

## Python / Streamlit

`examples/streamlit/app.py` consumes the public Python composition API and
embeds `Chart.to_html()` through stock Streamlit HTML components. Streamlit is
a development/test dependency and an application framework, not an XYG runtime
requirement or shipped adapter. Published Python users need no Node runtime.

The example builds deterministic representative chart families, supports app
reruns and native exports, and displays the shared browser client. The iframe
supports browser-side pan, zoom and hover. Its HTML is a snapshot: it has no
Python callback, cross-frame selection bridge or incremental streaming promise.
A rerun produces a fresh document. A missing dynamic tick attachment fails
closed; an iframe must not guess Worker URLs or invent JavaScript ticks.
Hosted tick tests must serve explicit same-origin packaged Worker/WASM URLs.

## Node / vanilla TypeScript

`examples/vanilla-ts/server.mjs` serves the shared client and Rust-backed Node
host payloads; `app.ts` consumes them with browser TypeScript. There is no Python
or Reflex dependency. Browser glue owns attachment, event forwarding and cleanup,
not product policy. Selection/update and disposal checks exercise this boundary;
large source arrays remain host-side and numerical paint planes remain binary
under dossier §29. Streamlit HTML embedding does not establish this live path.

## Coverage disposition

Framework-only behavior is retired: Reflex computed vars, registry tokens,
plugins, generated JSX/Tailwind discovery, socket.io namespaces and Reflex
reconnect/state machinery have no replacement compatibility obligation.

Shared contracts remain required: canonical selection and exact pick identity,
binary framing, coalesced streaming, stale-reply rejection, buffer retirement,
local packaged assets, visible paint, resize/visibility, context recovery and
cleanup. `tests/test_channel.py`, widget/channel tests, Node host/browser tests,
and the existing ABI/render/append smokes own their respective shared paths.
`scripts/app_lifecycle_smoke.py` retains the framework-neutral FastAPI lifecycle
journey; its former Reflex-oriented filename never established Reflex support.
Historical geographic adapter journeys remain provenance only; current native
notebook, Node/VS Code and browser contracts stay authoritative.

## Reproduction and release acceptance

```bash
uv sync --group dev
uv run streamlit run examples/streamlit/app.py
node examples/vanilla-ts/server.mjs
uv run pytest tests/test_streamlit_consumer.py -q
uv run python scripts/consumer_apps_smoke.py --chromium /usr/bin/google-chrome-stable
```

Source setup also requires the native core and generated client/WASM assets
(dossier §33). The consumer gate must verify actual browser paint and cleanup,
not merely a successful HTML response. Test claims must distinguish app reruns,
DOM selection and server-authoritative selection/streaming.

Wheel/sdist verification rejects adapter paths and Reflex dependency/extra
metadata. Clean-install tests preserve native-load diagnostics, coreless compute
failures and Python-without-Node consumption. Existing Node packaging and host
independence gates remain required. Consumer examples/tests are repository-only.

The #40/#54 host acceptance matrix replaces its Reflex rows with Python/Streamlit
and Node/vanilla TypeScript. #886's Reflex-only auto-attach requirement is retired;
its shared packaged WASM asset, strict-CSP, tick admission, failure/recovery,
density no-refinement and source-bound evidence requirements remain. This change
does not accept the entire #54 matrix, #886, GraphForge Streamlit #1016, or a new
release candidate. No timing or competitor-performance win is claimed.

The required consumer gate builds and verifies a wheel (or accepts an exact
`--wheel PATH`), installs it plus lock-constrained Streamlit into a clean venv,
and stages/packs/installs the Node facade, current-platform native and browser
client archives. It reuses `scripts/stage_node_packages.py`, with a local-only
`0.0.0-test.1063` npm candidate version; nothing is published. Application
imports and client assets resolve inside those installs. Native development
overrides and `PYTHONPATH`/`NODE_PATH` are removed. Dedicated executable-only
PATH directories exclude Node from the Python app and Python from the Node app;
the runner checks absence before recording isolation. Build tools remain
available to the runner. CI retains `consumer-apps-smoke.json` (schema 1:
versions, artifact SHA-256 values and scenario results) plus host logs and
screenshots under `consumer-apps-smoke/`.
