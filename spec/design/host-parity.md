# Host parity — Python and Node

**Status:** requirements / architecture intent. Python and Node hosts share one
viz Rust C ABI and one WebGL client so **all chart types** have the same
semantics on both languages.

**Priority:** **graph visualization** is the core feature and the first surface
that must prove dual-host end to end
([graph-fork-requirements.md](graph-fork-requirements.md)). Other chart types
keep the same first-class API feel and speed — sequencing graph first is fine;
a degraded non-graph path is not.

Does not change runtime behavior until a Node host package lands. Supersedes
the upstream xy “Python-only forever” reading of dossier §32 for this product
line.

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

## 2. Placement rule

From [rust-engine.md](rust-engine.md) §1:

- **xy Rust** — O(N) / O(|V|+|E|) **viz** work that must be bit-identical
  across hosts (display layouts, decimation, channel scans, screen LOD).
- **Host (Python *or* Node)** — API ergonomics, validation, spec assembly,
  policy; recorded decisions (§28) must not diverge.
- **JS client** — screen-bounded draw and gestures only.

Graph **analysis algorithms** (paths, centrality, communities, Cypher, …) are
not owned here — they live in GraphForge (and similar peers). This charting
stack plots their outputs; it does not reimplement them.

Node must not reimplement layouts or mark geometry in TypeScript.

---

## 3. Requirements

- **REQ-HOSTPARITY-1 (MUST).** One xy Rust C ABI serves Python (`ctypes` today)
  and Node (N-API). `ABI_VERSION` bumps apply to both loaders.
- **REQ-HOSTPARITY-2 (MUST).** For every public chart type, Python and Node
  produce the same figure spec shape and §29 buffers for the same inputs.
  Graph is the core feature and first golden suite; other types MUST not ship
  on a slower or thinner host path.
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
- **REQ-HOSTPARITY-6 (SHOULD).** When bringing a mark to Node, prefer Rust for
  any remaining host-only layout (e.g. Sankey) so Node does not grow a parallel
  layout tree.

---

## 4. Delivery order

1. Extend the language-neutral viz C ABI.
2. Implement graph layout/render (**core feature**).
3. Node loader; graph fixtures match Python.
4. Expose remaining chart types on Node (same feel/speed).

---

## 5. Non-goals

- Separate Node-only renderers.
- Reimplementing GraphForge (or peer) analysis algorithms inside xy.
- Requiring Node for Python users or vice versa.
- Bit-identical *policy source* across languages — only identical recorded
  decisions and buffers.
