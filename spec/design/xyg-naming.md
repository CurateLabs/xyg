# XYG naming matrix and identity migration

**Status:** locked (owner-decided, 2026-08-11). This document is the canonical
naming matrix required by issue #18 ("Establish XYG architecture"). Mechanical
renames follow this matrix; ad-hoc aliases are prohibited. Release/distribution
identity coordinates with #13; user-facing branding/link cleanup with #14.

## 0. Identity

**XYG** is the current product: an independent, GraphForge-oriented graph and
data-visualization engine in which Rust owns every decision that changes
shipped buffers or recorded outcomes, Python and Node are thin host bindings
over one native C ABI, and browser WASM executes the same engine in a Worker. The TypeScript
client owns paint, pick, gestures, transport, and DOM presentation.

**XY** is provenance. This repository began as a fork of `reflex-dev/xy`
(upstream license and attribution are preserved — see `LICENSE`); the
divergence is permanent product divergence, not temporary fork cleanup.

### XY-vs-XYG usage policy

- Use **XYG** for the current product everywhere: architecture, docs, specs,
  examples, benchmarks, error text, and all new code and identifiers.
- Use **XY** only for: (a) historical provenance and upstream comparison,
  (b) inherited compatibility surfaces that are explicitly documented as such
  (e.g. the matplotlib-compat corpus inherited from upstream evidence),
  (c) attribution required by the upstream license, and (d) identifiers whose
  migration is scheduled for a later stage in §3 (each one is enumerated
  there — an identifier is never "grandfathered" silently).
- The stale-name gate (`scripts/check_stale_names.py`) enforces this policy
  mechanically; its allowlist is the machine-readable twin of §3.

## 1. Canonical naming matrix (decided)

