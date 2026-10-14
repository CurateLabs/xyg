# XYG documentation site

The public docs use Astro Starlight, matching the CurateLabs GraphForge docs.
Canonical Markdown lives one directory above this application. The site is
static: production needs no Python or application server.

From the repository root:

```bash
cargo build --release
npm ci
node js/build.mjs
uv sync --group dev
npm ci --prefix docs/app
npm run check --prefix docs/app
npm run build --prefix docs/app
npm run test --prefix docs/app
node docs/app/scripts/browser-smoke.mjs
npm run preview --prefix docs/app
```

Preview the built site at `http://localhost:4321/docs/xy/`. Use `npm run dev
--prefix docs/app` for development. Node 22.12 or newer is required; use a current
npm release supported by Astro.

Build preparation compiles the original chart examples through Python and the
Rust core into binary first-paint frames. The published site uses the shared
browser renderer for paint, picking, pan, and zoom. Stateful examples show an
initial snapshot and explain when updates need an application host. The static
site contains no second implementation of chart policy.

`src/content/docs/`, `public/`, `.generated/`, `.astro/`, and `dist/` are generated
and ignored. Page Markdown, API references, `llms.txt`, and `llms-full.txt` are
built from the same content as the HTML. Edit the canonical `docs/*.md` sources,
not generated copies. The native example and content preparation scripts live
in `scripts/`.

The compatibility base remains `/docs/xy/`. Set `XY_DOCS_PUBLIC_URL` to the owned
HTTPS URL ending in `/docs/xy` only for a real deployment. An unset value builds
a preview without public canonical, sitemap, or social-image URLs. CI verifies
and retains the static site; it does not publish it.

The framework migration contract and verification requirements are in
[`spec/design/docs-starlight.md`](../../spec/design/docs-starlight.md).

The code-native brand assets can be rebuilt with:

```bash
uv run --with playwright==1.61.1 python docs/app/scripts/build_brand_assets.py
```
