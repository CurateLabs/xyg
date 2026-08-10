# Host parity — Python and Node

**Status:** requirements / architecture intent. Python and Node hosts share one
viz Rust C ABI and one WebGL client so **all chart types** have the same
semantics on both languages.

**Priority:** **graph visualization** is the core feature and the first surface
that must prove dual-host end to end
([graph-fork-requirements.md](graph-fork-requirements.md)). Other chart types
keep the same first-class API feel and speed — sequencing graph first is fine;
a degraded non-graph path is not.

**Architecture principle — Rust-first for binding parity:** do **as much as
possible in the shared Rust C ABI** so Python and Node stay thin loaders over
identical behavior. Prefer moving logic into Rust whenever leaving it in a host
would force a second implementation or risk semantic drift. Hosts own
ergonomics and idiomatic I/O only; the JS client owns screen-bounded draw and
gestures only.

---

## 1. Goal

| Layer | Shared across Python and Node |
|---|---|
| Rust viz `cdylib` C ABI | All kernels (existing marks + `xy_graph_*`) |
| Wire / §29 buffers | Identical binary payloads for the same figure spec |
| JS render client | One bundled WebGL client |
| Public chart semantics | Same mark kinds, options, defaults, layout/LOD decisions |

Host-only differences are idiomatic (NumPy/pandas/Arrow vs TypedArrays;
notebook/Reflex vs Node embed). Names and defaults match.

---

## 2. Placement rule (Rust-first)

Default: **implement in Rust** unless the work is inherently host- or
client-bound. This is stricter than upstream rust-engine §1’s “Python owns
decisions” habit where that habit would duplicate policy across bindings.

| Lives in | Examples |
|---|---|
| **xy Rust (shared)** | Display layouts, graph adjacency/position buffers for viz, channel resolution, decimation, LOD aggregates, anything O(N)/O(|V|+|E|), and any deterministic policy whose result must match across hosts (thresholds that affect buffers, layout params application, recorded §28 decisions that change geometry) |
| **Host (Python *or* Node)** | Public API shapes, idiomatic ingest coercion (list/NumPy/TypedArray → pointers), error message text, transport attach — **no** second layout/algorithm/encode path |
| **JS client** | WebGL draw, hit-test, pan/zoom/select/drag gestures applying uploaded buffers |

If a feature needs the same outcome in Python and Node, put it in Rust **before**
writing it twice in hosts. When an existing mark still has host-only layout
(e.g. Sankey in Python), promote it to Rust as part of dual-host work.

Graph **analysis algorithms** (paths, centrality, communities, Cypher, …) are
not owned here — they live in GraphForge (and similar peers). This charting
stack plots their outputs; it does not reimplement them.

Node must not reimplement layouts or mark geometry in TypeScript.

---

## 3. Requirements

- **REQ-HOSTPARITY-1 (MUST).** One xy Rust C ABI serves Python (`ctypes` today)
  and Node (N-API). `ABI_VERSION` bumps apply to both loaders.
- **REQ-HOSTPARITY-1b (MUST).** Rust-first: new chart/graph behavior that
  affects buffers, layout, encodings, or recorded LOD/layout decisions is
  implemented in Rust. Hosts MAY validate and coerce inputs but MUST NOT own a
  parallel implementation of that behavior.
- **REQ-HOSTPARITY-2 (MUST).** For every public chart type, Python and Node
  produce the same figure spec shape and §29 buffers for the same inputs.
  Graph is the core feature and first golden suite; other types MUST not ship
  on a slower or thinner host path.
- **REQ-HOSTPARITY-2b (MUST).** Non-graph marks retain the same composition
  quality and performance bar (Rust kernels, binary transport, WebGL). Graph
  work MUST NOT regress them or leave them second-class.
- **REQ-HOSTPARITY-2c (MUST).** Graph ingest helpers (including any GraphForge
  primary path) MUST NOT be the only way to build a graph chart on either host.
  xy-native column/sequence formats from
  [graph-fork-requirements.md](graph-fork-requirements.md) REQ-API-3 remain
  available with the same semantics on Python and Node.
- **REQ-HOSTPARITY-3 (MUST).** The browser client is shared; hosts only differ
  in transport attachment.
- **REQ-HOSTPARITY-4 (MUST).** Graph viz is the lead dual-host delivery surface
  ([graph-fork-requirements.md](graph-fork-requirements.md)).
- **REQ-HOSTPARITY-5 (SHOULD).** Document §32 divergence from upstream xy when
  the Node package ships.
- **REQ-HOSTPARITY-6 (MUST).** Dual-host work for a mark promotes any remaining
  host-only layout/encode logic into Rust (e.g. Sankey) so Node does not grow
  a parallel tree.

---

## 4. Delivery order

1. Extend the language-neutral viz C ABI.
2. Implement graph layout/render (**core feature**).
3. Node loader; graph fixtures match Python.
4. Expose remaining chart types on Node (same feel/speed).

---

## 5. Non-goals

- Separate Node-only renderers or host-side reimplementations of Rust kernels.
- Reimplementing GraphForge (or peer) analysis algorithms inside xy.
- Leaving new layout/encode/LOD logic in one host language “for now.”
- Requiring Node for Python users or vice versa.
- Bit-identical *policy source* across languages — only identical recorded
  decisions and buffers (achieved by putting that policy in Rust).
