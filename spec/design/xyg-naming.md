# XYG naming matrix and identity migration

**Status:** locked (owner-decided, 2026-08-11). This document is the canonical
naming matrix required by issue #18 ("Establish XYG architecture"). Mechanical
renames follow this matrix; ad-hoc aliases are prohibited. Release/distribution
identity coordinates with #13; user-facing branding/link cleanup with #14.

## 0. Identity

**XYG** is the current product: an independent, GraphForge-oriented graph and
data-visualization engine in which Rust owns every decision that changes
shipped buffers or recorded outcomes, Python and Node are thin host bindings
over one native C ABI, and the browser client is paint/pick/gesture/transport
only.

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
| ABI manifest | — (declarations duplicated by hand) | **`spec/abi/xyg-abi.json`**, generated from `crates/xyg-core/src/lib.rs` by `scripts/gen_abi_manifest.py`; parity-checked against Python/Node/smoke declarations by `scripts/check_abi_parity.py` | decided |
| Python distribution | `xy` | **`xyg`** | decided (owner, 2026-08-11; clean break, no alias) |
| Python import namespace | `import xy` (`python/xy/`) | **`import xyg`** (`python/xyg/`) | decided (owner, 2026-08-11) |
| Bundled Reflex adapter | `reflex_xy` (`python/reflex_xy/`) | **`reflex_xyg`** (`python/reflex_xyg/`); extra spelled `xyg[reflex]` | decided (owner, 2026-08-11) |
| Paint client (npm) | (Python `python/xy/static` only) | **`@curatelabs/xyg`** (owned by #23; listed so the matrix is complete) | decided |
| Node package | `@xy/node` (`packages/xy-node/`) | **`@curatelabs/xyg-node`** (in-tree directory stays `packages/xy-node`; never publish `@xy/node`) | decided (owner; npm scope locked with #24/#23) |
| Native-lib override env var | `XY_NATIVE_LIB` | **`XYG_NATIVE_LIB`** (both hosts + Bazel wrappers; packaged paths otherwise — never a broadened system search) | decided |
| Build-hook env switches | `XY_SKIP_CARGO`, `XY_REQUIRE_CARGO`, `XY_SKIP_NODE`, `XY_CARGO_TARGET`, `XY_WHEEL_PLATFORM` | **`XYG_SKIP_CARGO`, `XYG_REQUIRE_CARGO`, `XYG_SKIP_NODE`, `XYG_CARGO_TARGET`, `XYG_WHEEL_PLATFORM`** | decided |
| Release publish guard | `XY_ALLOW_PYPI_PUBLISH` (#13) | **`XYG_ALLOW_PYPI_PUBLISH`** | decided |
| SIMD kill switch (read by the engine) | `XY_SIMD` | **`XYG_SIMD`** | decided |
| Expected-ABI test override | `XY_EXPECTED_ABI` | **`XYG_EXPECTED_ABI`** | decided |
| Bazel cdylib target | `//:xy_core` → `libxy_core.so` | **`//:xyg_core`** → `libxyg_core.so` | decided |
| Repository slug | `CurateLabs/graphforge-xy` (fork of `reflex-dev/xy`) | **`CurateLabs/xyg`** (renamed server-side 2026-08-11; old URLs redirect) | decided (owner, 2026-08-11) |
| Release publish-guard repo condition | `github.repository == 'CurateLabs/graphforge-xy'` | **`github.repository == 'CurateLabs/xyg'`** | decided |

Because **no XYG release has ever shipped** (the fork has published nothing to
PyPI or npm), there are no external consumers to migrate: the Python/Node
renames are a clean break with **no compatibility alias**, per the owner's
direction. The old `XY_*` environment variables above are likewise removed,
not aliased; they are documented here as the historical names.

## 2. Deferred identifiers (recorded, later stages)

These are current-product XY identifiers whose rename is deliberately staged
later; the stale-name gate allows them by explicit allowlist entry until their
stage lands. Proposed targets are recorded so the later rename is mechanical.

| Surface | Today | Proposed | Stage |
|---|---|---|---|
| Browser standalone global | `window.xy` (IIFE bundle name in `js/build.mjs`) | `window.xyg` | browser/branding stage (#14) — changes every embedding example and smoke |
| Root DOM class / CSS namespace | `class="xy"` (`js/src/50_chartview.ts`) | `class="xyg"` | browser/branding stage (#14) — public styling surface, coordinate with docs |
| Wire-protocol constants | `XY_FRAME_MAGIC`, `XY_FRAME_VERSION`, `XY_PAYLOAD_MAGIC`, … (Python + TS) | `XYG_*` with a protocol-version bump | wire-protocol stage — byte-level magic changes need migration evidence (`spec/design/wire-protocol.md`) |
| Widget/anywidget module + static bundle names | `python/xy/static/{index,standalone}.js` internals | unchanged paths until `import xyg`; internal names follow browser stage | browser/branding stage (#14) |
| Dev/test/bench env knobs | `XY_BROWSER`, `XY_CHROMIUM`, `XY_LIVE_POINTS`, `XY_CONTEXT_GOVERNOR`, `XY_NOTEBOOK_DISPLAY`, `XY_SHARED_WEBGL`, `XY_POLAR_AA`, and other dev-only `XY_*` knobs | `XYG_*` sweep | branding stage (#14) — dev-only, no product artifact depends on them |
| Python-internal constant prefixes | `XY_OK`, `XY_ERROR`, `XY_VERSION`, … (module-level constants) | `XYG_*` | with the wire/branding stages that own each constant |
| README, user docs, branding sweep | README branding, docs-app copy | — | #14 (explicitly out of scope here) |
| Historical repository slugs | `graphforge-xy`, `reflex-dev/xy` | permitted only in provenance/evidence contexts (old URLs redirect); current-product references use `CurateLabs/xyg` | policy (gate-enforced) |
| Upstream-inherited corpus/fixtures | `scripts/rename_fc_to_xy.py`, matplotlib compat corpus labels | permitted historical evidence | never (provenance) |

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
3. **ABI contract** — symbol prefix `xyg_*`, `ABI_VERSION = 58`, generated
   manifest, and the parity gate. Python ctypes, Node koffi, and the ABI smoke
   are re-bound to the new names **in the same change** as the Rust rename, so
   at every commit each host either fully matches the library it loads or
   fails loudly at load (`xyg_abi_version` is bound and checked first).
4. **Build/distribution paths** — `hatch_build.py`, wheel/sdist verification,
   Bazel, CI, benchmark and smoke scripts all locate `libxyg_core`.
5. **Host namespace renames** — Node package.json becomes `@curatelabs/xyg-node`
   with this crate split (directory stays `packages/xy-node`). Python
   `import xyg` / `python/xyg/` / `reflex_xyg` is decided (§1) but **staged
   after** the crate split, native artifact, and Node lookup so Python package
   churn cannot block `libxyg_core`. Until that commit, hosts still import
   `xy` from `python/xy/`.
6. **Stale-name gate** — `scripts/check_stale_names.py` turns the policy in
   §0/§2 into a repository-wide check.

Safety properties: the ABI version bump plus the symbol-prefix change make old
and new libraries mutually unloadable by the wrong wrapper (an old wrapper
finds no `xy_abi_version` in a new library and fails before binding anything;
a new wrapper fails the same way against an old library). Because publishing
happens only from tagged `main` after the full sequence merges — and no XY or
XYG artifact has ever been published from this fork — no intermediate mixed
artifact can exist.

## 4. Follow-ups recorded for later stages

- Python `xyg` / `@curatelabs/xyg-node` first-release version line and PyPI/npm project
  registration: #13.
- README, user docs, repository links, branding sweep, deferred identifier
  batches in §2: #14.
- Phase-4 tile spill (#5–#11): WP1 (#8) is paused pending the crate split; its
  future home is `crates/xyg-engine`.
- Graph force-layout process-wide mutex: separate concurrency defect, tracked
  outside this migration (issue #18 implementation notes).
