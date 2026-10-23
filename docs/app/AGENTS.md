# XYG docs application

Use Astro Starlight, consistent with the other CurateLabs documentation sites.
The repository's public Markdown lives in `docs/` and is authoritative; keep the
platform contract in `spec/design/docs-starlight.md` current.

`docs/app/` is a private npm application. Its production output is static HTML,
CSS, JavaScript, Markdown, and native binary chart snapshots in `dist/`.
The site must not require a Python web server. Python and Rust are build tools
for compiling the original XYG examples and inspecting real public APIs.

Do not edit or commit generated `src/content/docs/`, `public/`, `.generated/`,
`.astro/`, or `dist/`. Edit source Markdown, preparation scripts, Astro
components, and styles. Preserve `/docs/xy/` routes and useful legacy redirects.

Chart previews must use actual XYG data and native compiled payloads with the
shared browser client. Do not replace examples with unrelated charts, or move
layout, LOD, encoding, or graph policy into documentation JavaScript. Explain
initial snapshots and application-host requirements for stateful examples.

Lead with GraphForge use and the shared Rust core across Python, Node, and
browser WASM. Distinguish measured results, supported features, and goals.
Application consumers use Streamlit/Python or Node/vanilla TypeScript as described
in `spec/design/application-consumers.md`. No framework adapter ships in the SDK.

Run the commands in README.md. CI checks the static site, links, Markdown/API
exports, and real charts in Chromium and retains a build artifact. Publishing
requires an explicitly configured owned HTTPS URL; do not invent a public docs
domain or add deployment credentials.