| Surface | Old (XY) | New (XYG) | Status |
|---|---|---|---|
| Product name | XY | **XYG** | decided |
| Safe Rust engine crate | — (mixed into `xy-core`) | **`crates/xyg-engine`** (`xyg_engine`) | decided |
| C ABI shell crate | `xy-core` (`xy_core`) | **`crates/xyg-core`** (`xyg_core`) | decided |
| Shipped cdylib artifact | `libxy_core.so` / `libxy_core.dylib` / `xy_core.dll` | **`libxyg_core.so` / `libxyg_core.dylib` / `xyg_core.dll`** (one artifact per platform; wasm target packs as `libxyg_core.so`) | decided |
| C ABI symbol prefix | `xy_*` (e.g. `xy_abi_version`) | **`xyg_*`** (e.g. `xyg_abi_version`); prefix change ships with the ABI 58 bump, so an old wrapper can never half-bind a new library | decided |
| ABI contract | — (declarations duplicated by hand) | **`spec/abi/xyg-abi.json` + `xyg.h`**, generated with Python ctypes and Node Koffi declarations from `crates/xyg-core/src/lib.rs` by `scripts/gen_abi_manifest.py`; byte-for-byte checked by `scripts/check_abi_parity.py` | landed (#57) |
| Python distribution | `xy` | **`xyg`** | landed (`pyproject.toml` / wheels / `pip install xyg`) |
| Python import namespace | `import xy` (`python/xy/`) | **`import xyg`** (`python/xyg/`) | landed (#51); no compatibility alias |
| Bundled Reflex adapter | **`reflex_xy`** (`python/reflex_xy/`) | unchanged; extra spelled `xyg[reflex]` | retained by #51 product decision |
| Paint client (npm) | (Python `python/xyg/static` only) | **`@curatelabs/xyg`** (owned by #23; listed so the matrix is complete) | decided |
| Node package | `@xy/node` (`packages/xy-node/`) | **`@curatelabs/xyg-node`** (in-tree directory stays `packages/xy-node`; never publish `@xy/node`) | decided (owner; npm scope locked with #24/#23) |
| Node exact-platform natives | (none; repo/`_native_lib` only) | **`@curatelabs/xyg-node-{darwin-arm64,darwin-x64,linux-x64,linux-arm64,win32-x64}`** as optionalDependencies of the facade; Windows arm64 unsupported; inventory/hashes/budgets via `scripts/verify_node_packages.py` | release staging plus native clean-install/load/export matrix landed; registry and VS Code remote conformance remain (#52) |
| Native-lib override env var | `XY_NATIVE_LIB` | **`XYG_NATIVE_LIB`** (both hosts; packaged paths otherwise — never a broadened system search) | decided |
| Build-hook env switches | `XY_SKIP_CARGO`, `XY_REQUIRE_CARGO`, `XY_SKIP_NODE`, `XY_CARGO_TARGET`, `XY_WHEEL_PLATFORM` | **`XYG_SKIP_CARGO`, `XYG_REQUIRE_CARGO`, `XYG_SKIP_NODE`, `XYG_CARGO_TARGET`, `XYG_WHEEL_PLATFORM`** | decided |
| Release publish guard | `XY_ALLOW_PYPI_PUBLISH` (#13) | **`XYG_ALLOW_PYPI_PUBLISH`** | decided |
| SIMD kill switch (read by the engine) | `XY_SIMD` | **`XYG_SIMD`** | decided |
| Expected-ABI test override | `XY_EXPECTED_ABI` | **`XYG_EXPECTED_ABI`** | decided |
| Browser executable override | `XY_BROWSER` | **`XYG_BROWSER`** | landed; public export configuration, no retired alias |
| Chromium-specific executable override | `XY_CHROMIUM` | **`XYG_CHROMIUM`** | landed; public export configuration, no retired alias |
| Repository slug | `CurateLabs/graphforge-xy` (fork of `reflex-dev/xy`) | **`CurateLabs/xyg`** (renamed server-side 2026-08-11; old URLs redirect) | decided (owner, 2026-08-11) |
| Release publish-guard repo condition | `github.repository == 'CurateLabs/graphforge-xy'` | **`github.repository == 'CurateLabs/xyg'`** | decided |

At the identity cutover no XYG release had shipped, so the Python/Node renames
were a clean break with **no compatibility alias**, per the owner's direction.
The old `XY_*` environment variables above were removed rather than aliased.
That historical cutover is not a current no-consumers guarantee: the registry
snapshot on 2026-10-14 contains PyPI `xyg` 0.0.1a2. Both npm packages remain
unpublished. Subsequent compatibility decisions must account for released users.

## 2. Deferred identifiers (recorded, later stages)

These are current-product XY identifiers whose rename is deliberately staged
later; the stale-name gate allows them by explicit allowlist entry until their
stage lands. Proposed targets are recorded so the later rename is mechanical.

| Surface | Today | Proposed | Stage |
|---|---|---|---|
| Browser standalone global | `window.xy` (IIFE bundle name in `js/build.mjs`) | `window.xyg` | browser/branding stage (#14) — changes every embedding example and smoke |
| Root DOM class / CSS namespace | `class="xy"` (`js/src/50_chartview.ts`) | `class="xyg"` | browser/branding stage (#14) — public styling surface, coordinate with docs |
| Wire-protocol constants | `XY_FRAME_MAGIC`, `XY_FRAME_VERSION`, `XY_PAYLOAD_MAGIC`, … (Python + TS) | `XYG_*` with a protocol-version bump | wire-protocol stage — byte-level magic changes need migration evidence (`spec/design/wire-protocol.md`) |
| Widget/anywidget module + static bundle names | `python/xyg/static/{index,standalone}.js` internals | unchanged paths until `import xyg`; internal names follow browser stage | browser/branding stage (#14) |
| Dev/test/bench env knobs | `XY_LIVE_POINTS`, `XY_CONTEXT_GOVERNOR`, `XY_NOTEBOOK_DISPLAY`, `XY_SHARED_WEBGL`, `XY_POLAR_AA`, and other dev-only `XY_*` knobs | `XYG_*` sweep | branding stage (#14) — dev-only, no product artifact depends on them |
| Benchmark/report arm keys | `xy`, `xy-exact` in committed benchmark schemas, CLI selectors, and historical result assets | `xyg`, `xyg-exact` with an explicit report-schema migration | cross-host release evidence (#40) — display labels must say XYG now; machine keys remain stable until readers and baselines migrate together |
| Python-internal constant prefixes | `XY_OK`, `XY_ERROR`, `XY_VERSION`, … (module-level constants) | `XYG_*` | with the wire/branding stages that own each constant |
| README, user docs, branding sweep | inherited visual identity | **XYG** wordmark, chart hero, and social card | public copy/assets corrected; versioned browser/wire renames remain deferred |
| Historical repository slugs | `graphforge-xy`, `reflex-dev/xy` | permitted only in provenance/evidence contexts (old URLs redirect); current-product references use `CurateLabs/xyg` | policy (gate-enforced) |
| Public documentation platform and origin | inherited Reflex app and `https://reflex.dev/docs/xy` | Astro Starlight at `docs/app`, sourced from public `docs/` Markdown; explicit CurateLabs-owned public URL configuration | public base `/docs/xy/` retained; no Reflex docs shell or deployment origin is implied; unset preview origins omit absolute canonical/social URLs |
| Upstream-inherited corpus/fixtures | `scripts/rename_fc_to_xy.py`, matplotlib compat corpus labels | permitted historical evidence | never (provenance) |

The host-relative `/docs/xy/` route, `xy-*` DOM/event/CSS prefixes,
`xy_client.js` asset name, and `packages/xy-node/` source directory are
compatibility or protocol surfaces rather than the Python product identity.
They remain unchanged in #51 and must never be presented as the current
package, import namespace, or product brand. The browser compatibility global
likewise remains only `window.xy`, `xy.renderStandalone`, and `xy.decodeFrame`
until its separately versioned migration.

Current repository, build, release, and contributor metadata use the XYG
identity: the private root npm tool package is
`xyg-dev-tools`, and current workflow step labels and top-level guidance say
XYG. The stale-name gate checks these structural locations directly so prose
or package metadata cannot regress while the explicitly versioned exceptions
above remain available.

## 3. Migration order (no mixed intermediate artifact)

The rule: **no published artifact may combine an old host wrapper with a
newly named or ABI-incompatible library.** Order of operations, all landing in
one reviewed PR on `main` before any release tag:

1. **Lock this matrix + spec framing** (this document; `spec/README.md`,
   `spec/design-dossier.md`, `spec/design/rust-engine.md`,
   `spec/design/host-parity.md`).
2. **Cargo workspace split** — `crates/xyg-engine` (safe algorithms + policy)
   and `crates/xyg-core` (C ABI shell). The shipped artifact becomes
   `libxyg_core` at this step. Repo-internal only; nothing is published from
   an intermediate commit.
3. **ABI contract** — symbol prefix `xyg_*`, lockstep `ABI_VERSION` (58 at
   the crate-split landing; 59 adds `xyg_stream_*`; 60 adds the first
   versioned canonical scene records; 61 adds canonical numeric ticks; 62 adds
   canonical numeric scale mapping), generated
   manifest, and the parity gate. Python ctypes, Node koffi, and the ABI smoke
   are re-bound to the new names **in the same change** as the Rust rename, so
   at every commit each host either fully matches the library it loads or
   fails loudly at load (`xyg_abi_version` is bound and checked first).
4. **Build/distribution paths** — `hatch_build.py`, wheel/sdist verification,
   Cargo, CI, benchmark and smoke scripts all locate `libxyg_core`.
5. **Host namespace renames** — Node package.json becomes `@curatelabs/xyg-node`
   with this crate split (directory stays `packages/xy-node`). Python
   `import xyg` / `python/xyg/` lands after the crate split, native artifact,
   and Node lookup; the `reflex_xy` integration namespace remains stable. The
   **distribution** name `xyg` (wheels,
   sdists, `pip install xyg`, `importlib.metadata.version("xyg")`) lands with
   the crate-split PR so PyPI trusted publishing can claim project `xyg`.
   The old `xy` import is intentionally absent after the clean cutover.
6. **Stale-name gate** — `scripts/check_stale_names.py` turns the policy in
   §0/§2 into a repository-wide check.

Safety properties: the ABI version bump plus the symbol-prefix change make old
and new libraries mutually unloadable by the wrong wrapper (an old wrapper
finds no `xy_abi_version` in a new library and fails before binding anything;
a new wrapper fails the same way against an old library). The original cutover
preceded the fork's first publication. Future tagged artifacts still require
every host wrapper to match the native library; the existence of a published
alpha does not relax that release contract.

## 4. Follow-ups recorded for later stages

- Python `xyg` release coverage and `@curatelabs/xyg-node` npm registration: #13.
- README, user docs, repository links, branding sweep, deferred identifier
  batches in §2: #14.
- Phase-4 tile spill (#5–#11): WP1 (#8) re-landed in `crates/xyg-engine` (ABI 73); its
  future home is `crates/xyg-engine`.
- Graph force-layout process-wide mutex: separate concurrency defect, tracked
  outside this migration (issue #18 implementation notes).

## 5. Python import cutover checklist (#51)

**Landed identity:**

| Fact | Value |
|---|---|
| Distribution / PyPI project | `xyg` (`pyproject.toml` `name`, wheels, `pip install xyg`) |
| Import namespace | `import xyg` from `python/xyg/` |
| Reflex adapter | `reflex_xy` — **retained** for #51 |
| Compatibility alias | **None** — `import xy` fails |

**Completed cutover steps (one coherent change; no published mixed artifact):**

1. `git mv python/xy python/xyg` (and update hatch `packages` / sdist includes / artifacts to `python/xyg/**`).
2. Rewrite every product `import xy` / `from xy…` to `xyg` (tests, examples, docs, scripts, benches, and Reflex adapter imports of the chart package — adapter package name stays `reflex_xy`).
3. Update `hatch_build.py` destinations (`python/xyg/_native_lib`, `python/xyg/static`).
4. Update `scripts/verify_wheel.py` / `verify_sdist.py` expected paths (`xyg/_native_lib/…`, `xyg/static/…`).
5. Keep `python/reflex_xy` / `import reflex_xy`; extra remains `xyg[reflex]`.
6. Refresh this matrix status to **landed**, clear stale allowlist entries that existed only for the old Python tree, and update host-parity / production-readiness wording.
7. Prove BDD: clean `pip install` of wheel/sdist → `import xyg` renders; `import xy` raises `ModuleNotFoundError`.

**Guardrail:** `tests/test_xyg_package_identity.py` locks the landed distribution/import identity, absence of the old namespace, and retained `reflex_xy` adapter.

## 6. Public positioning and evidence contract

XYG was forked from upstream XY because GraphForge needed billion-scale graph
visualization. Lead with graph visualization and charting for **Python,
Node-native, and browser WASM**, powered by one Rust engine. Everyday plots,
custom application visuals, and large-data exploration remain first-class
across notebooks, applications, and static exports. Host identities belong in
the introduction, installation paths, and social metadata; Python examples do
not make this a Python-only product.

State the billion-scale graph goal separately from demonstrated capacity:
the recorded graph-scale diagnostic executes through 1M source nodes, while
its 1B rows check LOD policy without materializing or rendering that graph.
Scatter/density capacity is a different workload. Browser WASM is a bounded
direct-execution foundation, not a claim of complete Python/Node feature parity.

Current-facing imagery must depict **XYG**, not upstream XY or a Reflex product.
The README hero is `spec/assets/xyg-sdf-binned-scatter.png`; docs social assets
use XYG typography and the graph-first, three-host identity. The old XY hero
and benchmark assets are historical evidence, not current brand assets.
Preserve upstream license notices and identify provenance separately from the
current CurateLabs/XYG identity.

The public documentation platform is **Astro Starlight**, following CurateLabs'
other documentation sites. `docs/app` contains the static-site build;
`docs/` Markdown remains the authoring source. The public base stays
`/docs/xy/` for link compatibility. Executable example fences contain host-neutral chart authoring and are
compiled at build time into native chart previews, without requiring a
framework docs runtime. The site navigation and
landing/integration/deployment guidance lead with **Use with GraphForge**.
Reflex is upstream provenance and a retained optional technical adapter; it is
not XYG's product identity or required application framework. Source-only
adapter references may remain where they accurately document that code.

README and public docs describe current source behavior and distinguish it
from dated registry availability. An owned deployment must configure its
origin explicitly; a preview must not borrow Reflex's origin. Navbar, page,
search, and social metadata use the same graph-first, three-host position as
the visible introduction. Metadata is part of the claim surface.

Public architecture guidance explains the fork's Python-to-Rust migration:
row processing and decisions that change geometry, encodings, layout, ticks,
LOD, GraphForge composition, and recorded outcomes belong to the shared Rust
engine. Python/Node native bindings and browser WASM invoke that implementation;
hosts keep idiomatic APIs, packaging, transport, and lifecycle. Parity claims
name their tested contracts, not universal API or pixel equivalence. Browser
WASM remains bounded, including the rendered GraphForge Scene's 1,024-node
ceiling and primitive budget. Broader native authoring and export coverage
must not be implied for the browser host.

Claims must name their scope: browser CSS/Tailwind chrome versus validated
mark/axis/theme styling and renderer-specific export support; aggregated
overviews versus exact points; source-row ingest/preparation versus bounded
draw/transport work; live-kernel refinement versus standalone HTML. Slot counts
come from the generated capability matrix instead of hand-maintained headlines.
OpenStreetMap demonstrates roughly 10.7 billion **node locations** as density,
with dedicated disk preparation, not all map entities or semantics.

Public performance numbers require archived raw runs, environments, source
versions, output contracts, and relevant competitors. The unarchived UX
headline table is withdrawn; see `spec/benchmarks/results.md`. Do not relabel
upstream historical measurements as current XYG results or imply a universal
performance/customization win over Matplotlib, Seaborn, Plotly, Bokeh, Altair,
Datashader, HoloViews/hvPlot, or emerging alternatives.
