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

The AppTest module skips when the optional Streamlit framework is absent, as
in the minimal Python-floor lane (XYG plus pytest only). The required application
lane runs the unconditional real-app consumer gate, which installs the locked
consumer group into the clean wheel environment and executes every AppTest.
Missing framework prerequisites fail that gate. Optional test collection must not turn that required consumer proof into a skip.

### Bounded GraphForge consumer (#1016)

The same example adds `graphforge-property` and `graphforge-pagerank` using
only `compose_graphforge()` and `graphforge_chart()` followed by the existing
public HTML/static export methods. The former omits analytical layers and
exercises #934's base-property defaults (label colors/legend, caption fallback,
directed arrowheads and relationship hover metadata). The latter composes one
Core-produced PageRank IPC result against its matching base and generation.
Fixtures are the existing repository `tests/fixtures/graphforge/results/`
Core 0.5.2 corpus; no analytical engine or fixture generator runs in the app.
They are repository-only example inputs, not wheel contents. There is no new
framework adapter or public product policy. The current consumer-group floor
is `streamlit>=1.56,<2`; the lock pins the version used by the mandatory gate.

The example displays native PNG and SVG previews and offers their original
bytes as downloads. An independent direct public-Python fixture producer
(`tests/fixtures/packaged_streamlit_graphforge.py`) builds the same two
compositions with the installed wheel. The browser helper
`scripts/streamlit_graphforge_browser.mjs`, invoked by the existing consumer
runner, requires exact HTML and download SHA-256 equality to that producer,
graph pixels, painted property captions/legend, decoded static images,
local brush/zoom, no external requests or CSP violations, and no Python comm bridge.
Property paint must contain chromatic pixels; PageRank's default score-size
encoding uses neutral paint and therefore requires nonwhite plot ink instead.
Rust's collision plan may admit a subset of the property captions at home;
AppTest checks the complete fallback-caption plane, while the browser checks
the admitted painted captions rather than assuming DOM text labels.
AppTest exercises explicit same-input script reruns and switch-away/return
determinism. Two browser switch cycles per graph require exactly one iframe,
the same document on return, fresh painted views, and observed CDP destruction
of each outgoing iframe's default execution context.
The browser selects the exact visible Chart option before checking the
committed caption and settled iframe; typed filter text is not a selection.

