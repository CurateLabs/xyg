# Specification

The root-level `spec/` directory is XYG's engineering source of truth:
intended behavior, architecture, compatibility, benchmarks, release readiness,
and contributor contracts. The public documentation lives directly under
`docs/`, while the Reflex application that renders it lives in `docs/app/`.

**XYG** is an independent, GraphForge-oriented graph and data-visualization
engine: Rust owns every decision that changes shipped buffers or recorded
outcomes, Python and Node are thin host bindings over one native C ABI
(`libxyg_core`), and the browser client is paint/pick/gesture/transport only.
The project began as a fork of `reflex-dev/xy`; **XY** appears in this tree
only as historical provenance, upstream comparison, inherited compatibility
evidence, or license attribution. The canonical naming matrix and the staged
identity migration live in [`design/xyg-naming.md`](design/xyg-naming.md).

Keep this tree current with every relevant code, configuration, build, and
release change. A change is incomplete while its affected specification is
missing, stale, or inconsistent with the implementation; resolve discrepancies
instead of treating the implementation alone as authoritative.

**Install doors.** Python: `pip install xyg` (import remains `xy` until the
staged `python/xyg/` cutover). JavaScript / browser: `npm install @curatelabs/xyg`.
Node host: `npm install @curatelabs/xyg-node` (registry publish still #13).

[`design-dossier.md`](design-dossier.md) is the entry point — the single
compiled record of the design, the competitive research behind it, the
performance estimates, and the audit trail. Code comments cite its sections by
number (e.g. §16 = deep-zoom re-centering).

## api/

The public surface: what callers can build, style, export, and interact with.

- [`api-examples.md`](api/api-examples.md) — copyable examples for every
  implemented 2D chart family; the Python snippets are executed by
  `tests/test_docs_examples.py`, so API drift fails the suite.
- [`chart-kind-contract.md`](api/chart-kind-contract.md) — how to add a 2D chart
  type: what the shared machinery provides and what a new kind must supply.
- [`capability-matrix.md`](api/capability-matrix.md) — **generated**: the
  inventory of what can be styled and extended, per renderer, from
  `python/xy/styling/capabilities.py`.
  Regenerate with `scripts/gen_capability_matrix.py --write`; the test suite
  fails if it is stale.
- [`chart-roadmap.md`](api/chart-roadmap.md) — the staged chart-type coverage
  backlog, from core 2D through geographic, 3D, and volume visualization.
- [`export.md`](api/export.md) — how a figure becomes bytes: one entry point
  across five image formats, deterministic engine choice, browser-free default.
- [`interaction.md`](api/interaction.md) — the authority on which browser
  interactions exist, which are configurable, and every event payload.
- [`styling.md`](api/styling.md) — the implementation contract for CSS-addressable
  chrome, per-slot styles, and the documented static-render approximations.

## design/

Internal architecture: how the engine is built and why.

- [`chart-grammar.md`](design/chart-grammar.md) — the declarative composition
  model (`Chart` + `Mark` + `Axis` + `Legend`), fixed before the catalog grows.
- [`animation.md`](design/animation.md) — declarative entrance/update/exit
  motion, stable identity, interruption, reduced motion, and export determinism.
- [`lod-architecture.md`](design/lod-architecture.md) — the Tier 0/1/2/3
  LOD/drilldown design that keeps large data truthful and interactive.
- [`pan-and-zoom-configuration.md`](design/pan-and-zoom-configuration.md) — the
  flat per-axis viewport-navigation contract: capability/action/axis/source
  switches, `zoom_limits`, reset, and the semantic `ranges` view events.
- [`reflex-integration.md`](design/reflex-integration.md) — the bundled
  `xy[reflex]` integration design: figures as first-class Reflex components over a second
  socket.io namespace.
- [`reflex-shaped-api.md`](design/reflex-shaped-api.md) — how the core package
  feels Reflex-shaped while keeping no Reflex dependency.
- [`renderer-architecture.md`](design/renderer-architecture.md) — audit of the
  shipped WebGL2 render path plus the architecture it converges to.
- [`rust-engine.md`](design/rust-engine.md) — the Rust workspace
  (`crates/xyg-engine` + `crates/xyg-core`), what lives in Rust vs the hosts,
  and how the C-ABI/FFI seam evolves without rewrites.
- [`scene-ir.md`](design/scene-ir.md) — versioned, bounded canonical scene
  records and the #58 vertical-slice migration from host render policy to Rust.
- [`xyg-naming.md`](design/xyg-naming.md) — the locked XYG naming matrix, the
  XY-vs-XYG usage policy, and the identity-migration order.
- [`host-parity.md`](design/host-parity.md) — three runtime surfaces; Rust owns
  decisions; Python and Node stay thin loaders over one C ABI.
- [`host-neutral-architecture.md`](design/host-neutral-architecture.md) —
  sequenced plan so Python exists only when the user is using Python: crate
  split (#18), `stream.rs` (#22), paint client `@curatelabs/xyg` (#23), Node
  host `@curatelabs/xyg-node` (never publish `@xy/node`). Tracking: GitHub #24.
- [`view-state.md`](design/view-state.md) — the unified view-state layer:
  one serializable state object behind history, programmatic zoom/pan/select,
  axis-scoped gestures, and framework-owned tooltips.
- [`wire-protocol.md`](design/wire-protocol.md) — the client↔Python message
  catalog, first-paint buffer layouts, and the version handshake.

## abi/

Machine-checkable C ABI contract for `libxyg_core`.

- [`xyg-abi.json`](abi/xyg-abi.json) — **generated** from
  `crates/xyg-core/src/lib.rs` by `scripts/gen_abi_manifest.py`, including
  ordered names, widths, pointer direction/depth, and buffer metadata.
- [`xyg.h`](abi/xyg.h) — generated C header for the same contract.

The same command generates `python/xy/_abi_generated.py` and
`packages/xy-node/src/_abi_generated.js`. `scripts/check_abi_parity.py`
checks all artifacts byte-for-byte; do not hand-edit any of them.

## matplotlib/

The `xy.pyplot` shim and its corpus-defined compatibility contract.

- [`compat.md`](matplotlib/compat.md) — the supported `xy.pyplot` surface and
  what the one-line import change does and does not promise.
- [`compat-matrix.md`](matplotlib/compat-matrix.md) — method-by-method
  compatibility against the pinned upstream revision. Generated by
  `scripts/sync_matplotlib_compat.py`; do not hand-edit.
- [`compat-changelog.md`](matplotlib/compat-changelog.md) — changes to the
  upstream compatibility target and to the meaning of the compatibility levels.
- [`shim-todo.md`](matplotlib/shim-todo.md) — the audit and remaining work to
  make the shim reliable, separating the supported target from full parity.

## benchmarks/

Measured numbers and the rules that make them defensible.

- [`results.md`](benchmarks/results.md) — the cross-library scatter comparison:
  point ceiling, speed, memory, and payload size per library.
- [`metrics.md`](benchmarks/metrics.md) — the current regression metric table.
  Emitted by `scripts/check_regressions.py --emit-md` in CI; do not hand-edit.
- [`methodology.md`](benchmarks/methodology.md) — how numbers are produced:
  mode-scoped, reproducible, oracle-checked, and publishing the cases we lose.

## process/

Release bar, contribution rules, and audit trail.

- [`contributing.md`](process/contributing.md) — the contribution bar and the
  production invariants a change must not lose.
- [`production-readiness.md`](process/production-readiness.md) — the release
  bar, separating hard gates from advisory measurements.
- [`rendering-verification.md`](process/rendering-verification.md) — the
  LOD-invariant property tests and golden visual-regression corpus that make
  renderer churn safe.
- [`security-audit-2026-07-06.md`](process/security-audit-2026-07-06.md) —
  scope, findings, and status of the 2026-07-06 source audit.
- [`tailwind-customizability-audit-2026-07-26.md`](process/tailwind-customizability-audit-2026-07-26.md)
  — Tailwind source discovery, cascade ownership, live updates, slot coverage,
  production-browser matrix, and remaining browser boundaries.
- [`css-tailwind-surface-audit-2026-07-30.md`](process/css-tailwind-surface-audit-2026-07-30.md)
  — component-by-component DOM/canvas audit, granular modebar/colorbar/axis
  slots, matched browser evidence, and the CSS/Tailwind ownership boundary.

## assets/

Files under `assets/` are dated evidence snapshots; their recorded dates are
intentional and do not represent the freshness of the current regression gates.

- [CodSpeed benchmark snapshot](assets/benchmark-snapshot.svg) records the
  historical 2026-07-09 run described in its caption.
- [Launch benchmark comparison](assets/launch-benchmark-comparison.svg) is the
  comparison graphic used by the repository README.
