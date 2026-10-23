# Application consumers

XYG provides Python and Node native authoring, notebook widgets, HTML/static
export, and the shared browser client. Application frameworks consume these APIs;
XYG does not ship a web-framework adapter.

## Python with Streamlit

The repository example at `examples/streamlit/app.py` builds charts through the
public Python composition API, exports HTML, and displays it with stock Streamlit
HTML components. Streamlit is a development/test dependency, not an XYG runtime
requirement. Build the native core and client assets using the repository setup,
then run:

```bash
uv sync --group dev
uv run --group consumers streamlit run examples/streamlit/app.py
```

The embedded document supports browser-local pan, zoom and hover according to
the chart configuration. It is a snapshot. Chart callbacks do not reach Python,
and appending data in Python does not update an already rendered iframe. An app
rerun builds a new document. Use the notebook widget or an explicit live transport
when the application needs Python callbacks or incremental streaming.

## Node with vanilla TypeScript

`examples/vanilla-ts/server.mjs` uses the native Node authoring package and serves
binary chart payloads to `app.ts`, which mounts the shared browser client. This
consumer requires no Python runtime. Selection/update and disposal use the same
client boundary available to other JavaScript applications; Rust owns product
policy and numeric paint buffers stay binary.

```bash
node examples/vanilla-ts/server.mjs
```

Follow the example's setup instructions for generated client/WASM assets and the
Node native binding. A browser application must serve Worker/WASM assets through
explicit same-origin URLs; an embedded HTML snapshot cannot infer those URLs.

## Migrating the removed framework integration

Reflex support has been removed, including the bundled adapter namespace,
dependency extra, registry tokens, generated JSX and framework event forwarding.
There is no compatibility shim. Replace chart mounting with public Python HTML
or notebook APIs, or the Node/browser APIs. Application state, layout, Tailwind
source discovery and event forwarding belong to the application host.

`Chart.chrome_components()` still returns opaque custom chrome objects for hosts
that explicitly mount them. Its former framework-named alias is removed. The
public declarative chart vocabulary and notebook/static-export APIs remain.

Existing dated adapter benchmark records describe prior releases and do not
establish current framework support. The current coverage and release contract
is [application-consumers.md](https://github.com/CurateLabs/xyg/blob/main/spec/design/application-consumers.md).