This is snapshot-document lifecycle evidence. The app has no handle to call
`ChartView.destroy()` on the outgoing frame, and the tests do not inject one;
browser navigation retires that execution context. General live-view GPU,
Worker, listener and frame cleanup stays under the existing shared/Node gates.
Local interactions do not imply a tested UUID round-trip to Python. Stock
Streamlit HTML remains paint-only; no custom component or event adapter is
added. Cache only immutable IPC or finished exports with complete generation,
input and presentation keys; mutable charts/selection/live views must not be
shared through global resource caching. The guide is
[`docs/integrations/graphforge.md`](../../docs/integrations/graphforge.md#streamlit-test-and-documentation-host).

The existing unconditional consumer job and Release surfaces aggregate cover
this bounded proof; no additional job, trigger, dependency group or runtime
extra is needed. `tests/test_dependencies.py` guards package imports and
dependencies even without Streamlit; `tests/test_streamlit_package_boundary.py`
also scans the installed wheel for framework imports, extras and adapter paths.
The optional AppTest module skips only if the framework is absent; a broken
installed framework import fails. Wheel/sdist metadata guards reject a
Streamlit runtime requirement, while wheel root guards exclude example and
adapter namespaces. The runner retains direct inputs/artifact hashes, source
hashes, downloaded bytes, screenshots and raw AppTest/browser reports with the
existing consumer artifacts. Local receipts and exact reproduction details
are recorded in `spec/performance/graphforge-streamlit-1016/README.md`.
Source-checkout proof, local installed-wheel proof and final release-cohort
qualification must be named separately. This slice does not close #1016,
Milestone 4, #36, #934 or #935, update remote #31/#40 host lists, or qualify
large/massive graph capacity or competitor timing claims.

## Node / vanilla TypeScript

`examples/vanilla-ts/server.mjs` serves the shared client and Rust-backed Node
host payloads; `app.ts` consumes them with browser TypeScript. There is no Python
or Reflex dependency. Browser glue owns attachment, event forwarding and cleanup,
not product policy. Selection/update and disposal checks exercise this boundary;
large source arrays remain host-side and numerical paint planes remain binary
under dossier §29. Streamlit HTML embedding does not establish this live path.

`examples/vanilla-ts/graphforge-live.mjs` independently exercises the async Node
GraphForge scheduling boundary on a four-node fixture. Its
[local receipt](../performance/graph-node-scheduling-35-2026-10-31/README.md)
binds native ABI 397 and generated painter assets to initial and changed final
paint, pointer picks resolving source UUIDs, and pan response on both frames.
It separates checkpoint arrival from painted frames. Each update replaces the
whole ChartView and resets the viewport; retained S5 updates remain open.
The repaired consumer resolves picks through Rust-derived render membership,
independently of full source-position indexing; its
[repair receipt](../performance/graph-node-scheduling-35-review-repair-2026-10-31/README.md)
retains exact GPU-hit/UUID checks and initial/final specs and binary payloads.
This source-checkout fixture qualifies no shipping WASM artifact, packaged
consumer, editor adapter, large-data ladder or release cohort. Existing installed
consumer receipts remain independent evidence.

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
uv run --group consumers streamlit run examples/streamlit/app.py
node examples/vanilla-ts/server.mjs
uv run --group consumers pytest tests/test_streamlit_consumer.py -q
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

The npm install starts with a fresh temporary cache. XYG packages come from
the locally packed archives; the Koffi FFI dependency may be fetched from the
registry, pinned by an override to the exact Node host lockfile version. The
gate checks the installed version and resolves Koffi inside the clean install.
It must not depend on pre-existing cached npm registry metadata. Network access
during dependency installation does not relax browser/app runtime isolation.

The Node browser proof retains the outgoing view before disposal, waits for
Rust tick admission, and verifies destroyed state, listener/frame cleanup, GPU
context release and actual Worker termination before remounting. Removing the
canvas alone does not satisfy cleanup. State polls use synchronous predicates;
a truthy Promise does not prove tick admission or disposal. The Streamlit proof
clicks both export buttons, captures the downloads, verifies filenames, parses SVG chart content
and decodes the PNG at its expected dimensions. Download bytes and hashes are
retained. CI uploads available consumer evidence with `if: always()`, including
after a required smoke fails; the smoke itself remains unconditional and fatal.
The browser runner defaults to a failed exit until the complete report is
written, so an incomplete asynchronous journey cannot be reported as success.

The same installed consumer gate preserves the public HTML density degradation
proof from #1065. `tests/fixtures/packaged_density_export.py` produces a real
`Chart.to_html()` document with the installed wheel; the framework-free
`scripts/packaged_density_export_browser.mjs` withholds or corrupts its optional
inline WASM module. Both cases require unchanged Rust overview/grid/texture,
colored zoom pixels, exact home ranges and released Workers/object URLs. Home
display readback allows at most one integer channel value of rounding while
requiring identical grid bytes and texture identity; zoom must exceed that
rounding tolerance, and observed deltas are recorded. Reports,
screenshots and the compressed generated document stay in the existing CI
evidence directory. The former compiled Reflex app and its six adapter-only
cases retire; their immutable historical evidence remains unchanged.

Application frameworks live in the `consumers` dependency group, separate from
`dev` and the Matplotlib-only reference lane. Installing Streamlit transitively
installs pandas, which otherwise activates optional pandas compatibility probes
in unrelated suites. The consumer gate exports both locked groups as constraints
but installs framework packages only inside its fresh wheel environment. It
imports AppTest unconditionally, runs `tests/test_streamlit_consumer.py` without
checkout conftest/source-path injection, and rejects zero tests, failures, errors
or skips in the resulting JUnit record. Browser checks then exercise the same
installed environment. This boundary isolates framework dependencies without
softening the required Streamlit tests or changing pandas/pyplot product policy.

## Packaged tick and density qualification (#886)

The same clean-install gate also runs `tests/fixtures/packaged_consumer_ticks.py`
with the installed wheel and hosts its public `Chart.to_html(wasm_ticks=True)`
documents with Python's standard HTTP server, with Node absent from its PATH.
The installed Node fixture uses the unchanged vanilla TypeScript `app.ts` mount
for secondary Cartesian and degree-based polar ticks. Both hosts serve explicit
paired local Worker/WASM URLs under CSP; neither infers iframe asset URLs.
The shared `scripts/packaged_consumer_browser.mjs` checks actual admitted Rust
cache slots, formatted labels and colored plot pixels. Angular/radial slots
retain the painter's `x`/`y` identities, with explicit polar coordinates and
degree units; the secondary Cartesian case additionally requires `y2`.

Each host also serves a missing module (HTTP 404) and a genuinely corrupt
four-byte module (HTTP 200, bytes `00 01 02 03`). The latter reaches
`WebAssembly.compile` rejection with valid HTML/Worker framing. These tick
failures leave empty fail-closed slots, preserve chart paint, emit
`XYG_WASM_INIT_FAILED` and terminate the failed Worker. They are distinct from
the optional inline-density failures already covered by the public file export.

One ordinary installed Node split-density payload qualifies the applicable
unsupported-source boundary through the public kernel-less `ChartView` API.
Its native `wasm_density.unsupported` descriptor is consumed unchanged alongside
its raw split buffers; the fixture does not synthesize that descriptor into
packed HTML or promise a host callback. Actual public zoom/home state and live
refinement scheduling must report `XYG_WASM_SOURCE_UNSUPPORTED` with the native
reason and trace identity. Overview/grid/texture identity and zero replacement
uploads remain exact; zoom pixels must change by more than one channel value,
while restored home pixels allow at most one value of presentation rounding.
Only the explicit tick Worker exists. Every new case checks GL/context release,
listener/frame cleanup, actual Worker termination, zero object URLs and no
late events after destruction. Request allowlists reject hidden asset fetches,
off-origin requests and CSP violations.

The report adds fetched module statuses/hashes, input and harness hashes,
events, lifecycle diagnostics and screenshots to the existing schema-1 evidence.
Module evidence captures the single upstream HTTP response body before fulfilling
the intercepted request with those same bytes; it never refetches the module or
reads its body through a Worker CDP target that compile failure may already have
terminated. Collection explicitly awaits the browser response event and transfer
completion, including delayed delivery, and requires exactly one expected module
response with matching status. Missing, duplicate, unexpected or unreadable
responses fail the proof; corrupt bytes must still reach real Worker compilation
and retain their exact four-byte hash. Counts are checked again after cleanup.
The deterministic collector regression runs with
`node --test packages/xy-node/test/packaged-consumer-browser.test.mjs`.
Bounded local receipts and their remaining limitations are recorded in
[`application-consumers-886`](../performance/application-consumers-886/README.md).
Together with the reused public file-export and standalone failure cases,
this gate satisfies amended #886's named supported-consumer correctness
requirements: installed tick admission, local CSP/assets, missing/invalid
modules, unsupported refinement, overview retention and resource cleanup.
This disposition does not claim exhaustive source-family/axis combinations,
complete #108 acceptance or #54's final-candidate artifact qualification.
