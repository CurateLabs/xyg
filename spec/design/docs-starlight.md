# Public documentation: Astro Starlight

## Decision and boundary

XYG's public documentation uses Astro Starlight, matching the CurateLabs
GraphForge documentation platform. `docs/app/` is a private npm application,
not a Python web application. It builds a static site in `docs/app/dist/`.
The docs shell requires neither Reflex nor a Python server in production.
Historical attribution to the upstream XY/Reflex project remains separate from
XYG's product identity and GraphForge integration guidance.

Public Markdown under `docs/` remains the authoring source of truth. Internal
`spec/` documents remain repository-only and must never become published
Starlight pages. The build prepares the public Markdown for Starlight in a
local generated content directory; contributors edit the original pages,
not that directory. The npm lock pins the complete documentation toolchain,
and Node 22 is the CI runtime. Generated content, dependencies, Astro caches,
and `dist/` are not committed.

## URLs and content contracts

- Preserve the existing `/docs/xy/` route base, including nested page routes,
  internal links, downloadable Markdown, and documentation indexes. This is a
  compatibility URL, not the current product name.
- Navigation, page titles, descriptions, social metadata, and visual branding
  identify **XYG** as the GraphForge-oriented graph visualization and charting
  engine for Python, Node, and browser WASM.
- The static output includes per-page Markdown and the agent-readable indexes;
  compiled pages, links, metadata, Markdown assets, and live demos are checked
  against the actual built output.
- Public Python demos are compiled against the checked-out XYG package during
  preparation. Their binary first-paint snapshots use the shared browser paint client
  in the static documentation. Stateful examples clearly identify the initial
  snapshot and the application host needed for callbacks or data updates.
  Preview compilation uses XYG's supported fluid width so original chart
  geometry is visible within the responsive docs column; mark data and chart
  heights are retained. Browser checks reject cropped preview canvases. The docs do not replace Rust
  algorithms with JavaScript, depend on the Reflex adapter, or request a
  documentation-specific data server at runtime.
- Examples and API reference content continue to describe the actual exported
  package surface. Preserve source provenance for generated example outputs.

The UI uses Starlight's responsive navigation, theme controls, search, and
code rendering. Its browser smoke checks the production static output and
interactive examples. Accessibility claims describe the checks actually run;
this migration does not certify all screen-reader and OS combinations.

## Reproduction and verification

From a clean checkout, build the native core and shared browser client and
install the root Python development environment before compiling demos:

```bash
cargo build --release
npm ci
node js/build.mjs
uv sync --frozen --group dev
npm ci --prefix docs/app
npm run check --prefix docs/app
npm run build --prefix docs/app
npm run test --prefix docs/app
uv run python scripts/verify_docs_quickstart.py
```

`npm run check` prepares the content and runs Astro's checks. `npm run build`
prepares the same content and builds the static site. `npm run test` runs the
Node tests and built-output validators. `make check-docs` combines these gates
with the existing canonical chart-example checks. Chromium verification runs
separately, after the build:

```bash
npx playwright install chromium
node docs/app/scripts/browser-smoke.mjs
```

The root `.venv` supplies build-time Python dependencies. There is no separate
`docs/app/pyproject.toml`, docs Python lock, Reflex initialization step, or
production backend process. The documentation codespell hook runs a pinned
standalone codespell tool with the docs app's configuration; Ruff continues to
check Python build helpers through the root project configuration.

## CI and deployment

`.github/workflows/docs.yml` builds and verifies the documentation on the
pinned Blacksmith Linux runner. It installs the root checkout, native core,
shared client, and locked Starlight dependencies; runs source checks, static
build, built-output validators, checkout quickstart, Chromium smoke, and
quality hooks; and retains the verified `docs/app/dist/` site as an artifact.
The CI contract uses a single static-site job, replacing the old Python-version
matrix and Reflex production-server polling.

Publishing remains a separate CurateLabs-owned operation. This migration
creates a deployable static artifact, without restoring the removed upstream
registries, Helm chart destination, or reflex.dev promotion workflow. Any
future deployment must specify its origin, `/docs/xy/` base handling, credentials,
and release gate separately.
